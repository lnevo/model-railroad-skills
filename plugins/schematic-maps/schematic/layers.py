"""Layers: read one level's input files, split by kind.

    <name>.plan_overrides.json   layer 1  facts about the railroad the plan does not hold (always read)
    <name>.signals.json          layer 1  masts, generated from the Layout Editor panel (signal_reader.py)
    <name>.preferences.json      layer 3  the owner's look for this sheet (optional, read last)
    <name>.hints.json            comparison only: hand hints from before the rules replaced them

Each kind may instead be one file for every input, `<kind>.json` (plan_overrides.json, preferences.json, ...), whose
top-level keys are the input names, each holding what `<name>.<kind>.json` would (keys starting with "_" are notes).
An input's section and its own file must not both exist: LayerError names the two, so no copy silently wins. A
combined file with no section for an input gives that input nothing of that kind, as a missing file does.

Layer 2 is the code (the generation rules), not a file. Merged in that order: a dict merges key by key, a
list named in APPEND is added to (so edits keep their order across files), and anything else is replaced.
Keys that start with "_" are notes and are dropped.

`hints` is read only when asked for. It exists so a run can show what a rule gets right or wrong by
comparing against the hand-set value it replaces; the drawings the tool is judged by never use it.
"""
import json
from pathlib import Path

from .core import SchematicError

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


LAYER_KINDS = ("plan_overrides", "hints", "preferences", "signals")   # <name>.<kind>.json or <kind>.json: what load reads


class LayerError(SchematicError):
    """A layer file cannot be read as the layers need it; the message names the file."""


def combined_path(kind, data):
    """The one file of a kind for every input: <data>/<kind>.json."""
    return Path(data) / f"{kind}.json"


def read_layer(name, kind, data):
    """The layer `kind` of input `name`: its own file <name>.<kind>.json, or its section of <kind>.json, or None when
    neither has it. LayerError when both do, when the combined file is not an object of objects, or on bad JSON."""
    own = Path(data) / f"{name}.{kind}.json"
    combined = combined_path(kind, data)
    section = None
    if combined.exists():
        try:
            whole = json.loads(combined.read_text())
        except ValueError as exc:
            raise LayerError(f"{combined}: not JSON ({exc})") from None
        if not isinstance(whole, dict):
            raise LayerError(f"{combined}: must be an object with one section per input name")
        bad = sorted(k for k, v in whole.items() if not k.startswith("_") and not isinstance(v, dict))
        if bad:
            raise LayerError(f"{combined}: section(s) {', '.join(bad)} are not objects")
        section = whole.get(name)
    if own.exists():
        if section is not None:
            raise LayerError(f"{name} has both {own.name} and a section in {combined.name}: keep one")
        try:
            return json.loads(own.read_text())
        except ValueError as exc:
            raise LayerError(f"{own}: not JSON ({exc})") from None
    return section


def load(name, data, preferences=True, hints=False):
    """The options of one named level with the layers asked for. Layer 1 is always read."""
    opts = {}
    for kind, on in (("plan_overrides", True), ("hints", hints), ("preferences", preferences)):
        layer = read_layer(name, kind, data) if on else None
        if layer is not None:
            opts = merge(opts, layer)
    sig = read_layer(name, "signals", data)        # layer 1 too, generated from the panel by signal_reader.py
    if sig is not None:
        opts["signals"] = sig["signals"]
    return opts
