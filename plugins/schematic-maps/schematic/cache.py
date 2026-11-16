"""Solved-sheet cache, off unless SCHEMATIC_CACHE names a folder.

Solving a sheet (laying out every band, then placing labels and growing room for them) is the slow part of every
command, and a build pipeline that draws the sheet, its detail sheets and its panels solves the same inputs again
each time. With SCHEMATIC_CACHE=<folder>, sheet.build keeps each solved Sheet there, keyed on everything a build
reads: this package's source, each input graph and its layer name, the layer files layers.load reads for that name
and sheet.preferences.json, the preferences and hints switches and the Python version. Any change to one of them is
a new key, so a stale sheet is never returned. Each call gets its own copy, so a caller that changes the bands
cannot change what the next caller gets. The newest KEEP entries are kept.

The key cannot see module values changed while the program runs (a test that patches sheet.ROOM_ROUNDS, say):
such a build must run with the cache off. The entries are pickles, read back as code would be: point
SCHEMATIC_CACHE only at a folder that you alone write to.

The cache only saves time. A sheet that cannot be stored, an entry that cannot be read and a graph that cannot be
keyed are reported on stderr and the build goes on solving; only a folder that cannot be made stops it, since that
is a wrong setting.
"""
import hashlib
import json
import os
import pickle
import sys
import tempfile
import time
from pathlib import Path

from .core import SchematicError
from .layers import LAYER_KINDS

ENV = "SCHEMATIC_CACHE"
KEEP = 24
STALE_TMP = 3600       # seconds: a half-written entry this old was left by a writer that was killed
VERSION = b"sheet-cache 2"


def warn(text):
    print(f"{ENV}: {text}", file=sys.stderr)


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


def read_files(inputs, data):
    """The files a build reads besides the graphs: each input's layer files and sheet.preferences.json."""
    d = Path(data)
    return [d / f"{name}.{kind}.json" for _, name in inputs for kind in LAYER_KINDS] + [d / "sheet.preferences.json"]


def key(inputs, data, preferences, hints):
    """A hex digest of everything sheet.build reads for these arguments, or None (and a warning) when a graph given
    as a dict is not plain JSON."""
    h = hashlib.sha256(VERSION)
    h.update(sys.version.encode())                 # pickles are read back by the same Python only
    src = Path(__file__).resolve().parent
    for f in sorted(src.rglob("*.py")):
        h.update(f.relative_to(src).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    for graph, name in inputs:
        if isinstance(graph, dict):
            try:
                body = json.dumps(graph, sort_keys=True).encode()
            except (TypeError, ValueError) as exc:
                warn(f"input {name} is not plain JSON ({exc}); solving without the cache")
                return None
        else:
            body = Path(graph).read_bytes()
        h.update(str(name).encode() + b"\0" + body + b"\0")
    for f in read_files(inputs, data):            # a missing file and an empty one are different keys
        h.update(str(f.relative_to(data) if f.is_relative_to(data) else f).encode() + b"\0")
        h.update(b"+" + f.read_bytes() + b"\0" if f.exists() else b"-\0")
    h.update(repr((bool(preferences), bool(hints))).encode())
    return h.hexdigest()


def load(where, k):
    """A fresh copy of the cached Sheet for key k, or None. An entry that cannot be read is reported and dropped."""
    path = where / f"{k}.pickle"
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        warn(f"cannot read {path.name} ({exc}); solving again")
        return None
    try:
        sheet = pickle.loads(data)
    except Exception as exc:                      # a truncated or foreign file: say so, drop it, solve again
        warn(f"dropping unreadable {path.name} ({type(exc).__name__})")
        path.unlink(missing_ok=True)
        return None
    try:
        os.utime(path)                            # only the pruning order: newest use kept longest
    except OSError:
        pass
    return sheet


def store(where, k, sheet):
    """Write the Sheet under key k, atomically so a parallel reader never sees half a file, then prune. Returns the
    pickled bytes, or None (and a warning) when it could not be stored."""
    try:
        data = pickle.dumps(sheet, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        warn(f"cannot store the sheet ({type(exc).__name__}: {exc}); it was solved and is used as it is")
        return None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=where, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, where / f"{k}.pickle")
        tmp = None
    except OSError as exc:
        warn(f"cannot write to {where} ({exc}); the solved sheet is used as it is")
        return data
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    prune(where)
    return data


def _mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:                               # removed by another build in the meantime
        return None


def prune(where):
    """Keep the KEEP newest entries; remove half-written files older than STALE_TMP. Another build may remove the
    same files at the same time, which is fine."""
    entries = [(m, p) for p in where.glob("*.pickle") if (m := _mtime(p)) is not None]
    for _, old in sorted(entries, reverse=True)[KEEP:]:
        old.unlink(missing_ok=True)
    now = time.time()
    for tmp in where.glob("*.tmp"):
        m = _mtime(tmp)
        if m is not None and now - m > STALE_TMP:
            tmp.unlink(missing_ok=True)
