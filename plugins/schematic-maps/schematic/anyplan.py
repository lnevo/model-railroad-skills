"""Read an AnyRail plan (.any) straight from the file: its track parts, their end points with heights, the flex
track curves, how the parts join, and what kind of part each is.

AnyRail's file is a binary archive with no published format. What this reads was worked out on real plans and
checked against AnyRail's JMRI export of the same plans; a new AnyRail version may write it differently, so read the
report's counts against the plan before trusting them:

- A part's name record is two length-prefixed strings: the catalogue name and its library code. Scenery, vehicles
  and buildings have name records too.
- An end point record is four doubles (x, y, z in cm, and the end's heading in radians) followed by a
  length-prefixed track system string. The bytes before the doubles differ for the first record of its kind in a
  file (the archive writes the record's class there), so records are found by what follows the doubles, never by
  a tag in front of them.
- A track part is a name record whose library starts with a system that end points use, so the reader keeps
  every maker's track and no scenery, without a list of makers. Its end points are the end point records between
  its name record and the next part's.
- A flex track's curve is a list of Bezier points: a count, then per point a two-byte class tag, an id and x and
  y. The tag is numbered per file (two plans used two different tags), so a list counts only when every point
  carries the same tag and the curve starts and ends on the part's end points.

The type of a part comes from its end points, not its catalogue name: one end is a track end, two are track, three a
turnout (straight or curved, left or right), four a three-way, a double crossover or a crossing (a diamond or slip,
which the ends alone cannot tell apart).

Coordinates are AnyRail's: centimetres, y growing down the screen. A part's index (its place in the file) is its
T number in a plan graph read with a parts list (`plan --parts`).

    schematic anyplan PLAN.any --report            levels, track ends, grades, likely faults
    schematic anyplan PLAN.any --parts parts.json  the parts list `schematic plan --parts` reads
    schematic anyplan PLAN.any --cut -5 --stubs lower.json upper.json
        each level's plan graph gets its share of a run that climbs between them (a helix), up to the cut height
"""
import bisect
import collections
import math
import re
import struct
import sys
from pathlib import Path

from .pieces import bezier_geometry, wrap_deg
from .plan_reader import PlanError

JOIN_CM = 0.15          # two ends this close (in plan) are joined, as AnyRail snaps them
JOIN_DZ_CM = 0.5        # ... and this close in height
NEAR_MISS_CM = 5.0      # a free end this close to another end is reported: it probably should join
MAX_XY_CM = 5000.0      # a plan coordinate beyond this is not a coordinate
PARALLEL_DEG = 2.0      # two ends this close in heading run the same way
LEVEL_CM = 0.05         # a part's ends within this much height are level
STUB_PX = 60.0          # how far out along its leg a cut stub's track end is placed in a plan graph (export px)

LENGTH_RE = re.compile(rb"(?=[\x01-\x30]\x00{7})")      # where a length-prefixed string may start
PRINTABLE = re.compile(rb"[\x20-\x7e]+")
CODE = re.compile(rb"[A-Za-z0-9_-]+")
POINT_BYTES = 22        # tag (2), id (4), x (8), y (8)


def _finite(*v):
    return all(math.isfinite(x) for x in v)


def _string(d: bytes, at: int, shape, lo: int, hi: int):
    """The length-prefixed string at `at` (an 8-byte length, then exactly that many bytes) if it has `shape` and a
    length in lo..hi, else None. The length decides where it ends, whatever byte follows."""
    n = d[at]
    if not lo <= n <= hi or d[at + 1:at + 8] != b"\x00" * 7 or at + 8 + n > len(d):
        return None
    s = d[at + 8:at + 8 + n]
    return s.decode() if shape.fullmatch(s) else None


def _names(d: bytes):
    """[(offset, name, library)] of every name record: two strings, the second a library code."""
    out = []
    for m in LENGTH_RE.finditer(d):
        o = m.start()
        name = _string(d, o, PRINTABLE, 3, 48)
        if name is None:
            continue
        lib = _string(d, o + 8 + len(name), CODE, 2, 16)
        if lib is not None:
            out.append((o, name, lib))
    return out


