#!/usr/bin/env python3
"""Replay the showcase railroad from build/*.json on a fresh copy of servers/blank.

    build.py OUTDIR [--through N] [--no-merge] [--ship]

Every step goes through the plugin's own functions in servers/ (the code the MCP tools call):
  {"plan": [actions], "accept_new_errors": bool}   ops_plan then ops_apply
  {"session": [actions]}                           ops_session
  {"deliver": {"car", "location", "track"}}        ops_deliver_car
  {"hand_edit": {"file", "find", "replace", "reason", "count"?}}   exact text replacement, reason required
Steps name objects, never ids, so replay does not depend on them.

Merge rule (PLAN.md section 6), unless --no-merge: one real JMRI load-and-save whose six files replace
the replayed ones, then a real build of every train to collect buildstatus/, then a backup set.
OUTDIR is left holding the six files, buildstatus/ and backups/. examples/showcase/operations is only
written with --ship.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVERS = HERE.parents[1] / "servers"
sys.path.insert(0, str(SERVERS))

import ops_jmri  # noqa: E402
import ops_store  # noqa: E402

ops_store.running_jmri = lambda *a, **k: []  # as tests/test_write.py does: nothing real is running here


def numbered(through: int | None) -> list[Path]:
    files = []
    for path in (HERE / "build").glob("*.json"):
        match = re.match(r"(\d+)", path.name)
        if match and (through is None or int(match.group(1)) <= through):
            files.append((int(match.group(1)), path.name, path))
    return [p for _, _, p in sorted(files)]


def hand_edit(base: Path, edit: dict) -> None:
    if not edit.get("reason"):
        raise SystemExit("hand_edit needs a reason")
    target = base / edit["file"]
    text = target.read_text(encoding="utf-8")
    count = text.count(edit["find"])
    if count != edit.get("count", 1):
        raise SystemExit(f"hand_edit {edit['file']}: found {count} matches, expected {edit.get('count', 1)}")
    target.write_text(text.replace(edit["find"], edit["replace"]), encoding="utf-8")


def run_step(base: Path, step: dict, label: str) -> None:
    if "plan" in step:
        plan = ops_store.plan(base, step["plan"])
        if not plan["changed"]:
            print(f"  {label}: plan changes nothing")
            return
        ops_store.apply(plan["plan_id"], bool(step.get("accept_new_errors")))
        print(f"  {label}: plan applied ({len(step['plan'])} actions)")
    elif "session" in step:
        ops_store.quick(base, step["session"])
        print(f"  {label}: session applied ({len(step['session'])} actions)")
    elif "deliver" in step:
        d = step["deliver"]
        ops_jmri.deliver_car(base, d["car"], d["location"], d["track"])
        print(f"  {label}: delivered {d['car']} to {d['location']}/{d['track']}")
    elif "hand_edit" in step:
        hand_edit(base, step["hand_edit"])
        print(f"  {label}: hand edit of {step['hand_edit']['file']} ({step['hand_edit']['reason']})")
    else:
        raise SystemExit(f"{label}: unknown step {sorted(step)}")


def merge(base: Path) -> None:
    """One real load-and-save, then a real build of every train for buildstatus/, then a backup set."""
    if ops_jmri.jmri_home() is None:
        raise SystemExit("JMRI was not found (set JMRI_HOME); use --no-merge to skip the merge")
    keep = base.parent / (base.name + ".saved")
    shutil.rmtree(keep, ignore_errors=True)
    keep.mkdir(parents=True)
    result = ops_jmri.run_worker(base, {"save": True}, keep)
    if result.get("log_errors"):
        raise SystemExit(f"JMRI logged errors on load-and-save: {result['log_errors']}")
    for name in ops_store.FILES:
        if (keep / name).is_file():
            shutil.copy2(keep / name, base / name)
    shutil.rmtree(keep)
    keep.mkdir(parents=True)
    built = ops_jmri.run_worker(base, {"build": True}, keep)  # the shipped files stay unbuilt
    if (keep / "buildstatus").is_dir():
        shutil.rmtree(base / "buildstatus", ignore_errors=True)
        shutil.copytree(keep / "buildstatus", base / "buildstatus")
    shutil.rmtree(keep)
    print("  merge: saved by JMRI, buildstatus from", len(built.get("builds", {})), "trains")
    print("  backup:", ops_store.backup(base, "manual"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("outdir")
    parser.add_argument("--through", type=int, help="stop after the build file with this number")
    parser.add_argument("--no-merge", action="store_true", help="skip the JMRI load-and-save merge")
    parser.add_argument("--ship", action="store_true", help="also copy the result to examples/showcase/operations")
    args = parser.parse_args()
    out = Path(args.outdir).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    shutil.copytree(SERVERS / "blank", out, dirs_exist_ok=True)
    for path in numbered(args.through):
        import json
        print(path.name)
        for index, step in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
            run_step(out, step, f"step {index}")
    if not args.no_merge:
        merge(out)
    if args.ship:
        ship = HERE / "operations"
        shutil.rmtree(ship, ignore_errors=True)
        shutil.copytree(out, ship)
        print("shipped to", ship)


if __name__ == "__main__":
    main()
