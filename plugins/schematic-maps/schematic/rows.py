"""Rows: each switch keeps one leg level, and rows are chosen so the sloped legs are short."""
import collections

import math

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


SPREAD = 0.3        # cost of each row the band spans, top to bottom


def row_price(slopes, bias, lo, hi):
    """The cost from its parts: the weighted slope lengths, the bias, and the band's height (hi - lo rows)."""
    return (slopes + bias) + SPREAD * (hi - lo)


def rows_cost(r, terms, bias):
    """What an arrangement of rows costs, added up in full."""
    return row_price(sum(w * abs(r[a] - r[b]) for a, b, w in terms), bias, min(r.values()), max(r.values()))


def half_rows(w):
    """A slope weight as a whole count of half rows, or None when it is not one (or not finite)."""
    h = w * 2
    return int(h) if math.isfinite(h) and h == int(h) else None


def search_rows(start, classes, above, below, terms, bias):
    """The row search: descend_rows when every weight is a whole count of half rows (all of solve's are), else the
    plain core.descend with the cost added up in full, which chooses the same where both apply."""
    if all(half_rows(w) is not None for _a, _b, w in terms):
        return descend_rows(start, classes, above, below, terms, bias)
    push = lambda r, c, step: {**r, **push_rows(r, c, step, above, below)}      # noqa: E731
    return descend(dict(start), classes, push, lambda r: rows_cost(r, terms, bias))


def push_rows(r, c, step, above, below):
    """The rows that change when class c moves one row (step +1 or -1), pushing what must stay above or below it.
    Returns {class: new row} for the classes that move; r is not changed."""
    new = {c: r[c] + step}
    todo = [c]
    if step > 0:
        while todo:
            k = todo.pop()
            up = new[k] + 1
            for d in above.get(k, ()):
                if new.get(d, r[d]) < up:
                    new[d] = up
                    todo.append(d)
    else:
        while todo:
            k = todo.pop()
            down = new[k] - 1
            for d in below.get(k, ()):
                if new.get(d, r[d]) > down:
                    new[d] = down
                    todo.append(d)
    return new


