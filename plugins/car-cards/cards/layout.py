"""Builder 3c. The card and the sheet, drawn with python-docx from measurements (no third-party
template). Ported from the source pipeline's generate_card_template.py, generate_all_cards.py and
card_description.py.

Measurements are in twips (1/20 pt, 1440 to the inch) unless a name says otherwise.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .config import Config
from .paths import Paths

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
ICON_ROAD_NAME = ICON_DIR / "railroad.png"  # tracks in a circle
ICON_ROAD_NUM = ICON_DIR / "number.png"     # # in a circle
ICON_DESC = ICON_DIR / "pencil.png"         # pencil in a circle


@dataclass
class Card:
    kind: str              # car | loco
    type_label: str        # the boxed title, e.g. "BOX CAR", "LOCOMOTIVE"
    road_name: str         # cfg.display_road(marks)
    road_number: str
    description: str
    image: Path | None


@dataclass(frozen=True)
class SheetSpec:
    """Inches. A preset from PRESETS, with any cfg.sheet keys of the same names over it."""
    page_w: float
    page_h: float
    margin_top: float
    margin_bottom: float
    margin_left: float
    margin_right: float
    slot_w: float
    slot_h: float
    columns: int
    rows: int


def _in(twips: int) -> float:
    return twips / 1440


# The poker-size sticker sheet: nine slots of 3686 x 5098 twips on US Letter, margins as measured
# from the vendor's 3 x 3 page, which prints closer to the sticker edge.
POKER_SLOT_W = 3686
POKER_SLOT_H = 5098
PRESETS: dict[str, SheetSpec] = {
    "poker-3x3": SheetSpec(page_w=8.5, page_h=11.0, margin_top=_in(202), margin_bottom=_in(101),
                           margin_left=_in(418), margin_right=_in(360), slot_w=_in(POKER_SLOT_W),
                           slot_h=_in(POKER_SLOT_H), columns=3, rows=3),
}


def sheet_spec(cfg: Config) -> SheetSpec:
    """The preset named in cfg.sheet['preset'] with the other cfg.sheet keys (inches) laid over it."""
    over = dict(cfg.sheet)
    name = over.pop("preset", "poker-3x3")
    if name not in PRESETS:
        raise SystemExit(f"cards.toml: unknown sheet preset {name!r}; known: {', '.join(sorted(PRESETS))}")
    fields = {f.name: f.type for f in dataclasses.fields(SheetSpec)}
    for key, value in over.items():
        if key not in fields:
            raise SystemExit(f"cards.toml: unknown sheet setting {key!r}; known: {', '.join(fields)}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SystemExit(f"cards.toml: sheet.{key} must be a number")
        needs_positive = key.startswith(("page", "slot")) or key in ("columns", "rows")
        if value < 0 or (needs_positive and value <= 0):
            raise SystemExit(f"cards.toml: sheet.{key} is out of range")
        if key in ("columns", "rows"):
            over[key] = int(value)
    return dataclasses.replace(PRESETS[name], **over)


# ---- descriptions

def _type_title(name: str, cfg: Config) -> str:
    """The car type as printed: aliases applied, and a run-together '...car' split ('Boxcar' -> 'Box Car')."""
    t = cfg.car_type(name)
    if t.lower().endswith("car") and " " not in t and len(t) > 3:
        return f"{t[:-3]} Car"
    return t


def describe(row: dict, cfg: Config) -> str:
    """'<color> · <type label> · <length>'' from a cars.csv row; row['description'] wins when set;
    '—' when nothing is known. Type labels come from cfg.car_type and cfg.descriptions."""
    override = (row.get("description") or "").strip()
    if override:
        return override
    ctype = _type_title(row.get("car_type") or "", cfg)
    label = ctype
    car_class = (row.get("car_class") or "").strip().upper()
    text = f"{row.get('description') or ''} {row.get('notes') or ''}".lower()
    for rule in cfg.descriptions:
        if rule.type.strip().lower() != ctype.lower() and _type_title(rule.type, cfg).lower() != ctype.lower():
            continue
        if (car_class and car_class in (c.strip().upper() for c in rule.classes)) or \
                any(w and w in text for w in rule.words):
            label = rule.label
            break
    color = (row.get("color") or "").strip()
    length = (row.get("length_ft") or "").strip()
    parts = [p for p in (color, label, f"{length}'" if length else "") if p]
    return " · ".join(parts) if parts else "—"


def card_image(row: dict, paths: Paths) -> Path | None:
    """The picture for a fleet row: images/print/<stem>.png only when it is newer than
    images/final/<stem>.png, else the final picture, else None."""
    final = paths.resolve((row.get("image") or "").strip())
    if final is None or not final.is_file():
        return None
    print_copy = paths.print_copies / final.name
    if print_copy.is_file() and print_copy.stat().st_mtime > final.stat().st_mtime:
        return print_copy
    return final


def card_for_car(row: dict, paths: Paths, cfg: Config) -> Card:
    marks = (row.get("reporting_marks") or "").strip()
    return Card(kind="car", type_label=_type_title(row.get("car_type") or "", cfg).upper(),
                road_name=cfg.display_road(marks) if marks else "?",
                road_number=(row.get("road_number") or "").strip() or "?",
                description=describe(row, cfg), image=card_image(row, paths))


def card_for_loco(row: dict, paths: Paths, cfg: Config) -> Card:
    """Description: the row's own text, else '<builder> · <model> · <length>''."""
    marks = (row.get("reporting_marks") or "").strip()
    length = (row.get("length_ft") or "").strip()
    parts = [(row.get("builder") or "").strip(), (row.get("model") or "").strip(),
             f"{length}'" if length else ""]
    text = (row.get("description") or "").strip() or " · ".join(p for p in parts if p) or "—"
    return Card(kind="loco", type_label="LOCOMOTIVE",
                road_name=cfg.display_road(marks) if marks else "?",
                road_number=(row.get("road_number") or "").strip() or "?",
                description=text, image=card_image(row, paths))


# ---- card measurements
FONT = "Arial"
DIVIDER_CLR = "BFBFBF"
LABEL_CLR = RGBColor(0, 0, 0)
VALUE_CLR = RGBColor(70, 70, 70)
INNER_BORDER = 8          # 1pt (sz is in 1/8 pt)

H_HEADER = 860
H_IMAGE = 2004            # at the poker slot height; extra slot height goes here
H_DATA_SECTION = 1450
DATA_TABLE_TOP_PAD = 140
IMG_OUTER_PAD_TOP = 50
IMG_OUTER_PAD_BOTTOM = 80
IMG_INNER_PAD = 20
H_FOOTER = 110
H_FOOTER_LINE_TWIPS = 110

# The art is laid out on a block 285 twips narrower than its slot (142 left, 143 right); on the
# poker slot that block is 3401 wide, which is what the margins below were measured on.
BLOCK_GAP = 285
CENTER_OFFSET = 142
CONTENT_MARGIN = 110
FRAME_MARGIN = 140
CARD_TOP_PAD = 166 + 180  # frame origin below slot top: 166 + 1/8 in
SIDE_PAD = 160
FRAME_STROKE_PT = 2.25
FRAME_GROW_TWIPS = 45
FRAME_GROW_PT = 72.0 / 32
FRAME_ARCSIZE = 0.07
FRAME_BASE_H_PT = 3.16 * 72.0
LOGO_W_IN = 0.56
PICTURE_W_IN = 1.84
ICON_W_IN = 0.15


# ---- low-level OOXML helpers

def _tc_pr(cell):
    return cell._tc.get_or_add_tcPr()


def width(cell, twips: int) -> None:
    tc_pr = _tc_pr(cell)
    el = tc_pr.find(qn("w:tcW"))
    if el is None:
        el = OxmlElement("w:tcW")
        tc_pr.append(el)
    el.set(qn("w:w"), str(twips))
    el.set(qn("w:type"), "dxa")


def pad(cell, top=0, left=0, bottom=0, right=0) -> None:
    tc_pr = _tc_pr(cell)
    el = tc_pr.find(qn("w:tcMar"))
    if el is not None:
        tc_pr.remove(el)
    el = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        s = OxmlElement(f"w:{side}")
        s.set(qn("w:w"), str(val))
        s.set(qn("w:type"), "dxa")
        el.append(s)
    tc_pr.append(el)


def row_h(row, twips: int) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    el = tr_pr.find(qn("w:trHeight"))
    if el is None:
        el = OxmlElement("w:trHeight")
        tr_pr.append(el)
    el.set(qn("w:val"), str(twips))
    el.set(qn("w:hRule"), "exact")


def grid(table, widths: list[int]) -> None:
    tbl = table._tbl
    old = tbl.find(qn("w:tblGrid"))
    if old is not None:
        tbl.remove(old)
    g = OxmlElement("w:tblGrid")
    for w in widths:
        c = OxmlElement("w:gridCol")
        c.set(qn("w:w"), str(w))
        g.append(c)
    tbl.insert(0, g)


def tbl_width_dxa(table, twips: int, *, center=True) -> None:
    pr = table._tbl.tblPr
    el = pr.find(qn("w:tblW"))
    if el is None:
        el = OxmlElement("w:tblW")
        pr.append(el)
    el.set(qn("w:w"), str(twips))
    el.set(qn("w:type"), "dxa")
    lay = pr.find(qn("w:tblLayout"))
    if lay is None:
        lay = OxmlElement("w:tblLayout")
        pr.append(lay)
    lay.set(qn("w:type"), "fixed")
    if center:
        jc = pr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pr.append(jc)
        jc.set(qn("w:val"), "center")


def add_round_frame(paragraph, idx, *, width_pt, height_pt, left_pt, top_pt) -> None:
    """Anchor a rounded-rectangle outline behind the card content (VML). The shape id and the
    spid carry the card's number in full, so a long run of cards never repeats one."""
    z = -251650000 - idx
    style = (
        "position:absolute;"
        f"margin-left:{left_pt:.2f}pt;margin-top:{top_pt:.2f}pt;"
        f"width:{width_pt:.2f}pt;height:{height_pt:.2f}pt;"
        f"z-index:{z};"
        "mso-position-horizontal-relative:text;"
        "mso-position-vertical-relative:text"
    )
    xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word">'
        '<w:rPr><w:noProof/></w:rPr>'
        '<w:pict>'
        f'<v:roundrect id="cardframe{idx}" o:spid="_x0000_s{1025 + idx}" '
        f'style="{style}" arcsize="{FRAME_ARCSIZE}" '
        'filled="f" stroked="t" strokecolor="#1F1F1F" '
        f'strokeweight="{FRAME_STROKE_PT}pt" '
        'xmlns:o="urn:schemas-microsoft-com:office:office">'
        '<v:stroke joinstyle="round"/>'
        '<w10:wrap type="none"/>'
        '</v:roundrect>'
        '</w:pict>'
        '</w:r>'
    )
    paragraph._p.append(parse_xml(xml))