def _end_records(d: bytes):
    """[(offset, x, y, z, a, system)] of every record shaped like an end point: four doubles, then a system code."""
    out = []
    for m in LENGTH_RE.finditer(d):
        o = m.start()
        system = _string(d, o, CODE, 3, 32) if o >= 32 else None
        if system is None:
            continue
        x, y, z, a = struct.unpack("<4d", d[o - 32:o])
        # (0, 0) is not a place on a plan, and a subnormal double (8e-320) is not a measure: headers have that shape
        real = not any(0.0 < abs(v) < sys.float_info.min for v in (x, y, z, a))
        if (real and _finite(x, y, z, a) and abs(x) < MAX_XY_CM and abs(y) < MAX_XY_CM and abs(z) < 1000
                and abs(a) < 10 and max(abs(x), abs(y)) > 1e-6):
            out.append((o - 32, x, y, z, a, system))
    return out


def _curve(d: bytes, start: int, ends):
    """The Bezier points of the flex curve stored after `start`, or None: a count then that many points with one tag,
    starting and ending on the part's ends."""
    for o in range(start, min(start + 400, len(d) - 10)):
        n = d[o]
        if not (4 <= n <= 64 and (n - 1) % 3 == 0 and d[o + 1:o + 8] == b"\x00" * 7):
            continue
        tag, base = d[o + 8:o + 10], o + 8
        if base + n * POINT_BYTES > len(d) or tag[1] != 0 or not 0x20 <= tag[0] <= 0x7e:
            continue
        pts = []
        for k in range(n):
            p = base + k * POINT_BYTES
            if d[p:p + 2] != tag:
                break
            x, y = struct.unpack("<2d", d[p + 6:p + 22])
            if not _finite(x, y) or abs(x) > MAX_XY_CM or abs(y) > MAX_XY_CM:
                break
            pts.append((x, y))
        if len(pts) != n:
            continue
        tips = (pts[0], pts[-1])
        if all(min(math.dist(t, (e["x"], e["y"])) for t in tips) < 0.5 for e in ends):
            return pts
    return None


def bezier_length(pts):
    """Length of a flex curve stored as a chain of cubic Beziers (1 + 3n points), measured along each."""
    if len(pts) < 4 or (len(pts) - 1) % 3:
        raise PlanError(f"a chain of cubic Beziers has 1 + 3n points (n at least 1), got {len(pts)}")
    return sum(bezier_geometry(pts[s:s + 4])[0] for s in range(0, len(pts) - 3, 3))


def read(path) -> list[dict]:
    """The plan's track parts in file order: {index, name, library, system, ends [{x, y, z, a}], curve, cm, kind,
    ...}; `cm` is a flex track's length along its curve, None for a fixed part."""
    try:
        d = Path(path).read_bytes()
    except OSError as e:
        raise PlanError(f"{path}: cannot be read ({e.strerror})") from None
    names = _names(d)
    records = _end_records(d)
    libraries = {lib for _, _, lib in names}
    systems = {s for *_, s in records if any(lib.startswith(s) for lib in libraries)}     # codes of 3 or more
    if not systems:
        raise PlanError(f"{path}: no track end points found; is it an AnyRail plan?")
    kept = [n for n in names if any(n[2].startswith(s) for s in systems)]
    starts = [o for o, _, _ in kept]
    parts = [dict(index=i, name=n, library=lib, offset=o, ends=[]) for i, (o, n, lib) in enumerate(kept)]
    for o, x, y, z, a, s in records:
        if s not in systems:
            continue
        i = bisect.bisect_right(starts, o) - 1
        if i < 0:
            raise PlanError(f"{path}: a track end point at byte {o} comes before any track part")
        parts[i]["ends"].append(dict(x=x, y=y, z=z, a=a, system=s, offset=o))
    # a library none of whose parts has two ends is placed objects (benchwork, scenery), not track
    track_libs = {p["library"] for p in parts if len(p["ends"]) >= 2}
    parts = [p for p in parts if p["library"] in track_libs]
    for i, p in enumerate(parts):
        p["index"] = i
    bad = [(p["index"], p["name"], len(p["ends"])) for p in parts if len(p["ends"]) > 4]
    if bad:
        raise PlanError(f"{path}: parts with more than four ends, which no track part has (index, name, ends): {bad}")
    parts = [p for p in parts if p["ends"]]          # catalogue items with no ends (a label, a sign) are not track
    for i, p in enumerate(parts):
        p["index"] = i
        p["system"] = p["ends"][0]["system"]
        p["curve"] = _curve(d, p["ends"][-1]["offset"] + 32, p["ends"]) if len(p["ends"]) == 2 else None
        p["cm"] = bezier_length(p["curve"]) if p["curve"] else (fixed_length(p["ends"]) if len(p["ends"]) == 2 else None)
        p.update(classify(p["ends"]))
    return parts


