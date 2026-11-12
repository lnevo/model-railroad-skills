import dataclasses
import os
import time
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches
from PIL import Image

from helpers import CardFolder, PHOTOS
from cards import config, layout
from cards.layout import Card

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FLATCAR = PHOTOS / "flatcar.jpg"


def twips(el, tag="w"):
    return int(el.get(qn(f"w:{tag}")))


class Sheet(CardFolder):
    """The golden test: the saved .docx holds the measurements of the poker sheet."""

    def make(self, logo: bool):
        cfg = self.cfg
        if logo:
            Image.new("RGB", (60, 60), (30, 60, 120)).save(self.tmp / "logo.png")
            cfg = config.load_with_logo(self.tmp) if hasattr(config, "load_with_logo") else cfg
            cfg = dataclasses.replace(cfg, logo=self.tmp / "logo.png")
        cards = [Card("car", "BOX CAR", "NW", str(1000 + i), "Black · Box Car · 50'", FLATCAR) for i in range(10)]
        out = layout.build_sheet(cards, self.tmp / "output" / "sheet.docx", cfg)
        return cfg, Document(out), out

    def check(self, logo: bool):
        cfg, doc, out = self.make(logo)
        sect = doc.sections[0]
        self.assertEqual((sect.page_width, sect.page_height), (Inches(8.5), Inches(11)))
        mar = doc.element.body.find(qn("w:sectPr")).find(qn("w:pgMar"))
        self.assertEqual([twips(mar, k) for k in ("top", "bottom", "left", "right")], [202, 101, 418, 360])
        body = doc.element.body
        tables = body.findall(qn("w:tbl"))
        self.assertEqual(len(tables), 2)
        for tbl in tables:
            self.assertEqual([twips(c) for c in tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))], [3686] * 3)
            self.assertEqual(tbl.find(qn("w:tblPr")).find(qn("w:jc")).get(qn("w:val")), "center")
            rows = tbl.findall(qn("w:tr"))
            self.assertEqual(len(rows), 3)
            for tr in rows:
                h = tr.find(qn("w:trPr")).find(qn("w:trHeight"))
                self.assertEqual((twips(h, "val"), h.get(qn("w:hRule"))), (5098, "exact"))
                self.assertEqual(len(tr.findall(qn("w:tc"))), 3)
            # no grid lines on the slots
            for edge in tbl.find(qn("w:tblPr")).find(qn("w:tblBorders")):
                self.assertEqual(edge.get(qn("w:val")), "nil")
        self.assertIn("pageBreakBefore", etree_str(tables[1].find(qn("w:tr"))))

        def cards_in(tbl):
            return sum(1 for tc in tbl.iter(qn("w:tc")) if tc.find(qn("w:tcPr")) is not None
                       and "cardframe" in etree_str(tc) and tc.getparent().getparent() is tbl)
        self.assertEqual([cards_in(t) for t in tables], [9, 1])

        xml = etree_str(body)
        # pictures: card photo 1.84 in; icons 0.15 in; logo 0.56 in when there is one
        widths = [int(e.get("cx")) for e in body.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")]
        self.assertEqual(widths.count(Inches(1.84)), 10)
        self.assertEqual(widths.count(Inches(0.15)), 30)
        self.assertEqual(widths.count(Inches(0.56)), 10 if logo else 0)
        # fonts and sizes
        runs = {}
        for r in body.iter(qn("w:r")):
            t = "".join(x.text or "" for x in r.findall(qn("w:t")))
            if not t:
                continue
            rpr = r.find(qn("w:rPr"))
            runs.setdefault(t, set()).add((rpr.find(qn("w:rFonts")).get(qn("w:ascii")),
                                           twips(rpr.find(qn("w:sz")), "val"),
                                           rpr.find(qn("w:b")) is not None and rpr.find(qn("w:b")).get(qn("w:val")) != "0",
                                           rpr.find(qn("w:color")).get(qn("w:val")) if rpr.find(qn("w:color")) is not None else None))
        self.assertEqual(runs["BOX CAR"], {("Arial", 24, True, None)})
        self.assertEqual(runs["ROAD NAME:"], {("Arial", 12, False, "000000")})
        self.assertEqual(runs["NW"], {("Arial", 18, True, "464646")})
        self.assertEqual(runs["1003"], {("Arial", 18, True, "464646")})
        self.assertEqual(runs["Black · Box Car · 50'"], {("Arial", 11, True, "464646")})  # over 18 chars: 5.5 pt
        self.assertEqual(runs[cfg.form], {("Arial", 11, False, "505050")})
        # frame ids unique
        ids = [e.get("id") for e in doc.element.body.iter("{urn:schemas-microsoft-com:vml}roundrect")]
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(set(ids)), 10)
        self.assertIn("cardframe9", ids)
        self.assertIn(cfg.form, xml)

    def test_without_logo(self):
        self.check(False)

    def test_with_logo(self):
        self.check(True)

    def test_logo_cell_is_blank_without_one(self):
        _, doc, _ = self.make(False)
        self.assertNotIn("LOGO", etree_str(doc.element.body))

    def test_frame_ids_stay_unique_past_a_hundred_cards(self):
        cards = [Card("car", "BOX CAR", "NW", str(i), "x", None) for i in range(120)]
        out = layout.build_sheet(cards, self.tmp / "many.docx", self.cfg)
        doc = Document(out)
        spids = [e.get("{urn:schemas-microsoft-com:office:office}spid")
                 for e in doc.element.body.iter("{urn:schemas-microsoft-com:vml}roundrect")]
        self.assertEqual(len(spids), 120)
        self.assertEqual(len(set(spids)), 120)

    def test_no_cards_gives_one_empty_page(self):
        doc = Document(layout.build_sheet([], self.tmp / "none.docx", self.cfg))
        self.assertEqual(len(doc.element.body.findall(qn("w:tbl"))), 1)

    def test_a_wider_slot_widens_the_card_only(self):
        cfg = config.from_dict({"sheet": {"slot_w": 2.7}}, self.tmp)
        spec = layout.sheet_spec(cfg)
        out = layout.build_sheet([Card("car", "BOX CAR", "NW", "1", "x", FLATCAR)], self.tmp / "w.docx", cfg)
        doc = Document(out)
        slot = round(spec.slot_w * 1440)
        outer = doc.element.body.find(qn("w:tbl"))
        self.assertEqual([twips(c) for c in outer.find(qn("w:tblGrid")).findall(qn("w:gridCol"))], [slot] * 3)
        card_tbl = outer.find(qn("w:tr")).find(qn("w:tc")).find(qn("w:tbl"))
        self.assertEqual(twips(card_tbl.find(qn("w:tblGrid")).find(qn("w:gridCol"))), slot - 505)


