"""Builder 3a. Locomotive pictures: cut from the photo as taken, backdrop evened to a grey gradient.

Ported from the source pipeline's loco_backdrop.py (numpy, Pillow, scipy.ndimage).
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .image import CropResult
from .paths import Paths

REF_WIDTH = 1400  # boxes are measured on the photo scaled to this width


def clean(photo, box: tuple[int, int, int, int], target: float = 175.0, shadow: float = 0.55, lift: float = 10.0):
    """PIL Image of the photo -> PIL Image: the box (x0, y0, x1, y1 on the REF_WIDTH copy) with the
    backdrop replaced by a smooth neutral grey and a soft shadow kept under the locomotive."""
    raise NotImplementedError


def loco_picture(png: Path, paths: Paths, cfg: Config, box: tuple[int, int, int, int] | None = None) -> CropResult:
    """Write images/final/<stem>.png for a locomotive and remove any images/print/<stem>.png, so a
    stale freight-style print copy cannot win. box None = the whole photo."""
    raise NotImplementedError
