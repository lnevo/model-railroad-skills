"""Sweep: the top-to-bottom order of the tracks, left to right."""
from .core import TURN_SIGN, dx_tracks, legs


def sweep(nodes, strands, col, warn):
    L, alive, done, snaps, enclosed, free, ev = [], set(), set(), [], {}, set(), {}

    def snap():
        snaps.append([s for s in L if s in alive])

    def where(hint):
        if hint is None:
            return len(L)
        i = L.index(hint[0])
        return i if hint[1] == "above" else i + 1

    def process(n, hint=None):
        d = nodes[n]
        k = d["kind"]
        if k == "switch" and d["sig"] == 1:
            a = d["ins"]["A"]
            up, lo = legs(nodes, n)
            i = L.index(a)
            alive.discard(a)
            L[i:i + 1] = [up, a, lo]
            alive.update((up, lo))
        elif k == "switch":
            up, lo = legs(nodes, n)
            iu, il = L.index(up), L.index(lo)
            if iu > il or any(s in alive for s in L[min(iu, il) + 1:max(iu, il)]):
                # the layout is not flat here (one track passes over another): let the shorter leg cross
                f = min((up, lo), key=lambda s: strands[s]["cm"])
                free.add(f)
                warn(f"switch {d['label']}: one leg has to cross other track to reach it")
                iu, il = min(iu, il), max(iu, il)
            alive.difference_update((up, lo))
            L.insert(il, d["outs"]["A"])
            alive.add(d["outs"]["A"])
        elif k == "dx":
            (iu_, ou), (il_, ol) = dx_tracks(nodes, n)
            if L.index(iu_) > L.index(il_):
                warn(f"double crossover {d['label']}: tracks arrive in the opposite order")
                (iu_, ou), (il_, ol) = (il_, ol), (iu_, ou)
            if any(s in alive for s in L[L.index(iu_) + 1:L.index(il_)]):
                warn(f"double crossover {d['label']}: a track lies between its two tracks")
            alive.difference_update((iu_, il_))
            L.insert(L.index(il_), ol)
            L.insert(L.index(iu_) + 1, ou)
            alive.update((ou, ol))
        elif k == "end" and d["outs"]:
            s = d["outs"]["E"]
            L.insert(where(hint), s)
            alive.add(s)
        elif k == "end":
            alive.discard(d["ins"]["E"])
        elif k == "turnL":
            s0, s1 = d["outs"][0], d["outs"][1]
            want = hint[2] if hint and len(hint) > 2 else s0
            other = s1 if want == s0 else s0
            if hint is None:        # nothing to sit beside: take the order from which way the loop bends on the layout
                (u, pu), (v, _) = strands[s0]["dst"], strands[s1]["dst"]
                du = nodes[u].get("dirs", {}).get(pu)
                if du and "xy" in nodes[u] and "xy" in nodes[v]:
                    px, py = TURN_SIGN * -du[1], TURN_SIGN * du[0]
                    if nodes[v]["xy"][0] * px + nodes[v]["xy"][1] * py > nodes[u]["xy"][0] * px + nodes[u]["xy"][1] * py:
                        want, other = s1, s0
                if nodes[strands[s0]["dst"][0]].get("flipped"):     # a loop off a flipped switch is flipped with it
                    want, other = other, want
            pair = [want, other] if (hint is None or hint[1] == "below") else [other, want]
            i = where(hint)
            L[i:i] = pair
            alive.update(pair)
        elif k == "turnR":
            i0, i1 = sorted((L.index(d["ins"][0]), L.index(d["ins"][1])))
            inside = [s for s in L[i0 + 1:i1] if s in alive]
            if inside:
                warn(f"turnback {n}: tracks still open inside it")
            enclosed[n] = [s for s in L[i0 + 1:i1]]
            alive.difference_update(d["ins"].values())
        ev[n] = len(done)
        done.add(n)
        snap()

    def demand(s, hint):
        p = strands[s]["src"][0]
        d = nodes[p]
        if p in done:
            return
        if d["kind"] == "end":
            process(p, hint)
        elif d["kind"] == "turnL":
            process(p, (hint[0], hint[1], s))
        elif d["kind"] == "switch" and d["sig"] == 1:
            if d["ins"]["A"] not in alive:
                demand(d["ins"]["A"], hint)
            process(p)
        else:
            up, lo = legs(nodes, p) if d["kind"] == "switch" else [t[0] for t in dx_tracks(nodes, p)]
            have = [x for x in (up, lo) if x in alive]
            if not have:
                demand(up, hint)
                have = [up]
            if up not in alive:
                demand(up, (lo, "above"))
            if lo not in alive:
                demand(lo, (up, "below"))
            process(p)

    def prio(n):
        d = nodes[n]
        if d["kind"] == "end":
            return (0, col[n])
        if d["kind"] == "turnR":
            i0, i1 = sorted((L.index(d["ins"][0]), L.index(d["ins"][1])))
            return (1 if not any(s in alive for s in L[i0 + 1:i1]) else 9, col[n])
        return (2 if d["sig"] == -1 or d["kind"] == "dx" else 3, col[n])

    while len(done) < len(nodes):
        ready = [n for n, d in nodes.items() if n not in done and d["ins"]
                 and all(s in alive for s in d["ins"].values())]
        if ready:
            process(min(ready, key=prio))
            continue
        part = [n for n, d in nodes.items() if n not in done and d["ins"]
                and any(s in alive for s in d["ins"].values())]
        if part:
            n = min(part, key=lambda n: col[n])
            d = nodes[n]
            if d["kind"] == "turnR":
                have = next(s for s in d["ins"].values() if s in alive)
                miss = next(s for s in d["ins"].values() if s not in alive)
                demand(miss, (have, "below"))
            else:
                up, lo = legs(nodes, n) if d["kind"] == "switch" else [t[0] for t in dx_tracks(nodes, n)]
                if up in alive:
                    demand(lo, (up, "below"))
                else:
                    demand(up, (lo, "above"))
            continue
        src = [n for n, d in nodes.items() if n not in done and not d["ins"]]
        process(min(src, key=lambda n: -sum(strands[s]["cm"] for s in nodes[n]["outs"].values())))
    return L, snaps, enclosed, free, ev


