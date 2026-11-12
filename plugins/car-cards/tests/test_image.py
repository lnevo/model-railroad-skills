"""Photo conversion, crop detection, levelling, blur score and the car crop on the fixture photos."""
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from helpers import PHOTOS, CardFolder

from cards import image
from cards._img_detect import _trim_foreground


class TrimForeground(unittest.TestCase):
    """Crop detection must ignore a dark table strip below the track."""

    def test_cuts_full_width_dark_strip(self):
        region = np.full((100, 200), 220, dtype=np.uint8)
        region[60:64, 20:180] = 40   # rails: dark but not full width
        region[80:, :] = 10          # table
        cut = _trim_foreground(region).shape[0]
        self.assertTrue(70 <= cut <= 80, cut)  # edge smoothing may take a few rows

    def test_leaves_normal_photo_alone(self):
        region = np.full((100, 200), 220, dtype=np.uint8)
        region[60:64, 20:180] = 40
        self.assertEqual(_trim_foreground(region).shape[0], 100)

    def test_cuts_the_fade_above_the_table(self):
        region = np.full((200, 200), 220, dtype=np.uint8)
        region[40:44, 20:180] = 40                      # rails
        for i, y in enumerate(range(150, 170)):          # backdrop edge fading to black
            region[y, : int(10 * (i + 1))] = 20
        region[170:, :] = 10
        cut = _trim_foreground(region).shape[0]
        self.assertLess(cut, 155)
        self.assertGreater(cut, 44)


class ToPng(CardFolder):
    def test_exif_orientation_is_applied(self):
        src = self.tmp / "turned.jpg"
        img = Image.new("RGB", (60, 40), (200, 30, 30))
        exif = Image.Exif()
        exif[0x0112] = 6  # stored sideways: shown rotated 90 degrees clockwise
        img.save(src, exif=exif)
        out = image.to_png(src, self.paths.converted)
        self.assertEqual(out, self.paths.converted / "turned.png")
        self.assertEqual(Image.open(out).size, (40, 60))

    def test_upright_png_is_copied_and_jpg_converted(self):
        png = self.tmp / "a.png"
        Image.new("RGB", (30, 20), (1, 2, 3)).save(png)
        out = image.to_png(png, self.paths.converted)
        self.assertEqual(Image.open(out).size, (30, 20))
        out = image.to_png(PHOTOS / "flatcar.jpg", self.paths.converted)
        self.assertEqual(out.name, "flatcar.png")
        self.assertEqual(Image.open(out).size, (1200, 900))


class Scores(unittest.TestCase):
    def test_blur_score_prefers_sharp_edges(self):
        sharp = np.zeros((200, 200), dtype=np.uint8)
        sharp[:, 100:] = 255
        soft = np.tile(np.linspace(0, 255, 200).astype(np.uint8), (200, 1))
        tmp = Path(__import__("tempfile").mkdtemp())
        Image.fromarray(sharp).save(tmp / "s.png")
        Image.fromarray(soft).save(tmp / "b.png")
        self.assertGreater(image.blur_score(tmp / "s.png"), image.blur_score(tmp / "b.png"))

    def test_sharpen_for_print_keeps_size_and_brightens(self):
        img = Image.new("RGB", (50, 30), (100, 100, 100))
        out = image.sharpen_for_print(img)
        self.assertEqual(out.size, (50, 30))
        self.assertGreater(out.getpixel((25, 15))[0], 100)


class CropCar(CardFolder):
    def crop(self, name):
        png = image.to_png(PHOTOS / name, self.paths.converted)
        return image.crop_car(png, self.paths, self.cfg)

    def test_fixtures_crop_ok_with_files_and_a_wide_sharp_picture(self):
        for name in ("flatcar.jpg", "hopper.jpg"):
            res = self.crop(name)
            self.assertEqual(res.status, "ok", name)
            stem = Path(name).stem
            self.assertEqual(res.crop, self.paths.crops / f"{stem}.png")
            self.assertEqual(res.final, self.paths.final / f"{stem}.png")
            self.assertEqual(res.print, self.paths.print_copies / f"{stem}.png")
            for p in (res.crop, res.final, res.print):
                self.assertTrue(p.is_file(), p)
            w, h = Image.open(res.final).size
            # a freight car side is a long, low picture (the card shows it in its own box)
            self.assertTrue(2.5 < w / h < 5.0, (name, w, h))
            self.assertGreater(image.blur_score(res.final), self.cfg.blur_threshold, name)

    def test_the_picture_is_cut_from_the_levelled_photo_not_filled_with_wall(self):
        res = self.crop("hopper.jpg")
        arr = np.asarray(Image.open(res.final).convert("L"), float)
        self.assertLess(arr[: arr.shape[0] // 2].mean(), 235)  # not a blank wall

    def test_no_car_still_writes_a_picture_to_fix_in_the_picker(self):
        blank = self.paths.converted / "blank.png"
        Image.new("RGB", (1000, 750), (190, 188, 185)).save(blank)
        res = image.crop_car(blank, self.paths, self.cfg)
        self.assertEqual(res.status, "failed")
        self.assertTrue(res.final.is_file())
        w, h = Image.open(res.final).size
        self.assertEqual((w, h), (800, round(750 * 0.35)))

    def test_plan_crop_box_is_inside_the_levelled_photo_for_a_car(self):
        with Image.open(PHOTOS / "hopper.jpg") as im:
            plan = image.plan_crop(im)
        x, y, w, h = plan["box"]
        W, H = plan["leveled"].size
        self.assertTrue(0 <= x and x + w <= W and 0 <= y and y + h <= H, plan["box"])

    def test_flatcar_height_rule_only_for_short_wide_crops(self):
        self.assertTrue(image._is_flatcar_crop(2000, 500))
        self.assertFalse(image._is_flatcar_crop(2000, 700))
        self.assertFalse(image._is_flatcar_crop(900, 500))


class HeicNeedsSomething(CardFolder):
    def test_heic_without_converters_says_so(self):
        src = self.tmp / "p.heic"
        src.write_bytes(b"not really")
        with mock.patch.dict("sys.modules", {"pillow_heif": None}), \
                mock.patch("cards.image.shutil.which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                image.to_png(src, self.paths.converted)
        self.assertIn("pillow-heif", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
