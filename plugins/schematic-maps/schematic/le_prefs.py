"""Layout Editor preferences that change the drawing (layer 3, `<name>.preferences.json`). Only `le` reads them: the
sheet, the detail sheets and the CATS panel are drawn as before.

    bands = le_prefs.drawn_bands(bands, page)    # le.panel, first: a band's le_shift and le_longer_straights
    clear = le_prefs.title_clear(page)           # le.panel: the page's le_title_clear (None: the gap as given)
    xs = le_prefs.extra_steps(P, opts, extras)   # le.panel, after the label layer: le_labels extra_steps/follow
    le_prefs.stretched(scale, page)              # a caller's grid widened by the page's le_stretch factor
    le_prefs.check_stretch(size, fit, chrome, page)  # ... and the panel it gives checked against the window's shape

A band's preferences (keyed by band key, the first word of its title, as `band_width`; each band reads only its own
entry from its own preferences, and a key naming a band the page does not know stops):
  le_shift             {band: [{"from": switch, "to": switch, "columns": n}]}: every node of that band (switch or
                       end; a turnback keeps its own column) at or between the columns of switches `from` and `to`
                       moves n whole grid columns (negative: to the left), so the tracks reaching in from outside
                       grow or shrink by as much and the band keeps its width. `from` must stand at or left of `to`.
                       A track with one end moved keeps its ends in their order and as many columns apart as its
                       climbs need, or the run stops naming it. Entries apply in order.
  le_longer_straights  {band: [{"from": switch, "to": switch, "columns": c}]}: the one track joining switches `from`
                       and `to` has the climb at its `from` end end c columns sooner (c above zero, less than that
                       climb), so its straight at `to` is c columns longer: room for a crossover's angle there.
                       Only the bend moves; both switches stay.
  le_crossover_angle   {band: degrees}: every crossover of that band crosses at this angle, one row deep (le.panel's
                       crossover_run of row / tan(angle) px for it; not with that argument given too). For a panel
                       at a given grid: a panel fitted to a window draws its crossovers as they fall (logged).
Both apply to the Layout Editor drawing only, before anything is drawn, `le_shift` first, once per band
(drawn_bands marks the bands it returns).

The page's preferences:
  le_title_clear       px: the gaps between bands fit the drawing, each next band's title that many px below the
                       lowest thing drawn for the band above (track, labels, icons, masts; and a caller's own items
                       under it, le.panel's `band_bottoms`). Settled by drawing again until the gaps hold (le's
                       TITLE_ROUNDS). For a panel at a given grid: a panel fitted to a window keeps `gap` (logged).
  le_stretch           {"factor": f, "tolerance": t}: for a caller that fits a panel to a window and draws it at
                       that grid widened by f (stretched), so a larger panel keeps the window's shape when zoomed to
                       fit; check_stretch stops when the panel drawn is more than t (a share) off that shape, naming
                       the factor that would give it.

A band's `le_labels` (its own, not the page's; le_labels checks the keys):
  extra_steps          [[id, id, id, ...], ...]: caller's items (le.panel's `extras`) that step along one slope: each
                       after the second stands at the first's x plus its place times the first two's step (x only;
                       the label layer finds its y). The first group's step per px of y is the band's slope.
  extra_follow         [[leader, follower], ...]: the follower stands at the leader's x plus the band's slope times
                       how far below the leader it stands (needs an extra_steps group).
An item the caller gives an `x` keeps it (a panel drawn again at another's places). The panel is drawn once more
with the stepped items at their x; P.extra_x holds them ({id: x}). With no extras given there is nothing to step.
"""
import math

from .core import SchematicError
from .draw import band_key

BAND_PREFS = ("le_shift", "le_longer_straights")
ENTRY_KEYS = {"from", "to", "columns"}


