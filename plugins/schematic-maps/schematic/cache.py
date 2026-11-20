"""Solved-sheet and Layout Editor panel cache, off unless SCHEMATIC_CACHE names a folder.

Solving a sheet (laying out every band, then placing labels and growing room for them) is the slow part of every
command, and a build pipeline that draws the sheet, its detail sheets and its panels solves the same inputs again
each time. With SCHEMATIC_CACHE=<folder>, sheet.build keeps each solved Sheet there, keyed on everything a solve
reads: the source of the modules the solve runs (sheet.py and what it imports, found by reading their imports, so
a change to the Layout Editor or CATS code keeps the solve), each input graph and its layer name, the layer files
layers.load reads for that name and sheet.preferences.json, the preferences and hints switches and the Python
version. The title block's own fields (TITLE_FIELDS: date, revision, sheet) are left out of the key: they change no
part of the solve, so a hit takes them from the files as they are now and draws the page again (sheet.build). Any
other change is a new key, so a stale sheet is never returned. Each call gets its own copy, so a caller that
changes the bands cannot change what the next caller gets. The newest KEEP entries are kept.

memo() keeps any other result the same way, keyed on its own name, the source of the modules it runs and its
arguments as plain data (digest): le.panel keeps whole panels and the grid its window fit settled on.

The key cannot see module values changed while the program runs (a test that patches sheet.ROOM_ROUNDS, say):
such a build must run with the cache off. The entries are pickles, read back as code would be: point
SCHEMATIC_CACHE only at a folder that you alone write to.

The cache only saves time. A result that cannot be stored, an entry that cannot be read and arguments that cannot be
keyed are reported on stderr and the work goes on without the cache; only a folder that cannot be made stops it,
since that is a wrong setting.
"""
import ast
import functools
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
KEEP = 48              # solved sheets and Layout Editor panels together
STALE_TMP = 3600       # seconds: a half-written entry this old was left by a writer that was killed
VERSION = b"sheet-cache 3"
TITLE_FIELDS = ("date", "revision", "sheet")    # preferences that only fill the title block (draw.title_fields)
PACKAGE = Path(__file__).resolve().parent


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
    return ([d / f"{name}.{kind}.json" for _, name in inputs for kind in LAYER_KINDS]
            + [d / f"{kind}.json" for kind in LAYER_KINDS] + [d / "sheet.preferences.json"])


class Unfollowed(Exception):
    """A module imports this package in a way modules() cannot follow."""


@functools.lru_cache(maxsize=None)
def modules(*roots):
    """Sorted paths of the package modules `roots` (names such as "sheet") run: each root and every module of this
    package it imports, at the top of a file or inside a function, followed through the modules it reaches. Worked
    out once per process: the source does not change while it runs. Raises Unfollowed for an import of the package
    it cannot follow (a parent-relative or absolute one) and SchematicError for a root that is no module."""
    todo, seen = list(roots), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        path = PACKAGE / f"{name}.py"
        if not path.is_file():
            raise SchematicError(f"cache: no module {name} in {PACKAGE}")
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_bytes(), str(path))):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                if node.module:                                 # from .x import y
                    todo.append(node.module.split(".")[0])
                else:                                           # from . import x, y
                    todo.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level > 1 or \
                    isinstance(node, (ast.Import, ast.ImportFrom)) and \
                    any((getattr(node, "module", None) or a.name).split(".")[0] == PACKAGE.name for a in node.names):
                raise Unfollowed(f"{path.name} imports this package in a way the key cannot follow")
    return tuple(sorted(PACKAGE / f"{n}.py" for n in seen))


def _sources(h, roots):
    """Hash the source of the modules `roots` run into h; False (and a warning) when they cannot be found."""
    try:
        files = modules(*roots)
    except Unfollowed as exc:
        warn(f"{exc}; working without the cache")
        return False
    for f in files:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return True


