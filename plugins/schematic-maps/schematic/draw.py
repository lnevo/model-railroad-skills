"""Drawing: bands, masts and the page, as SVG in the NYAMR Physical Characteristics Book style."""
import collections  # noqa: F401
import datetime
import math
from xml.sax.saxutils import escape

from . import capacity, direction, labels
from .core import SchematicError, dedupe, dx_tracks, legs, other_end  # noqa: F401
from .layout import paths



def can_grow(band, k):
    """A strand R12 can lengthen: not a slope (its length follows the rows) and not a connector stub."""
    nodes, strands = band["nodes"], band["strands"]
    return k in strands and k not in band["R"]["diag"] and not any(
        nodes[t].get("sub") == "link" for t in (strands[k]["src"][0], strands[k]["dst"][0]))


def band_key(title):
    """The word that names a band in the preferences: the first word of its title."""
    words = (title or "").split()
    return words[0] if words else ""


BAND_SETTINGS = ("band_legend", "track_arrows", "rotate_bands", "band_cell", "band_align", "band_shift",
                 "band_width", "band_order")      # settings that name bands by their key

LEGENDS = {"normal": {"west": "left"}, "reversed": {"west": "right"}, "none": None}


def band_legend(opts, title):
    """The band's own direction legend as (west side, arrows shown), or None for no band legend.

    `band_legend` in the preferences, by band: "normal" (west to the left), "reversed" (west to the right), "none",
    or {"west": "left" or "right", "show": "both", "west" or "east"}; "show" names one arrow for a band whose
    traffic runs one way. Once any band declares one, the page legend is not drawn (`_band_legends`) and a band
    that declares nothing is "normal", or "reversed" when it is turned end for end (`rotate_bands`)."""
    spec = opts.get("band_legend", {}).get(band_key(title))
    if spec is None:
        turned = band_key(title) in opts.get("rotate_bands", ())
        spec = ("reversed" if turned else "normal") if opts.get("_band_legends") else "none"
    if isinstance(spec, str):
        if spec not in LEGENDS:
            raise SchematicError(f"band_legend for {band_key(title)} must be normal, reversed, none or "
                                 f"{{\"west\": ..., \"show\": ...}}, not {spec!r}")
        spec = LEGENDS[spec]
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise SchematicError(f"band_legend for {band_key(title)} must be a word or an object, not {spec!r}")
    west, show = spec.get("west", "left"), spec.get("show", "both")
    if west not in ("left", "right") or show not in ("both", "west", "east"):
        raise SchematicError(f"band_legend for {band_key(title)}: west is left or right and show is both, "
                             f"west or east, not {spec!r}")
    return west, show


def legend_texts(opts, west, show):
    """[(text, which)] left to right, e.g. [("\u2190 WEST", "west"), ("EAST \u2192", "east")]."""
    w, e = opts["left"].upper(), opts["right"].upper()
    pieces = ([(f"\u2190 {w}", "west"), (f"{e} \u2192", "east")] if west == "left"
              else [(f"\u2190 {e}", "east"), (f"{w} \u2192", "west")])
    return [pc for pc in pieces if show in ("both", pc[1])]


def track_way(s):
    """Which way trains run on a drawn strand, from its `way` (layer 1 track_directions): True to the right,
    False to the left, None both ways or not known. A strand's src is its left end; a fold half or a half cut
    at a level boundary holds only one end of its track, so the end it does hold decides."""
    way = s.get("way")
    if not way or way == "both":
        return None
    frm, to = way
    p, q = s["src"][0], s["dst"][0]
    if to == q or frm == p:
        return True
    if to == p or frm == q:
        return False
    return None


def track_runs(band, drawn, mode):
    """[(row, x from, x to, way, [strands])] for the track arrows: every strand with a declared way, and with
    `track_arrows` "main" every main strand too (two ways where none is declared). Level pieces of at least one
    cell that meet end to end on a row with the same way are one run, so a straight line carries one arrow. A
    strand drawn only on a slope has no level piece: its arrow sits on the middle of its longest sloped piece,
    pointing the way the slope runs across the page."""
    strands = band["strands"]
    pieces, sloped = [], []
    for k, pts in drawn.items():
        s = strands.get(k)
        if s is None or (s.get("way") is None and not (mode == "main" and s["main"])):
            continue
        way = track_way(s)
        level = [(r1, min(c1, c2), max(c1, c2), way, k) for (c1, r1), (c2, r2) in zip(pts, pts[1:])
                 if r1 == r2 and abs(c2 - c1) >= 1]
        pieces += level
        slopes = [((c1, r1), (c2, r2)) for (c1, r1), (c2, r2) in zip(pts, pts[1:])
                  if r1 != r2 and abs(c2 - c1) >= 1e-6]
        if not level and slopes:
            (c1, r1), (c2, r2) = max(slopes, key=lambda sl: abs(sl[1][0] - sl[0][0]))
            lo, hi = min(c1, c2), max(c1, c2)
            sloped.append(((r1 + r2) / 2, lo + (hi - lo) / 4, hi - (hi - lo) / 4, way, [k]))
    runs = []
    for row, a, b, way, k in sorted(pieces, key=lambda pc: pc[:3]):
        if runs and runs[-1][0] == row and runs[-1][3] == way and a <= runs[-1][2] + 1e-6:
            runs[-1] = (row, runs[-1][1], max(b, runs[-1][2]), way, runs[-1][4] + [k])     # meeting or overlapping
        else:
            runs.append((row, a, b, way, [k]))
    return runs + sloped


