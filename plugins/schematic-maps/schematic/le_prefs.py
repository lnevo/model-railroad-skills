"""Layout Editor preferences that change the drawing (layer 3, `<name>.preferences.json`). Only `le` reads them: the
sheet, the detail sheets and the CATS panel are drawn as before.

    bands = le_prefs.drawn_bands(bands, page)    # le.panel, first: a band's le_shift and le_longer_straights
    clear = le_prefs.title_clear(page)           # le.panel: the page's le_title_clear (None: the gap as given)
    xs = le_prefs.extra_steps(P, opts, extras)   # le.panel, after the label layer: le_labels extra_steps/follow
    le_prefs.stretched(scale, page)              # (a caller's grid widened by le_stretch's factor, the factor)
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
  le_tight_crossovers  {band: [[switch, switch], ...]}: le.panel's `tight_crossovers` for that band (two single
                       crossovers sharing a track drawn as close on it as their shapes allow; needs a crossover run,
                       le_crossover_angle).
  le_split_crossovers  {band: [switch, ...]}: le.panel's `split_crossovers` for that band (single crossovers drawn as
                       two plain turnouts on their one turnout name).
  le_crossover_pairs   {band: [[switch, switch], ...]}: le.panel's `crossover_pairs` for that band (two plain
                       turnouts of different numbers joined by one track, one crossover on the ground: that
                       track crosses at the band's le_crossover_angle, the east one and everything east of it
                       slid along the rows to give it).
  le_mast_room         {band: true or false}: le.panel's `mast_room` takes that band (its tracks let out for mast
                       icons that have no room).
  le_name_room         {band: true or false}: le.panel's `name_room` takes that band (its named tracks let out to
                       their names' width, the band no wider than the widest).
  le_band_labels       {band: {le_labels key: value}}: that band's label options (le_labels.options), over the
                       page's le_labels and beside the band's own flat le_labels (a key in both stops). For a file
                       that sets the page and several bands at once, where a flat le_labels reaches all of them.
`le_shift` and `le_longer_straights` apply to the Layout Editor drawing only, before anything is drawn, `le_shift`
first, once per band (drawn_bands marks the bands it returns). The last five are for a panel at a given grid, as
le_crossover_angle (grid_options): a panel fitted to a window draws without them (logged), and giving le.panel the
argument too stops.

The page's preferences:
  le_title_clear       px: the gaps between bands fit the drawing, each next band's title that many px below the
                       lowest thing drawn for the band above (track, labels, icons, masts; and a caller's own items
                       under it, le.panel's `band_bottoms`: px below that band's box, so it moves with the band). Settled by drawing again until the gaps hold (le's
                       TITLE_ROUNDS). For a panel at a given grid: a panel fitted to a window keeps `gap` (logged).
  le_stretch           {"factor": f, "tolerance": t}: for a caller that fits a panel to a window and draws it at
                       that grid widened by f (stretched), so a larger panel keeps the window's shape when zoomed to
                       fit; check_stretch stops when the panel drawn is more than t (a share) off that shape, naming
                       the factor that would give it.
  le_window            [width, height] whole px: the window the caller's panel opens in at 100% zoom, frame
                       included (window(page): for le.panel's `fit`, le.check_stretch and the caller's own use). No
                       default: the run stops when a caller asks for it and the page has none.
  le_row               px above zero: the rows a caller draws its panel at (row(page): for le.panel's `row`, which
                       the caller may scale with its grid); le.ROW when not set.

A band's `le_labels` (its own or its le_band_labels entry, not the page's; le_labels checks the keys):
  extra_steps          [[id, id, id, ...], ...]: caller's items (le.panel's `extras`) that step along one slope: each
                       after the second stands at the first's x plus its place times the first two's step (x only;
                       the label layer finds its y). The first group's step per px of y is the band's slope.
  extra_follow         [[leader, follower], ...]: the follower stands at the leader's x plus the band's slope times
                       how far below the leader it stands (needs an extra_steps group).
An item the caller gives an `x` keeps it (a panel drawn again at another's places). The panel is drawn once more
with the stepped items at their x; P.extra_x holds them ({id: x}), and the run stops if that drawing moved what they
step from (check_steps). A follower's leader may not itself be stepped or follow (le_labels checks). With no extras
given there is nothing to step (logged).
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
          "le_crossover_angle": "degrees", "le_tight_crossovers": "[[switch, switch], ...]",
          "le_split_crossovers": "[switch, ...]", "le_crossover_pairs": "[[switch, switch], ...]",
          "le_mast_room": "true or false", "le_name_room": "true or false", "le_band_labels": "{le_labels key: value}"}
# the band preferences that are le.panel arguments for a panel at a given grid (grid_options): preference: argument
GRID_PREFS = {"le_tight_crossovers": "tight_crossovers", "le_split_crossovers": "split_crossovers",
              "le_crossover_pairs": "crossover_pairs", "le_mast_room": "mast_room", "le_name_room": "name_room"}


def band_entries(bands, page, pref):
    """{band index: value} of the band preference `pref` (SHAPES), checked: an object of band key to its value (a
    list of {from, to, columns} entries, an angle, a GRID_PREFS value: _check_grid, or for le_band_labels an
    le_labels object: le_labels._check), each band key one the page
    knows, and the value for a drawn
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
            elif pref in GRID_PREFS:
                _check_grid(title, pref, key, value)
            elif pref == "le_band_labels":
                from .le_labels import _check as check_labels       # le_labels imports this module first
                check_labels(f"{title}: le_band_labels for {key}", value)
            else:
                if not isinstance(value, list):
                    raise SchematicError(f"{title}: {pref} for {key} must be a list of {{from, to, columns}}, not "
                                         f"{value!r}")
                for e in value:
                    _check_entry(pref, key, e)
            if key in drawn:
                out[drawn[key][0]] = value
    return out