def _layer_bytes(f):
    """What the key reads of a layer file: its bytes, but a preferences file as JSON without TITLE_FIELDS."""
    raw = f.read_bytes()
    if not f.name.endswith("preferences.json"):
        return raw
    try:
        prefs = json.loads(raw)
    except ValueError:
        return raw                                  # the solve reports it; the key needs only to differ
    if not isinstance(prefs, dict):
        return raw
    if f.name == "preferences.json":                # one section per input (layers.read_layer): strip each
        prefs = {k: ({kk: vv for kk, vv in v.items() if kk not in TITLE_FIELDS} if isinstance(v, dict) else v)
                 for k, v in prefs.items()}
        return json.dumps(prefs, sort_keys=True).encode()
    return json.dumps({k: v for k, v in prefs.items() if k not in TITLE_FIELDS}, sort_keys=True).encode()


def key(inputs, data, preferences, hints):
    """A hex digest of everything sheet.build reads for these arguments but the title block's own fields, or None
    (and a warning) when a graph given as a dict is not plain JSON or the solve's modules cannot be followed."""
    h = hashlib.sha256(VERSION)
    h.update(sys.version.encode())                 # pickles are read back by the same Python only
    if not _sources(h, ("sheet", "cache")):
        return None
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
        h.update(b"+" + _layer_bytes(f) + b"\0" if f.exists() else b"-\0")
    h.update(repr((bool(preferences), bool(hints))).encode())
    return h.hexdigest()


def _encode(obj, out):
    """Plain data as bytes that do not depend on dict order, set order or the string hash seed."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        out.append(f"{type(obj).__name__}:{obj!r};".encode())
    elif isinstance(obj, (list, tuple)):
        out.append(f"{type(obj).__name__}[{len(obj)}](".encode())
        for v in obj:
            _encode(v, out)
        out.append(b")")
    elif isinstance(obj, (set, frozenset)):
        items = sorted(b"".join(_encode(v, [])) for v in obj)
        out.append(f"set[{len(items)}](".encode() + b"".join(items) + b")")
    elif isinstance(obj, dict):
        pairs = sorted((b"".join(_encode(k, [])), b"".join(_encode(v, []))) for k, v in obj.items())
        out.append(f"dict[{len(pairs)}](".encode() + b"".join(k + b"=" + v for k, v in pairs) + b")")
    else:
        raise TypeError(f"{type(obj).__name__} is not plain data")
    return out


def untitled(opts):
    """Options without the title block's fields (TITLE_FIELDS), for a key of something that does not draw them."""
    return {k: v for k, v in opts.items() if k not in TITLE_FIELDS} if isinstance(opts, dict) else opts


def digest(obj):
    """A hex digest of plain data (None, bool, int, float, str, and lists, tuples, sets and dicts of them), the same
    whatever the order of a dict or set. Raises TypeError for anything else."""
    return hashlib.sha256(b"".join(_encode(obj, []))).hexdigest()


def memo(name, roots, args, compute):
    """compute(), kept in the cache under `name` and a key of the source of the package modules `roots` run and
    `args` (plain data, see digest). The cache off, or args that are not plain data (said on stderr): compute() as
    it is. A hit is a fresh copy, so the caller may change what it gets."""
    where = folder()
    if where is None:
        return compute()
    h = hashlib.sha256(VERSION + b"\0" + name.encode() + b"\0" + sys.version.encode())
    if not _sources(h, tuple(roots)):
        return compute()
    try:
        h.update(digest(args).encode())
    except TypeError as exc:
        warn(f"{name}: arguments are not plain data ({exc}); computing without the cache")
        return compute()
    k = h.hexdigest()
    got = load(where, k)
    if got is not None:
        return got
    got = compute()
    stored = store(where, k, got)
    return pickle.loads(stored) if stored is not None else got


def load(where, k):
    """A fresh copy of the cached result for key k, or None. An entry that cannot be read is reported and dropped."""
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
    """Write a result under key k, atomically so a parallel reader never sees half a file, then prune. Returns the
    pickled bytes, or None (and a warning) when it could not be stored."""
    try:
        data = pickle.dumps(sheet, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        warn(f"cannot store the result ({type(exc).__name__}: {exc}); it is used as it is")
        return None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=where, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, where / f"{k}.pickle")
        tmp = None
    except OSError as exc:
        warn(f"cannot write to {where} ({exc}); the result is used as it is")
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
