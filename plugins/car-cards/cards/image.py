"""Photo conversion, the freight-car crop and levelling, blur score, print sharpening.

Ported from the source pipeline's crop_car_image.py, the algorithm parts of finalize_car_images.py
(without its per-photo tables) and sharpen_card_fill_images.py. Pillow and numpy only. The
detection and levelling code lives in _img_detect.py; this module is the crop, the centred
final picture and the files.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from ._img_detect import (  # noqa: F401  (re-exported: the picker and the tests use these)
    BODY_THRESH, LONG_CAR_MIN_FRAC, LONG_CAR_PAD_X, PAD_BOTTOM, PAD_TOP, TIE_MARGIN_COUNT, TRACK_THRESH,
    Y0, _backdrop_color, _estimate_tie_pitch, _level_image, _trim_foreground, detect_car_bbox,
    estimate_rotation, match_lightbox_white_balance)
from .config import Config
from .paths import Paths

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}

# Card-box geometry (the card's picture box is 1.84 x 1.12 in).
CARD_EMBED_WIDTH_IN = 1.84
CARD_DISPLAY_HEIGHT_IN = 1.12
# A short, wide crop (a flatcar) is made as tall as a box car so cards match. The source averaged
# the heights of its own box-car crops between BOX_HEIGHT_MIN and BOX_HEIGHT_MAX and fell back to
# 671 when it had none; a fixed 671 is used here. These are pixels at the source photo size.
BOX_HEIGHT_MIN = 620
BOX_HEIGHT_MAX = 720
BOX_CAR_TARGET_HEIGHT = 671
FLATCAR_MAX_HEIGHT = 620
FLATCAR_MIN_HEIGHT = 400
FLATCAR_MIN_RATIO = 3.0

# Print prep: the final picture stays as is, the print copy is sharpened.
BRIGHTNESS = 1.14
CONTRAST = 1.04
SHARPNESS = 1.12
UNSHARP = dict(radius=0.9, percent=115, threshold=2)

# The picker's loose box when nothing was found: 80% x 35% of the photo, centred.
FALLBACK_W, FALLBACK_H = 0.8, 0.35


@dataclass
class CropResult:
    crop: Path | None     # images/crop/<stem>.png
    final: Path | None    # images/final/<stem>.png, the card picture
    print: Path | None    # images/print/<stem>.png, sharpened for print
    status: str           # "ok" | "review" | "failed"


def to_png(src: Path, dest_dir: Path) -> Path:
    """An upright (EXIF-applied) PNG copy of a photo in dest_dir, named <stem>.png. A PNG already
    upright may be copied as is. HEIC needs pillow-heif, else macOS `sips`, else SystemExit saying so."""
    src, dest_dir = Path(src), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / f"{src.stem}.png"
    heic = src.suffix.lower() in (".heic", ".heif")
    if heic:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            if shutil.which("sips") is None:
                raise SystemExit(f"{src.name}: HEIC photos need the pillow-heif package (pip install "
                                 f"pillow-heif), or convert them to JPG first.") from None
            tmp = dest_dir / f".{src.stem}.sips.png"
            subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(tmp)],
                           check=True, capture_output=True)
            # sips applies the orientation itself, so the file is already upright
            tmp.replace(dst)
            return dst
    with Image.open(src) as im:
        upright = im.getexif().get(0x0112, 1) in (0, 1)
        if src.suffix.lower() == ".png" and upright:
            if src.resolve() != dst.resolve():
                shutil.copyfile(src, dst)  # an upright PNG needs no re-encoding
            return dst
        out = ImageOps.exif_transpose(im).convert("RGB")
    out.save(dst)
    return dst


def blur_score(path: Path) -> float:
    """Edge-response variance of a 1000 px greyscale copy. Higher is sharper (config blur_threshold)."""
    image = Image.open(path).convert("L")
    image.thumbnail((1000, 1000))
    edges = np.asarray(image.filter(ImageFilter.FIND_EDGES), dtype="float64")
    return float(edges.var())


def sharpen_for_print(img):
    """PIL Image -> PIL Image, the print copy's brightness, contrast and unsharp mask."""
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(BRIGHTNESS)
    rgb = ImageEnhance.Contrast(rgb).enhance(CONTRAST)
    rgb = ImageEnhance.Sharpness(rgb).enhance(SHARPNESS)
    return rgb.filter(ImageFilter.UnsharpMask(**UNSHARP))


