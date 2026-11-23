"""Orient: which way each switch faces, and which runs are drawn as turnbacks."""
import collections
import itertools
import math
import random
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


def split_through_loops(g):
    """A switch whose points (A) and straight (B) legs are joined by one run is a balloon loop closed on the through
    route: no left-to-right form holds it. Returns (graph, notes) where each such run becomes two short runs, A and B
    each to a bumper of its own (a stub beside the switch), and `notes` says so. Without one, the graph itself."""
    loops = [e for e in g["edges"] if e["u"] == e["v"] and g["nodes"][e["u"]]["kind"] == "switch"
             and {e["up"], e["vp"]} == {"A", "B"}]
    if not loops:
        return g, []
    nodes, edges, notes, drop = dict(g["nodes"]), [], [], {e["id"] for e in loops}
    for e in g["edges"]:
        if e["id"] not in drop:
            edges.append(e)
            continue
        x, y = g["nodes"][e["u"]]["xy"]
        for k, port in enumerate((e["up"], e["vp"])):
            d = g["nodes"][e["u"]].get("dirs", {}).get(port) or (0, 0)
            end = f"{e['id']}.end{k}"
            nodes[end] = dict(kind="end", sub="bumper", label="", xy=[x + 20 * d[0], y + 20 * d[1]])
            edges.append(dict(e, id=f"{e['id']}.{k}", u=e["u"], up=port, v=end, vp="E"))
        notes.append(f"switch {g['nodes'][e['u']].get('label') or e['u']}: a balloon loop on its through route, "
                     "drawn as a reversing loop (two stubs beside the switch)")
    return dict(g, nodes=nodes, edges=edges), notes


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


def cyclic_nodes(nodes, strands):
    """How many nodes the left-to-right graph cannot order (those on or behind a cycle)."""
    indeg = {n: len(d["ins"]) for n, d in nodes.items()}
    todo = [n for n, k in indeg.items() if k == 0]
    seen = 0
    while todo:
        n = todo.pop()
        seen += 1
        for sid in nodes[n]["outs"].values():
            m = strands[sid]["dst"][0]
            indeg[m] -= 1
            if indeg[m] == 0:
                todo.append(m)
    return len(nodes) - seen


SECOND_RESTARTS = 30
SECOND_STEPS = 4000
SECOND_MORE = 4         # restarts tried after the first one that finds a drawing


def second_pass(g, sw, must, seconds, keep):
    """A seeded, deterministic local search over the east/west colouring of the switches, for plans the first pass
    cannot solve (any non-link run may turn back). It minimises the runs that must be turnbacks plus a penalty for
    each node the columns cannot order, and keeps the acyclic colourings found, cheapest first."""
    junctions = sorted(n for n, d in g["nodes"].items() if d["kind"] in JUNCTION)
    if not junctions:
        return []
    musts = {e["id"] for e in must}
    rng = random.Random(1)
    deadline = time.monotonic() + seconds
    found, seen = [], set()

    def turned(sig):
        return {e["id"] for e in sw if sig[e["u"]] * sig[e["v"]] != -TAU[e["up"]] * TAU[e["vp"]]}

    def score(sig):
        T = turned(sig)
        bad = sum(1 for e in sw if e["link"] and e["id"] in T) + len(musts - T)
        nodes, strands = build(g, sig, T)
        return len(T) + 8 * bad + 5 * cyclic_nodes(nodes, strands), T, bad

    after = 0
    for _ in range(SECOND_RESTARTS):
        if found:
            after += 1
            if after > SECOND_MORE:     # enough restarts after the first success; the result is the same on every run
                break
        sig = {n: rng.choice((1, -1)) for n in junctions}
        cost, T, bad = score(sig)
        temp = 3.0
        for _ in range(SECOND_STEPS):
            if time.monotonic() > deadline:
                break
            n = rng.choice(junctions)
            sig[n] = -sig[n]
            cost2, T2, bad2 = score(sig)
            if cost2 <= cost or rng.random() < math.exp((cost - cost2) / temp):
                cost, T, bad = cost2, T2, bad2
                if cost == len(T) and bad == 0:         # nothing cyclic and no run wrongly turned
                    key = frozenset(T)
                    if key not in seen:
                        ids = set(T)
                        edges = [e for e in sw if e["id"] in ids]
                        full = colour(g, sw, ids)        # the same colouring test as the first pass
                        nodes, strands = build(g, full, ids) if full is not None else (None, None)
                        col = columns(nodes, strands) if full is not None else None
                        if col is not None:
                            seen.add(key)
                            c = 10 * len(ids) + 0.2 * max(col.values())
                            c += sum(6 * (1 - udot(g, e)) for e in edges)
                            found.append((c, sorted(ids), full, ids))
            else:
                sig[n] = -sig[n]
            temp = max(0.2, temp * 0.999)
        if time.monotonic() > deadline:
            break
    found.sort(key=lambda f: (f[0], f[1]))
    return found[:keep]


def orient(g, max_turnbacks=3, keep=10, require=(), log=None, seconds=RAISE_SECONDS):
    """The cheapest ways to face every switch, best first: (facing, turnback edges). `require`: edge ids that are
    turnbacks in every way tried (the `turnbacks` preference), on top of up to max_turnbacks others. When nothing is
    found at that cap, it rises one at a time up to the plan's independent loops plus 2 (each step passed to `log`)."""
    g, _ = split_through_loops(g)
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
        if log:
            log("turnbacks: nothing found by counting runs; second pass: a seeded search over every run that may turn back")
        found = second_pass(g, sw, must, seconds, keep)
        if found:
            return [(sig, ids) for _, _, sig, ids in found]
        raise SchematicError(f"no orientation found: {why}")
    found.sort(key=lambda f: (f[0], f[1]))
    return [(sig, ids) for _, _, sig, ids in found[:keep]]
