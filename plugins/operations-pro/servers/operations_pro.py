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
import ops_live
import ops_report
import ops_store
from mcp_stdio import Tool, serve
from ops_actions import ACTIONS
from ops_data import Railroad, directions, load
from ops_gates import Gates

LIST_TYPES = ("locations", "tracks", "schedules", "routes", "trains", "cars", "engines", "loads")
# ---- Train schedule days and manifest formats: rr.days and rr.manifest list as records.
LIST_TYPES += ("days", "manifest")
# ---- End of train schedule days and manifest formats


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


DETAIL = {"type": "string", "enum": ["summary", "normal", "full"],
          "description": "How much of each build report to return: summary (default), normal or full, "
                         "as ops_explain_build gives them"}


def explain_build(args: dict) -> object:
    car, detail = args.get("car"), args.get("detail", "normal")
    if args.get("text"):
        return ops_report.explain(args["text"], car, detail)
    path = args.get("path") or ops_report.report_path(folder(args), args["train"])
    return ops_report.explain_file(path, car, detail)


def action_help(args: dict) -> object:
    wanted = args.get("session_only")
    return {name: {"session": entry["session"], "help": entry["help"]}
            for name, entry in sorted(ACTIONS.items()) if entry["session"] or not wanted}


def tools() -> list[Tool]:
    directory = {"ops_dir": {"type": "string", "description": "Operations directory; defaults to OPS_DIR"}}
    actions = {"actions": {"type": "array", "items": {"type": "object"},
                           "description": "Each item names action plus its fields. See ops_actions."}}
    plan_id = {"plan_id": {"type": "string", "description": "From ops_plan"}}
    url = {"jmri_url": {"type": "string", "description": "JMRI web server; defaults to JMRI_URL, then localhost:12080"}}
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
        Tool("ops_explain_build",
             "Read a train's build report and say what the builder did: the outcome and failure cause, each stop's "
             "moves, the cars excluded before the search and why, and for each car the tracks tried, the refusal "
             "and its gate id. Reads the file JMRI wrote in buildstatus; give car to follow one car, "
             "detail 'full' for every line.",
             {"type": "object",
              "properties": {
                  **directory,
                  "train": {"type": "string", "description": "Train name, as in the buildstatus file name"},
                  "path": {"type": "string", "description": "A report file anywhere, instead of train and ops_dir"},
                  "text": {"type": "string", "description": "Pasted report text, instead of a file"},
                  "car": {"type": "string", "description": "Car id or road and number: only that car's story"},
                  "detail": {"type": "string", "enum": ["normal", "full"]}}},
             explain_build),
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
             "Each train comes back with its build report read as ops_explain_build reads it: "
             "outcome and findings by default, detail 'normal' or 'full' for more. Changes nothing.",
             {"type": "object", "properties": {**directory, "terminate": {"type": "boolean"}, "detail": DETAIL}},
             lambda a: ops_jmri.dry_run(folder(a), a.get("terminate", True), a.get("detail", "summary"))),
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
        Tool("ops_install_agent",
             "Copy the live agent beside the Operations files and plan the startup entry that runs it. "
             "Show the plan, then ops_apply it with JMRI exited. Needed for ops_train build and reset, "
             "ops_live_car, ops_live_save, ops_live_report and ops_live_automation.",
             {"type": "object", "properties": directory},
             lambda a: ops_live.install_agent(folder(a)), read_only=False),
        Tool("ops_live_status",
             "Ask a running JMRI what state each train is in and whether the agent is running. Changes nothing.",
             {"type": "object", "properties": url}, lambda a: ops_live.status(a.get("jmri_url"))),
        Tool("ops_train",
             "Build, move, terminate or reset a train in a running JMRI. train may be 'all' for build (enabled, "
             "unbuilt trains in time order), terminate and reset. Build opens no dialogs and answers with the "
             "report read as ops_explain_build reads it (outcome and findings; detail for more): a staging track is "
             "then chosen by JMRI, not asked for. Building a built train needs rebuild.",
             {"type": "object",
              "properties": {**url, "action": {"type": "string", "enum": ["build", "move", "terminate", "reset"]},
                             "train": {"type": "string"},
                             "location": {"type": "string", "description": "For move: a location on the route"},
                             "rebuild": {"type": "boolean"}, "detail": DETAIL},
              "required": ["action", "train"]},
             lambda a: ops_live.train_action(a["action"], a["train"], a.get("location"), a.get("rebuild", False),
                                             a.get("jmri_url"), a.get("detail", "summary")), read_only=False),
        Tool("ops_live_car",
             "Set a car on a track in a running JMRI and run that track's schedule, as Set Car does. "
             "Refused for a car on a train. If the schedule refuses it, the car goes back.",
             {"type": "object",
              "properties": {**url, "car": {"type": "string"}, "location": {"type": "string"},
                             "track": {"type": "string"}},
              "required": ["car", "location", "track"]},
             lambda a: ops_live.ask(ops_live.base_url(a.get("jmri_url")), "set_car", car=a["car"],
                                    location=a["location"], track=a["track"]), read_only=False),
        Tool("ops_live_save",
             "Make a running JMRI save its Operations files now, so ops_why_not and ops_audit see the latest state.",
             {"type": "object", "properties": url},
             lambda a: ops_live.ask(ops_live.base_url(a.get("jmri_url")), "save"), read_only=False),
        Tool("ops_live_report",
             "Read the end of a train's build report or manifest from a running JMRI.",
             {"type": "object",
              "properties": {**url, "train": {"type": "string"},
                             "kind": {"type": "string", "enum": ["build", "manifest"]}},
              "required": ["train"]},
             lambda a: ops_live.ask(ops_live.base_url(a.get("jmri_url")), "report", train=a["train"],
                                    kind=a.get("kind", "build"))),
        Tool("ops_live_automation",
             "Run a named Operations automation in a running JMRI, with build dialogs off, and wait up to two "
             "minutes. A Message step in the automation still opens a window on that computer.",
             {"type": "object", "properties": {**url, "name": {"type": "string"}}, "required": ["name"]},
             lambda a: ops_live.ask(ops_live.base_url(a.get("jmri_url")), "automation", name=a["name"]),
             read_only=False),
    ]


if __name__ == "__main__":
    serve("operations-pro", tools())
