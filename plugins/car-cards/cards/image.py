"""Builder 3a. Photo conversion, the freight-car crop and levelling, blur score, print sharpening.

Ported from the source pipeline's crop_car_image.py, the algorithm parts of finalize_car_images.py
(without its per-photo tables) and sharpen_card_fill_images.py. Pillow and numpy only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .paths import Paths

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}


@dataclass
class CropResult:
    crop: Path | None     # images/crop/<stem>.png
    final: Path | None    # images/final/<stem>.png, the card picture
    print: Path | None    # images/print/<stem>.png, sharpened for print
    status: str           # "ok" | "review" | "failed"


def to_png(src: Path, dest_dir: Path) -> Path:
    """An upright (EXIF-applied) PNG copy of a photo in dest_dir, named <stem>.png. A PNG already
    upright may be copied as is. HEIC needs pillow-heif, else macOS `sips`, else SystemExit saying so."""
    raise NotImplementedError


def blur_score(path: Path) -> float:
    """Edge-response variance of a 1000 px greyscale copy. Higher is sharper (config blur_threshold)."""
    raise NotImplementedError


def crop_car(png: Path, paths: Paths, cfg: Config) -> CropResult:
    """Crop and level a side-on freight car photo; write crop, final and print copies under paths."""
    raise NotImplementedError


def sharpen_for_print(img):
    """PIL Image -> PIL Image, the print copy's brightness, contrast and unsharp mask."""
    raise NotImplementedError