def etree_str(el) -> str:
    from lxml import etree
    return etree.tostring(el, encoding="unicode")


class Spec(CardFolder):
    def test_default_is_the_poker_preset(self):
        spec = layout.sheet_spec(self.cfg)
        self.assertEqual(spec, layout.PRESETS["poker-3x3"])
        self.assertEqual((round(spec.slot_w * 1440), round(spec.slot_h * 1440)), (3686, 5098))
        self.assertEqual((spec.columns, spec.rows), (3, 3))

    def test_overrides(self):
        cfg = config.from_dict({"sheet": {"preset": "poker-3x3", "margin_left": 0.5, "columns": 2}}, self.tmp)
        spec = layout.sheet_spec(cfg)
        self.assertEqual((spec.margin_left, spec.columns, spec.rows), (0.5, 2, 3))

    def test_refusals(self):
        for bad in ({"preset": "nope"}, {"slot_x": 1.0}, {"slot_w": "wide"}, {"slot_w": 0}, {"columns": 0},
                    {"margin_top": -1}):
            cfg = config.from_dict({"sheet": bad}, self.tmp)
            with self.assertRaises(SystemExit, msg=str(bad)):
                layout.sheet_spec(cfg)


class Calibration(CardFolder):
    def test_page_geometry_and_labels(self):
        out = layout.calibration_page(self.tmp / "cal.docx", self.cfg)
        doc = Document(out)
        mar = doc.element.body.find(qn("w:sectPr")).find(qn("w:pgMar"))
        self.assertEqual([twips(mar, k) for k in ("top", "bottom", "left", "right")], [202, 101, 418, 360])
        tbl = doc.element.body.find(qn("w:tbl"))
        self.assertEqual([twips(c) for c in tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))], [3686] * 3)
        rows = tbl.findall(qn("w:tr"))
        self.assertEqual([twips(r.find(qn("w:trPr")).find(qn("w:trHeight")), "val") for r in rows], [5098] * 3)
        cells = [tc for r in rows for tc in r.findall(qn("w:tc"))]
        self.assertEqual(len(cells), 9)
        for tc in cells:
            bd = tc.find(qn("w:tcPr")).find(qn("w:tcBorders"))
            self.assertTrue(all(e.get(qn("w:val")) == "single" for e in bd))
            self.assertEqual(twips(bd[0], "sz"), 4)
        centre = "".join(t.text for t in cells[4].iter(qn("w:t")))
        self.assertIn("Slot row 2, column 2", centre)
        self.assertIn("2.560 x 3.540 in", centre)
        self.assertIn("top 0.140", centre)
        self.assertIn("left 0.290", centre)
        self.assertNotIn("Margins", "".join(t.text for t in cells[0].iter(qn("w:t"))))


