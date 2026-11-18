"""CATS panel preferences (layer 3, `<name>.preferences.json`): the page's choices for a CATS panel. Only a caller
building a CATS panel reads them (the command's `cats`, or a script through cats.options); the sheet, the detail
sheets and the Layout Editor panel are drawn as before.

    o = cats.options(page, bands)      # {"scale", "helix_blocks", "band_gap", "title_gap", "window", "fit"}
    P = cats.panel(bands, scale=o["scale"], helix_blocks=o["helix_blocks"], band_gap=o["band_gap"],
                   title_gap=o["title_gap"], max_cols=o["fit"] and o["fit"][0])
    cats.check_fit(P, *o["fit"]); cats.to_xml(P, "CTC", header, o["window"])

The page's preferences (the page is the last input's preferences; a band's own file holding one of these with
another value stops, as no panel would read it):
  cats_cells_per_unit  1 or an even number: cats.panel's `scale`, CATS cells per schematic grid unit; SCALE when
                       not set. 1 fits a smaller screen (names placed on the track); 2 leaves a free row for names.
  cats_helix_blocks    "one" or "apart": cats.panel's `helix_blocks`, a helix track drawn on two bands is one block or
                       a block on each band (parted at the join); "one" when not set.
  cats_band_gap        whole rows, 0 or more: cats.panel's `band_gap`, the empty rows between a band's lowest cell
                       and the next band's title; COMPACT_GAP - 1 (compact) or BAND_GAP - 1 when not set.
  cats_title_gap       whole rows, 0 or more: cats.panel's `title_gap`, the empty rows between a band's title and
                       its top track; 1 when not set. Fewer rows than the defaults only on a compact panel
                       (cats_cells_per_unit 1), whose labels are placed around them and their clashes logged.
  cats_window          [width, height] whole px: the window CATS opens the panel in, written to the panel (to_xml's
                       `window`). CATS has no zoom and draws GRID_PX cells, so it also sets the cells the panel must
                       show at most (`fit`): (width - CHROME[0]) // GRID_PX columns by (height - CHROME[1]) //
                       GRID_PX rows. Not set: CATS's own window and no fit.
CHROME is the px of the window CATS keeps for itself: the frame and the scrollbar across, the title bar, the menu
bar and the train status line down (CATS 3.2 on Windows).
"""
from .core import SchematicError
from .cats_px import GRID_PX

__all__ = ["SCALE", "HELIX_BLOCKS", "CHROME", "PAGE_PREFS", "check_scale", "check_helix_blocks", "check_rows",
           "options"]

SCALE = 2
HELIX_BLOCKS = ("one", "apart")
CHROME = (20, 100)
PAGE_PREFS = ("cats_cells_per_unit", "cats_helix_blocks", "cats_band_gap", "cats_title_gap", "cats_window")


def check_scale(scale, what="the CATS scale"):
    """`scale` if it is 1 or an even whole number of cells per grid unit; an error naming `what` otherwise."""
    if not isinstance(scale, int) or isinstance(scale, bool) or not (scale == 1 or (scale >= 2 and scale % 2 == 0)):
        raise SchematicError(f"{what} is 1 or an even number of cells per grid unit, not {scale!r}")
    return scale


def check_helix_blocks(value, what="helix_blocks"):
    """`value` if it is one of HELIX_BLOCKS; an error naming `what` otherwise."""
    if value not in HELIX_BLOCKS:
        raise SchematicError(f"{what} is one of {', '.join(HELIX_BLOCKS)}, not {value!r}")
    return value


def check_rows(value, what):
    """`value` if it is a whole number of rows, 0 or more; an error naming `what` otherwise."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SchematicError(f"{what} is a whole number of rows, 0 or more, not {value!r}")
    return value


def _window(v):
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in v)
            and v[0] > CHROME[0] + GRID_PX and v[1] > CHROME[1] + GRID_PX):
        raise SchematicError(f"cats_window must be [width, height] in whole px, more than CATS's frame "
                             f"({CHROME[0]} x {CHROME[1]} px) and one {GRID_PX} px cell each way, not {v!r}")
    return tuple(v)


def options(page, bands=()):
    """{"scale", "helix_blocks", "band_gap", "title_gap", "window", "fit"} from the page's preferences, checked:
    the gaps are None when not set (cats.panel's defaults), window and fit when
    cats_window is not set. A `cats_` key the page does not know stops (a misspelt preference would be read by no
    one), and so does one a band's own preferences hold with a value the page does not (bands: [(title, band,
    options)]). A preference set to null is not set."""
    page = page or {}
    for where, opts in [("the page's preferences", page)] + [(title, o or {}) for title, _b, o in bands]:
        unknown = sorted(k for k in opts if k.startswith("cats_") and k not in PAGE_PREFS)
        if unknown:
            raise SchematicError(f"{where}: {', '.join(unknown)}, which no CATS panel reads "
                                 f"(CATS preferences: {', '.join(PAGE_PREFS)})")
    for title, _b, opts in bands:
        for k in sorted(k for k in (opts or {}) if k.startswith("cats_")):
            if opts[k] != page.get(k):
                raise SchematicError(f"{title}: {k} is a page preference; set it in the page's preferences (the "
                                     "last input's), where a CATS panel reads it")
    given = lambda k, default: default if page.get(k) is None else page[k]     # null: not set
    scale = check_scale(given("cats_cells_per_unit", SCALE), "cats_cells_per_unit")
    helix = check_helix_blocks(given("cats_helix_blocks", "one"), "cats_helix_blocks")
    gaps = {k: given(f"cats_{k}", None) for k in ("band_gap", "title_gap")}     # None: cats.panel's default
    for k, v in gaps.items():
        if v is not None:
            check_rows(v, f"cats_{k}")
    window = fit = None
    if page.get("cats_window") is not None:
        window = _window(page["cats_window"])
        fit = ((window[0] - CHROME[0]) // GRID_PX, (window[1] - CHROME[1]) // GRID_PX)
    return {"scale": scale, "helix_blocks": helix, **gaps, "window": window, "fit": fit}
