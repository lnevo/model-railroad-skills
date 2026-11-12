"""Builder 3b. The approved fleet: data/cars.csv and data/locos.csv (schema.CAR_COLUMNS, LOCO_COLUMNS).

Ported from the record parts of the source pipeline's cars.py, locos.py and roster_id.py, without
any roster XML, simulator or publishing step.
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .paths import Paths


def roster_id(marks: str, number: str, cfg: Config) -> str:
    """cfg.road_code(marks) + digits of number, no space; '' when either is missing."""
    raise NotImplementedError


def read_rows(path: Path, columns: list[str]) -> list[dict]:
    """Rows of a fleet CSV ([] when the file is missing), with every column present."""
    raise NotImplementedError


def write_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    """Atomic write (temp file, then replace)."""
    raise NotImplementedError


def record(review_row: dict, batch: str, paths: Paths, cfg: Config) -> str:
    """Write one approved review row into cars.csv or locos.csv by its kind. Returns the outcome
    text for the manifest: 'new car X', 'photo added to X', 'skipped: X already has a picture',
    'new loco X; needs model, loco_type' and so on."""
    raise NotImplementedError