ARROWS = {True: "\u2192", False: "\u2190", None: "\u2194"}


def arrow_mark(svg, P, xy, way, size):
    """A track arrow in the box a two-character label would take at (x, baseline y): a shaft with a head at the
    end trains run toward, or at both ends for a track run both ways."""
    w = labels.text_width(ARROWS[way] * 2, size, "bold", 0.0)
    x, y = xy[0], xy[1] - 0.33 * size
    a, b, h = x - w / 2, x + w / 2, 0.3 * size
    d = f"M{a:.1f},{y:.1f} L{b:.1f},{y:.1f}"
    if way in (True, None):
        d += f" M{b - h:.1f},{y - h:.1f} L{b:.1f},{y:.1f} L{b - h:.1f},{y + h:.1f}"
    if way in (False, None):
        d += f" M{a + h:.1f},{y - h:.1f} L{a:.1f},{y:.1f} L{a + h:.1f},{y + h:.1f}"
    svg.append(f'<path d="{d}" stroke-width="1.3"/>')
    P.box(labels.text_box(xy[0], xy[1], "middle", ARROWS[way] * 2, size, "bold"))


def draw_band(band, title, opts, top, left):
    cell, rowh = opts["cell"], opts["rowh"]
    cell = opts.get("band_cell", {}).get(band_key(title), cell)      # a band can be stretched along its length
    legend = band_legend(opts, title)
    lead = 18 if legend else 0              # the band's own legend sits above its title, inside the band
    nodes, strands, R, x = band["nodes"], band["strands"], band["R"], band["x"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    x0, y0 = min(x.values()), min(srow.values())
    svg, text = [], []

    def X(c):
        return left + (c - x0) * cell

    def Y(r):
        return top + 30 + lead + (r - y0) * rowh

    # a band can be turned end for end (180 degrees): the line work is rotated, the lettering stays upright
    turned = band_key(title) in opts.get("rotate_bands", ())
    cx = (X(x0) + X(max(x.values()))) / 2
    cy = (Y(y0) + Y(max(srow.values()))) / 2

    P = labels.Placer()

    unturned = set()                        # boxes of fixed text (title, band legend): never turned with the band

    def label(xp, yp, s, size, anchor="middle", weight="normal", extra="", fixed=False):
        sp = float(extra.split('letter-spacing="')[1].split('"')[0]) if "letter-spacing" in extra else 0.0
        P.box(labels.text_box(xp, yp, anchor, str(s), size, weight, sp))
        if fixed:
            unturned.add(len(P.boxes) - 1)
        if turned and not fixed:
            xp, yp = 2 * cx - xp, 2 * cy - yp + size * 0.7
            anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
        text.append(f'<text x="{xp:.1f}" y="{yp:.1f}" font-size="{size}" text-anchor="{anchor}" '
                    f'font-weight="{weight}" fill="#000" stroke="none" {extra}>{escape(str(s))}</text>')

    helix = []
    if legend:
        xl = left
        for txt, _ in legend_texts(opts, *legend):
            label(xl, top + 4, txt, 11, anchor="start", weight="bold", extra='letter-spacing="1.5"', fixed=True)
            xl += labels.text_width(txt, 11, "bold", 1.5) + 24
    if title:
        label(left, top + 4 + lead, title.upper(), 12, anchor="start", weight="bold", extra='letter-spacing="1.5"',
              fixed=True)

    drawn = paths(band)
    cars = capacity.counts(band, opts)              # yard and stub tracks: how many cars each holds
    for k, pts in drawn.items():
        s = strands.get(k)
        wd = opts["main_w"] if (s is None or s["main"]) else opts["side_w"]
        if s is None:
            wd = max(opts["main_w"] if strands[q]["main"] else opts["side_w"] for q in strands
                     if k in (strands[q]["src"][0], strands[q]["dst"][0]))
        d = "M" + " L".join(f"{X(px):.1f},{Y(py):.1f}" for px, py in pts)
        dash = ' stroke-dasharray="7 5"' if s and s["hidden"] else ""
        svg.append(f'<path d="{d}" stroke-width="{wd}"{dash}/>')
        for (c1, r1), (c2, r2) in zip(pts, pts[1:]):
            P.line((X(c1), Y(r1)), (X(c2), Y(r2)), wd)
        if s and (s["name"] or k in cars) and k not in diag:
            shown = " ".join(t for t in (s["name"].upper(), f"({cars[k]})" if k in cars else "") if t)
            su, sv, _ = band["need"][k]
            xa, xb, yr = X(x[s["src"][0]] + su), X(x[s["dst"][0]] - sv), Y(srow[k])
            mid, q = (xa + xb) / 2, (xb - xa) / 4
            cands = [(xx, yr + dy, "middle") for dy in (-5, 5 + 0.72 * opts["name_px"] + 1)
                     for xx in (mid, mid - q, mid + q, xa + 0.6 * q, xb - 0.6 * q)]
            P.ask("track", shown, opts["name_px"], cands, spacing=0.4, room=[k] if can_grow(band, k) else [],
                  emit=lambda xy, t=shown: label(xy[0], xy[1], t, opts["name_px"], anchor=xy[2],
                                                               extra='letter-spacing="0.4"'))
    if opts.get("direction_arrows") and not turned:   # a band that runs east to the left somewhere: an arrow per main run
        for row, xa, xb, right, run in direction.main_runs(band, drawn):
            a, b = X(xa), X(xb)
            arrow = f"{opts['right'].upper()} \u2192" if right else f"\u2190 {opts['right'].upper()}"
            q = (b - a) / 6
            cands = [(xx, Y(row) + dy, "middle") for dy in (-5, 5 + 0.72 * 7.5 + 1)
                     for xx in ((a + q, a + 2 * q, (a + b) / 2) if right else (b - q, b - 2 * q, (a + b) / 2))]
            P.ask("track", arrow, 7.5, cands, weight="bold", spacing=0.4, room=[k for k in run if can_grow(band, k)],
                  emit=lambda xy, t=arrow: label(xy[0], xy[1], t, 7.5, anchor=xy[2], weight="bold", extra='letter-spacing="0.4"'))
    mode = opts.get("track_arrows", {}).get(band_key(title))
    if mode not in (None, "main", "listed"):
        raise SchematicError(f"track_arrows for {band_key(title)} must be main or listed, not {mode!r}")
    for row, xa, xb, way, run in track_runs(band, drawn, mode):     # which way trains run on each track
        a, b = X(xa), X(xb)
        q = (b - a) / 4
        cands = [(xx, Y(row) + dy, "middle") for dy in (-5, 5 + 0.72 * 11 + 1)
                 for xx in ((a + b) / 2, a + q, b - q, a + 0.6 * q, b - 0.6 * q)]
        # placed like a label (its box is two arrow characters wide), drawn as line work so a turned band turns it
        P.ask("track", ARROWS[way] * 2, 11, cands, weight="bold", room=[k for k in run if can_grow(band, k)],
              emit=lambda xy, w=way: arrow_mark(svg, P, xy, w, 11))
    switch_numbers, switch_strands = {}, {}
    for n, d in nodes.items():
        if d["kind"] == "switch":
            up, lo = legs(nodes, n)
            a_row = nrow[n]
            low = lo in diag and nrow[other_end(strands, lo, n)] > a_row or lo not in diag and srow[lo] > a_row
            high = up in diag and nrow[other_end(strands, up, n)] < a_row or up not in diag and srow[up] < a_row
            dy = -7 if low and not high else 13
            xs, ys, sg_ = X(x[n]), Y(a_row), d["sig"] or 1
            mine = [(xs + ddx * sg_, ys + ddy, "middle") for ddy in (dy, 20 - dy)
                    for ddx in (-7, 0, -13, 7, 13, -19)]
            lab = d.get("label") or ""
            base, star = (lab[:-1], "*") if lab.endswith("*") else (lab, "")
            shown = base + d.get("facing", "") + star             # R or L: which way the points face, when asked for
            switch_numbers.setdefault(shown, []).append((xs, ys, mine))
            points = d["ins"].get("A") or d["outs"].get("A")     # the number sits by the points: that track grows
            switch_strands.setdefault(shown, set()).update(q for q in (points,) if can_grow(band, q))
        elif d["kind"] == "dx":
            (iu_, _), (il_, _) = dx_tracks(nodes, n)
            r1, r2 = sorted((srow[iu_], srow[il_]))
            h = (Y(r2) - Y(r1)) / 2
            svg.append(f'<path d="M{X(x[n]) - h:.1f},{Y(r1):.1f} L{X(x[n]) + h:.1f},{Y(r2):.1f} '
                       f'M{X(x[n]) - h:.1f},{Y(r2):.1f} L{X(x[n]) + h:.1f},{Y(r1):.1f}" stroke-width="{opts["side_w"]}"/>')
            label(X(x[n]), Y(r1) - 6, d["label"], opts["num_px"], weight="bold")
        elif d["kind"] == "end":
            xe, ye = X(x[n]), Y(nrow[n])
            dirx = 1 if d["ins"] else -1
            style = opts.get("helix_style", "box")
            tag = ""
            if d.get("sub") == "helix":         # the same letter for the same track on every level
                tracks = opts.get("helix_tracks") or sorted(
                    {strands[q]["name"] for q in strands for e_ in (strands[q]["src"][0], strands[q]["dst"][0])
                     if nodes[e_].get("sub") == "helix"})
                mine = next(strands[q]["name"] for q in strands if n in (strands[q]["src"][0], strands[q]["dst"][0]))
                if mine not in tracks:          # a helix end added by an `end` edit, after the declared ones
                    tracks = list(tracks) + [mine]
                tag = "H" + str(1 + tracks.index(mine))
            if d.get("sub") == "helix" and style == "box":
                helix.append((xe, ye, d.get("to", ""), dirx))
            elif d.get("sub") == "helix" and style == "coil":       # three turns of a coil on the track, then its letter
                for k in range(3):
                    svg.append(f'<ellipse cx="{xe + (7 + 7 * k) * dirx:.1f}" cy="{ye:.1f}" rx="6" ry="9" stroke-width="1.6"/>')
                P.box((min(xe + dirx, xe + 27 * dirx), ye - 10, max(xe + dirx, xe + 27 * dirx), ye + 10))
                label(xe + 34 * dirx, ye + 3.5, tag, 10, anchor="start" if dirx == 1 else "end", weight="bold")
                label(xe + 50 * dirx, ye + 3, "HELIX TO " + d.get("to", "").upper(), 6.5,
                      anchor="start" if dirx == 1 else "end")
            elif d.get("sub") == "helix" and style == "letters":    # a lettered connector, like the rise
                svg.append(f'<circle cx="{xe + 9 * dirx:.1f}" cy="{ye:.1f}" r="8" stroke-width="1.4" fill="#fff"/>')
                label(xe + 9 * dirx, ye + 3, tag, 8, weight="bold")
                label(xe + 21 * dirx, ye + 3, "HELIX TO " + d.get("to", "").upper(), 6.5,
                      anchor="start" if dirx == 1 else "end")
            elif d.get("sub") == "helix":                           # arrow: plain arrowhead and words
                svg.append(f'<path d="M{xe - 6 * dirx:.1f},{ye - 5:.1f} L{xe:.1f},{ye:.1f} L{xe - 6 * dirx:.1f},{ye + 5:.1f}" stroke-width="1.8"/>')
                label(xe + 6 * dirx, ye + 3, tag + " HELIX TO " + d.get("to", "").upper(), 6.5,
                      anchor="start" if dirx == 1 else "end", weight="bold")
            elif d.get("sub") == "link":
                svg.append(f'<circle cx="{xe + 9 * dirx:.1f}" cy="{ye:.1f}" r="8" stroke-width="1.4" fill="#fff"/>')
                P.box((xe + 9 * dirx - 9, ye - 9, xe + 9 * dirx + 9, ye + 9))
                label(xe + 9 * dirx, ye + 3.5, d["label"], 10, weight="bold")
                cx_, txt = xe + 9 * dirx, "TO " + d["to"].upper()      # under the circle, or above it, or beside it
                P.ask("connector", txt, 6, [(cx_, ye + 19, "middle"), (cx_, ye - 12, "middle"),
                                            (cx_ + 11 * dirx, ye + 19, "start" if dirx == 1 else "end"),
                                            (cx_ - 11 * dirx, ye + 19, "end" if dirx == 1 else "start"),
                                            (cx_, ye + 29, "middle"), (cx_, ye - 21, "middle"),
                                            (cx_ + 11 * dirx, ye - 12, "start" if dirx == 1 else "end"),
                                            (cx_ - 11 * dirx, ye - 12, "end" if dirx == 1 else "start")],
                      emit=lambda xy, t=txt: label(xy[0], xy[1], t, 6, anchor=xy[2]))
            elif d.get("sub") == "open":
                svg.append(f'<path d="M{xe:.1f},{ye:.1f} m{-6 * dirx},-5 l{6 * dirx},5 l{-6 * dirx},5" stroke-width="1.6"/>')
                if d.get("label"):
                    label(xe + 8 * dirx, ye + 3, d["label"].upper(), opts["name_px"],
                          anchor="start" if dirx == 1 else "end", weight="bold")
            else:
                svg.append(f'<path d="M{xe:.1f},{ye - 5:.1f} L{xe:.1f},{ye + 5:.1f}" stroke-width="2.4"/>')
                P.line((xe, ye - 5), (xe, ye + 5), 2.4)
    # the helix box and the station brackets are drawn before the labels are placed, so labels keep clear of them
    if helix:          # one box where this band's helix tracks end
        east = helix[0][3] == 1         # the box sits beyond the end, on the side the track ends toward
        bx = max(h[0] for h in helix) + 6 if east else min(h[0] for h in helix) - 6 - 58
        mid_x = bx + 29
        y1, y2 = min(h[1] for h in helix) - 12, max(h[1] for h in helix) + 12
        for xe, ye, *_ in helix:
            far = bx if east else bx + 58
            svg.append(f'<path d="M{xe:.1f},{ye:.1f} L{far:.1f},{ye:.1f}" stroke-width="{opts["main_w"]}"/>')
            P.line((xe, ye), (far, ye), opts["main_w"])
        svg.append(f'<rect x="{bx:.1f}" y="{y1:.1f}" width="58" height="{y2 - y1:.1f}" rx="5" fill="#fff" stroke-width="1.8"/>')
        P.box((bx - 1, y1 - 1, bx + 59, y2 + 1))
        label(mid_x, (y1 + y2) / 2 + 1, "HELIX", 10, weight="bold", extra='letter-spacing="1.5"')
        label(mid_x, (y1 + y2) / 2 + 11, "TO " + helix[0][2].upper(), 5.5)
    bottom = Y(max(srow.values()))
    totals = capacity.station_totals(band, opts, x, turned)
    lane_h = 40 if totals else 30
    lanes = []
    for name, members in opts.get("stations", {}).items():
        xs = [X(x[n]) for n, d in nodes.items() if d["kind"] == "switch" and d["label"] in members]
        if not xs:
            continue
        a, b = min(xs) - 10, max(xs) + 10
        lane = next((i for i, taken in enumerate(lanes) if all(b < p or a > q for p, q in taken)), len(lanes))
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((a - 30, b + 30))
        yb = bottom + 34 + lane * lane_h
        svg.append(f'<path d="M{a:.1f},{yb - 6} L{a:.1f},{yb} L{b:.1f},{yb} L{b:.1f},{yb - 6}" stroke-width="1.4"/>')
        P.line((a, yb - 6), (a, yb), 1.4)
        P.line((a, yb), (b, yb), 1.4)
        P.line((b, yb), (b, yb - 6), 1.4)
        label((a + b) / 2, yb + 14, name.upper(), 12, weight="bold", extra='letter-spacing="1"')
        if totals.get(name):
            label((a + b) / 2, yb + 25, f"{totals[name]} CARS", 8, extra='letter-spacing="0.5"')
    bottom += 34 + len(lanes) * lane_h if lanes else 0
    if opts.get("signals"):
        draw_signals(band, drawn, opts, X, Y, svg, label, P)
    for num, spots in switch_numbers.items():      # a crossover's two halves share one number, printed once
        cands = []
        if len(spots) == 2:
            (x1, y1, _), (x2, y2, _) = spots
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            cands += [(mx + 6, my + 3, "start"), (mx - 6, my + 3, "end")]
        for _, _, mine in spots:
            cands += mine
        P.ask("switch", num, opts["num_px"], cands, weight="bold", room=sorted(switch_strands.get(num, ())),
              emit=lambda xy, t=num: label(xy[0], xy[1], t, opts["num_px"], anchor=xy[2], weight="bold"))
    for a, xy in P.solve():
        a["emit"](xy)
    band["short"] = set(P.short)
    band["unplaced"] = list(P.unplaced)
    if opts.get("band_gap") is not None:   # measured to the lowest label or mark, not just the lowest track row
        ends = [b[3] for b in P.boxes] + [max(a[1], b[1]) + w / 2 for a, b, w in P.lines]
        if turned:                          # turned end for end: what was highest is now lowest
            ends = [b[3] if i in unturned else 2 * cy - b[1] for i, b in enumerate(P.boxes)]
            ends += [2 * cy - min(a[1], b[1]) + w / 2 for a, b, w in P.lines]
        bottom = max([bottom] + ends)
    if turned:
        svg = [f'<g transform="rotate(180 {cx:.1f} {cy:.1f})">'] + svg + ["</g>"]
    return svg + text, X(max(x.values())) + 110, bottom - top + 14


def _along(pts, dist):
    """The point at a distance along a polyline, and the unit direction of the segment it falls on."""
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        if L and dist <= L:
            t = dist / L
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1)), ((x2 - x1) / L, (y2 - y1) / L)
        dist -= L
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    L = math.hypot(x2 - x1, y2 - y1) or 1
    return (x2, y2), ((x2 - x1) / L, (y2 - y1) / L)