def check_page_band_prefs(bands, page):
    """A page that holds a band preference (SHAPES: le_shift, le_longer_straights, le_crossover_angle and the
    GRID_PREFS) that no band drawn holds as its own would be ignored (band preferences are read from each band's own
    options): stop, naming it. The page is often the last input's own options, so a value one of the bands drawn also holds, or one for a band not
    drawn now, is fine."""
    drawn = {band_key(t): (o or {}) for t, _b, o in bands}
    for pref in SHAPES:
        given = (page or {}).get(pref)
        if given is None:
            continue
        if not isinstance(given, dict):
            raise SchematicError(f"page: {pref} must be an object of band: {SHAPES[pref]}, not {given!r}")
        for key, value in given.items():
            own = drawn.get(key, {}).get(pref)
            if key in drawn and (not isinstance(own, dict) or own.get(key) != value):
                raise SchematicError(f"page: {pref} for {key} is not in that band's own preferences, so it would not "
                                     f"be read; set it in {key}'s preferences")


def _switch(v):
    return isinstance(v, str) and bool(v.strip())


def _check_grid(title, pref, key, value):
    """One band's value of a GRID_PREFS preference, its shape checked (the switches are checked against the band
    when le.panel draws it: check_tight, check_split, check_pairs)."""
    where = f"{title}: {pref} for {key}"
    if pref in ("le_mast_room", "le_name_room"):
        if not isinstance(value, bool):
            raise SchematicError(f"{where} must be true or false, not {value!r}")
    elif pref == "le_split_crossovers":
        if not isinstance(value, list) or not all(_switch(x) for x in value):
            raise SchematicError(f"{where} must be a list of switch numbers (text), not {value!r}")
        if len(set(value)) != len(value):
            raise SchematicError(f"{where} names a switch twice: {value!r}")
    else:
        if not isinstance(value, list) or not all(isinstance(p, list) and len(p) == 2 and all(_switch(x) for x in p)
                                                  and p[0] != p[1] for p in value):
            raise SchematicError(f"{where} must be a list of [switch, switch] pairs of two different switch numbers "
                                 f"(text), not {value!r}")


def grid_options(bands, page):
    """({le.panel argument: value}, [argument, ...]) of the band preferences that are le.panel arguments for a panel
    at a given grid (GRID_PREFS): the values, for the bands drawn that set them, in the bands' order (tight_crossovers,
    split_crossovers and crossover_pairs as {band key: value}, mast_room and name_room as the band keys whose value is true; an
    argument that would ask for nothing is left out), and every argument some drawn band's preferences set, false
    included (a caller's argument beside it stops: le.panel)."""
    out, held = {}, []
    for pref, arg in GRID_PREFS.items():
        entries = band_entries(bands, page, pref)
        if not entries:
            continue
        held.append(arg)
        if pref in ("le_mast_room", "le_name_room"):
            keys = [band_key(bands[bi][0]) for bi, on in sorted(entries.items()) if on]
            if keys:
                out[arg] = keys
        else:
            out[arg] = {band_key(bands[bi][0]): value for bi, value in sorted(entries.items())}
    return out, held


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
            if d.get("kind") == "switch" and d.get("label") == label and n in band["x"]}
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
    moved = {n for n, c in band["x"].items() if lo <= c <= hi and not is_turnback(band, n)}
    # a diagonal (drawn node to node) with one end moved would change its slope: a crossover's two halves, or a
    # ladder's step, part
    torn = sorted(band["strands"][sid].get("name") or sid for sid in band.get("R", {}).get("diag", ())
                  if sid in band["strands"] and
                  (band["strands"][sid]["src"][0] in moved) != (band["strands"][sid]["dst"][0] in moved))
    if torn:
        raise SchematicError(f"{title}: le_shift from switch {e['from']} to {e['to']} moves one end of the diagonal "
                             f"track(s) {', '.join(torn)} and not the other; widen or narrow the range")
    from .le import let_out, let_out_fault       # le imports this module first
    shifts = {n: float(n_cols) for n in moved}
    why = let_out_fault(band, shifts)
    if why:
        raise SchematicError(f"{title}: le_shift of {n_cols} columns from switch {e['from']} to {e['to']}: {why}")
    return let_out(band, shifts)


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
    if not isinstance(band.get("need", {}).get(sid), (list, tuple)) or len(band["need"][sid]) < 2:
        raise SchematicError(f"{title}: le_longer_straights: track {st.get('name') or sid} has no climbs in the solved "
                             "band (its \"need\"), so there is no bend to move")
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
    """le.panel's `band_bottoms` ({band key: px}, how far below the band's box, P.band_boxes, the caller's own items
    under it reach; negative: above its bottom), checked."""
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