def fixed_length(ends):
    """A two-ended part with no curve in the file (sectional track, or flex stored another way): its length from its
    ends, straight or a circular arc through the change of heading between them."""
    a, b = ends
    chord = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
    turn = math.radians(abs(wrap_deg(math.degrees(a["a"] - b["a"]) - 180)))
    return chord if turn < 1e-6 else chord * (turn / 2) / math.sin(turn / 2)


def _heading(e):
    return math.degrees(e["a"])


def classify(ends) -> dict:
    """{kind, ...} from a part's ends. kind: end (a buffer stop); track; turnout (points, straight, diverging end indices, hand L/R,
    curved); threeway (points); double_crossover; crossing (diamond or slip)."""
    xy = [(e["x"], e["y"]) for e in ends]
    if len(ends) == 2:
        return dict(kind="track")
    if len(ends) == 3:
        far = [sum(math.dist(xy[i], xy[j]) for j in range(3)) for i in range(3)]
        p = max(range(3), key=far.__getitem__)
        legs = [i for i in range(3) if i != p]
        back = _heading(ends[p]) + 180
        s, dv = sorted(legs, key=lambda i: abs(wrap_deg(_heading(ends[i]) - back)))
        (sx, sy), (dx, dy) = [(xy[i][0] - xy[p][0], xy[i][1] - xy[p][1]) for i in (s, dv)]
        hand = "R" if sx * dy - sy * dx > 0 else "L"       # y grows down: clockwise on screen is to the right
        curved = abs(wrap_deg(_heading(ends[s]) - back)) > PARALLEL_DEG
        return dict(kind="turnout", points=p, straight=s, diverging=dv, hand=hand, curved=curved)
    if len(ends) == 1:
        return dict(kind="end")
    h = [_heading(e) for e in ends]
    near = lambda u, v, tol: abs(wrap_deg(u - v)) < tol                                   # noqa: E731
    for p in range(4):                  # a three-way: the other three leave the way the points end faces away
        if all(near(h[i], h[p] + 180, 45) for i in range(4) if i != p):
            return dict(kind="threeway", points=p)
    for a, b, c, e in ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2)):
        if near(h[a], h[b], PARALLEL_DEG) and near(h[c], h[e], PARALLEL_DEG) and near(h[a], h[c] + 180, PARALLEL_DEG):
            return dict(kind="double_crossover")
    return dict(kind="crossing")


def joins(parts):
    """(links [(part, end, part, end)], free [(part, end)]). Ends join when they meet in plan and height."""
    ends = [(p["index"], k, e) for p in parts for k, e in enumerate(p["ends"])]
    cell = lambda e: (math.floor(e["x"] / 1), math.floor(e["y"] / 1))          # noqa: E731
    grid = collections.defaultdict(list)
    for t in ends:
        grid[cell(t[2])].append(t)
    links, degree = [], collections.Counter()
    for i, k, e in ends:
        cx, cy = cell(e)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j, m, f in grid[(gx, gy)]:
                    if (j, m) <= (i, k):
                        continue
                    if math.hypot(e["x"] - f["x"], e["y"] - f["y"]) < JOIN_CM and abs(e["z"] - f["z"]) < JOIN_DZ_CM:
                        links.append((i, k, j, m))
                        degree[(i, k)] += 1
                        degree[(j, m)] += 1
    crowded = [t for t, n in degree.items() if n > 1]
    if crowded:
        raise PlanError(f"more than two track ends meet at one spot: {crowded}")
    free = [(i, k) for i, k, _ in ends if not degree[(i, k)]]
    return links, free