def signal_spot(pts, cm, edge_cm, cell, slide=0.0):
    """Where on a drawn run (screen polyline starting at the switch or end the move is heading for) a mast goes.

    A mast at the switch (cm 0) stands just outside the points, on the first level stretch. A mast out on the
    run goes at its share of the run's real length, moved onto the nearest level stretch. Returns the point and
    the direction of the governed move (back toward the start of the polyline)."""
    segs, d0 = [], 0.0
    if not any(abs(b[1] - a[1]) < 0.01 and b != a for a, b in zip(pts, pts[1:])):
        return None                 # no level stretch on this run: the caller draws the mast along the slope
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L and abs(b[1] - a[1]) < 0.01:
            segs.append((d0, d0 + L))
        d0 += L
    total = d0
    if not segs:
        segs = [(0.0, total)]
    if cm <= 0.5:
        want = segs[0][0] + min((0.7 + slide) * cell, (segs[0][1] - segs[0][0]) * 0.8)
    else:
        want = total * min(max(cm / max(edge_cm, 1), 0.0), 1.0)
        a, b = min(segs, key=lambda sg: 0 if sg[0] <= want <= sg[1] else min(abs(want - sg[0]), abs(want - sg[1])))
        margin = min(0.7 * cell, (b - a) / 2)
        want = min(max(want + slide * cell, a + margin), b - margin)
    p, u = _along(pts, want)
    return p, (-u[0], -u[1])


