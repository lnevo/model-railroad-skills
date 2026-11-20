"""Layers: read one level's input files, split by kind.

    <name>.plan_overrides.json   layer 1  facts about the railroad the plan does not hold (always read)
    <name>.signals.json          layer 1  masts, generated from the Layout Editor panel (signal_reader.py)
    <name>.preferences.json      layer 3  the owner's look for this sheet (optional, read last)
    <name>.hints.json            comparison only: hand hints from before the rules replaced them

Each kind may instead be one file for every input, `<kind>.json` (plan_overrides.json, preferences.json, ...) holding
"_sections": true, whose other top-level keys are the input names, each holding what `<name>.<kind>.json` would (keys
starting with "_" are notes). A `<kind>.json` without that key is not a layer file and is not read.
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


SECTIONS = "_sections"     # the key a combined file holds, true, to say it is one: a <kind>.json without it is not read


def combined_path(kind, data):
    """The one file of a kind for every input: <data>/<kind>.json."""
    return Path(data) / f"{kind}.json"


def _json(path):
    try:
        return json.loads(path.read_text())
    except ValueError as exc:
        raise LayerError(f"{path}: not JSON ({exc})") from None


def sections(kind, data):
    """{input name: section} of the combined file of `kind`, or None when there is none. A <kind>.json without
    "_sections": true is some other file and is not read (an old railroad's own signals.json, say). LayerError when it
    says it is one but is not an object of objects."""
    combined = combined_path(kind, data)
    if not combined.exists():
        return None
    whole = _json(combined)
    if not isinstance(whole, dict) or whole.get(SECTIONS) is not True:
        return None
    bad = sorted(k for k, v in whole.items() if not k.startswith("_") and not isinstance(v, dict))
    if bad:
        raise LayerError(f"{combined}: section(s) {', '.join(bad)} are not objects")
    return {k: v for k, v in whole.items() if not k.startswith("_")}


def read_layer(name, kind, data):
    """The layer `kind` of input `name`: its own file <name>.<kind>.json, or its section of <kind>.json (a file with
    "_sections": true), or None when neither has it. LayerError when both do, on an input name starting with "_" (a
    note's key in a combined file), on a layer that is not a JSON object, or on bad JSON."""
    if str(name).startswith("_"):
        raise LayerError(f"input name {name!r}: a name starting with _ is a note's key in a combined layer file")
    own = Path(data) / f"{name}.{kind}.json"
    section = (sections(kind, data) or {}).get(name)
    if own.exists():
        if section is not None:
            raise LayerError(f"{name} has both {own.name} and a section in {combined_path(kind, data).name}: keep one")
        layer = _json(own)
        if not isinstance(layer, dict):
            raise LayerError(f"{own}: must be a JSON object")
        return layer
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
        if not isinstance(sig.get("signals"), list):
            raise LayerError(f"{name}'s signals layer has no \"signals\" list (the signals command's output, or its "
                             "section of signals.json)")
        opts["signals"] = sig["signals"]
    return opts
