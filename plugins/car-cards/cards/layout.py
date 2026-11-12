"""Builder 3c. The card and the sheet, drawn with python-docx from measurements (no third-party
template). Ported from the source pipeline's generate_card_template.py, generate_all_cards.py and
card_description.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .paths import Paths


@dataclass
class Card:
    kind: str              # car | loco
    type_label: str        # the boxed title, e.g. "BOX CAR", "LOCOMOTIVE"
    road_name: str         # cfg.display_road(marks)
    road_number: str
    description: str
    image: Path | None


@dataclass(frozen=True)
class SheetSpec:
    """Inches. A preset from PRESETS, with any cfg.sheet keys of the same names over it."""
    page_w: float
    page_h: float
    margin_top: float
    margin_bottom: float
    margin_left: float
    margin_right: float
    slot_w: float
    slot_h: float
    columns: int
    rows: int


PRESETS: dict[str, SheetSpec] = {}  # "poker-3x3": the poker-size sticker sheet, US Letter


def sheet_spec(cfg: Config) -> SheetSpec:
    raise NotImplementedError


def describe(row: dict, cfg: Config) -> str:
    """'<color> · <type label> · <length>'' from a cars.csv row; row['description'] wins when set;
    '—' when nothing is known. Type labels come from cfg.car_type and cfg.descriptions."""
    raise NotImplementedError


def card_image(row: dict, paths: Paths) -> Path | None:
    """The picture for a fleet row: images/print/<stem>.png only when it is newer than
    images/final/<stem>.png, else the final picture, else None."""
    raise NotImplementedError


def card_for_car(row: dict, paths: Paths, cfg: Config) -> Card:
    raise NotImplementedError


def card_for_loco(row: dict, paths: Paths, cfg: Config) -> Card:
    raise NotImplementedError


def build_sheet(cards: list[Card], out: Path, cfg: Config) -> Path:
    """Cards in order, nine (columns x rows) to a page, written to out (.docx)."""
    raise NotImplementedError


def calibration_page(out: Path, cfg: Config) -> Path:
    """One page of slot outlines and measurements on plain paper, to hold against the stock."""
    raise NotImplementedError
