"""Rows: each switch keeps one leg level, and rows are chosen so the sloped legs are short."""
import collections

from .core import descend, dx_tracks



def find_cycle(classes, above):
    """One directed cycle as a list of (from, to), or None."""
    state, stack = {}, []

    def visit(c):
        state[c] = 1
        stack.append(c)
        for d in sorted(above[c]):
            if state.get(d) == 1:
                i = stack.index(d)
                path = stack[i:] + [d]
                return list(zip(path, path[1:]))
            if d not in state:
                r = visit(d)
                if r:
                    return r
        stack.pop()
        state[c] = 2
        return None

    for c in classes:
        if c not in state:
            r = visit(c)
            if r:
                return r
    return None


class Rows:
    def __init__(self, nodes, strands, snaps, free=(), pins=None, close=(), rule_pins=None):
        self.nodes, self.strands, self.snaps, self.free = nodes, strands, snaps, set(free)
        # owner's hints: which leg of a switch runs level, by switch label or plan part number
        find_ref = lambda ref: [n for n, d in nodes.items() if d["kind"] == "switch"
                                and ref in (d.get("alias"), d.get("label"))]
        # owner's hints: pairs of switches to keep on neighbouring rows
        self.close = [(a[0], b[0]) for a, b in ((find_ref(p), find_ref(q)) for p, q in close) if a and b]
        self.pins = dict(rule_pins or {})       # R5 and R6; a hand pin (a comparison run) overrides them
        self.pins.update({n: port for n, d in nodes.items() if d["kind"] == "switch"
                          for ref, port in (pins or {}).items() if ref in (d.get("alias"), d.get("label"))})
        self.extra = set()
        self.flat = {n: "B" for n, d in nodes.items() if d["kind"] == "switch"}
        self.tolerant = bool(free)
        self.spans = None       # R7: when set, two tracks keep their order only if their extents overlap
        self.dropped = 0

    def frog(self, n):
        d = self.nodes[n]
        return d["outs"] if d["sig"] == 1 else d["ins"]

    def a_strand(self, n):
        d = self.nodes[n]
        return (d["ins"] if d["sig"] == 1 else d["outs"])["A"]

    def sloped(self, sid, end):
        n, p = self.strands[sid][end]
        return self.nodes[n]["kind"] == "switch" and p in "BC" and self.flat[n] != p

    def solve(self):
        st = self.strands
        parent = {s: s for s in st}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for n, f in self.flat.items():
            parent[find(self.a_strand(n))] = find(self.frog(n)[f])
        for n, d in self.nodes.items():
            if d["kind"] == "dx":
                for a, b in dx_tracks(self.nodes, n):
                    parent[find(a)] = find(b)
        diag = {s for s, d in st.items() if self.sloped(s, "src") and self.sloped(s, "dst")
                and (d["link"] or (not d["name"] and d["cm"] < 40))}
        above = collections.defaultdict(set)
        pairs = set(self.extra)
        for snap in self.snaps:
            row = [s for s in snap if s not in diag and s not in self.free]
            if self.spans is None:
                pairs.update(zip(row, row[1:]))
                continue
            for i, a in enumerate(row):         # R7: only tracks that really run side by side need separate rows
                for b in row[i + 1:]:
                    if a in self.spans and b in self.spans and (
                            self.spans[a][0] < self.spans[b][1] and self.spans[b][0] < self.spans[a][1]):
                        pairs.add((a, b))
        self.dropped = 0
        for a, b in pairs:
            if a in diag or b in diag:
                continue
            ca, cb = find(a), find(b)
            if ca == cb:
                if not self.tolerant:
                    return None
                self.dropped += 1
                continue
            above[ca].add(cb)
        classes = sorted({find(s) for s in st if s not in diag})
        while self.tolerant:            # break "A over B over ... over A" loops, one rule at a time
            cyc = find_cycle(classes, above)
            if not cyc:
                break
            a, b = cyc[0]
            above[a].discard(b)
            self.dropped += 1
        below = collections.defaultdict(set)
        indeg = {c: 0 for c in classes}
        for c in classes:
            for d in above[c]:
                indeg[d] += 1
                below[d].add(c)
        row = {c: 0 for c in classes}
        todo = [c for c in classes if indeg[c] == 0]
        seen = 0
        while todo:
            c = todo.pop()
            seen += 1
            for d in above[c]:
                row[d] = max(row[d], row[c] + 1)
                indeg[d] -= 1
                if indeg[d] == 0:
                    todo.append(d)
        if seen != len(classes):
            return None
        terms = []                      # (class, class, weight): slope length between two rows
        for n, f in self.flat.items():
            s = self.frog(n)["C" if f == "B" else "B"]
            me = find(self.a_strand(n))
            if s in diag:
                o = st[s]["src"][0] if st[s]["dst"][0] == n else st[s]["dst"][0]
                terms.append((me, find(self.a_strand(o)), 0.5))
            else:
                terms.append((me, find(s), 1.0))
        for a, b in self.close:
            terms.append((find(self.a_strand(a)), find(self.a_strand(b)), 5.0))
        for n, d in self.nodes.items():     # a double crossover wants its two tracks on neighbouring rows
            if d["kind"] == "dx":
                (a, _), (b, _) = dx_tracks(self.nodes, n)
                terms.append((find(a), find(b), 9.0))
        bias = 0.0
        for n, f in self.flat.items():      # a long track should run level and the short link slope
            level = st[self.frog(n)[f]]["cm"]
            other = st[self.frog(n)["C" if f == "B" else "B"]]["cm"]
            bias += (0.2 if other > 2 * level + 20 else 0.0) + (0.01 if f == "C" else 0.0)

        def cost(r):
            return (sum(w * abs(r[a] - r[b]) for a, b, w in terms) + bias
                    + 0.3 * (max(r.values()) - min(r.values())))

        def push(r, c, step):
            new = dict(r)
            new[c] += step
            todo = [c]
            while todo:
                k = todo.pop()
                if step > 0:
                    for d in above[k]:
                        if new[d] < new[k] + 1:
                            new[d] = new[k] + 1
                            todo.append(d)
                else:
                    for d in below[k]:
                        if new[d] > new[k] - 1:
                            new[d] = new[k] - 1
                            todo.append(d)
            return new

        row, c = descend(row, classes, push, cost)
        lo = min(row.values())
        srow = {s: row[find(s)] - lo for s in st if s not in diag}
        nrow = {}
        for n, d in self.nodes.items():
            if d["kind"] == "switch":
                nrow[n] = srow[self.a_strand(n)]
            elif d["kind"] == "end":
                nrow[n] = srow[next(iter(list(d["ins"].values()) + list(d["outs"].values())))]
        return dict(srow=srow, nrow=nrow, diag=diag, cost=c)

    def optimise(self):
        """Best of several starts, since the step-by-step search can stop at a poor arrangement."""
        import random
        rng = random.Random(7)
        keys = sorted(self.flat)
        starts = [dict(self.flat), {n: "B" for n in keys}, {n: "C" for n in keys}]
        starts += [{n: rng.choice("BC") for n in keys} for _ in range(5)]
        for st_ in starts:
            st_.update(self.pins)
        best = None
        for start in starts:
            self.flat = dict(start)
            r = self.optimise_from_here()
            sc = (self.dropped, r["cost"])
            if best is None or sc < best[0]:
                best = (sc, r, dict(self.flat))
        self.flat = best[2]
        self.dropped = best[0][0]
        return best[1]

    def optimise_from_here(self):
        """Choose each switch's level leg: first so that no above/below rule is broken, then for short slopes."""
        self.tolerant = True

        def score(r):
            return (self.dropped, r["cost"])

        best = self.solve()
        best_score = score(best)
        improved = True
        while improved:
            improved = False
            for n in self.flat:
                if n in self.pins:
                    continue
                self.flat[n] = "C" if self.flat[n] == "B" else "B"
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                else:
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
            if improved:
                continue
            # stuck on single changes: try two neighbouring switches together
            pairs = {tuple(sorted((d["src"][0], d["dst"][0]))) for d in self.strands.values()
                     if d["src"][0] in self.flat and d["dst"][0] in self.flat}
            for a, b in sorted(pairs):
                if a in self.pins or b in self.pins:
                    continue
                for n in (a, b):
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                    break
                for n in (a, b):
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
        self.dropped = best_score[0]
        return best