def draw_sloped_signal(sg, pts, half, heads, r, arm, stem, gap, dash, opts, svg, label, P):
    """A mast on a run that is all slope (a ladder link): the symbol is drawn along the slope, on the right-hand
    side of the move; its name stays level, in line behind the stem (as the Book has it) or beside the symbol.
    The other side of the track is used only when the right-hand side has no room at all."""
    L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    length = arm + 2 * r * heads
    size = opts["num_px"]
    w = labels.text_width(sg["mast"], size, "normal", 0.0)

    def name_cands(t):
        """Where the name may go: in line behind the stem, in line beyond the circles, then level beside."""
        cx, cy, deg, box = t
        c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        reach = (w * abs(c) + 0.72 * size * abs(sn)) / 2       # half the name's extent along the slope
        out = []
        for d in (-(reach + 2.5), length + reach + 2.5, -(reach + 5)):
            for k in (0, 1.5, -1.5, 3, -3, 4.5, -4.5):      # also shifted across the slope, toward the middle of a gap
                mx, my = cx + c * d - sn * k, cy + sn * d + c * k
                out.append((mx, my + 0.36 * size, "middle"))
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        out += [(box[2] + 2, my + 0.36 * size, "start"), (box[0] - 2, my + 0.36 * size, "end"),
                (mx, box[3] + 0.72 * size + 1.5, "middle"), (mx, box[1] - 1.5, "middle")]
        return out

    def fits(t):
        """The symbol's own shape (stem, circles) clear of every line, and room for the name on one side."""
        cx, cy, deg, box = t
        c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        at = lambda a, b: (cx + a * c - b * sn, cy + a * sn + b * c)
        spots = [(at(0, -stem / 2), 0.5), (at(0, stem / 2), 0.5), (at(0, 0), 0.5)]
        spots += [(at(arm + r + 2 * r * h, 0), r) for h in range(heads)]
        for a, b, w in P.lines:
            if any(labels.seg_point(a, b, q) < rad + w / 2 + 0.6 for q, rad in spots):
                return False
        if any(labels.boxes_overlap(box, o, 0.6) for o in P.boxes):
            return False
        return any(P.clear(labels.text_box(x, y, an, sg["mast"], size, "normal"), 0.6)
                   for x, y, an in name_cands(t))

    tries = []
    for hand in (1, -1):                        # right-hand side first; the other side only when it is blocked
        for f in (1 / 3, 1 / 2, 2 / 3):
            (px, py), u = _along(pts, L * f)
            tx, ty = -u[0], -u[1]               # the governed move runs back toward the start of pts
            nx, ny = -ty * hand, tx * hand      # hand 1: right-hand side of that move (screen y points down)
            off = half + gap + r
            cx, cy = px + nx * off, py + ny * off
            deg = math.degrees(math.atan2(ty, tx))
            c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            xy = [(cx + a * c - b * sn, cy + a * sn + b * c) for a, b in ((0, -stem / 2), (0, stem / 2), (length, -r), (length, r))]
            box = (min(p[0] for p in xy), min(p[1] for p in xy), max(p[0] for p in xy), max(p[1] for p in xy))
            tries.append((cx, cy, deg, box))
            if fits(tries[-1]):
                break
        else:
            continue
        break
    cx, cy, deg, box = tries[-1] if fits(tries[-1]) else tries[0]
    parts = [f'<path d="M0,{-stem / 2} L0,{stem / 2} M0,0 L{arm},0" stroke-width="0.9"/>']
    parts += [f'<circle cx="{arm + r + 2 * r * h:.1f}" cy="0" r="{r}" stroke-width="0.9" fill="#fff"{dash}/>'
              for h in range(heads)]
    svg.append(f'<g transform="translate({cx:.1f},{cy:.1f}) rotate({deg:.1f})">' + "".join(parts) + "</g>")
    P.box(box)
    P.ask("mast", sg["mast"], size, name_cands((cx, cy, deg, box)),        # on a slope: no track to lengthen
          emit=lambda q, t=sg["mast"]: label(q[0], q[1], t, size, anchor=q[2]))


