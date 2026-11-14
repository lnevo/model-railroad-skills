"""Page folding (style rule 24): a band too long for the page is cut into rows stacked down the page.

Folding is a generation rule (layer 2) switched on by a preference: `fold: true`, or `fold_min_scale: 0.6` (which
also sets the smallest scale a sheet may be drawn at before bands are folded; `fold: true` alone uses DEFAULT_MIN).
With neither, nothing here runs and the page is drawn exactly as before.

The band is drawn whole, once; each row is a window onto that drawing (a clip), so nothing inside it is redrawn
differently. This module chooses where the windows meet and draws the arrows that join them.

Where a band is cut (`cuts`), in order of what matters:
  - never through a sloped line (a ladder, a crossover half, a loop's bend), a double crossover or a label or symbol;
  - not under a station bracket, if any other place will do;
  - where as few tracks as possible run on past the cut;
  - so that the rows come out about equally full.
"""
import math

DEFAULT_MIN = 0.65          # a sheet smaller than this is folded
ARROW = 34                  # room each side of a cut for the "continued" arrows
ROW_LEFT = 110              # where the drawing of a folded row starts, clear of an arrow and a helix box on the left
RIGHT_EXTRA = 80            # beyond the last switch: end marks, helix box
STEP = 2.0                  # candidate cuts are tried every this many drawing units
BAD, BRACKET, PER_TRACK = 100000.0, 500.0, 5.0


def setting(opts):
    """The smallest allowed scale, or None when folding is off."""
    if opts.get("fold_min_scale") is not None:
        return float(opts["fold_min_scale"])
    return DEFAULT_MIN if opts.get("fold") else None


def tracks_crossing(fold, u):
    """{y: widest line width} of the track lines that run across the vertical at u."""
    lo, hi = fold["track_y"]
    out = {}
    for a, b, w in fold["lines"]:
        if a[1] != b[1] or not lo - 1 <= a[1] <= hi + 1:
            continue
        if min(a[0], b[0]) < u < max(a[0], b[0]):
            y = round(a[1], 1)
            out[y] = max(out.get(y, 0), w)
    return out


def cost(fold, u):
    """How bad a cut at u is: BAD per thing it would cut through, then a little for each track it crosses."""
    c = 0.0
    lo, hi = fold["track_y"]
    for a, b, w in fold["lines"]:
        if min(a[0], b[0]) - 1 < u < max(a[0], b[0]) + 1:
            horizontal = a[1] == b[1]
            on_tracks = lo - 1 <= min(a[1], b[1]) and max(a[1], b[1]) <= hi + 1
            if not horizontal and on_tracks:
                c += BAD                        # a slope, or a vertical stub, on the tracks
            elif horizontal and not on_tracks:
                c += BRACKET                    # a station bracket
    for x0, y0, x1, y1 in fold["boxes"]:
        if x0 - 2 < u < x1 + 2:
            c += BAD
    for x0, x1 in fold["zones"]:
        if x0 < u < x1:
            c += BAD
    return c + PER_TRACK * len(tracks_crossing(fold, u))


def cuts(fold, width, cap):
    """Where to cut a band `width` units long into rows of at most `cap`: ([cut positions], clean). `clean` is
    False when some cut had to go through something."""
    out, start, clean = [], 0.0, True
    while width - start > cap:
        even = (width - start) / math.ceil((width - start) / cap)       # rows come out about equally full
        lo, hi = start + 0.8 * even, min(start + cap, start + 1.2 * even)
        best, u = None, hi
        while u >= lo:
            c = cost(fold, u) + abs(u - start - even) * 0.01      # a clean cut beats an even one; then the evener
            if best is None or c < best[0]:
                best = (c, u)
            u -= STEP
        clean &= best[0] < BAD
        out.append(best[1])
        start = best[1]
    return out, clean


