"""Label placement on a compact CATS panel."""

from .cats_px import GRID_PX, crosses, overlaps, signal_boxes, text_box, track_lines


SPILL_RANKS = (0, 2)    # band titles and end labels may run past the last track column; shown() counts them


def place_labels(P):
    """Place a compact panel's pending labels, lower rank first: each at its first candidate that stays inside the
    drawing and covers no track, signal or placed label; else at the candidate with the fewest such clashes,
    inside the drawing if any is (logged). Band titles and end labels may run past the last track column."""
    lines, signals = track_lines(P), signal_boxes(P)
    right = (max(c[0] for c in P.cells) + 1) * GRID_PX
    placed = []
    def clashes(box):
        return sum(crosses(box, ln) for ln in lines) + sum(overlaps(box, sb, 0) for sb in signals) + \
            sum(overlaps(box, pb) for pb in placed)

    queue = sorted(P.pending, key=lambda r: r[:2])
    while queue:
        rank, seq, cands, text, font = queue.pop(0)
        if isinstance(text, list):      # a group of names [(row, text, own candidates)]: one common column and
            for col in cands:           # spot, a column (over or under the track) or (column, spots)
                even = len({len(t) for _, t, _ in text}) == 1     # names of unequal length start in one line
                col, locs = (col, ("UPCENT", "LOWCENT") if even else ("UPLEFT", "LOWLEFT", "UPCENT", "LOWCENT")) \
                    if isinstance(col, int) else col
                for loc in locs:
                    spots = [((col, y), text_box((col, y), loc, t, font)) for y, t, _ in text]
                    if all(c not in P.labels for c, _ in spots) and \
                            all(b[0] >= GRID_PX and (b[2] <= right or rank in SPILL_RANKS) for _, b in spots) and \
                            not any(clashes(b) for _, b in spots) and \
                            not any(overlaps(a[1], b[1]) for i, a in enumerate(spots) for b in spots[i + 1:]):
                        for (c, b), (_, t, _) in zip(spots, text):
                            P.labels[c] = (t, loc, font)
                            placed.append(b)
                        break
                else:
                    continue
                break
            else:                       # no common column: each on its own
                queue[:0] = [(rank, seq, own, t, font) for _, t, own in text]
            continue
        best = None
        spill = rank in SPILL_RANKS
        for cell, loc in cands:
            if cell in P.labels or cell[0] < 1 or cell[1] < 1:
                continue
            box = text_box(cell, loc, text, font)
            if box[0] < GRID_PX:
                continue
            past = box[2] > right and not spill      # past the last track column: only if nothing else will do
            clash = clashes(box)
            if best is None or (past, clash) < best[0]:
                best = ((past, clash), cell, loc, box)
            if (past, clash) == (False, 0):
                break
        if best is None:
            P.log.append(f"no room for label {text!r}")
            continue
        (past, clash), cell, loc, box = best
        if clash:
            P.log.append(f"label {text!r} at {cell} {loc} crosses {clash} track lines, signals or labels")
        if past:
            P.log.append(f"label {text!r} at {cell} {loc} runs past the last track column")
        P.labels[cell] = (text, loc, font)
        placed.append(box)
    P.pending = None
