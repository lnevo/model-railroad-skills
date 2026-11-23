"""Orient: which way each switch faces, and which runs are drawn as turnbacks."""
import collections
import itertools
import math
import time

from .core import JUNCTION, TAU, SchematicError, tidy



def colour(g, sw_edges, T):
    sig = {}
    adj = collections.defaultdict(list)
    for e in sw_edges:
        r = (1 if e["id"] in T else -1) * TAU[e["up"]] * TAU[e["vp"]]
        adj[e["u"]].append((e["v"], r))
        adj[e["v"]].append((e["u"], r))
    for start in (n for n, d in g["nodes"].items() if d["kind"] in JUNCTION):
        if start in sig:
            continue
        sig[start] = 1
        todo = [start]
        while todo:
            u = todo.pop()
            for v, r in adj[u]:
                if v not in sig:
                    sig[v] = r * sig[u]
                    todo.append(v)
                elif sig[v] != r * sig[u]:
                    return None
    return sig


def build(g, sig, T):
    """Strands (drawn pieces of track) and the left-to-right graph."""
    nodes = {n: dict(d, ins={}, outs={}) for n, d in g["nodes"].items()}
    strands = {}

    def side(n, p):
        return sig[n] * TAU[p] if nodes[n]["kind"] in JUNCTION else None

    def add(sid, src, dst, e, name):
        strands[sid] = dict(src=src, dst=dst, edge=e["id"], ends=(e["u"], e["v"]), name=name, cm=e["cm"],
                            main=e["main"], link=e["link"], hidden=e.get("hidden", False),
                            way=e.get("way"))
        nodes[src[0]]["outs"][src[1]] = sid
        nodes[dst[0]]["ins"][dst[1]] = sid

    for e in g["edges"]:
        u, v = (e["u"], e["up"]), (e["v"], e["vp"])
        su, sv = side(*u), side(*v)
        names = tidy(e["names"])
        if su is None and sv is None:
            raise SchematicError("edge between two track ends")
        if su is None:
            su = -sv
        if sv is None:
            sv = -su
        if su != sv:
            a, b = (u, v) if su == 1 else (v, u)
            add(e["id"], a, b, e, " / ".join(names))
        else:
            t = "turn:" + e["id"]
            nodes[t] = dict(kind="turnR" if su == 1 else "turnL", ins={}, outs={}, label="")
            n0 = names[0] if names else ""
            n1 = names[-1] if len(names) > 1 else ""
            if su == 1:
                add(e["id"] + ".0", u, (t, 0), e, n0)
                add(e["id"] + ".1", v, (t, 1), e, n1)
            else:
                add(e["id"] + ".0", (t, 0), u, e, n0)
                add(e["id"] + ".1", (t, 1), v, e, n1)
    for n, d in nodes.items():
        d["sig"] = sig.get(n, 0)
    return nodes, strands



def columns(nodes, strands):
    """Longest-path column per node, or None when the left-to-right graph has a cycle."""
    indeg = {n: len(d["ins"]) for n, d in nodes.items()}
    col = {n: 0 for n in nodes}
    todo = [n for n, k in indeg.items() if k == 0]
    seen = 0
    while todo:
        n = todo.pop()
        seen += 1
        for sid in nodes[n]["outs"].values():
            m = strands[sid]["dst"][0]
            col[m] = max(col[m], col[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                todo.append(m)
    return col if seen == len(nodes) else None


def udot(g, e):
    du = g["nodes"][e["u"]].get("dirs", {}).get(e["up"])
    dv = g["nodes"][e["v"]].get("dirs", {}).get(e["vp"])
    return du[0] * dv[0] + du[1] * dv[1] if du and dv else 0.0


RAISE_SECONDS = 60.0        # longest the raised steps run in all, so the whole solve can stay in a 2 minute budget
RAISE_BUDGET = 3_000_000    # most combinations tried in all the raised steps together, after the first cap finds nothing


def loops_of(g):
    """The plan's independent loops: edges - nodes + components."""
    parent = {n: n for n in g["nodes"]}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in g["edges"]:
        parent[find(e["u"])] = find(e["v"])
    return len(g["edges"]) - len(g["nodes"]) + len({find(n) for n in g["nodes"]})


class OutOfTime(Exception):
    pass


def search(g, sw, must, cand, ks, found, best, deadline=None):
    """Try every set of k candidate runs as turnbacks, for k in `ks`; adds to `found` and returns the cheapest so far."""
    for k in ks:
        for T in (tuple(must) + c for c in itertools.combinations(cand, k)):
            if deadline is not None and time.monotonic() > deadline:
                raise OutOfTime()
            ids = {e["id"] for e in T}
            sig = colour(g, sw, ids)
            if sig is None:
                continue
            nodes, strands = build(g, sig, ids)
            col = columns(nodes, strands)
            if col is None:
                continue
            width = max(col.values())
            cost = 10 * k + 0.2 * width
            for e in T:
                cost += 6 * (1 - udot(g, e))   # a turnback should be a U-turn on the layout too
            found.append((cost, sorted(ids), sig, ids))
            if best is None or cost < best[0] - 1e-9:
                best = (cost, sig, ids)
        if best is not None and k + len(must) > len(best[2]):
            break
    return best


def orient(g, max_turnbacks=3, keep=10, require=(), log=None, seconds=RAISE_SECONDS):
    """The cheapest ways to face every switch, best first: (facing, turnback edges). `require`: edge ids that are
    turnbacks in every way tried (the `turnbacks` preference), on top of up to max_turnbacks others. When nothing is
    found at that cap, it rises one at a time up to the plan's independent loops plus 2 (each step passed to `log`)."""
    sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in JUNCTION for n in (e["u"], e["v"]))]
    must = [e for e in sw if e["id"] in set(require)]
    cand = [e for e in sw if not e["link"] and e["id"] not in set(require)]
    if len(cand) > 40:      # big plan: only runs that bend back on the layout may be turnbacks
        cand = [e for e in cand if udot(g, e) > -0.5]
        max_turnbacks = 5
    found = []
    best = search(g, sw, must, cand, range(max_turnbacks + 1), found, None)
    why = ""
    if best is None:
        limit, spent, deadline = loops_of(g) + 2, 0, time.monotonic() + seconds
        why = f"turnback counts up to {limit} (the plan's loops plus 2) were all tried"
        if max_turnbacks + 1 > limit:
            why = f"up to {max_turnbacks} turnbacks were tried, and the plan has {limit - 2} independent loops"
        for k in range(max_turnbacks + 1, limit + 1):
            n = math.comb(len(cand), k)
            if spent + n > RAISE_BUDGET:
                why = f"the search stopped at {k - 1} turnbacks: {n} more combinations is over the budget of {RAISE_BUDGET}"
                if log:
                    log(f"turnbacks: {why}")
                break
            spent += n
            if log:
                log(f"turnbacks: nothing with {k - 1} or fewer; trying {k} ({n} combinations of {len(cand)} runs)")
            try:
                best = search(g, sw, must, cand, (k,), found, best, deadline)
            except OutOfTime:
                why = f"the search stopped at {k} turnbacks after {seconds:g} seconds"
                if log:
                    log(f"turnbacks: {why}")
                if found:       # the step found some before time ran out: use them
                    best = (found[0][0], found[0][2], found[0][3])
                break
            if best is not None:
                break
    if best is None:
        raise SchematicError(f"no orientation found: {why}")
    found.sort(key=lambda f: (f[0], f[1]))
    return [(sig, ids) for _, _, sig, ids in found[:keep]]
