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

from ops_data import OPTIONAL, REQUIRED, Railroad, load, operations_folder
from ops_gates import Gates

FILES = REQUIRED + OPTIONAL
ROOT_TAG = "<operations-config"
AUTOSAVE_WINDOW = 180  # Seconds. JMRI's autosave lands one to two minutes after a change.
DIFF_LIMIT = 400
# A JMRI program is Java running one of JMRI's application classes (apps.PanelPro.PanelPro,
# apps.gui3.dp3.DecoderPro3, apps.JmriFaceless, ...: the CLASSNAME the launchers pass; the launchers' quick
# Java version check is left out). The launcher scripts and LaunchJMRI.exe
# start that Java process and are not counted themselves, nor is a shell or editor naming jmri.jar.
JMRI_APP = re.compile(r"(?:^|\s)apps\.(?!JavaVersionCheckWindow\b)(?:[A-Za-z0-9_]+\.)*[A-Za-z0-9_]+(?=\s|$)")
JAVA = re.compile(r'^\s*"?(?:[^"]*[\\/])?javaw?(?:\.exe)?"?(?:\s|$)', re.I)
# This plugin's own JMRI runs: a scratch home folder from tempfile with the opspro- prefix (ops_jmri,
# the live and oracle tests) or a jython script run against a copy. None can hold the user's folder.
SCRATCH = re.compile(r'-D(?:user\.home|jmri\.prefsdir)="?[^"=]*?[\\/]opspro-|org\.python\.util\.jython')


class Refused(Exception):
    """A change that must not happen. The message says why."""


class Doc:
    """One XML file. Unedited content renders back byte for byte."""

    def __init__(self, path: Path, new: bytes | None = None):
        """With new, a file that does not exist yet: that text is the starting content."""
        self.path = path
        raw = path.read_bytes() if new is None else new
        self.original = raw if new is None else b""
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


def locate(directory: str | Path) -> Path:
    """The Operations folder, without reading the files: backups and restores must work when one is broken."""
    base = operations_folder(directory)
    if not base.is_dir():
        raise Refused(f"{base} is not a folder")
    return base


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
    return [line.strip()[:120] for line in listing.splitlines() if is_jmri(line)]


def is_jmri(line: str) -> bool:
    """A JMRI program that could hold the user's Operations files in memory."""
    return bool(JAVA.search(line) and JMRI_APP.search(line) and not SCRATCH.search(line))


def _audit(directory: Path) -> tuple[set, list[dict]]:
    findings = Gates(load(directory)).audit()["findings"]
    return {(f["rule"], f["subject"], f["message"]) for f in findings}, findings


def built_trains(base: Path) -> list[str]:
    return [t.name for t in load(base).trains.values() if t.built]


def _diff(name: str, before: bytes, after: bytes) -> list[str]:
    return list(difflib.unified_diff(
        before.decode("utf-8").splitlines(), after.decode("utf-8").splitlines(),
        f"a/{name}", f"b/{name}", lineterm="", n=1))


# The newest file time each folder had when this process last wrote it, so its own apply is not taken for JMRI saving.
_own_write: dict[str, float] = {}


def plans_root() -> Path:
    return Path(os.environ.get("OPS_PLAN_DIR") or Path(tempfile.gettempdir()) / "operations-pro-plans")


PLAN_MAX_AGE_DAYS = 7


def prune_plans(max_age_days: float = PLAN_MAX_AGE_DAYS, keep: str = "") -> int:
    """Remove plan folders nobody applied. Each holds a full copy of the Operations files."""
    import time
    root = plans_root()
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for folder in root.iterdir():
        try:
            if folder.is_dir() and folder.name != keep and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder)
                removed += 1
        except OSError:
            pass
    return removed


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
    prune_plans(keep=plan_id)
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
        old = (base / name).read_bytes() if (base / name).is_file() else b""
        diff += _diff(name, old, data)
    return {"changed": True, "plan_id": plan_id, "summary": summary, "files": sorted(changed),
            "new_findings": new, "findings_resolved": fixed,
            "blocked": bool(manifest["new_errors"]), "warnings": _warnings(base),
            "diff": "\n".join(diff[:DIFF_LIMIT]),
            "diff_truncated": max(0, len(diff) - DIFF_LIMIT)}


def newest_change(directory: str | Path) -> float:
    base = Path(directory)
    return max(((base / n).stat().st_mtime for n in FILES if (base / n).is_file()), default=0)


def _warnings(base: Path) -> list[str]:
    out = []
    newest = newest_change(base)
    age = time.time() - newest
    if age < AUTOSAVE_WINDOW and newest != _own_write.get(str(base)):
        out.append(f"The Operations files changed {int(age)} seconds ago. Make sure JMRI has finished "
                   "saving, on every computer that opens this folder.")
    conflicts = [p.name for p in base.glob("*conflicted copy*")]
    if conflicts:
        out.append(f"Possible sync conflict files here: {', '.join(conflicts)}")
    return out