def descend_rows(start, classes, above, below, terms, bias):
    """core.descend for rows, with the cost worked out from the moved classes only.

    The same moves are tried in the same order and kept on the same test (`c < best - 1e-9`) as core.descend with
    rows_cost, and every cost is the same float: the weights are whole multiples of 0.5, so the slope sum is
    exact whether it is added up in full or changed term by term; it is kept as a whole count of half rows and
    turned into the same float the full sum gives. Returns (rows, cost). search_rows picks it; a weight that is
    not a whole count of half rows is a ValueError here."""
    halves = collections.defaultdict(int)      # (class, other class): weight in half rows, both ways round
    for a, b, w in terms:
        h = half_rows(w)
        if h is None:
            raise ValueError(f"rows: slope weight {w} between {a} and {b} is not a whole count of half rows")
        if a != b:                              # a slope within one class is always 0
            halves[a, b] += h
            halves[b, a] += h
    links = collections.defaultdict(list)
    for (a, b), h in halves.items():
        links[a].append((b, h))
    cur = dict(start)
    total = sum(h * abs(cur[a] - cur[b]) for (a, b), h in halves.items()) // 2
    count = collections.Counter(cur.values())
    lo, hi = min(count), max(count)

    def price(total, lo, hi):
        return row_price(total * 0.5, bias, lo, hi)

    best = price(total, lo, hi)
    no_links = ()
    improved = True
    while improved:
        improved = False
        for it in classes:
            for step in (1, -1):
                moved = push_rows(cur, it, step, above, below)
                twice = 0           # the change in half rows, twice over: a slope between two moved classes is seen
                for k, nk in moved.items():                 # from both ends, one to an unmoved class from one end
                    ok = cur[k]
                    for o, h in links.get(k, no_links):
                        oo = cur[o]
                        no = moved.get(o)
                        if no is None:
                            twice += 2 * h * (abs(nk - oo) - abs(ok - oo))
                        else:
                            twice += h * (abs(nk - no) - abs(ok - oo))
                for k, v in moved.items():
                    count[cur[k]] -= 1
                    count[v] += 1
                vals = moved.values()
                nlo, nhi = min(lo, min(vals)), max(hi, max(vals))
                while not count[nlo]:
                    nlo += 1
                while not count[nhi]:
                    nhi -= 1
                c = price(total + twice // 2, nlo, nhi)
                if c < best - 1e-9:
                    cur.update(moved)
                    total, lo, hi, best, improved = total + twice // 2, nlo, nhi, c, True
                else:
                    for k, v in moved.items():
                        count[v] -= 1
                        count[cur[k]] += 1
    return cur, best

class Rows:
    def __init__(self, nodes, strands, snaps, free=(), pins=None, close=(), rule_pins=None):
        self.nodes, self.strands, self.snaps, self.free = nodes, strands, snaps, set(free)
        # owner's hints: which leg of a switch runs level, by switch label or plan part number
        find_ref = lambda ref: [n for n, d in nodes.items() if d["kind"] == "switch"
                                and ref in (d.get("alias"), d.get("label"), (d.get("label") or "").rstrip("*"))]
        # owner's hints: pairs of switches to keep on neighbouring rows
        self.close = [(a[0], b[0]) for a, b in ((find_ref(p), find_ref(q)) for p, q in close) if a and b]
        # R5 and R6 are strong preferences, not pins: breaking one costs `rule_weight`, so the search keeps them
        # unless the drawing gets clearly tighter without them. A hand pin (layer 3) is fixed and overrides them.
        self.soft = dict(rule_pins or {})
        self.rule_weight = 2.0
        self.pins = {}
        self.pins.update({n: port for n, d in nodes.items() if d["kind"] == "switch"
                          for ref, port in (pins or {}).items()
                          if ref in (d.get("alias"), d.get("label"), (d.get("label") or "").rstrip("*"))})
        self.extra = set()
        self.flat = {n: "B" for n, d in nodes.items() if d["kind"] == "switch"}
        self.tolerant = bool(free)
        self.spans = None       # R7: when set, two tracks keep their order only if their extents overlap
        self.dropped = 0
        self.memo = None        # while optimise runs: {level legs: (solve result, dropped)}
        self.memo_keep = (None, {})     # the memo kept between optimise calls, and the inputs it was made from

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
        """Rows for the current level legs. While optimise runs (where tolerant is always on), an arrangement solved
        before is read back, with the count of dropped rules it set. The key holds the level legs in their order (it
        decides the class names, and so the order of the search); optimise drops the memo when anything else solve
        reads has changed (optimise's ctx)."""
        if self.memo is None or not self.tolerant:
            return self.solve_now()
        key = tuple(self.flat.items())
        if key not in self.memo:
            self.memo[key] = (self.solve_now(), self.dropped)
        r, self.dropped = self.memo[key]
        return r

    def solve_now(self):
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

        row, c = search_rows(row, classes, above, below, terms, bias)
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
            st_.update(self.soft)
            st_.update(self.pins)
        best = None
        held, memo = self.memo_keep
        # everything else solve reads, as values: a change to any of them (the graph edited in place too) drops the
        # memo, and the entries of an earlier set of extra rules go with it
        ctx = (repr(self.nodes), repr(self.strands), None if self.spans is None else repr(self.spans),
               frozenset(self.free), repr(self.snaps), tuple(self.close), frozenset(self.extra),
               tuple(sorted(self.pins.items())), tuple(sorted(self.soft.items())))
        self.memo = memo if held == ctx else {}
        self.memo_keep = (ctx, self.memo)
        try:
            for start in starts:
                self.flat = dict(start)
                r = self.optimise_from_here()
                sc = (self.dropped, r["cost"] + self.broken())
                if best is None or sc < best[0]:
                    best = (sc, r, dict(self.flat))
        finally:
            self.memo = None
        self.flat = best[2]
        self.dropped = best[0][0]
        r = best[1]             # a copy, so a caller that changes it cannot change what the memo hands back later
        return dict(r, srow=dict(r["srow"]), nrow=dict(r["nrow"]), diag=set(r["diag"]))

    def broken(self):
        """The price of the R5 and R6 preferences the current choice breaks."""
        return self.rule_weight * sum(self.flat[n] != leg for n, leg in self.soft.items()
                                      if n in self.flat and n not in self.pins)

    def optimise_from_here(self):
        """Choose each switch's level leg: first so that no above/below rule is broken, then for short slopes."""
        self.tolerant = True

        def score(r):
            return (self.dropped, r["cost"] + self.broken())

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