def rows_of(width, cut_list):
    """[(start, end)] of each row of a band; the first starts and the last ends at the band's own edge (None)."""
    edges = [None] + list(cut_list) + [None]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def row_extent(width, seg):
    """How far right a row reaches from the left of the page's drawing area, in drawing units."""
    s, e = seg
    s = 0.0 if s is None else s
    last = e is None
    e = width if last else e
    return ROW_LEFT + (e - s) + (RIGHT_EXTRA if last else ARROW)


def plan(sized, opts, scale_of):
    """Choose how many rows to fold the long bands into. `sized` is [[title, band, o, width, height], ...].
    Returns (entries, notes) or None when folding does not help. entries are (index, seg, number, rows) in page
    order; seg is None for a band left whole."""
    floor = setting(opts)
    widths = [it[3] for it in sized]
    gap = opts.get("band_gap", 78)

    def evaluate(entries):
        total_w = max(sized[i][3] + 120 if seg is None else row_extent(sized[i][3], seg) + 10 for i, seg, _, _ in entries)
        total_h = sum(sized[i][4] for i, *_ in entries) + gap * (len(entries) - 1) + 30
        return scale_of(total_w, total_h)

    whole = [(i, None, 0, 1) for i in range(len(sized))]
    base = evaluate(whole)
    if base >= floor:
        return None
    best, widest = (base, None, None), max(widths)
    for k in range(2, 9):
        cap = widest / k + 10
        entries, notes = [], []
        for i, (title, band, o, w, h) in enumerate(sized):
            fold = band.get("fold")
            turned = title.split()[0] in o.get("rotate_bands", ()) if title.split() else False
            if w <= cap or fold is None or turned:
                entries.append((i, None, 0, 1))
                continue
            cut_list, clean = cuts(fold, w, cap)
            segs = rows_of(w, cut_list)
            entries += [(i, seg, n, len(segs)) for n, seg in enumerate(segs)]
            notes.append((title, cut_list, clean))
        s = evaluate(entries)
        if s > best[0] * 1.05 and (best[1] is None or s > best[0]):
            best = (s, entries, notes)
    if best[1] is None:
        return None
    return best[1], best[2], base, best[0]


def arrows(svg, fold, opts, y, seg, number, rows, start_x):
    """The arrows that join a row to its neighbours, as SVG added to `svg`. `y` is the band's top and `start_x` where
    the row's first column sits on the page."""
    s, e = seg
    for edge, there in ((s, number > 0), (e, number < rows - 1)):
        if edge is None or not there:
            continue
        for ly, wd in sorted(tracks_crossing(fold, edge).items()):
            main = wd >= opts["main_w"]
            yy = y + ly
            if edge is e:           # leaving to the right
                x0 = start_x + (e - (s or 0.0)) + 3
                head = x0 + ARROW - 8
                end = x0 + ARROW - 6
            else:                   # arriving from the left
                x0 = start_x - ARROW + 3
                head = start_x - 8
                end = start_x - 6
            if main:
                svg.append(f'<path d="M{x0:.1f},{yy:.1f} L{end:.1f},{yy:.1f}" stroke-width="{opts["main_w"]}"/>')
                svg.append(f'<path d="M{head - 2:.1f},{yy - 9:.1f} L{head + 12:.1f},{yy:.1f} L{head - 2:.1f},{yy + 9:.1f} Z" '
                           f'fill="#000" stroke-width="1"/>')
                word = "CONTINUES" if edge is e else "CONTINUED"
                svg.append(f'<text x="{(x0 + head + 12) / 2:.1f}" y="{yy - 13:.1f}" font-size="6" text-anchor="middle" '
                           f'font-weight="bold" fill="#000" stroke="none" letter-spacing="0.4">{word}</text>')
            else:
                svg.append(f'<path d="M{x0:.1f},{yy:.1f} L{end:.1f},{yy:.1f} M{head - 1:.1f},{yy - 4:.1f} '
                           f'L{head + 6:.1f},{yy:.1f} L{head - 1:.1f},{yy + 4:.1f}" stroke-width="{opts["side_w"]}"/>')
