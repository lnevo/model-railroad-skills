"""Solved-sheet cache, off unless SCHEMATIC_CACHE names a folder.

Solving a sheet (laying out every band, then placing labels and growing room for them) is the slow part of every
command, and a build pipeline that draws the sheet, its detail sheets and its panels solves the same inputs again
each time. With SCHEMATIC_CACHE=<folder>, sheet.build keeps each solved Sheet there, keyed on everything a build
reads: this package's source, each input graph and its layer name, every *.json file directly in the data folder
(the layer files and sheet.preferences.json) and the preferences and hints switches. Any change to one of them is a
new key, so a stale sheet is never returned. Each call gets its own copy, read back from the file, so a caller that
changes the bands cannot change what the next caller gets. The newest KEEP entries are kept. The entries are
pickles, read back as code would be: point SCHEMATIC_CACHE only at a folder that you alone write to.
"""
import hashlib
import json
import os
import pickle
import sys
import tempfile
from pathlib import Path

from .core import SchematicError

ENV = "SCHEMATIC_CACHE"
KEEP = 24
VERSION = b"sheet-cache 1"


def folder():
    """The cache folder from SCHEMATIC_CACHE, or None when caching is off."""
    value = os.environ.get(ENV, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SchematicError(f"{ENV}={value}: cannot make the cache folder ({exc})") from None
    return path


def key(inputs, data, preferences, hints):
    """A hex digest of everything sheet.build reads for these arguments."""
    h = hashlib.sha256(VERSION)
    h.update(sys.version.encode())                 # pickles are read back by the same Python only
    src = Path(__file__).resolve().parent
    for f in sorted(src.rglob("*.py")):
        h.update(f.relative_to(src).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    for graph, name in inputs:
        body = (json.dumps(graph, sort_keys=True).encode() if isinstance(graph, dict)
                else Path(graph).read_bytes())
        h.update(str(name).encode() + b"\0" + body + b"\0")
    for f in sorted(Path(data).glob("*.json")):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    h.update(repr((bool(preferences), bool(hints))).encode())
    return h.hexdigest()


def load(where, k):
    """The cached Sheet for key k, or None. An unreadable entry is removed and counts as a miss."""
    path = where / f"{k}.pickle"
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        sheet = pickle.loads(data)
    except Exception as exc:                      # a truncated or foreign file: say so, drop it, solve again
        print(f"{ENV}: dropping unreadable {path.name} ({type(exc).__name__})", file=sys.stderr)
        path.unlink(missing_ok=True)
        return None
    os.utime(path)                                # newest use first when pruning
    return sheet


def store(where, k, sheet):
    """Write the Sheet under key k (atomically, so a parallel reader never sees half a file), then prune."""
    fd, tmp = tempfile.mkstemp(dir=where, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(sheet, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, where / f"{k}.pickle")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    entries = sorted(where.glob("*.pickle"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in entries[KEEP:]:
        old.unlink(missing_ok=True)
