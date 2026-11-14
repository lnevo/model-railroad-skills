"""Layers: read one level's input files, split by kind.

    <name>.plan_overrides.json   layer 1  facts about the railroad the plan does not hold (always read)
    <name>.signals.json          layer 1  masts, generated from the Layout Editor panel (signal_reader.py)
    <name>.preferences.json      layer 3  the owner's look for this sheet (optional, read last)
    <name>.hints.json            comparison only: hand hints from before the rules replaced them

Layer 2 is the code (the generation rules), not a file. Merged in that order: a dict merges key by key, a
list named in APPEND is added to (so edits keep their order across files), and anything else is replaced.
Keys that start with "_" are notes and are dropped.

`hints` is read only when asked for. It exists so a run can show what a rule gets right or wrong by
comparing against the hand-set value it replaces; the drawings the tool is judged by never use it.
"""
import json
from pathlib import Path

# Lists that collect entries across layers; any other list (a title, a band order) is one value and is replaced.
APPEND = {"edits", "min_cells", "keep_close", "shorten", "main_route", "signals_planned", "track_directions"}


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        elif k in APPEND and isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out


def load(name, data, preferences=True, hints=False):
    """The options of one named level with the layers asked for. Layer 1 is always read."""
    opts = {}
    for kind, on in (("plan_overrides", True), ("hints", hints), ("preferences", preferences)):
        path = Path(data) / f"{name}.{kind}.json"
        if on and path.exists():
            opts = merge(opts, json.loads(path.read_text()))
    sig = Path(data) / f"{name}.signals.json"      # layer 1 too, generated from the panel by signal_reader.py
    if sig.exists():
        opts["signals"] = json.loads(sig.read_text())["signals"]
    return opts
