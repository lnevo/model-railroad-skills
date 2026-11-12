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
        self.assertEqual(w, 1200)  # the whole photo, not a freight crop
        self.assertGreater(image.blur_score(res.final), 100)

    def test_box_limits_the_picture(self):
        png = image.to_png(PHOTOS / "loco.jpg", self.paths.converted)
        res = loco.loco_picture(png, self.paths, self.cfg, box=(100, 300, 1300, 800))
        w, h = Image.open(res.final).size
        self.assertAlmostEqual(w, 1200 * 1200 / 1400, delta=2)
        self.assertAlmostEqual(h, 500 * 1200 / 1400, delta=2)


if __name__ == "__main__":
    unittest.main()