def mast_piece(sg, strands):
    """The drawn piece a mast stands on: (strand, cm from the piece's start, piece cm, start node), or None when
    the mast is on a part of its run that this band does not draw. A run that joins two levels is cut into halves
    `x` and `y`, one on each band, and the mast goes on the half its distance falls in. A run that doubles back is
    drawn as two fold halves joined at a turnback; the mast stays on the half its toward end is on."""
    edge, tn, cm = sg["_edge"], sg["_toward_node"], sg["cm_from_toward"]
    pieces = [k for k, st in strands.items() if st["edge"] in (edge, edge + "x", edge + "y")]
    if not pieces:
        return None
    length = {k: strands[k]["cm"] / 2 if k.endswith((".0", ".1")) else strands[k]["cm"] for k in pieces}
    ends = {k: (strands[k]["src"][0], strands[k]["dst"][0]) for k in pieces}
    first = next((k for k in pieces if tn in ends[k]), None)
    if first is None:                       # the toward end is on another band: start at this band's cut end
        first = pieces[0]
        start = next((n for n in ends[first] if n.startswith("LINK:")), ends[first][0])
        cm -= sg["edge_cm"] - sum(length.values())
    else:
        start = tn
    if cm < -0.5:
        return None
    if first.endswith((".0", ".1")):        # fold halves are drawn equal, which the real halves rarely are, so a
        return first, min(max(cm, 0.0), length[first]), length[first], start   # mast keeps to its toward end's half
    if cm > length[first] + 0.5:            # past this band's cut end: drawn on the other band
        return None
    return first, max(cm, 0.0), length[first], start


