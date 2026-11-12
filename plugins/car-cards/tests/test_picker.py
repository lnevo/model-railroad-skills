"""Crop picker: box format, re-cut, prepare and the page parts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from helpers import PHOTOS, CardFolder

from cards import image, picker
from cards.schema import REVIEW_COLUMNS


def row(photo, **fields):
    r = {c: "" for c in REVIEW_COLUMNS}
    r.update({"photo": photo, "kind": "car", "status": "pending", "blur": "100", **fields})
    return r


def gradient(w=400, h=300):
    """Each pixel's red is its column and green its row (both /2), so a crop can be located."""
    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    arr = np.stack([xs // 2, ys // 2, np.full_like(xs, 128)], -1).astype("uint8")
    return Image.fromarray(arr)


class Box(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(picker.parse_box("10,20,300,100"), (10, 20, 300, 100, 0.0))
        self.assertEqual(picker.parse_box("10, 20, 300, 100, -1.5"), (10, 20, 300, 100, -1.5))
        self.assertEqual(picker.format_box((10.4, 20, 300, 100, 0.02)), "10,20,300,100")
        self.assertEqual(picker.format_box((10, 20, 300, 100, 1.5)), "10,20,300,100,1.5")
        self.assertEqual(picker.format_box((10, 20, 300, 100)), "10,20,300,100")

    def test_bad_boxes_refused(self):
        for text in ("1,2,3", "a,b,c,d", "0,0,10,10"):
            with self.assertRaises(SystemExit):
                picker.parse_box(text)


class Cut(CardFolder):
    def put(self, name="p"):
        gradient().save(self.paths.converted / f"{name}.png")

    def test_car_cut_is_the_box_on_the_leveled_photo(self):
        self.put()
        with mock.patch.object(image, "_level_image", return_value=(gradient(), 0.0)):
            out = picker.cut(row("p.jpg"), "100,60,200,100", self.paths)
        self.assertEqual(out.size, (200, 100))
        r, g, _ = out.getpixel((0, 0))
        self.assertEqual((r, g), (50, 30))  # top-left of the box is photo pixel (100, 60)

    def test_box_past_the_edge_is_filled_not_shifted(self):
        self.put()
        with mock.patch.object(image, "_level_image", return_value=(gradient(), 0.0)):
            out = picker.cut(row("p.jpg"), "-50,0,200,100", self.paths)
        self.assertEqual(out.size, (200, 100))
        self.assertEqual(out.getpixel((50, 0))[:2], (0, 0))  # photo column 0 lands 50 px in


class PrepareAndApply(CardFolder):
    def setUp(self):
        super().setUp()
        self.batch = self.paths.batch("b1")
        self.batch.mkdir(parents=True)

    def car_row(self):
        png = image.to_png(PHOTOS / "hopper.jpg", self.paths.converted)
        res = image.crop_car(png, self.paths, self.cfg)
        return row("hopper.jpg", image=self.paths.rel(res.final))

    def test_prepare_writes_views_and_json_and_keeps_them(self):
        r = self.car_row()
        failed = row("none.jpg")  # no image: nothing to crop from
        picker.prepare(self.batch, [r, failed], self.paths, self.cfg)
        data = json.loads((self.batch / picker.DATA_FILE).read_text())
        self.assertEqual(list(data), ["hopper.jpg"])
        d = data["hopper.jpg"]
        self.assertEqual(d["kind"], "car")
        self.assertTrue((self.batch / d["view"]).is_file())
        x, y, w, h = d["auto_box"]
        self.assertTrue(w > 50 and h > 50 and x >= 0 and y >= 0)
        self.assertGreaterEqual(d["scale"], 1.0)
        mtime = (self.batch / d["view"]).stat().st_mtime_ns
        picker.prepare(self.batch, [r], self.paths, self.cfg)
        self.assertEqual((self.batch / d["view"]).stat().st_mtime_ns, mtime)  # kept
        r["kind"] = "loco"
        picker.prepare(self.batch, [r], self.paths, self.cfg)
        self.assertEqual(json.loads((self.batch / picker.DATA_FILE).read_text())["hopper.jpg"]["kind"], "loco")

    def test_page_parts_and_copy_command(self):
        self.assertEqual(picker.page_parts(self.batch), ("", "", ""))
        picker.prepare(self.batch, [self.car_row()], self.paths, self.cfg)
        css, html, script = picker.page_parts(self.batch)
        self.assertIn("Use this crop", html)
        self.assertIn("#pk", css)
        self.assertIn("cards crop ", script)
        self.assertNotIn("bin/cars", script)
        self.assertIn('"b1"', script)
        self.assertIn("hopper.jpg", script)

    def test_apply_recuts_a_car_and_updates_the_row(self):
        r = self.car_row()
        picker.prepare(self.batch, [r], self.paths, self.cfg)
        x, y, w, h = json.loads((self.batch / picker.DATA_FILE).read_text())["hopper.jpg"]["auto_box"]
        picker.apply(self.batch, r, picker.format_box((x, y, w * 0.9, h * 0.9)), self.paths, self.cfg)
        self.assertEqual(r["image"], "images/final/hopper.png")
        self.assertTrue(r["crop"].startswith(f"{x},{y},"))
        self.assertTrue(float(r["blur"]) > 0)
        self.assertTrue((self.paths.print_copies / "hopper.png").is_file())
        self.assertEqual(Image.open(self.paths.final / "hopper.png").size, (round(w * 0.9), round(h * 0.9)))

    def test_apply_to_a_loco_removes_the_print_copy(self):
        png = image.to_png(PHOTOS / "loco.jpg", self.paths.converted)
        stale = self.paths.print_copies / "loco.png"
        Image.new("RGB", (10, 10)).save(stale)
        r = row("loco.jpg", kind="loco", image="images/final/loco.png")
        picker.apply(self.batch, r, "100,300,1000,300", self.paths, self.cfg)
        self.assertFalse(stale.exists())
        self.assertEqual(Image.open(self.paths.final / "loco.png").size, (1000, 300))
        self.assertEqual(r["crop"], "100,300,1000,300")

    def test_view_for_other_kind_is_not_used_by_the_page_script(self):
        picker.prepare(self.batch, [self.car_row()], self.paths, self.cfg)
        _, _, script = picker.page_parts(self.batch)
        self.assertIn("P.kind===ROWS[i].kind", script)


if __name__ == "__main__":
    unittest.main()
