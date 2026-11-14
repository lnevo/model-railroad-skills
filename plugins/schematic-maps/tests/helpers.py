"""Shared fixtures: the made-up example written once per test run, and its sheets built once."""
import json
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
for p in (PLUGIN, PLUGIN / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import example  # noqa: E402
from schematic import panel_reader, plan_reader, sheet, signal_reader  # noqa: E402

GOLDEN = PLUGIN / "tests" / "golden"
_cache = {}


def folder():
    if "dir" not in _cache:
        _cache["tmp"] = tempfile.TemporaryDirectory()
        _cache["dir"] = Path(_cache["tmp"].name)
        _cache["files"] = example.write(_cache["dir"])
    return _cache["dir"]


def graph():
    """The plan reader's graph for the example, with part numbers and heights."""
    if "graph" not in _cache:
        f = folder()
        _cache["graph"] = plan_reader.read(str(f / "plan.xml"), None, json.loads((f / "parts.json").read_text()))
    return _cache["graph"]


def signals():
    if "signals" not in _cache:
        f = folder()
        from schematic import layers
        ov = layers.load("example", f, preferences=False)
        _cache["signals"] = signal_reader.read(str(f / "panel.xml"), graph(), ov,
                                               panel_reader.load_numbers(f / "numbers.csv"),
                                               panel_reader.load_lengths(f / "lengths.csv"))
    return _cache["signals"]


def data_with_signals():
    """The example folder with the generated signals file beside the layer files."""
    f = folder()
    signal_reader.write(f / "example.signals.json", signals())
    return f


def build(preferences=True):
    key = ("sheet", preferences)
    if key not in _cache:
        _cache[key] = sheet.build([(graph(), "example")], data_with_signals(), preferences=preferences)
    return _cache[key]