# ---- the first crop: car plus a few ties each side

def _centered_crop_box(gray: np.ndarray, bx0: int, by0: int, bx1: int, by1: int) -> tuple[int, int, int, int]:
    """Symmetric tie margins past coupler tips, centered on the car."""
    H, W = gray.shape
    cw, ch = bx1 - bx0, by1 - by0
    track_y0 = by0 + int(ch * 0.62)
    track_y1 = min(H, by1 + int(ch * 0.08))
    pitch = _estimate_tie_pitch(gray, bx0, bx1, track_y0, track_y1)
    pad_x = max(8, int(TIE_MARGIN_COUNT * pitch))
    if cw >= W * LONG_CAR_MIN_FRAC:
        pad_x = min(pad_x, max(8, int(cw * LONG_CAR_PAD_X)))
    pad_top = int(ch * PAD_TOP)
    pad_bottom = int(ch * PAD_BOTTOM)

    cx = (bx0 + bx1) / 2.0
    half_w = cw / 2.0 + pad_x
    src_left = int(round(cx - half_w))
    src_right = int(round(cx + half_w))
    want_w = src_right - src_left

    if src_left < 0:
        src_right = min(W, src_right - src_left)
        src_left = 0
    if src_right > W:
        src_left = max(0, src_left - (src_right - W))
        src_right = W

    crop_cx = (src_left + src_right) / 2.0
    shift = int(round(cx - crop_cx))
    if shift:
        nleft = max(0, src_left + shift)
        nright = min(W, src_right + shift)
        if nright - nleft >= want_w - 2:
            src_left, src_right = nleft, nright

    src_top = max(0, by0 - pad_top)
    src_bottom = min(H, by1 + pad_bottom)
    return src_left, src_top, src_right, src_bottom


def _crop_at_fixed_size(img: Image.Image, center_x: float, center_y: float,
                        target_w: int, target_h: int) -> Image.Image:
    """Extract a fixed-size window centered on (center_x, center_y); outside the photo is wall colour."""
    W, H = img.size
    src_left = int(round(center_x - target_w / 2.0))
    src_top = int(round(center_y - target_h / 2.0))
    src_right = src_left + target_w
    src_bottom = src_top + target_h

    canvas = Image.new(img.mode, (target_w, target_h), _backdrop_color(img))
    clip_left, clip_top = max(0, src_left), max(0, src_top)
    clip_right, clip_bottom = min(W, src_right), min(H, src_bottom)
    if clip_right > clip_left and clip_bottom > clip_top:
        canvas.paste(img.crop((clip_left, clip_top, clip_right, clip_bottom)),
                     (max(0, -src_left), max(0, -src_top)))
    return canvas


def assess_crop(bbox: tuple[int, int, int, int], img_size: tuple[int, int]) -> str:
    W, H = img_size
    x0, y0, x1, y1 = bbox
    cw, ch = x1 - x0, y1 - y0
    if cw < 0.20 * W or ch < 0.12 * H:
        return "review"
    return "ok"


# ---- the second stage: centre the finished picture on the rolling stock

def _card_box_height(out_tw: int) -> int:
    return int(round(out_tw * CARD_DISPLAY_HEIGHT_IN / CARD_EMBED_WIDTH_IN))


def _is_flatcar_crop(tw: int, th: int) -> bool:
    return FLATCAR_MIN_HEIGHT < th < FLATCAR_MAX_HEIGHT and tw / max(th, 1) >= FLATCAR_MIN_RATIO


def _rolling_stock_span(gray: np.ndarray) -> tuple[int, int]:
    """Coupler tips just outside the visible body silhouette."""
    h, w = gray.shape
    mid = gray[int(h * 0.30): int(h * 0.70), :]
    body = (mid < BODY_THRESH).mean(axis=0)
    cols = np.where(body > 0.15)[0]
    if not cols.size:
        lower = gray[int(h * 0.70):, :]
        lfrac = (lower < TRACK_THRESH).mean(axis=0)
        strong = np.where(lfrac > 0.22)[0]
        if strong.size:
            return int(strong[0]), int(strong[-1])
        return 0, w - 1

    blo, bhi = int(cols[0]), int(cols[-1])
    lower = gray[int(h * 0.72):, :]
    lfrac = (lower < TRACK_THRESH).mean(axis=0)
    reach = max(30, int(w * 0.035))
    l0 = max(0, blo - reach)
    left_tip = l0 + int(np.argmax(lfrac[l0: blo + 1]))
    r1 = min(w, bhi + reach + 1)
    right_tip = bhi + int(np.argmax(lfrac[bhi: r1]))
    return left_tip, right_tip