def backup(base: Path, tag: str = "before-change") -> str:
    """A set in JMRI's own backups folder, so JMRI's Restore dialog can see it too."""
    if not any((base / n).is_file() for n in FILES):
        return ""  # Nothing yet: a railroad started from nothing.
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
    if not set_name:
        return []
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
    base.mkdir(exist_ok=True)  # A profile's operations folder that JMRI has not made yet.
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
            for name in replaced:  # A file the plan created has no copy in the set.
                if name not in manifest["base"]:
                    (base / name).unlink(missing_ok=True)
        except BaseException as failure:
            raise Refused(f"Change failed ({exc}) and restoring from backups/{set_name} failed too ({failure}). "
                          f"Already replaced: {', '.join(replaced) or 'none'}. Restore that set by hand before "
                          "starting JMRI.") from failure
        if isinstance(exc, Exception):
            raise Refused(f"Change undone, files restored from {set_name}. Cause: {exc}") from exc
        raise
    _own_write[str(base)] = newest_change(base)
    shutil.rmtree(folder, ignore_errors=True)
    return {"applied": True, "files": manifest["changed"], "backup": set_name,
            "summary": manifest["summary"], "findings_before": len(before), "findings_after": len(after),
            "next": "Start JMRI and open Operations so it reads the new files."}


def quick(directory: str | Path, actions: list[dict], prepare=None, accept_new_errors: bool = False) -> dict:
    """The lighter path for session actions: no separate plan step, same transaction. A change the audit
    blocks can still go through when the user accepts its errors, as with ops_apply."""
    result = plan(directory, actions, session=True, prepare=prepare)
    if not result["changed"]:
        return result
    if result["blocked"] and not accept_new_errors:
        shutil.rmtree(plans_root() / result["plan_id"], ignore_errors=True)
        raise Refused("This adds audit errors: "
                      + "; ".join(f["message"] for f in result["new_findings"] if f["severity"] == "error"))
    return apply(result["plan_id"], accept_new_errors)


def backups(directory: str | Path) -> list[dict]:
    """Every set in backups and autoBackups. Reads no Operations file, so it works on a broken folder."""
    base = locate(directory)
    out = []
    for parent in ("backups", "autoBackups"):
        folder = base / parent
        if folder.is_dir():
            for entry in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if entry.is_dir():
                    out.append({"set": entry.name, "folder": parent,
                                "saved": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(timespec="seconds"),
                                "files": sorted(p.name for p in entry.glob("*.xml")),
                                "complete": all((entry / n).is_file() for n in REQUIRED)})
    return out


def restore(directory: str | Path, set_name: str, folder: str = "backups", file: str | None = None) -> dict:
    """Put a backup set back, or with file only that one file. Reads only the set, so it works when the
    current files are missing or unreadable. The current state is backed up first."""
    base = locate(directory)
    if folder not in ("backups", "autoBackups") or Path(set_name).name != set_name:
        raise Refused("Give a set name from ops_backups")
    source = base / folder / set_name
    if not source.is_dir():
        raise Refused(f"No set {set_name} in {folder}")
    if file is not None:
        if file not in FILES:
            raise Refused(f"file must be one of {', '.join(FILES)}")
        if not (source / file).is_file():
            raise Refused(f"{set_name} has no {file}")
        try:
            ET.parse(source / file)
        except ET.ParseError as exc:
            raise Refused(f"{set_name}/{file} will not parse ({exc}), so it must not replace the current file") from exc
        names = [file]
    else:
        if not all((source / n).is_file() for n in REQUIRED):
            raise Refused(f"{set_name} is not a complete backup set")
        try:
            Railroad(source)  # A set that will not parse must not replace good files.
        except (ET.ParseError, FileNotFoundError) as exc:
            raise Refused(f"{set_name} will not load ({exc})") from exc
        names = [n for n in FILES if (source / n).is_file()]
    _preflight(base)
    safety = backup(base, "before-restore")
    for name in names:
        _replace(base, name, (source / name).read_bytes())
    out = {"restored": set_name, "files": names, "backup_of_previous_state": safety}
    left = [n for n in FILES if n not in names and (base / n).is_file()]
    if file is None and left:
        # JMRI's own Restore does the same: it copies what the set holds (BackupBase.copyBackupSet:249-283).
        out["not_restored"] = left
        out["note"] = (f"The set has no {', '.join(left)}, so the current {'copies stay' if len(left) > 1 else 'one stays'}"
                       ", with the newer state. Run ops_audit before starting JMRI.")
    if file is not None:
        out["note"] = ("Only this file came back. The others still hold the newer state, and they refer to "
                       "locations, tracks, trains and cars by id, so run ops_audit before starting JMRI.")
    return out
