"""Backdrop clean-up for loco photos: neutral gradient, loco kept, stray wedge dropped."""
import unittest

import numpy as np
from PIL import Image

from helpers import PHOTOS, CardFolder

from cards import image, loco


def synthetic() -> Image.Image:
    a = np.zeros((1050, 1400, 3))
    a[...] = (185, 178, 160)                      # warm backdrop
    a[300:320, :, :] -= 25                        # a crease
    a[100:200, 0:60, :] = 30                      # dark corner wedge, not touching the loco
    a[500:700, 300:1100, :] = (60, 70, 120)       # the loco
    a[700:760, :, :] = (70, 55, 45)               # track
    return Image.fromarray(np.uint8(a))


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.out = np.asarray(loco.clean(synthetic(), (0, 0, 1400, 1050)), float)

    def test_backdrop_is_neutral_and_even(self):
        for y, x in ((20, 20), (250, 700), (310, 700), (950, 1300)):
            r, g, b = self.out[y, x]
            self.assertLess(max(r, g, b) - min(r, g, b), 3, (y, x))
        self.assertLess(abs(self.out[310, 700, 0] - self.out[250, 700, 0]), 8)  # crease gone

    def test_stray_wedge_is_dropped(self):
        self.assertGreater(self.out[150, 30].mean(), 150)

    def test_loco_and_track_are_kept(self):
        self.assertLess(self.out[600, 700, 0], 100)   # loco still dark blue
        self.assertLess(self.out[730, 700].mean(), 110)


class LocoPicture(CardFolder):
    def test_writes_final_and_removes_a_stale_print_copy(self):
        png = image.to_png(PHOTOS / "loco.jpg", self.paths.converted)
        stale = self.paths.print_copies / "loco.png"
        Image.new("RGB", (10, 10)).save(stale)
        res = loco.loco_picture(png, self.paths, self.cfg)
        self.assertEqual(res.final, self.paths.final / "loco.png")
        self.assertTrue(res.final.is_file())
        self.assertFalse(stale.exists())
        self.assertIsNone(res.print)
        self.assertEqual(res.status, "ok")
        w, h = Image.open(res.final).size
        # Cut round the locomotive (the fixture's sits at about x 238-1199, y 446-837 of 1400),
        # not the whole photo and not a freight crop.
        self.assertTrue(600 < w < 1100 and 2.0 < w / h < 3.2, (w, h))
        self.assertGreater(image.blur_score(res.final), self.cfg.blur_threshold)

    def test_auto_box_finds_the_locomotive(self):
        with Image.open(PHOTOS / "loco.jpg") as im:
            x0, y0, x1, y1 = loco.auto_box(im.convert("RGB"))
        self.assertTrue(150 < x0 < 300 and 1150 < x1 < 1300, (x0, x1))
        self.assertTrue(380 < y0 < 520 and 780 < y1 < 900, (y0, y1))

    def test_no_locomotive_gives_the_whole_photo_for_review(self):
        blank = self.paths.converted / "blank.png"
        Image.new("RGB", (1400, 1050), (200, 198, 195)).save(blank)
        res = loco.loco_picture(blank, self.paths, self.cfg)
        self.assertEqual(res.status, "review")
        self.assertEqual(Image.open(res.final).size, (1400, 1050))

    def test_box_limits_the_picture(self):
        png = image.to_png(PHOTOS / "loco.jpg", self.paths.converted)
        res = loco.loco_picture(png, self.paths, self.cfg, box=(100, 300, 1300, 800))
        w, h = Image.open(res.final).size
        self.assertAlmostEqual(w, 1200 * 1200 / 1400, delta=2)
        self.assertAlmostEqual(h, 500 * 1200 / 1400, delta=2)


if __name__ == "__main__":
    unittest.main()
