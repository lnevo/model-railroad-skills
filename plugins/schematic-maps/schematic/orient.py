"""Orient: which way each switch faces, and which runs are drawn as turnbacks."""
import collections
import itertools

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


def orient(g, max_turnbacks=3, keep=10):
    """The cheapest ways to face every switch, best first: (facing, turnback edges)."""
    sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in JUNCTION for n in (e["u"], e["v"]))]
    cand = [e for e in sw if not e["link"]]
    if len(cand) > 40:      # big plan: only runs that bend back on the layout may be turnbacks
        cand = [e for e in cand if udot(g, e) > -0.5]
        max_turnbacks = 5
    best, found = None, []
    for k in range(max_turnbacks + 1):
        for T in itertools.combinations(cand, k):
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
        if best is not None and k > len(best[2]):
            break
    if best is None:
        raise SchematicError("no orientation found; raise max_turnbacks")
    found.sort(key=lambda f: (f[0], f[1]))
    return [(sig, ids) for _, _, sig, ids in found[:keep]]


