"""Locomotive pictures: cut from the photo as taken, backdrop evened to a grey gradient.

Ported from the source pipeline's loco_backdrop.py (numpy, Pillow, scipy.ndimage). The freight-car
crop is made for freight cars and tilts and over-exposes locomotive photos, so a locomotive keeps
its own pixels (no rotation, no exposure change) and everything else is rebuilt:

* the backdrop (creases, tape, corner wedges) is replaced by a smooth grey gradient fitted to the
  backdrop itself, forced neutral;
* the locomotive and track are the one big region that is not backdrop-coloured (a dark corner
  wedge that does not touch them is dropped);
* a soft contact shadow is added under the track.

Boxes are x0, y0, x1, y1 on the photo scaled to 1400 px wide. Check the result by eye.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

from .config import Config
from .image import CropResult
from .paths import Paths

REF_WIDTH = 1400  # boxes are measured on the photo scaled to this width
SMALL = 3  # the mask and the backdrop fit run at 1/3 size


def loco_mask(small: np.ndarray, bg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(loco and track, backdrop): the largest region not coloured like the backdrop, and the backdrop."""
    lum = small.mean(2)
    r = small[..., 0] / (small[..., 1] + 1)
    b = small[..., 2] / (small[..., 1] + 1)
    near = (
        (lum > 0.62 * bg.mean())
        & (abs(r - bg[0] / bg[1]) < 0.045)
        & (abs(b - bg[2] / bg[1]) < 0.07)
    )
    near = ndi.binary_opening(near, iterations=1)
    labels, _ = ndi.label(near)
    edge = (set(np.unique(labels[0, :])) | set(np.unique(labels[-1, :]))) - {0}
    backdrop = np.isin(labels, list(edge))
    parts, count = ndi.label(~backdrop)
    sizes = ndi.sum(~backdrop, parts, range(1, count + 1))
    return parts == 1 + int(np.argmax(sizes)), backdrop


def _basis(x: np.ndarray, y: np.ndarray, degree: int = 3) -> np.ndarray:
    return np.stack([x**i * y**j for i in range(degree + 1) for j in range(degree + 1 - i)], -1)


def smooth_backdrop(small: np.ndarray, backdrop: np.ndarray, keep: np.ndarray, gain: np.ndarray):
    """Neutral grey polynomial surface fitted to the backdrop pixels (creases ignored)."""
    h, w, _ = small.shape
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = xx / w * 2 - 1, yy / h * 2 - 1
    use = backdrop & (ndi.distance_transform_edt(~keep) > 6)
    idx = np.argwhere(use)[::7]
    basis = _basis(x[idx[:, 0], idx[:, 1]], y[idx[:, 0], idx[:, 1]])
    value = (small[idx[:, 0], idx[:, 1]] * gain).mean(1)
    weight = np.ones(len(value))
    for _ in range(4):  # creases are darker than the fit: give them almost no weight
        coef = np.linalg.lstsq(basis * weight[:, None], value * weight, rcond=None)[0]
        weight = np.where(value - basis @ coef < -6, 0.05, 1.0)
    return _basis(x, y) @ coef


def clean(photo: Image.Image, box: tuple[int, int, int, int], target: float = 175.0,
          shadow: float = 0.55, lift: float = 10.0) -> Image.Image:
    scale = photo.width / REF_WIDTH
    img = photo.convert("RGB").crop(tuple(int(v * scale) for v in box))
    w, h = img.size
    small = np.asarray(img.resize((w // SMALL, h // SMALL), Image.LANCZOS), float)
    sh, sw, _ = small.shape
    bg = np.median(small[: int(sh * 0.07), int(sw * 0.35): int(sw * 0.65)].reshape(-1, 3), 0)
    gain = np.clip(target / bg, 0.8, 1.25)
    keep, backdrop = loco_mask(small, bg)
    surface = smooth_backdrop(small, backdrop, keep, gain)
    surface = np.asarray(Image.fromarray(np.float32(surface)).resize(img.size, Image.BICUBIC))
    back = np.clip(surface + lift, 0, 255)[..., None].repeat(3, 2)

    alpha = Image.fromarray(np.uint8(keep * 255)).resize(img.size, Image.BICUBIC)
    alpha = np.asarray(alpha.filter(ImageFilter.GaussianBlur(1.2)), float)[..., None] / 255
    drop = int(w * 0.014)
    moved = np.zeros_like(alpha[..., 0])
    moved[drop:] = alpha[:-drop, :, 0]
    soft = Image.fromarray(np.uint8(moved * 255)).filter(ImageFilter.GaussianBlur(w * 0.009))
    shade = 1 - shadow * (np.asarray(soft, float) / 255) * (1 - alpha[..., 0])
    body = np.clip(np.asarray(img, float) * gain, 0, 255)
    out = alpha * body + (1 - alpha) * back * shade[..., None]
    return Image.fromarray(np.uint8(np.clip(out, 0, 255)))


def auto_box(photo: Image.Image) -> tuple[int, int, int, int] | None:
    """A box around the locomotive (x0, y0, x1, y1 on the REF_WIDTH copy), or None when no body is
    found. The mask holds the locomotive and the track; the track is a thin band across the whole
    photo, so the locomotive is the columns where the mask stands well above it."""
    ref_h = round(photo.height * REF_WIDTH / photo.width)
    small = np.asarray(photo.convert("RGB").resize((REF_WIDTH // SMALL, ref_h // SMALL), Image.LANCZOS), float)
    sh, sw, _ = small.shape
    bg = np.median(small[: int(sh * 0.07), int(sw * 0.35): int(sw * 0.65)].reshape(-1, 3), 0)
    keep, _ = loco_mask(small, bg)
    cols = keep.sum(0)
    if cols.max() < sh * 0.08:
        return None
    xs = np.flatnonzero(cols > 0.35 * cols.max())
    x0, x1 = xs.min(), xs.max()
    rows = keep[:, x0: x1 + 1].sum(1)
    ys = np.flatnonzero(rows > 0.2 * (x1 - x0))
    if x1 - x0 < sw * 0.15 or len(ys) == 0:
        return None
    y0, y1 = ys.min(), ys.max()
    pad_x, top, bottom = 0.05 * (x1 - x0), 0.25 * (y1 - y0), 0.2 * (y1 - y0)
    box = (max(0, x0 - pad_x), max(0, y0 - top), min(sw, x1 + pad_x), min(sh, y1 + bottom))
    return tuple(int(round(v * SMALL)) for v in box)


def loco_picture(png: Path, paths: Paths, cfg: Config, box: tuple[int, int, int, int] | None = None) -> CropResult:
    """Write images/final/<stem>.png for a locomotive and remove any images/print/<stem>.png, so a
    stale freight-style print copy cannot win. box None = found by auto_box, else the whole photo
    with status "review"."""
    png = Path(png)
    with Image.open(png) as im:
        photo = im.convert("RGB")
    status = "ok"
    if box is None:
        box = auto_box(photo)
    if box is None:
        box, status = (0, 0, REF_WIDTH, round(photo.height * REF_WIDTH / photo.width)), "review"
    out = clean(photo, box)
    paths.final.mkdir(parents=True, exist_ok=True)
    final = paths.final / f"{png.stem}.png"
    out.save(final)
    (paths.print_copies / f"{png.stem}.png").unlink(missing_ok=True)
    return CropResult(None, final, None, status)
