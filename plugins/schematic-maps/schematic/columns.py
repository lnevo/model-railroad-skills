"""Columns: every track gets room for its name; spare length goes to the long tracks."""
import collections
import itertools
import math

from .core import JUNCTION, descend, dx_tracks  # noqa: F401



def name_cells(name, opts):
    return 0 if not name else math.ceil((len(name) * opts["name_px"] * 0.62 + 10) / opts["cell"])


class Unsettled(Exception):
    pass


def place(nodes, strands, R, enclosed, opts, extra=()):
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    cons, need, weight = [], {}, []
    for sid, s in strands.items():
        u, v = s["src"][0], s["dst"][0]
        if sid in diag:
            w = abs(nrow[u] - nrow[v])
            cons += [(u, v, w), (v, u, -w)]
            need[sid] = (0, 0, w)
            continue
        su = abs(srow[sid] - nrow[u]) if u in nrow else 0
        sv = abs(srow[sid] - nrow[v]) if v in nrow else 0
        h = max(name_cells(s["name"], opts), min(4, int(s["cm"] // 120)))   # a long track shows as a level run
        ends_ = {r for t in (u, v) for r in (nodes[t].get("alias"), nodes[t].get("label")) if r}
        tight = any(a in ends_ and b in ends_ for a, b in opts.get("shorten", ()))     # owner's hint: draw this run short
        if tight:
            h = 0
        refs = lambda n: {nodes[n].get("alias"), nodes[n].get("label")} - {None}
        for a, b, cells in opts.get("min_cells", ()):       # owner's hint: give this run at least so many cells
            e0, e1 = s["ends"]
            if (a in refs(e0) and b in refs(e1)) or (a in refs(e1) and b in refs(e0)):
                if "." not in sid or b in refs(u) | refs(v):  # of a folded run, the half that reaches b
                    h = max(h, cells)
        h += opts.get("_room", {}).get(s["edge"], 0)     # R12: cells claimed by labels that found no free position
        if nodes[u]["kind"] == "end" or nodes[v]["kind"] == "end":
            h = max(h, 1) + 1
        if nodes[u].get("sub") == "link" or nodes[v].get("sub") == "link":
            h, tight = 1, True          # a connector gets one short level cell, never more
        w = max(1, su + sv + h) + sum(nodes[t]["kind"] == "dx" for t in (u, v))
        need[sid] = (su, sv, w)
        cons.append((u, v, w))
        cm = s["cm"] / (2 if "." in sid else 1)
        weight.append((u, v, 20.0 if tight else 100.0 / (cm + 25.0), w))  # long tracks take up the slack
    for t, inside in enclosed.items():
        for sid in inside:
            n = strands[sid]["dst"][0]
            cons.append((n, t, 4 if nodes[n].get("sub") == "helix" else 1))     # room for the helix box
    cons += list(extra)
    fwd, back = collections.defaultdict(list), collections.defaultdict(list)
    for u, v, w in cons:
        fwd[u].append((v, w))
        back[v].append((u, w))
    x = {n: 0 for n in nodes}
    for _ in range(4 * len(nodes) + 10):
        changed = False
        for u, v, w in cons:
            if x[v] < x[u] + w:
                x[v], changed = x[u] + w, True
        if not changed:
            break
    else:
        raise Unsettled("columns: constraints do not settle")

    def cost(xs):
        # spare length is shared in proportion to the real length of each track (squared stretch), and a
        # small plain term keeps the whole band compact
        return sum(w * (xs[v] - xs[u] - least) ** 2 + 0.02 * (xs[v] - xs[u]) for u, v, w, least in weight)

    # switches joined by short links (a yard ladder, a crossover) also move as one block, and so does
    # each part of such a group either side of any one of its links
    links = [(s["src"][0], s["dst"][0]) for s in strands.values()
             if s["cm"] < 60 and nodes[s["src"][0]]["kind"] in JUNCTION and nodes[s["dst"][0]]["kind"] in JUNCTION]

    def groups(pairs):
        root = {n: n for n in nodes}

        def top(n):
            while root[n] != n:
                root[n] = root[root[n]]
                n = root[n]
            return n

        for u, v in pairs:
            root[top(u)] = top(v)
        out = collections.defaultdict(list)
        for n in nodes:
            out[top(n)].append(n)
        return {tuple(sorted(g)) for g in out.values() if len(g) > 1}

    blocks = groups(links)
    for i in range(len(links)):
        blocks |= groups(links[:i] + links[i + 1:])
    hangers = collections.defaultdict(set)          # track ends and fold-backs travel with the switch they hang off
    for s in strands.values():
        u, v = s["src"][0], s["dst"][0]
        for a, b in ((u, v), (v, u)):
            if nodes[a]["kind"] not in JUNCTION and nodes[b]["kind"] in JUNCTION:
                hangers[b].add(a)
    blocks = sorted({tuple(sorted(set(b) | {h for n in b for h in hangers[n]})) for b in blocks})

    def push(xs, n, step):
        new = dict(xs)
        todo = list(n) if isinstance(n, tuple) else [n]
        for m in todo:
            new[m] += step
        while todo:
            k = todo.pop()
            if step > 0:
                for v, w in fwd[k]:
                    if new[v] < new[k] + w:
                        new[v] = new[k] + w
                        todo.append(v)
            else:
                for u, w in back[k]:
                    if new[u] > new[k] - w:
                        new[u] = new[k] - w
                        todo.append(u)
        return new

    x, _ = descend(x, sorted(nodes) + blocks, push, cost)
    return x, need


def spans(nodes, strands, R, x, need):
    """Each level run's extent along its row, in columns: {strand: (left, right)}. A connector circle takes a cell."""
    room = lambda n: 1 if nodes[n].get("sub") in ("link", "helix") else 0
    out = {}
    for sid, s in strands.items():
        if sid in R["diag"]:
            continue
        su, sv, _ = need[sid]
        out[sid] = (x[s["src"][0]] + su - room(s["src"][0]), x[s["dst"][0]] - sv + room(s["dst"][0]))
    return out


def overlaps(nodes, strands, R, x, need, order):
    """Pairs of runs on the same row whose extents overlap."""
    rank = {s: i for i, s in enumerate(order)}
    sp = spans(nodes, strands, R, x, need)
    found = set()
    for (s1, (a1, b1)), (s2, (a2, b2)) in itertools.combinations(sp.items(), 2):
        if R["srow"][s1] == R["srow"][s2] and a1 < b2 and a2 < b1:
            found.add((s1, s2) if rank[s1] < rank[s2] else (s2, s1))
    return found