def _horizontal_shift(gray: np.ndarray) -> int:
    """Pixels to move content right for centering."""
    w = gray.shape[1]
    lo, hi = _rolling_stock_span(gray)
    return int(round(w / 2.0 - (lo + hi) / 2.0))


def finalize_box(leveled: Image.Image, crop_img: Image.Image, origin: tuple[int, int]) -> dict:
    """Where the finished picture sits on the levelled photo, given the first crop and where that
    crop was cut (origin = its left and top on the levelled photo).

    Returns ``leveled`` (the image), ``center`` (x, y) and ``size`` (w, h) of the window.
    """
    src_left, src_top = origin
    tw, th = crop_img.size
    crop_gray = np.asarray(ImageOps.grayscale(crop_img), dtype=np.uint8)
    shift = _horizontal_shift(crop_gray)
    new_left = src_left - shift
    center_x = new_left + tw / 2.0
    out_th = th
    if _is_flatcar_crop(tw, th):
        out_th = BOX_CAR_TARGET_HEIGHT
    center_y = src_top + th / 2.0
    return {"leveled": leveled, "center": (center_x, center_y), "size": (tw, out_th)}


def _loose_box(size: tuple[int, int]) -> list[float]:
    """A box around the middle of the photo, for when no car was found."""
    W, H = size
    w, h = W * FALLBACK_W, H * FALLBACK_H
    return [W * (1 - FALLBACK_W) / 2, H * 0.5 - h / 2, w, h]


def plan_crop(img: Image.Image) -> dict:
    """Level the photo and find the automatic card box on it, without writing anything.

    Returns leveled, rotation, status ("ok" | "review" | "failed"), box [x, y, w, h] on the
    levelled photo (the loose fallback when status is "failed"), and crop (the first crop's
    image, or None when failed) for crop_car to save.
    """
    img = img.convert("RGB")
    leveled, rotation = _level_image(img)
    W, H = leveled.size
    try:
        bbox = detect_car_bbox(leveled)
    except Exception:
        bbox = None
    y_top = int(Y0 * H)
    if bbox is None or (bbox[0] == 0 and bbox[2] == W and bbox[1] == y_top) or bbox[2] - bbox[0] < 20:
        # detect_car_bbox returns the whole search band when it finds nothing
        return {"leveled": leveled, "rotation": rotation, "status": "failed",
                "box": [round(v) for v in _loose_box(leveled.size)], "crop": None}
    gray = np.asarray(ImageOps.grayscale(leveled), dtype=np.uint8)
    left, top, right, bottom = _centered_crop_box(gray, *bbox)
    crop = leveled.crop((left, top, right, bottom))
    found = finalize_box(leveled, crop, (left, top))
    (cx, cy), (w, h) = found["center"], found["size"]
    return {"leveled": leveled, "rotation": rotation, "status": assess_crop(bbox, (W, H)),
            "box": [round(cx - w / 2), round(cy - h / 2), w, h], "crop": crop}


def crop_car(png: Path, paths: Paths, cfg: Config) -> CropResult:
    """Crop and level a side-on freight car photo; write crop, final and print copies under paths."""
    png = Path(png)
    stem = png.stem
    with Image.open(png) as im:
        plan = plan_crop(im)
    leveled, (x, y, w, h) = plan["leveled"], plan["box"]
    final_img = _crop_at_fixed_size(leveled, x + w / 2.0, y + h / 2.0, int(w), int(h))
    for folder in (paths.crops, paths.final, paths.print_copies):
        folder.mkdir(parents=True, exist_ok=True)
    crop_path = None
    if plan["crop"] is not None:
        crop_path = paths.crops / f"{stem}.png"
        plan["crop"].save(crop_path)
    final_path = paths.final / f"{stem}.png"
    final_img.save(final_path)
    print_path = paths.print_copies / f"{stem}.png"
    sharpen_for_print(final_img).save(print_path)
    return CropResult(crop_path, final_path, print_path, plan["status"])
