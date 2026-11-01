#!/usr/bin/env python3
"""MCP server for JMRI OperationsPro. Read-only so far: it opens the six XML files and nothing else.

Set OPS_DIR to the operations directory, or pass ops_dir on each call. Files are
re-read on every call, so a running JMRI's latest autosave is picked up.
"""
from __future__ import annotations

import os
from dataclasses import asdict

from mcp_stdio import Tool, serve
from ops_data import Railroad, directions, load
from ops_gates import Gates

LIST_TYPES = ("locations", "tracks", "schedules", "routes", "trains", "cars", "engines", "loads")


def railroad(args: dict) -> Railroad:
    directory = args.get("ops_dir") or os.environ.get("OPS_DIR")
    if not directory:
        raise ValueError("Set OPS_DIR or pass ops_dir: the folder holding the Operations XML files")
    return load(directory)


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


def tools() -> list[Tool]:
    directory = {"ops_dir": {"type": "string", "description": "Operations directory; defaults to OPS_DIR"}}
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
    ]


if __name__ == "__main__":
    serve("operations-pro", tools())
