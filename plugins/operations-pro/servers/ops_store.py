"""The file lane: plan a change, then apply it as a transaction.

Plan: run the actions on parsed copies, audit the result, show the diff. Nothing on
disk changes. Apply: JMRI must be exited and the files must still be what the plan saw.
Back up the set, replace the changed files, re-read and audit, and restore on failure.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from ops_data import OPTIONAL, REQUIRED, Railroad, load
from ops_gates import Gates

FILES = REQUIRED + OPTIONAL
ROOT_TAG = "<operations-config"
AUTOSAVE_WINDOW = 180  # Seconds. JMRI's autosave lands one to two minutes after a change.
DIFF_LIMIT = 400
JMRI_PROCESS = re.compile(r"jmri\.jar|apps\.[A-Za-z0-9_.]*(PanelPro|DecoderPro|SoundPro|LccPro|JmriFaceless)"
                          r"|(PanelPro|DecoderPro|SoundPro|LccPro|JmriFaceless)\.app", re.I)


class Refused(Exception):
    """A change that must not happen. The message says why."""


class Doc:
    """One XML file. Unedited content renders back byte for byte."""

    def __init__(self, path: Path):
        self.path = path
        raw = path.read_bytes()
        self.original = raw
        text = raw.decode("utf-8")
        self.crlf = "\r\n" in text
        start = text.index(ROOT_TAG)
        self.prolog = text[:start]
        body = text[start:].rstrip()
        self.trailer = text[start + len(body):]
        builder = ET.TreeBuilder(insert_comments=True, insert_pis=True)
        self.root = ET.fromstring(body.encode("utf-8"), parser=ET.XMLParser(target=builder))

    def render(self) -> bytes:
        body = ET.tostring(self.root, encoding="unicode")
        if self.crlf:
            body = body.replace("\r\n", "\n").replace("\n", "\r\n")
        return (self.prolog + body + self.trailer).encode("utf-8")

    @property
    def changed(self) -> bool:
        return self.render() != self.original


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve(directory: str | Path) -> Path:
    return load(directory).directory


def hashes(base: Path) -> dict[str, str]:
    return {n: sha((base / n).read_bytes()) for n in FILES if (base / n).is_file()}


def running_jmri(listing: str | None = None) -> list[str]:
    """Command lines of JMRI processes on this computer."""
    if listing is None:
        if sys.platform == "win32":
            command = ["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"]
        else:
            command = ["ps", "-A", "-o", "command="]
        try:
            listing = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise Refused(f"Could not check whether JMRI is running ({exc}). Nothing was changed.") from exc
    return [line.strip()[:120] for line in listing.splitlines() if JMRI_PROCESS.search(line)]


def _audit(directory: Path) -> tuple[set, list[dict]]:
    findings = Gates(load(directory)).audit()["findings"]
    return {(f["rule"], f["subject"], f["message"]) for f in findings}, findings


def built_trains(base: Path) -> list[str]:
    return [t.name for t in load(base).trains.values() if t.built]


def _diff(name: str, before: bytes, after: bytes) -> list[str]:
    return list(difflib.unified_diff(
        before.decode("utf-8").splitlines(), after.decode("utf-8").splitlines(),
        f"a/{name}", f"b/{name}", lineterm="", n=1))


def plans_root() -> Path:
    return Path(os.environ.get("OPS_PLAN_DIR") or Path(tempfile.gettempdir()) / "operations-pro-plans")


def plan(directory: str | Path, actions: list[dict], session: bool = False, prepare=None) -> dict:
    """Work out a change without touching the operations folder.

    prepare, used by actions that JMRI itself works out, edits the Editor directly and
    returns (summary lines, car ids allowed to change derived fields).
    """
    from ops_actions import Editor, guard  # ops_actions needs Refused from this module.
    rr = load(directory)
    base = rr.directory
    if not actions and prepare is None:
        raise Refused("No actions given")
    editor = Editor(base)
    built = [t.name for t in rr.trains.values() if t.built]
    if built and not session:
        raise Refused(f"Reset or terminate these trains first: {', '.join(built)}. "
                      "Build state spans several files, so setup edits are unsafe while a train is built.")
    summary, allowed = prepare(editor) if prepare else (editor.run(actions, session_only=session), ())
    guard(editor, allowed)
    plan_id = uuid.uuid4().hex[:12]
    folder = plans_root() / plan_id
    folder.mkdir(parents=True)
    trial = folder / "after"
    trial.mkdir()
    changed = {}
    for name in FILES:
        source = base / name
        if name in editor.docs and editor.docs[name].changed:
            changed[name] = editor.docs[name].render()
            (trial / name).write_bytes(changed[name])
        elif source.is_file():
            shutil.copy2(source, trial / name)
    if not changed:
        shutil.rmtree(folder)
        return {"changed": False, "summary": summary, "message": "These actions change nothing."}
    before_keys, _ = _audit(base)
    after_keys, after = _audit(trial)
    new = [f for f in after if (f["rule"], f["subject"], f["message"]) not in before_keys]
    fixed = len(before_keys - after_keys)
    manifest = {"id": plan_id, "ops_dir": str(base), "base": hashes(base), "changed": sorted(changed),
                "actions": actions, "session": session, "summary": summary, "created": time.time(),
                "new_errors": [f for f in new if f["severity"] == "error"]}
    (folder / "plan.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    diff: list[str] = []
    for name, data in changed.items():
        diff += _diff(name, (base / name).read_bytes(), data)
    return {"changed": True, "plan_id": plan_id, "summary": summary, "files": sorted(changed),
            "new_findings": new, "findings_resolved": fixed,
            "blocked": bool(manifest["new_errors"]), "warnings": _warnings(base),
            "diff": "\n".join(diff[:DIFF_LIMIT]),
            "diff_truncated": max(0, len(diff) - DIFF_LIMIT)}


def _warnings(base: Path) -> list[str]:
    out = []
    age = time.time() - max((base / n).stat().st_mtime for n in FILES if (base / n).is_file())
    if age < AUTOSAVE_WINDOW:
        out.append(f"The Operations files changed {int(age)} seconds ago. Make sure JMRI has finished "
                   "saving, on every computer that opens this folder.")
    conflicts = [p.name for p in base.glob("*conflicted copy*")]
    if conflicts:
        out.append(f"Possible sync conflict files here: {', '.join(conflicts)}")
    return out


def backup(base: Path, tag: str = "before-change") -> str:
    """A set in JMRI's own backups folder, so JMRI's Restore dialog can see it too."""
    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    name = f"opspro_{tag}_{stamp}"
    target = base / "backups" / name
    suffix = 1
    while target.exists():
        suffix += 1
        target = base / "backups" / f"{name}_{suffix}"
    target.mkdir(parents=True)
    for file in FILES:
        if (base / file).is_file():
            shutil.copy2(base / file, target / file)
    return target.name


def _replace(base: Path, name: str, data: bytes) -> None:
    temporary = base / f".{name}.opspro.tmp"
    try:
        temporary.write_bytes(data)
        os.replace(temporary, base / name)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _restore_set(base: Path, set_name: str) -> list[str]:
    source = base / "backups" / set_name
    names = [n for n in FILES if (source / n).is_file()]
    for name in names:
        _replace(base, name, (source / name).read_bytes())
    return names


def _load_plan(plan_id: str) -> tuple[Path, dict]:
    if not re.fullmatch(r"[0-9a-f]{12}", plan_id or ""):
        raise Refused(f"Not a plan id: {plan_id!r}")
    folder = plans_root() / plan_id
    if not (folder / "plan.json").is_file():
        raise Refused(f"No plan {plan_id}. Plans are used once; make a new one.")
    return folder, json.loads((folder / "plan.json").read_text(encoding="utf-8"))


def _preflight(base: Path) -> None:
    active = running_jmri()
    if active:
        raise Refused("JMRI is running here. Exit it fully first: it holds this data in memory and "
                      f"would overwrite the change on its next save. Found: {active[0]}")


def apply(plan_id: str, allow_new_errors: bool = False) -> dict:
    folder, manifest = _load_plan(plan_id)
    base = Path(manifest["ops_dir"])
    if manifest["new_errors"] and not allow_new_errors:
        raise Refused("This plan adds audit errors and was blocked: "
                      + "; ".join(f["message"] for f in manifest["new_errors"][:5]))
    _preflight(base)
    if hashes(base) != manifest["base"]:
        raise Refused("The Operations files changed after this plan was made. Make a new plan.")
    if not manifest["session"] and built_trains(base):
        raise Refused("A train has been built since this plan was made. Reset it first.")
    before_keys, before = _audit(base)
    set_name = backup(base)
    replaced: list[str] = []
    try:
        for name in manifest["changed"]:
            _replace(base, name, (folder / "after" / name).read_bytes())
            replaced.append(name)
        for name in manifest["changed"]:
            if sha((base / name).read_bytes()) != sha((folder / "after" / name).read_bytes()):
                raise Refused(f"{name} did not write correctly")
        after_keys, after = _audit(base)
        added = [f for f in after if f["severity"] == "error"
                 and (f["rule"], f["subject"], f["message"]) not in before_keys]
        if added and not allow_new_errors:
            raise Refused("Audit found new errors: " + "; ".join(f["message"] for f in added[:5]))
    except BaseException as exc:  # A Ctrl-C here must restore too.
        try:
            _restore_set(base, set_name)
        except BaseException as failure:
            raise Refused(f"Change failed ({exc}) and restoring from backups/{set_name} failed too ({failure}). "
                          f"Already replaced: {', '.join(replaced) or 'none'}. Restore that set by hand before "
                          "starting JMRI.") from failure
        if isinstance(exc, Exception):
            raise Refused(f"Change undone, files restored from {set_name}. Cause: {exc}") from exc
        raise
    shutil.rmtree(folder, ignore_errors=True)
    return {"applied": True, "files": manifest["changed"], "backup": set_name,
            "summary": manifest["summary"], "findings_before": len(before), "findings_after": len(after),
            "next": "Start JMRI and open Operations so it reads the new files."}


def quick(directory: str | Path, actions: list[dict], prepare=None) -> dict:
    """The lighter path for session actions: no separate plan step, same transaction."""
    result = plan(directory, actions, session=True, prepare=prepare)
    if not result["changed"]:
        return result
    if result["blocked"]:
        shutil.rmtree(plans_root() / result["plan_id"], ignore_errors=True)
        raise Refused("This adds audit errors: "
                      + "; ".join(f["message"] for f in result["new_findings"] if f["severity"] == "error"))
    return apply(result["plan_id"])


def backups(directory: str | Path) -> list[dict]:
    base = resolve(directory)
    out = []
    for parent in ("backups", "autoBackups"):
        folder = base / parent
        if folder.is_dir():
            for entry in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if entry.is_dir():
                    out.append({"set": entry.name, "folder": parent,
                                "saved": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(timespec="seconds"),
                                "files": sorted(p.name for p in entry.glob("*.xml"))})
    return out


def restore(directory: str | Path, set_name: str, folder: str = "backups") -> dict:
    base = resolve(directory)
    if folder not in ("backups", "autoBackups") or Path(set_name).name != set_name:
        raise Refused("Give a set name from ops_backups")
    source = base / folder / set_name
    if not source.is_dir() or not all((source / n).is_file() for n in REQUIRED):
        raise Refused(f"{set_name} is not a complete backup set")
    _preflight(base)
    Railroad(source)  # A set that will not parse must not replace good files.
    safety = backup(base, "before-restore")
    for name in FILES:
        if (source / name).is_file():
            _replace(base, name, (source / name).read_bytes())
    return {"restored": set_name, "backup_of_previous_state": safety}