def borders(table, *, outer=18, inner_h=0, inner_v=0, color="000000") -> None:
    """Set table borders. Sizes in 1/8-point units; 0 means none."""
    pr = table._tbl.tblPr
    old = pr.find(qn("w:tblBorders"))
    if old is not None:
        pr.remove(old)
    b = OxmlElement("w:tblBorders")
    specs = {"top": outer, "left": outer, "bottom": outer, "right": outer,
             "insideH": inner_h, "insideV": inner_v}
    for edge, sz in specs.items():
        el = OxmlElement(f"w:{edge}")
        if sz:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:color"), color)
            el.set(qn("w:space"), "0")
        else:
            el.set(qn("w:val"), "nil")
        b.append(el)
    pr.append(b)


def hrule(cell, size=6, color="808080") -> None:
    """Top and bottom borders only; left and right defer to the table."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("left", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    for edge in ("top", "bottom"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        b.append(el)
    tc_pr.append(b)


def cell_borders(cell, size: int = 0, color: str = "000000") -> None:
    """All four cell borders: thin lines of the given size, or none for size 0."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        if size:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:color"), color)
            el.set(qn("w:space"), "0")
        else:
            el.set(qn("w:val"), "nil")
        b.append(el)
    tc_pr.append(b)


def para(p, *, align=None, before=0, after=0):
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.0
    if align is not None:
        p.alignment = align


