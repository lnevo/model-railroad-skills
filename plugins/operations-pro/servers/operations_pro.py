#!/usr/bin/env python3
"""MCP server for JMRI OperationsPro.

Set OPS_DIR to the operations directory, or pass ops_dir on each call. Files are
re-read on every call, so a running JMRI's latest autosave is picked up. Reading tools
open only the six XML files. Changing tools work through ops_store's transaction.
"""
from __future__ import annotations

import os
from dataclasses import asdict

import ops_jmri
import ops_store
from mcp_stdio import Tool, serve
from ops_actions import ACTIONS
from ops_data import Railroad, directions, load
from ops_gates import Gates

LIST_TYPES = ("locations", "tracks", "schedules", "routes", "trains", "cars", "engines", "loads")


def folder(args: dict) -> str:
    directory = args.get("ops_dir") or os.environ.get("OPS_DIR")
    if not directory:
        raise ValueError("Set OPS_DIR or pass ops_dir: the folder holding the Operations XML files")
    return directory


def railroad(args: dict) -> Railroad:
    return load(folder(args))


def why_not(args: dict) -> object:
    return Gates(railroad(args)).why_not(
        args["car"], args["destination"], args.get("track"), args.get("train"))


def audit(args: dict) -> object:
    return Gates(railroad(args)).audit()


def _track(rr: Railroad, track) -> dict:
    cars, engines = rr.rolling_stock_on(track)
    row = asdict(track)
    row.update(location=rr.locations[track.location_id].name, directions=directions(track.dir),
               used_length=rr.used_length(track), cars=[str(c) for c in cars], engines=len(engines))
    return row


def list_items(args: dict) -> object:
    rr = railroad(args)
    kind = args["type"]
    if kind not in LIST_TYPES:
        raise ValueError(f"type must be one of: {', '.join(LIST_TYPES)}")
    if kind == "tracks":
        return [_track(rr, t) for t in rr.tracks.values()]
    if kind == "locations":
        return [{"id": x.id, "name": x.name, "directions": directions(x.dir), "staging": x.is_staging,
                 "types": x.types, "tracks": [t.name for t in x.tracks]} for x in rr.locations.values()]
    if kind == "loads":
        return {"default_empty": rr.default_empty, "default_load": rr.default_load,
                "custom": {k: [asdict(x) for x in v] for k, v in rr.loads.items()}}
    return [asdict(x) for x in getattr(rr, kind).values()]


def action_help(args: dict) -> object:
    wanted = args.get("session_only")
    return {name: {"session": entry["session"], "help": entry["help"]}
            for name, entry in sorted(ACTIONS.items()) if entry["session"] or not wanted}


def tools() -> list[Tool]:
    directory = {"ops_dir": {"type": "string", "description": "Operations directory; defaults to OPS_DIR"}}
    actions = {"actions": {"type": "array", "items": {"type": "object"},
                           "description": "Each item names action plus its fields. See ops_actions."}}
    plan_id = {"plan_id": {"type": "string", "description": "From ops_plan"}}
    return [
        Tool("ops_why_not",
             "Walk a car through every OperationsPro build gate to a destination, in JMRI's order, "
             "giving pass, fail or not_checked, the reason, and the screen and setting that fixes it.",
             {"type": "object",
              "properties": {
                  **directory,
                  "car": {"type": "string", "description": "Car id or road and number"},
                  "destination": {"type": "string", "description": "Location name or id"},
                  "track": {"type": "string", "description": "Track name or id; omit to try every track"},
                  "train": {"type": "string", "description": "Train name or id; omit to try every train"}},
              "required": ["car", "destination"]},
             why_not),
        Tool("ops_audit",
             "Check a whole railroad for types and loads nothing can carry, schedule and routing gaps, "
             "and settings JMRI silently ignores.",
             {"type": "object", "properties": directory}, audit),
        Tool("ops_list", "List one kind of OperationsPro record from the XML files.",
             {"type": "object",
              "properties": {**directory, "type": {"type": "string", "enum": list(LIST_TYPES)}},
              "required": ["type"]},
             list_items),
        Tool("ops_actions", "List every change action with its fields and whether it is a session action.",
             {"type": "object", "properties": {"session_only": {"type": "boolean"}}}, action_help),
        Tool("ops_plan",
             "Work out a change to the Operations files without touching them. Returns a plan id, the diff "
             "and new audit findings. Show these to the user before ops_apply.",
             {"type": "object", "properties": {**directory, **actions}, "required": ["actions"]},
             lambda a: ops_store.plan(folder(a), a["actions"])),
        Tool("ops_build_check",
             "Build every enabled train several times on copies, before and after a plan, using real JMRI, "
             "and compare. Changes nothing.",
             {"type": "object", "properties": {**plan_id, "runs": {"type": "integer"}}, "required": ["plan_id"]},
             lambda a: ops_jmri.build_check(a["plan_id"], a.get("runs", 4))),
        Tool("ops_dry_run",
             "Run a session on a copy with real JMRI: build all enabled trains, then terminate them, and report. "
             "Changes nothing.",
             {"type": "object", "properties": {**directory, "terminate": {"type": "boolean"}}},
             lambda a: ops_jmri.dry_run(folder(a), a.get("terminate", True))),
        Tool("ops_apply",
             "Apply a plan. JMRI must be fully exited. Backs up the set, writes, audits and restores on failure. "
             "A plan with new audit errors is refused unless the user accepts them: renaming something that "
             "already had a fault, for example, reports that fault under its new name.",
             {"type": "object",
              "properties": {**plan_id, "accept_new_errors": {"type": "boolean"}}, "required": ["plan_id"]},
             lambda a: ops_store.apply(a["plan_id"], a.get("accept_new_errors", False)), read_only=False),
        Tool("ops_session",
             "Apply session actions, such as correcting a car, without a separate plan. Same backup and audit. "
             "JMRI must be fully exited.",
             {"type": "object", "properties": {**directory, **actions}, "required": ["actions"]},
             lambda a: ops_store.quick(folder(a), a["actions"]), read_only=False),
        Tool("ops_deliver_car",
             "Set a car on a track and run that track's schedule as Set Car does: real JMRI works out the "
             "result on a copy, then the change is applied. JMRI must be fully exited.",
             {"type": "object",
              "properties": {**directory, "car": {"type": "string"}, "location": {"type": "string"},
                             "track": {"type": "string"}},
              "required": ["car", "location", "track"]},
             lambda a: ops_jmri.deliver_car(folder(a), a["car"], a["location"], a["track"]), read_only=False),
        Tool("ops_backups", "List backup sets.", {"type": "object", "properties": directory},
             lambda a: ops_store.backups(folder(a))),
        Tool("ops_restore",
             "Put a backup set back. JMRI must be fully exited. The current state is backed up first.",
             {"type": "object",
              "properties": {**directory, "set": {"type": "string"},
                             "folder": {"type": "string", "enum": ["backups", "autoBackups"]}},
              "required": ["set"]},
             lambda a: ops_store.restore(folder(a), a["set"], a.get("folder", "backups")), read_only=False),
    ]


if __name__ == "__main__":
    serve("operations-pro", tools())