def components(parts, links):
    root = list(range(len(parts)))

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    for a, _, b, _ in links:
        root[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for p in parts:
        groups[find(p["index"])].append(p["index"])
    return sorted(groups.values(), key=len, reverse=True)


def runs(parts, links):
    """Switch-to-switch runs: [(part, end, part or None, end or None, cm)] from every end of every part with three or
    more ends, through two-ended parts, to the next such part or a free end; each run once from each side. cm counts
    flex curves only (fixed parts add nothing), as AnyRail's export measures between turnout ends."""
    nbr = {}
    for a, ka, b, kb in links:
        nbr[(a, ka)], nbr[(b, kb)] = (b, kb), (a, ka)
    out = []
    for p in parts:
        if len(p["ends"]) < 3:
            continue
        for k in range(len(p["ends"])):
            here, cm, seen = (p["index"], k), 0.0, 0
            while here in nbr:
                j, m = nbr[here]
                q = parts[j]
                if len(q["ends"]) == 1:                     # a buffer stop ends the run as a track end does
                    out.append((p["index"], k, None, None, cm))
                    break
                if len(q["ends"]) != 2:
                    out.append((p["index"], k, j, m, cm))
                    break
                cm += q["cm"] or 0.0
                here, seen = (j, 1 - m), seen + 1
                if seen > len(parts):
                    raise PlanError(f"a run from part {p['index']} loops without reaching a switch")
            else:
                out.append((p["index"], k, None, None, cm))
    return out


def level_cuts(parts, links, cut_z) -> list[dict]:
    """The switch-to-switch runs that climb through height `cut_z` (a helix between two levels), once each:
    {low: (part, end), high: (part, end), low_cm, high_cm}, the run's length on each side of the cut, low the side
    below it. A run crosses the cut inside one of its flex pieces; the share of that piece on each side is taken in
    proportion to its height, as a piece's grade is even along it."""
    nbr = {}
    for a, ka, b, kb in links:
        nbr[(a, ka)], nbr[(b, kb)] = (b, kb), (a, ka)
    out = []
    for p, k, q, m, cm in runs(parts, links):
        if q is None or not parts[p]["ends"][k]["z"] < cut_z < parts[q]["ends"][m]["z"]:
            continue
        here, low_cm, at = (p, k), 0.0, None
        while True:
            j, mm = nbr[here]
            part = parts[j]
            if len(part["ends"]) != 2:
                break
            za, zb, length = part["ends"][mm]["z"], part["ends"][1 - mm]["z"], part["cm"] or 0.0
            if at is None and za <= cut_z < zb:
                at = low_cm + length * (cut_z - za) / (zb - za)
            low_cm += length
            here = (j, 1 - mm)
        if at is None:
            raise PlanError(f"the run from part {p} to part {q} crosses {cut_z} cm between two pieces, not in one")
        out.append(dict(low=(p, k), high=(q, m), low_cm=at, high_cm=cm - at))
    return out


def add_cut_stubs(graph, cuts, cut_z):
    """Give each switch in a plugin graph (`schematic plan` output) whose run leaves its level through the cut the
    track up to the cut: a track end `CUT:T<n>` (marked `cut` with the height) at the end of a new edge as long as
    the run's share on that side. The graph's switch is found by its T label; the run must be the one leg it lacks.
    Returns the T labels given a stub."""
    N, edges = graph["nodes"], graph["edges"]
    by_t = {d["label"]: n for n, d in N.items() if d["kind"] == "switch" and d.get("label", "").startswith("T")}
    used = collections.defaultdict(set)
    for e in edges:
        used[e["u"]].add(e["up"])
        used[e["v"]].add(e["vp"])
    done = []
    for c in cuts:
        for side, cm in (("low", c["low_cm"]), ("high", c["high_cm"])):
            t = f"T{c[side][0]}"
            n = by_t.get(t)
            if n is None:
                continue
            missing = sorted({"A", "B", "C"} - used[n])
            if len(missing) != 1:
                raise PlanError(f"{t} should lack one leg (its run through the {cut_z} cm cut) but lacks "
                                f"{missing or 'none'}")
            end, eid = f"CUT:{t}", f"e{len(edges)}"
            if end in N or any(e["id"] == eid for e in edges):
                raise PlanError(f"{t} already has a cut stub, or the graph's edge ids are not e0 to e{len(edges) - 1}")
            way = N[n].get("dirs", {}).get(missing[0])                  # set the end a little way out along that leg
            if not way:
                raise PlanError(f"{t} has no direction for its leg {missing[0]}, so its cut stub has nowhere to go")
            xy = [round(N[n]["xy"][i] + STUB_PX * way[i], 2) for i in (0, 1)]
            N[end] = dict(kind="end", label="", xy=xy, district=N[n].get("district", ""), cut=cut_z)
            edges.append(dict(u=n, up=missing[0], v=end, vp="E", names=[], cm=round(cm, 1), link=False, main=False,
                              district=N[n].get("district", ""), hidden=False, id=eid))
            used[n].add(missing[0])
            done.append(t)
    return done


def stub_graphs(parts, cut_z, graphs) -> list[str]:
    """add_cut_stubs on every graph, in memory; stops unless each side of every run through the cut got its stub in
    exactly one graph (a side at a junction no graph labels, such as a three-way half, would lose its helix share)."""
    links, _ = joins(parts)
    cuts = level_cuts(parts, links, cut_z)
    given = [t for g in graphs for t in add_cut_stubs(g, cuts, cut_z)]
    sides = [f"T{c[side][0]}" for c in cuts for side in ("low", "high")]
    if sorted(given) != sorted(sides):
        raise PlanError(f"the runs through {cut_z} cm end at {', '.join(sides) or 'no switch'}, but the graphs gave "
                        f"stubs at {', '.join(given) or 'none'}: each side must be one graph's switch")
    return given


def parts_list(parts) -> list[dict]:
    """The parts list the schematic-maps plugin reads (`plan --parts`): name and end points' x, y, z, in file order."""
    return [{"name": p["name"], "eps": [{k: e[k] for k in "xyz"} for e in p["ends"]]} for p in parts]


def report(parts) -> list[str]:
    links, free = joins(parts)
    comp = components(parts, links)
    lines = [f"{len(parts)} track parts, {sum(len(p['ends']) for p in parts)} ends, {len(links)} joins, "
             f"{len(free)} free ends, {len(comp)} connected piece(s): {[len(c) for c in comp[:6]]}"]
    kinds = collections.Counter((p["kind"], p.get("hand"), p.get("curved")) for p in parts
                                if p["kind"] not in ("track", "end"))
    guessed = sum(1 for p in parts if len(p["ends"]) == 2 and not p["curve"])
    lines.append(f"two-ended parts measured from their ends (no curve in the file): {guessed}")
    lines.append("switches: " + ", ".join(f"{k[0]}{' ' + k[1] if k[1] else ''}{' curved' if k[2] else ''} x{n}"
                                          for k, n in sorted(kinds.items(), key=str)))
    z = collections.Counter(round(e["z"], 2) for p in parts for e in p["ends"])
    lines.append("ends by height (cm): " + ", ".join(f"{h} x{n}" for h, n in z.most_common(8)))
    sw = collections.Counter(round(p["ends"][0]["z"], 2) for p in parts if len(p["ends"]) > 2)
    lines.append("switches by height (cm): " + ", ".join(f"{h} x{n}" for h, n in sorted(sw.items())))
    tilted = [p["index"] for p in parts if len(p["ends"]) > 2
              and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > LEVEL_CM]
    lines.append(f"switches not level: {tilted or 'none'}")
    grades = sorted(((100 * abs(p["ends"][0]["z"] - p["ends"][1]["z"]) / p["cm"], p["index"]) for p in parts
                     if p["cm"] and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > LEVEL_CM), reverse=True)
    lines.append(f"sloped flex pieces: {len(grades)}, steepest " +
                 ", ".join(f"T{i} {g:.2f}%" for g, i in grades[:5]) if grades else "sloped flex pieces: none")
    near, seen = [], set()
    for i, k in free:                   # a free end close to another end that faces it, once per pair
        e = parts[i]["ends"][k]
        for q in parts:
            for m, f in enumerate(q["ends"]):
                pair = frozenset(((i, k), (q["index"], m)))
                if q["index"] == i or pair in seen:
                    continue
                dist = math.hypot(e["x"] - f["x"], e["y"] - f["y"])
                facing = abs(wrap_deg(math.degrees(e["a"] - f["a"]))) > 135
                if dist < NEAR_MISS_CM and facing and abs(e["z"] - f["z"]) < JOIN_DZ_CM:
                    seen.add(pair)
                    near.append((i, q["index"], round(dist, 2), round(f["z"] - e["z"], 2)))
    lines.append(f"free ends within {NEAR_MISS_CM} cm of another end facing them at the same height: {near or 'none'}")
    return lines