def text(run, s, *, bold=False, size=8, color=None):
    run.text = s
    run.bold = bold
    run.font.name = FONT
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color if isinstance(color, RGBColor) else RGBColor(*color)


def _line_spacing(parent, line_twips: int):
    """An exact-height spacing element (no space before or after) on a paragraph's pPr."""
    old = parent.find(qn("w:spacing"))
    if old is not None:
        parent.remove(old)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), str(line_twips))
    spacing.set(qn("w:lineRule"), "exact")
    parent.append(spacing)


def _tiny_paragraph() -> OxmlElement:
    """A one-point paragraph: Word needs a paragraph after a table, and this one costs no room."""
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    _line_spacing(pPr, 20)
    rPr = OxmlElement("w:rPr")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "2")
    rPr.append(sz)
    pPr.append(rPr)
    p.append(pPr)
    return p


def tighten_cell(cell) -> None:
    """Drop the empty paragraphs python-docx leaves around a nested table, keeping one tiny
    trailing paragraph (a cell must end in a paragraph). Otherwise they push content down
    and exact-height rows clip it."""
    tc = cell._tc
    if not tc.findall(qn("w:tbl")):
        return
    for child in list(tc):
        if child.tag == qn("w:p") and not child.findall(qn("w:r")):
            tc.remove(child)
    if len(tc) and list(tc)[-1].tag == qn("w:tbl"):
        tc.append(_tiny_paragraph())