class Describe(CardFolder):
    toml = '''
[[descriptions]]
type = "Hopper"
classes = ["LO"]
words = ["Covered", "cement"]
label = "Cov Hopper"
'''

    def d(self, **row):
        return layout.describe(row, self.cfg)

    def test_plain(self):
        self.assertEqual(self.d(car_type="Gondola", color="Black", length_ft="52"), "Black · Gondola · 52'")
        self.assertEqual(self.d(car_type="Gondola", length_ft="52"), "Gondola · 52'")
        self.assertEqual(self.d(car_type="Gondola"), "Gondola")

    def test_covered_hopper_by_class(self):
        self.assertEqual(self.d(car_type="Hopper", car_class="lo", color="Gray", length_ft="40"),
                         "Gray · Cov Hopper · 40'")
        self.assertEqual(self.d(car_type="Hopper", car_class="HT", color="Gray"), "Gray · Hopper")

    def test_covered_hopper_by_word(self):
        self.assertEqual(self.d(car_type="Hopper", notes="Cement service", length_ft="40"), "Cov Hopper · 40'")
        self.assertEqual(self.d(car_type="hopper", notes="a COVERED hopper"), "Cov Hopper")

    def test_rule_is_for_its_type_only(self):
        self.assertEqual(self.d(car_type="Gondola", car_class="LO", notes="cement"), "Gondola")

    def test_aliases(self):
        self.assertEqual(self.d(car_type="Coal", car_class="LO"), "Cov Hopper")  # Coal is an alias of Hopper
        self.assertEqual(self.d(car_type="Boxcar", color="Red"), "Red · Box Car")
        self.assertEqual(self.d(car_type="Tank", length_ft="40"), "Tank Car · 40'")

    def test_override_wins(self):
        self.assertEqual(self.d(car_type="Hopper", car_class="LO", description="Special"), "Special")

    def test_empty_is_a_dash(self):
        self.assertEqual(self.d(), "—")
        self.assertEqual(self.d(car_type="", color="  "), "—")


class Pictures(CardFolder):
    def put(self, name, folder):
        dest = folder / name
        Image.new("RGB", (20, 20), "gray").save(dest)
        return dest

    def test_final_when_no_print_copy(self):
        final = self.put("a.png", self.paths.final)
        row = {"image": "images/final/a.png"}
        self.assertEqual(layout.card_image(row, self.paths), final)

    def test_newer_print_copy_wins_older_loses(self):
        final = self.put("a.png", self.paths.final)
        printed = self.put("a.png", self.paths.print_copies)
        row = {"image": "images/final/a.png"}
        now = time.time()
        os.utime(final, (now - 100, now - 100))
        os.utime(printed, (now, now))
        self.assertEqual(layout.card_image(row, self.paths), printed)
        os.utime(final, (now + 100, now + 100))  # the crop was redone after the print copy
        self.assertEqual(layout.card_image(row, self.paths), final)

    def test_none_when_blank_or_missing(self):
        self.assertIsNone(layout.card_image({"image": ""}, self.paths))
        self.assertIsNone(layout.card_image({}, self.paths))
        self.assertIsNone(layout.card_image({"image": "images/final/gone.png"}, self.paths))
        self.put("b.png", self.paths.print_copies)  # a print copy alone is not enough
        self.assertIsNone(layout.card_image({"image": "images/final/b.png"}, self.paths))


class Cards(CardFolder):
    def setUp(self):
        super().setUp()
        self.cfg = dataclasses.replace(self.cfg, road_display={"NW": "N&W"})

    def test_car(self):
        self.put_image()
        card = layout.card_for_car({"reporting_marks": "NW", "road_number": "32800", "car_type": "Flatcar",
                                    "color": "Black", "length_ft": "52", "image": "images/final/x.png"},
                                   self.paths, self.cfg)
        self.assertEqual((card.kind, card.type_label, card.road_name, card.road_number),
                         ("car", "FLAT CAR", "N&W", "32800"))
        self.assertEqual(card.description, "Black · Flat Car · 52'")
        self.assertEqual(card.image, self.paths.final / "x.png")

    def put_image(self):
        Image.new("RGB", (20, 20), "gray").save(self.paths.final / "x.png")

    def test_missing_marks_and_number_show_a_question_mark(self):
        card = layout.card_for_car({"car_type": "Gondola"}, self.paths, self.cfg)
        self.assertEqual((card.road_name, card.road_number, card.image), ("?", "?", None))

    def test_loco(self):
        card = layout.card_for_loco({"reporting_marks": "CSX", "road_number": "2121", "builder": "EMD",
                                     "model": "GP38-2", "length_ft": "59", "loco_type": "Diesel"},
                                    self.paths, self.cfg)
        self.assertEqual((card.kind, card.type_label, card.road_name, card.road_number),
                         ("loco", "LOCOMOTIVE", "CSX", "2121"))
        self.assertEqual(card.description, "EMD · GP38-2 · 59'")

    def test_loco_description_override_and_dash(self):
        row = {"reporting_marks": "NW", "road_number": "1", "description": "Yard switcher"}
        self.assertEqual(layout.card_for_loco(row, self.paths, self.cfg).description, "Yard switcher")
        self.assertEqual(layout.card_for_loco({}, self.paths, self.cfg).description, "—")


class Icons(unittest.TestCase):
    def test_small_transparent_black_icons(self):
        for name in ("railroad", "number", "pencil"):
            path = layout.ICON_DIR / f"{name}.png"
            self.assertLess(path.stat().st_size, 10_000)
            im = Image.open(path)
            self.assertEqual(im.size, (96, 96))
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((0, 0))[3], 0)
            self.assertEqual(im.convert("RGBA").getextrema()[0], (0, 0))


if __name__ == "__main__":
    unittest.main()
