"""Builder 3a. Reading reporting marks, number and weights with Tesseract (pytesseract).

Ported from the source pipeline's process_car_images.py: the band OCR, the colour-difference OCR
(gold on silver lettering), the digit fix for O/0 and friends, and the stencil parsing. Road names
come only from cfg (roads.aliases, roads.context, roads.known), never from code.
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .paths import Paths


def available() -> bool:
    """True when pytesseract imports and the tesseract program runs."""
    raise NotImplementedError


def digits(text: str) -> str:
    """Letters OCR mistakes for digits (O Q D -> 0, I l -> 1, S -> 5, B -> 8), then digits only."""
    raise NotImplementedError


def read(photo_png: Path, final_png: Path | None, paths: Paths, cfg: Config) -> dict:
    """Read one photo. Returns exactly schema.OCR_FIELDS as strings ('' when not found); writes the
    zoomed lettering to paths.ocr/<stem>.png. With no Tesseract, every field is ''."""
    raise NotImplementedError