def minimize_cell_tail(cell) -> None:
    """Shrink the paragraph python-docx leaves after the card table to a 1pt line, or nine
    filled cards overflow onto a second page."""
    tc = cell._tc
    children = list(tc)
    if not children or children[-1].tag != qn("w:p") or children[-1].findall(qn("w:r")):
        return
    tc.remove(children[-1])
    tc.append(_tiny_paragraph())


def tighten_revision_cell(cell, line_twips: int = H_FOOTER_LINE_TWIPS) -> None:
    """Strip all slack from the footer cell so the footer line cannot overlap."""
    pad(cell, top=0, left=0, bottom=0, right=0)
    tc = cell._tc
    paragraphs = tc.findall(qn("w:p"))
    for extra in paragraphs[1:]:
        if not extra.findall(qn("w:r")):
            tc.remove(extra)
    if paragraphs:
        _line_spacing(cell.paragraphs[0]._p.get_or_add_pPr(), line_twips)


# ---- the card

def build_card(cell, card: Card, idx: int, spec: SheetSpec, cfg: Config) -> None:
    """Draw one card into a sheet slot. Width scales with the slot (the art sits on a block 285
    twips narrower than the slot); extra slot height goes to the picture row and the frame. All
    else is fixed, as measured on the poker slot."""
    slot_w = round(spec.slot_w * 1440)
    extra_h = round(spec.slot_h * 1440) - POKER_SLOT_H
    block_w = slot_w - BLOCK_GAP
    card_w = block_w - 2 * CONTENT_MARGIN
    frame_w = block_w - 2 * FRAME_MARGIN

    cell.text = ""
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=BLOCK_GAP - CENTER_OFFSET)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    # The leading paragraph holds the frame shape; keep it tiny so it does not push the card down.
    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    add_round_frame(
        lead, idx,
        width_pt=(frame_w + 2 * FRAME_GROW_TWIPS) / 20.0,
        height_pt=FRAME_BASE_H_PT + FRAME_GROW_PT + extra_h / 20.0,
        left_pt=(FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0,
        top_pt=1.0)

    # One column, four stacked sections, no border: the rounded frame is the card outline.
    t = cell.add_table(rows=4, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, card_w, center=True)
    grid(t, [card_w])
    borders(t, outer=0)

    # Section 0: logo left, boxed type title right.
    row_h(t.rows[0], H_HEADER)
    c_head = t.rows[0].cells[0]
    width(c_head, card_w)
    pad(c_head, top=20, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    content_w = card_w - 2 * SIDE_PAD
    logo_w = 900
    title_w = content_w - logo_w
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, content_w, center=False)
    grid(head, [logo_w, title_w])
    borders(head, outer=0)
    h_logo, h_title = head.rows[0].cells
    width(h_logo, logo_w)
    width(h_title, title_w)
    for c in (h_logo, h_title):
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Zero right margin so the 0.56" image is not clipped; a small left margin keeps it off the frame.
    pad(h_logo, left=40, right=0, top=0, bottom=0)
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    if cfg.logo is not None and Path(cfg.logo).is_file():
        p.add_run().add_picture(str(cfg.logo), width=Inches(LOGO_W_IN))

    # The type: centred capitals between a top and bottom rule that hug the text.
    pad(h_title, left=150, right=0, top=0, bottom=0)
    inner_title = title_w - 150
    type_box = h_title.add_table(rows=1, cols=1)
    tbl_width_dxa(type_box, inner_title, center=False)
    grid(type_box, [inner_title])
    borders(type_box, outer=0)
    tc = type_box.rows[0].cells[0]
    width(tc, inner_title)
    pad(tc, top=36, bottom=36)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    text(p.add_run(), card.type_label.upper(), bold=True, size=12)
    tighten_cell(h_title)
    tighten_cell(c_head)

    # Section 1: the picture, in its own inset box.
    row_h(t.rows[1], max(H_IMAGE + extra_h, 1700))
    c_img = t.rows[1].cells[0]
    width(c_img, card_w)
    pad(c_img, top=IMG_OUTER_PAD_TOP, left=SIDE_PAD, bottom=IMG_OUTER_PAD_BOTTOM, right=SIDE_PAD)
    c_img.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    img_w = card_w - 2 * SIDE_PAD
    img = c_img.add_table(rows=1, cols=1)
    tbl_width_dxa(img, img_w, center=True)
    grid(img, [img_w])
    borders(img, outer=INNER_BORDER, color=DIVIDER_CLR)
    ic = img.rows[0].cells[0]
    width(ic, img_w)
    ic.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(ic, top=IMG_INNER_PAD, bottom=IMG_INNER_PAD, left=40, right=40)
    p = ic.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if card.image is not None and Path(card.image).is_file():
        p.add_run().add_picture(str(card.image), width=Inches(PICTURE_W_IN))
    else:
        text(p.add_run(), "NO PHOTO", size=7, color=(140, 140, 140))
    tighten_cell(c_img)

    # Section 2: road name, road number and description, each with an icon.
    row_h(t.rows[2], H_DATA_SECTION)
    c_data = t.rows[2].cells[0]
    width(c_data, card_w)
    pad(c_data, top=DATA_TABLE_TOP_PAD, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_data.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    icon_w, label_w = 340, 1040
    value_w = content_w - icon_w - label_w
    data = c_data.add_table(rows=3, cols=3)
    tbl_width_dxa(data, content_w, center=True)
    grid(data, [icon_w, label_w, value_w])
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    fields = [("ROAD NAME:", card.road_name, ICON_ROAD_NAME, False),
              ("ROAD NUMBER:", card.road_number, ICON_ROAD_NUM, False),
              ("DESCRIPTION:", card.description, ICON_DESC, True)]
    for ri, (label, value, icon_path, is_desc) in enumerate(fields):
        c_icon, c_lbl, c_val = data.rows[ri].cells
        width(c_icon, icon_w)
        pad(c_icon, top=16, left=30, bottom=10, right=30)
        c_icon.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        width(c_lbl, label_w)
        pad(c_lbl, top=30, left=30, bottom=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        width(c_val, value_w)
        pad(c_val, top=30, left=30, bottom=30, right=30)
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p = c_icon.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=1.5)
        p.add_run().add_picture(str(icon_path), width=Inches(ICON_W_IN))

        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), label, bold=False, size=6, color=LABEL_CLR)

        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        size = (5.5 if len(value) > 18 else 6.5) if is_desc else 9
        text(p.add_run(), value, bold=True, size=size, color=VALUE_CLR)
    tighten_cell(c_data)

    # Section 3: the footer line.
    row_h(t.rows[3], H_FOOTER)
    c_ftr = t.rows[3].cells[0]
    width(c_ftr, card_w)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), cfg.form, size=5.5, color=(80, 80, 80))
    tighten_revision_cell(c_ftr)

    minimize_cell_tail(cell)  # keep all nine cards on one page