def window(page):
    """(width, height) of the page's le_window, checked; stops when the page has none."""
    v = (page or {}).get("le_window")
    if v is None:
        raise SchematicError("the page's preferences hold no le_window ([width, height] in px)")
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) and n > 0
                                                         for n in v)):
        raise SchematicError(f"le_window must be [width, height] in whole px above zero, not {v!r}")
    return tuple(v)


def row(page, default):
    """The page's le_row in px, checked; `default` (le.ROW) when not set."""
    v = (page or {}).get("le_row")
    if v is None:
        return default
    if not _number(v) or v <= 0:
        raise SchematicError(f"le_row must be a number of px above zero, not {v!r}")
    return v


def check_page(page, bands=()):
    """The page's Layout Editor preferences checked up front (le_stretch and le_window only when given), and no
    band preference in it that no band reads (check_page_band_prefs)."""
    title_clear(page)
    row(page, None)
    check_page_band_prefs(bands, page)
    if (page or {}).get("le_stretch") is not None:
        stretch(page)
    if (page or {}).get("le_window") is not None:
        window(page)


def stretched(scale, page):
    """((across * factor, down), factor): the grid `scale` (across, down) widened by the page's le_stretch factor, and
    the factor, so a caller reports what it used without reading the preference again."""
    factor, _t = stretch(page)
    return (scale[0] * factor, scale[1]), factor


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

def step_targets(P, opts, extras):
    """{extra id: x} every stepped item's x as the boxes P.extras placed give it (module text), whether or not the
    caller gave it one. Stops on an id that is not one of the extras placed on that band, or a group whose first two
    stand on one row (no slope)."""
    given = {e["id"] for e in extras}
    placed = {e["id"]: e for e in P.extras}
    out = {}
    for bi, o in enumerate(opts):
        groups, follow = o.get("extra_steps", []), o.get("extra_follow", [])

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
            out[follower] = round(lx + slope * (fy - ly))
    return out


def extra_steps(P, opts, extras):
    """{extra id: x} for the caller's items that step and were given no x (step_targets); {} with no extras (logged
    for each band whose le_labels ask for steps)."""
    if not extras:
        for bi, o in enumerate(opts):
            if o.get("extra_steps") or o.get("extra_follow"):
                P.log.append(f"le_labels extra_steps/extra_follow of band {bi + 1}: the panel has no caller's items, "
                             "so nothing is stepped")
        return {}
    given = {e["id"]: e for e in extras}
    return {i: x for i, x in step_targets(P, opts, extras).items() if "x" not in given[i]}


def check_steps(P, opts, extras, xs):
    """After the panel is drawn again with the stepped items at their x (`xs`): stop unless every one stands where
    the boxes now placed give it (step_targets), since an item that leads (the first two of a group, a follower's
    leader) or a follower's row may move in the second drawing."""
    if not xs:
        return
    now = step_targets(P, opts, extras)
    bad = sorted(f"{i} at {xs[i]}, its leaders now give {now.get(i)}" for i in xs if now.get(i) != xs[i])
    if bad:
        raise SchematicError("le_labels extra_steps/extra_follow: drawn again with the stepped items at their x, "
                             "the items they step from moved: " + "; ".join(bad))


def with_x(extras, xs):
    """`extras` (a list) with each item in `xs` given that x."""
    return [dict(e, x=xs[e["id"]]) if e["id"] in xs else e for e in extras or []]
