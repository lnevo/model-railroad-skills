"""Digit fix, stencil parsing, the generic road-mark finder and, with Tesseract, a real read."""
import unittest
from pathlib import Path
from unittest import mock

from helpers import FIXTURES, NEEDS_TESSERACT, PHOTOS, CardFolder

from cards import config, image, ocr
from cards.schema import OCR_FIELDS


class Digits(unittest.TestCase):
    def test_digits_fix_letters_read_as_numbers(self):
        self.assertEqual(ocr.digits("37 97 O2"), "379702")
        self.assertEqual(ocr.digits("B4S"), "845")


class ParseMarkings(unittest.TestCase):
    def test_weights_with_and_without_commas(self):
        out = ocr._parse_markings("CAPY 200,000 LD LMT 243400 LT WT 42600")
        self.assertEqual((out["capy_lbs"], out["ld_lmt_lbs"], out["lt_wt_lbs"]), ("200000", "243400", "42600"))

    def test_light_weight_spelling_and_build_date(self):
        out = ocr._parse_markings("LIGHT WT 61400 BLT 8-59")
        self.assertEqual((out["lt_wt_lbs"], out["built"]), ("61400", "8-59"))
        self.assertEqual(ocr._parse_markings("NEW 10-72")["built"], "10-72")
        self.assertEqual(ocr._parse_markings("BUILT 1-80")["built"], "1-80")

    def test_class_only_when_printed_as_a_word(self):
        self.assertEqual(ocr._parse_markings("AAR XM BOX")["car_class"], "XM")
        self.assertNotIn("car_class", ocr._parse_markings("SOMETHING"))

    def test_nothing_found_is_empty(self):
        self.assertEqual(ocr._parse_markings("NOISE ~ ~"), {})


class FindRoadMark(CardFolder):
    def test_generic_marks_and_number(self):
        self.assertEqual(ocr._find_road_mark("CSXT 379808", self.cfg), ("CSXT", "379808"))

    def test_weight_lines_are_not_marks(self):
        self.assertEqual(ocr._find_road_mark("LD LMT 243400 LT WT 42600", self.cfg), ("", ""))

    def test_a_number_that_is_a_weight_is_skipped(self):
        self.assertEqual(ocr._find_road_mark("CAPY 200000", self.cfg), ("", ""))

    def test_split_number(self):
        self.assertEqual(ocr._find_road_mark("XYZ 600 409", self.cfg), ("XYZ", "600409"))


class FindRoadMarkWithSettings(unittest.TestCase):
    def setUp(self):
        self.cfg = config.from_dict({"roads": {"known": ["NW", "BO"], "aliases": {"N&W": "NW", "NOW": "NW"},
                                               "context": {"BALTIMORE": "BO"}}}, Path("."))

    def test_aliases_map_a_misread_to_the_canonical_mark(self):
        self.assertEqual(ocr._find_road_mark("NOW 32800", self.cfg), ("NW", "32800"))
        self.assertEqual(ocr._find_road_mark("N&W 32800", self.cfg), ("NW", "32800"))

    def test_context_word_names_the_road(self):
        self.assertEqual(ocr._find_road_mark("BALTIMORE AND OHIO 123456", self.cfg), ("BO", "123456"))

    def test_known_road_beats_an_earlier_unknown_one(self):
        self.assertEqual(ocr._find_road_mark("ZZZ 11111 NW 32800", self.cfg), ("NW", "32800"))

    def test_unknown_road_is_still_returned_when_nothing_is_known(self):
        self.assertEqual(ocr._find_road_mark("ZZZ 11111", self.cfg), ("ZZZ", "11111"))


class Read(CardFolder):
    def test_without_tesseract_every_field_is_empty(self):
        png = image.to_png(PHOTOS / "hopper.jpg", self.paths.converted)
        with mock.patch.object(ocr, "available", return_value=False):
            out = ocr.read(png, None, self.paths, self.cfg)
        self.assertEqual(out, {k: "" for k in OCR_FIELDS})

    @NEEDS_TESSERACT
    def test_small_fixture_returns_exactly_the_ocr_fields(self):
        # 1200 px is too small for the colour-difference read of the lettering: only the shape is asserted
        png = image.to_png(PHOTOS / "hopper.jpg", self.paths.converted)
        res = image.crop_car(png, self.paths, self.cfg)
        out = ocr.read(png, res.final, self.paths, self.cfg)
        self.assertEqual(list(out), OCR_FIELDS)
        self.assertTrue(all(isinstance(v, str) for v in out.values()))
        self.assertTrue((self.paths.ocr / "hopper.png").is_file())

    @NEEDS_TESSERACT
    def test_large_hopper_reads_marks_number_and_weights(self):
        png = image.to_png(FIXTURES / "ocr" / "hopper_large.jpg", self.paths.converted)
        res = image.crop_car(png, self.paths, self.cfg)
        out = ocr.read(png, res.final, self.paths, self.cfg)
        self.assertEqual(out["reporting_marks"], "CSXT")
        self.assertEqual(out["road_number"], "379808")
        self.assertLessEqual(len(out["ocr_text"]), 400)
        self.assertEqual(list(out), OCR_FIELDS)


if __name__ == "__main__":
    unittest.main()