# ---- the sheet

def _new_document(spec: SheetSpec) -> Document:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    section = doc.sections[0]
    section.page_width = Inches(spec.page_w)
    section.page_height = Inches(spec.page_h)
    # The margins go in as whole twips so the saved file reads back the numbers in the spec.
    for name, inches in (("top_margin", spec.margin_top), ("bottom_margin", spec.margin_bottom),
                         ("left_margin", spec.margin_left), ("right_margin", spec.margin_right)):
        setattr(section, name, Inches(round(inches * 1440) / 1440))
    section.header_distance = 0
    section.footer_distance = 0
    return doc


def _slot_grid(doc: Document, spec: SheetSpec):
    """A table of columns x rows slots with exact row heights, centred, borderless."""
    slot_w, slot_h = round(spec.slot_w * 1440), round(spec.slot_h * 1440)
    table = doc.add_table(rows=spec.rows, cols=spec.columns)
    tbl_width_dxa(table, slot_w * spec.columns, center=True)
    grid(table, [slot_w] * spec.columns)
    borders(table, outer=0)
    look = table._tbl.tblPr.find(qn("w:tblLook"))
    if look is not None:
        table._tbl.tblPr.remove(look)
    for row in table.rows:
        row_h(row, slot_h)
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.insert(0, cant)
        for cell in row.cells:
            width(cell, slot_w)
            cell_borders(cell, 0)
    return table