def draw_signals(band, drawn, opts, X, Y, svg, label, P):
    """Masts in the style of the NYAMR Physical Characteristics Book: a stem across the mast's foot, a short arm,
    one open circle per head pointing the way the mast governs, the name beyond the stem. Each sits on the
    right-hand side of the track for its direction of travel. Virtual masts are not drawn; planned ones are
    dashed."""
    nodes, strands = band["nodes"], band["strands"]
    r, arm, stem, gap = 3.6, 4.0, 8.0, 2.0
    for sg in opts["signals"]:
        if sg["kind"] == "virtual":
            continue
        spot = mast_piece(sg, strands)
        if spot is None:                    # its run, or the part of it the mast stands on, is on another band
            continue
        k, at, piece_cm, start = spot
        sg = dict(sg, cm_from_toward=at, edge_cm=piece_cm)
        pts = [(X(c), Y(rw)) for c, rw in drawn[k]]
        if strands[k]["dst"][0] == start:
            pts = pts[::-1]
        half = (opts["main_w"] if strands[k]["main"] else opts["side_w"]) / 2
        heads = sg.get("heads", 1)
        dash = ' stroke-dasharray="1.6 1.2"' if sg["kind"] == "planned" else ""
        if signal_spot(pts, sg["cm_from_toward"], sg["edge_cm"], opts["cell"]) is None:
            draw_sloped_signal(sg, pts, half, heads, r, arm, stem, gap, dash, opts, svg, label, P)
            continue
        best = None
        for slide in (0.0, 0.5, 1.0, -0.4, 1.5, 2.0):      # slide along the level stretch until the symbol is clear
            cm = sg["cm_from_toward"]
            (px, py), (tx, ty) = signal_spot(pts, cm, sg["edge_cm"], opts["cell"], slide)
            tx = 1.0 if tx >= 0 else -1.0
            side = 1 if tx > 0 else -1             # right-hand side: below for a move to the right, above to the left
            cy = py + side * (half + gap + r)
            xs = (px, px + tx * (arm + 2 * r * heads))
            sym = (min(xs), cy - max(r, stem / 2), max(xs), cy + max(r, stem / 2))
            if P.clear(sym, 0.8):
                best = (px, py, tx, cy, sym)
                break
            best = best or (px, py, tx, cy, sym)
        px, py, tx, cy, sym = best
        P.box(sym)
        svg.append(f'<path d="M{px:.1f},{cy - stem / 2:.1f} L{px:.1f},{cy + stem / 2:.1f} '
                   f'M{px:.1f},{cy:.1f} L{px + tx * arm:.1f},{cy:.1f}" stroke-width="0.9"/>')
        for h in range(sg.get("heads", 1)):
            cx = px + tx * (arm + r + 2 * r * h)
            svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" stroke-width="0.9" fill="#fff"{dash}/>')
        far = px + tx * (arm + 2 * r * heads)
        yb = cy + opts["num_px"] * 0.36
        near_an, far_an = ("end", "start") if tx > 0 else ("start", "end")
        out_y = cy + (1 if cy > py else -1) * (r + 1 + 0.72 * opts["num_px"])     # outside the symbol, away from the track
        cands = [(px - tx * 2.5, yb, near_an), (far + tx * 2, yb, far_an),
                 ((px + far) / 2, out_y + (0.72 * opts["num_px"] if cy > py else 0), "middle")]
        P.ask("mast", sg["mast"], opts["num_px"], cands, room=[k] if can_grow(band, k) else [],
              emit=lambda xy, t=sg["mast"]: label(xy[0], xy[1], t, opts["num_px"], anchor=xy[2]))


MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def title_fields(opts):
    """The title block's own fields, from the options `date` (YYYY-MM-DD), `revision` and `sheet` ("1 of 1"):
    e.g. ["NOV 14, 2026", "REV 1", "SHEET 1 OF 1"]. Each is left out when not set; none set, no column."""
    out = []
    if opts.get("date"):
        try:
            d = datetime.date.fromisoformat(str(opts["date"]))
        except ValueError:
            raise SchematicError(f"preference date must be a real date written YYYY-MM-DD, not {opts['date']!r}") from None
        out.append(f"{MONTHS[d.month - 1]} {d.day}, {d.year}")
    if opts.get("revision") not in (None, ""):
        out.append(f"REV {opts['revision']}")
    if opts.get("sheet"):
        out.append(f"SHEET {str(opts['sheet']).upper()}")
    return out


def page_svg(bands, opts):
    """The finished page as SVG text."""
    pw, ph, m = 1056, 816, 48
    names = {band_key(title) for title, *_ in bands}
    seen = set()
    for o in [opts] + [own[0] for _, _, *own in bands if own]:   # a band named in these settings must exist
        if id(o) in seen:
            continue
        seen.add(id(o))
        for key in BAND_SETTINGS:
            unknown = set(o.get(key) or ()) - names
            if unknown:
                raise SchematicError(f"{key} names {', '.join(sorted(unknown))}, which is not a band "
                                     f"(bands: {', '.join(sorted(names))})")
    own_legends = any(band_key(title) in (own[0] if own else opts).get("band_legend", {})
                      or band_key(title) in (own[0] if own else opts).get("rotate_bands", ())
                      for title, _, *own in bands)        # a turned band needs its own legend too
    top, foot = (56 if own_legends else 96), 100       # clear of the page's direction legend and the title block
    sized = []
    for title, band, *own in bands:           # measure first, so every band can be centred
        o = own[0] if own else opts
        if own_legends:                       # each band says its own direction; no page legend
            o = dict(o, _band_legends=True)
        if opts.get("band_gap") is not None:  # a page setting: every band is measured to its lowest label
            o = dict(o, band_gap=opts["band_gap"])
        _, w, bottom = draw_band(band, title, o, 0, 0)
        sized.append([title, band, o, w - 110, bottom])
    if opts.get("equal_width"):               # stretch the narrower bands along their length to match the widest
        widest = max(w for *_, w, _ in sized)
        for item in sized:
            title, band, o, w, _ = item
            key = band_key(title)
            cell = o.get("band_cell", {}).get(key, o["cell"])
            share = opts.get("band_width", {}).get(key, 1.0)        # owner's hint: this band a little narrower
            factor = min(2.5, widest * share / max(w, 1))
            item[2] = dict(o, band_cell=dict(o.get("band_cell", {}), **{key: cell * factor}))
            _, w2, bottom = draw_band(band, title, item[2], 0, 0)
            item[3], item[4] = w2 - 110, bottom
    gap = opts.get("band_gap", 78)            # band_gap also measures each band to its lowest label (draw_band)
    total_h = sum(h for *_, h in sized) + gap * (len(sized) - 1) + 30
    total_w = max(w for *_, w, _ in sized) + 120
    scale = min(1.0, (pw - 2 * m) / total_w, (ph - top - foot) / total_h)
    body, y = [], 30
    for title, band, o, w, h in sized:
        side = opts.get("band_align", {}).get(band_key(title), "centre")
        room = total_w - 120 - w
        left = 40 + {"left": 0, "right": room}.get(side, room / 2)
        left += opts.get("band_shift", {}).get(band_key(title), 0)      # owner's nudge, in drawing units
        part, _, _ = draw_band(band, title, o, y, left)
        body += part
        y += h + gap
    ox = (pw - total_w * scale) / 2
    oy = top + ((ph - top - foot) - total_h * scale) / 2
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw} {ph}" width="{pw}" height="{ph}" '
           f'font-family="\'Helvetica Neue\',Helvetica,Arial,sans-serif">',
           f'<rect width="{pw}" height="{ph}" fill="#fff"/>',
           f'<rect x="24" y="24" width="{pw - 48}" height="{ph - 48}" fill="none" stroke="#000" stroke-width="1.5"/>',
           f'<g transform="translate({ox:.1f},{oy:.1f}) scale({scale:.4f})" fill="none" '
           f'stroke="#000" stroke-linecap="round" stroke-linejoin="round">'] + body + ["</g>"]
    cx = pw / 2
    if not own_legends:                       # one legend for the page, east to the right (style rule 12)
        svg.append(f'<text x="{cx - 20}" y="62" font-size="15" text-anchor="end" font-weight="bold" letter-spacing="2">'
                   f'&#8592; {escape(opts["left"].upper())}</text>')
        svg.append(f'<text x="{cx + 20}" y="62" font-size="15" text-anchor="start" font-weight="bold" letter-spacing="2">'
                   f'{escape(opts["right"].upper())} &#8594;</text>')
    bx, by = 24, ph - 24 - 64
    fields = title_fields(opts)
    tw = max([330] + [math.ceil(labels.text_width(line.upper(), 14 if i == 0 else 11, "bold" if i == 0 else "normal", 1)) + 20
                      for i, line in enumerate(opts["title"])])      # the box grows for a long title line
    svg.append(f'<rect x="{bx}" y="{by}" width="{tw}" height="64" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    for i, line in enumerate(opts["title"]):
        svg.append(f'<text x="{bx + 10}" y="{by + 20 + i * 18}" font-size="{14 if i == 0 else 11}" '
                   f'font-weight="{"bold" if i == 0 else "normal"}" letter-spacing="1">{escape(line.upper())}</text>')
    if fields:                                # date, revision and sheet in a ruled column at the right of the box
        cx0 = bx + tw
        cw = max([104] + [math.ceil(labels.text_width(t, 9.5, "normal", 1)) + 16 for t in fields])
        svg.append(f'<rect x="{cx0}" y="{by}" width="{cw}" height="64" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        for i, text in enumerate(fields):
            if i:
                svg.append(f'<path d="M{cx0},{by + i * 64 / 3:.1f} L{cx0 + cw},{by + i * 64 / 3:.1f}" stroke="#000" stroke-width="0.8"/>')
            svg.append(f'<text x="{cx0 + 8}" y="{by + 14.5 + i * 64 / 3:.1f}" font-size="9.5" letter-spacing="1">{escape(text)}</text>')
    svg.append("</svg>")
    return "\n".join(svg)





DEFAULTS = dict(cell=28, rowh=28, name_px=8.5, num_px=8, main_w=3.2, side_w=1.4, left="West", right="East",
                title=["Schematic diagram"], stations={}, left_end=None, ends={}, edits=[], levels=None)