def _number(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def known_bands(bands, page):
    """The band keys the page knows: the bands drawn and every band its `band_order` lists (so `--band` may draw
    part of a page whose preferences name all its bands)."""
    drawn = [band_key(t) for t, _b, _o in bands]
    order = (page or {}).get("band_order") or []
    return drawn + [k for k in order if isinstance(k, str) and k not in drawn]


SHAPES = {"le_shift": "[{from, to, columns}, ...]", "le_longer_straights": "[{from, to, columns}, ...]",
          "le_crossover_angle": "degrees"}


def band_entries(bands, page, pref):
    """{band index: value} of the band preference `pref` (SHAPES), checked: an object of band key to its value (a
    list of {from, to, columns} entries, or an angle), each band key one the page knows, and the value for a drawn
    band set in that band's own preferences (another input's preferences naming it would be read by no band)."""
    known = known_bands(bands, page)
    drawn = {band_key(t): (bi, o or {}) for bi, (t, _b, o) in enumerate(bands)}
    out = {}
    for title, _b, opts in bands:
        given = (opts or {}).get(pref)
        if given is None:
            continue
        if not isinstance(given, dict):
            raise SchematicError(f"{title}: {pref} must be an object of band: {SHAPES[pref]}, not {given!r}")
        for key, value in given.items():
            if key not in known:
                raise SchematicError(f"{title}: {pref} names {key}, which is no band (bands: {', '.join(known)})")
            own = drawn[key][1].get(pref) if key in drawn else None
            if key in drawn and (not isinstance(own, dict) or own.get(key) != value):
                raise SchematicError(f"{title}: {pref} for {key} is in another band's preferences; set it in "
                                     f"{key}'s own")
            if pref == "le_crossover_angle":
                if not _number(value) or not 0 < value < 90:
                    raise SchematicError(f"{title}: le_crossover_angle for {key} must be degrees above 0 and below "
                                         f"90, not {value!r}")
            else:
                if not isinstance(value, list):
                    raise SchematicError(f"{title}: {pref} for {key} must be a list of {{from, to, columns}}, not "
                                         f"{value!r}")
                for e in value:
                    _check_entry(pref, key, e)
            if key in drawn:
                out[drawn[key][0]] = value
    return out


def crossover_runs(bands, page, row):
    """{band key: px across} a crossover's diagonal runs at its band's le_crossover_angle, one row (`row` px) deep;
    {} when no band has one."""
    angles = band_entries(bands, page, "le_crossover_angle")
    return {band_key(bands[bi][0]): row / math.tan(math.radians(a)) for bi, a in sorted(angles.items())}


def _check_entry(pref, key, e):
    where = f"{pref} for {key}"
    if not isinstance(e, dict) or set(e) != ENTRY_KEYS:
        raise SchematicError(f"{where}: each entry must be {{from, to, columns}} and nothing else, not {e!r}")
    for k in ("from", "to"):
        if not isinstance(e[k], str) or not e[k].strip():
            raise SchematicError(f"{where}: {k} must be a switch number (text), not {e[k]!r}")
    if e["from"] == e["to"]:
        raise SchematicError(f"{where}: from and to are both switch {e['from']}")
    c = e["columns"]
    if pref == "le_shift" and (isinstance(c, bool) or not isinstance(c, int) or c == 0):
        raise SchematicError(f"{where}: columns must be a whole number of grid columns other than 0 (negative: to "
                             f"the left), not {c!r}")
    if pref == "le_longer_straights" and (not _number(c) or c <= 0):
        raise SchematicError(f"{where}: columns must be a number of grid columns above zero, not {c!r}")


DRAWN = "le_drawn"      # set on a band drawn_bands returns: its preferences are applied, never twice


def drawn_bands(bands, page):
    """`bands` as the Layout Editor draws them: each band's le_shift, then its le_longer_straights, applied to a copy
    marked DRAWN (the bands given are not changed). A band already marked is checked but left as it is, so a caller
    may take the bands as drawn first (to name what the drawing shows, say, before it relabels switches) and pass
    them on to le.panel, which calls this too."""
    shifts = band_entries(bands, page, "le_shift")
    longer = band_entries(bands, page, "le_longer_straights")
    out = []
    for bi, (title, band, opts) in enumerate(bands):
        if not band.get(DRAWN) and (shifts.get(bi) or longer.get(bi)):
            for e in shifts.get(bi, ()):
                band = shifted(title, band, e)
            for e in longer.get(bi, ()):
                band = lengthened(title, band, e)
            band = dict(band, **{DRAWN: True})
        out.append((title, band, opts))
    return out


def is_turnback(band, n):
    """A turnback node (its own column at the band's end)."""
    return band["nodes"].get(n, {}).get("kind", "").startswith("turn")


def switch_column(title, band, label, pref):
    """The grid column switch `label` stands at on the band; stops when no switch has that label, or its switches
    (a crossover's two halves) stand on different columns."""
    cols = {band["x"][n] for n, d in band["nodes"].items()
            if d["kind"] == "switch" and d.get("label") == label and n in band["x"]}
    if not cols:
        raise SchematicError(f"{title}: {pref}: no switch {label} is drawn on the band")
    if len(cols) > 1:
        raise SchematicError(f"{title}: {pref}: switch {label} stands on columns {sorted(cols)}; name a switch drawn "
                             "on one column")
    return cols.pop()


def shifted(title, band, e):
    """A copy of `band` with one le_shift entry applied (module text); stops on switches not drawn left to right, or a
    track the shift leaves overlapped, reversed or shorter than its climbs need."""
    lo, hi = (switch_column(title, band, e[k], "le_shift") for k in ("from", "to"))
    if lo > hi:
        raise SchematicError(f"{title}: le_shift: switches {e['from']} and {e['to']} are not drawn left to right")
    n_cols = e["columns"]
    x = {n: c + n_cols if lo <= c <= hi and not is_turnback(band, n) else c for n, c in band["x"].items()}
    # a track with one end moved and one not keeps its ends in their order, as many columns apart as its climbs
    # need (band "need"), so nothing outside the shift is overlapped or passed
    bad = []
    for sid, st in band["strands"].items():
        u, v = st["src"][0], st["dst"][0]
        if u not in x or v not in x or (x[u] == band["x"][u]) == (x[v] == band["x"][v]):
            continue
        old, new = band["x"][v] - band["x"][u], x[v] - x[u]
        need = sum(band["need"].get(sid, (0, 0))[:2])
        if old * new <= 0 or abs(new) < need:
            bad.append(f"{st.get('name') or sid} ({old:g} -> {new:g} columns, needs {need:g})")
    if bad:
        raise SchematicError(f"{title}: le_shift of {n_cols} columns from switch {e['from']} to {e['to']} leaves "
                             "tracks overlapped or reversed: " + ", ".join(bad))
    return dict(band, x=x)


def lengthened(title, band, e):
    """A copy of `band` with one le_longer_straights entry applied (module text); stops on a track not found (or more
    than one), or one with no climb at its `from` end longer than `columns`."""
    label = {n: d.get("label") for n, d in band["nodes"].items()}
    found = [(sid, s) for sid, s in band["strands"].items()
             if {label[s["src"][0]], label[s["dst"][0]]} == {e["from"], e["to"]}]
    if len(found) != 1:
        raise SchematicError(f"{title}: le_longer_straights: {len(found)} tracks join switches {e['from']} and "
                             f"{e['to']}, not one")
    sid, st = found[0]
    su, sv, *rest = band["need"][sid]
    at_src = label[st["src"][0]] == e["from"]
    climb = su if at_src else sv
    if climb <= e["columns"]:
        raise SchematicError(f"{title}: le_longer_straights: track {st.get('name') or sid} climbs {climb:g} columns "
                             f"at switch {e['from']}, not more than {e['columns']:g}")
    need = (su - e["columns"], sv, *rest) if at_src else (su, sv - e["columns"], *rest)
    return dict(band, need=dict(band["need"], **{sid: need}))


# ---------------------------------------------------------------- the page's

def title_clear(page):
    """The page's le_title_clear in px (None when not set), checked."""
    v = (page or {}).get("le_title_clear")
    if v is not None and (not _number(v) or v < 0):
        raise SchematicError(f"le_title_clear must be a number of px, 0 or more, not {v!r}")
    return v


def check_bottoms(bands, bottoms):
    """le.panel's `band_bottoms` ({band key: px}, the lowest y of the caller's own items under a band), checked."""
    if bottoms is None:
        return {}
    if not isinstance(bottoms, dict):
        raise SchematicError(f"band_bottoms must be an object of band: px, not {bottoms!r}")
    keys = [band_key(t) for t, _b, _o in bands]
    for k, v in bottoms.items():
        if k not in keys:
            raise SchematicError(f"band_bottoms names {k}, which is no band drawn (bands: {', '.join(keys)})")
        if not _number(v):
            raise SchematicError(f"band_bottoms for {k} must be a number of px, not {v!r}")
    return dict(bottoms)


def stretch(page):
    """(factor, tolerance) of the page's le_stretch, checked; stops when the page has none."""
    v = (page or {}).get("le_stretch")
    if v is None:
        raise SchematicError("the page's preferences hold no le_stretch ({\"factor\": f, \"tolerance\": t})")
    if not isinstance(v, dict) or set(v) != {"factor", "tolerance"}:
        raise SchematicError(f"le_stretch must be {{\"factor\": f, \"tolerance\": t}} and nothing else, not {v!r}")
    f, t = v["factor"], v["tolerance"]
    if not _number(f) or f <= 0:
        raise SchematicError(f"le_stretch: factor must be a number above zero, not {f!r}")
    if not _number(t) or not 0 < t < 1:
        raise SchematicError(f"le_stretch: tolerance must be a share between 0 and 1, not {t!r}")
    return f, t


def check_page(page):
    """The page's Layout Editor preferences checked up front (le_stretch only when given)."""
    title_clear(page)
    if (page or {}).get("le_stretch") is not None:
        stretch(page)


def stretched(scale, page):
    """The grid `scale` (across, down) widened by the page's le_stretch factor: (across * factor, down)."""
    factor, _t = stretch(page)
    return (scale[0] * factor, scale[1])


def check_stretch(size, fit, chrome, page):
    """Stop unless a panel `size` (width, height) has the shape of the `fit` window's panel area (fit less `chrome`,
    Layout Editor's frame) within le_stretch's tolerance, naming the factor that would give it (the panel's width
    grows about in step with it)."""
    factor, tolerance = stretch(page)
    if not (len(fit) == 2 and all(_number(v) for v in fit) and fit[0] > chrome[0] and fit[1] > chrome[1]):
        raise SchematicError(f"a {fit!r} window leaves no room for a panel inside its frame")
    if not (len(size) == 2 and all(_number(v) and v > 0 for v in size)):
        raise SchematicError(f"the panel's size must be two numbers of px above zero, not {size!r}")
    want = (fit[0] - chrome[0]) / (fit[1] - chrome[1])
    got = size[0] / size[1]
    if abs(got / want - 1) > tolerance:
        raise SchematicError(f"the panel is {size[0]}x{size[1]} px, {got:.3f} wide to 1 high; the {fit[0]}x{fit[1]} "
                             f"window's panel area is {want:.3f}: set le_stretch's factor to about "
                             f"{factor * want / got:.3f} (now {factor})")


# ---------------------------------------------------------------- caller's items stepped (a band's le_labels)

def extra_steps(P, opts, extras):
    """{extra id: x} for the caller's items that step (module text), from the boxes the label layer placed (P.extras)
    and each band's le_labels options `opts` (le_labels.options); {} with no extras. Stops on an id that is not one
    of the extras placed on that band, or a group whose first two stand on one row (no slope)."""
    if not extras:
        return {}
    given = {e["id"]: e for e in extras}
    placed = {e["id"]: e for e in P.extras}
    out = {}
    for bi, o in enumerate(opts):
        groups, follow = o.get("extra_steps", []), o.get("extra_follow", [])
        if not groups and not follow:
            continue

        def box(i, bi=bi):
            if i not in given:
                raise SchematicError(f"le_labels extra_steps/extra_follow: {i} is not one of the caller's extras")
            if i not in placed or placed[i]["band"] != bi:
                raise SchematicError(f"le_labels extra_steps/extra_follow: extra {i} is not placed on the band whose "
                                     "le_labels name it")
            return placed[i]["box"]

        slope = None
        for group in groups:
            (x0, y0, *_), (x1, y1, *_) = box(group[0]), box(group[1])
            step = x1 - x0
            for k, g in enumerate(group[2:], 2):
                box(g)
                if "x" not in given[g]:
                    out[g] = round(x0 + k * step)
            if slope is None:
                if y1 == y0:
                    raise SchematicError(f"le_labels extra_steps: {group[0]} and {group[1]} stand on one row, so "
                                         "they give no slope")
                slope = step / (y1 - y0)
        for lead, follower in follow:
            (lx, ly, *_), (_fx, fy, *_) = box(lead), box(follower)
            if slope is None:
                raise SchematicError("le_labels extra_follow: an item follows another, but no extra_steps group gives "
                                     "the slope")
            if "x" not in given[follower]:
                out[follower] = round(lx + slope * (fy - ly))
    return out


def with_x(extras, xs):
    """`extras` (a list) with each item in `xs` given that x."""
    return [dict(e, x=xs[e["id"]]) if e["id"] in xs else e for e in extras or []]