def _break_before(table) -> None:
    """Start the table on a new page (set after the cards are drawn: drawing resets the cell)."""
    p = table.rows[0].cells[0].paragraphs[0]._p
    p.get_or_add_pPr().insert(0, OxmlElement("w:pageBreakBefore"))


def _separator(doc: Document) -> None:
    """A one-point paragraph so Word keeps two sheets as two tables."""
    sect = doc.element.body.find(qn("w:sectPr"))
    sect.addprevious(_tiny_paragraph())


def build_sheet(cards: list[Card], out: Path, cfg: Config) -> Path:
    """Cards in order, nine (columns x rows) to a page, written to out (.docx)."""
    spec = sheet_spec(cfg)
    per_page = spec.columns * spec.rows
    doc = _new_document(spec)
    pages = [cards[i:i + per_page] for i in range(0, len(cards), per_page)] or [[]]
    for page_no, batch in enumerate(pages):
        if page_no:
            _separator(doc)
        table = _slot_grid(doc, spec)
        for i, card in enumerate(batch):
            r, c = divmod(i, spec.columns)
            build_card(table.rows[r].cells[c], card, page_no * per_page + i, spec, cfg)
        if page_no:
            _break_before(table)
    _separator(doc)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def calibration_page(out: Path, cfg: Config) -> Path:
    """One page of slot outlines and measurements on plain paper, to hold against the stock."""
    spec = sheet_spec(cfg)
    doc = _new_document(spec)
    table = _slot_grid(doc, spec)
    mid = (spec.rows // 2, spec.columns // 2)
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            cell_borders(cell, 4, "000000")
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            lines = [f"Slot row {r + 1}, column {c + 1}", f"{spec.slot_w:.3f} x {spec.slot_h:.3f} in"]
            if (r, c) == mid:
                lines += [f"Page {spec.page_w:g} x {spec.page_h:g} in",
                          f"Margins: top {spec.margin_top:.3f}, bottom {spec.margin_bottom:.3f},",
                          f"left {spec.margin_left:.3f}, right {spec.margin_right:.3f} in"]
            first = True
            for line in lines:
                p = cell.paragraphs[0] if first else cell.add_paragraph()
                first = False
                para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
                text(p.add_run(), line, size=7, color=(0, 0, 0))
    _separator(doc)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out
