"""The approved fleet: data/cars.csv and data/locos.csv (schema.CAR_COLUMNS, LOCO_COLUMNS).

A car or locomotive is written here by `cards records`. Cards are built from these rows, and
the card_built / card_printed columns say which cards still wait to print.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from . import schema
from .config import Config
from .paths import Paths

CAR_FIELDS = ["reporting_marks", "road_number", "car_type", "car_class", "color", "length_ft",
              "capy_lbs", "ld_lmt_lbs", "lt_wt_lbs", "built", "description"]
LOCO_FIELDS = ["reporting_marks", "road_number", "length_ft", "description"]


def today() -> str:
    return date.today().isoformat()


def roster_id(marks: str, number: str, cfg: Config) -> str:
    """cfg.road_code(marks) + digits of number, no space; '' when either is missing."""
    code = cfg.road_code(marks)
    digits = re.sub(r"\D", "", number or "")
    return f"{code}{digits}" if code and digits else ""


def read_rows(path: Path, columns: list[str]) -> list[dict]:
    """Rows of a fleet CSV ([] when the file is missing), with every column present."""
    if not Path(path).is_file():
        return []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [{c: (row.get(c) or "") for c in columns} for row in csv.DictReader(fh)]


def write_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    """Atomic write (temp file, then replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def fleet_file(kind: str, paths: Paths) -> tuple[Path, list[str]]:
    return (paths.locos_csv, schema.LOCO_COLUMNS) if kind == "loco" else (paths.cars_csv, schema.CAR_COLUMNS)


def missing_loco_fields(row: dict) -> list[str]:
    return [f for f in schema.LOCO_REQUIRED if not (row.get(f) or "").strip()]


def record(review_row: dict, batch: str, paths: Paths, cfg: Config, dry_run: bool = False,
           planned: set[str] | None = None) -> str:
    """Write one approved review row into cars.csv or locos.csv by its kind. Returns the outcome
    text for the manifest: 'new car X', 'photo added to X', 'skipped: X already has a picture',
    'new loco X; needs model, loco_type' and so on. With dry_run nothing is written; pass the same
    planned set for every row of a dry run so it reports what the real run would."""
    kind = "loco" if review_row.get("kind") == "loco" else "car"
    path, columns = fleet_file(kind, paths)
    rows = read_rows(path, columns)
    new = {c: "" for c in columns}
    for key in LOCO_FIELDS if kind == "loco" else CAR_FIELDS:
        new[key] = review_row.get(key, "") or ""
    rid = roster_id(new["reporting_marks"], new["road_number"], cfg)
    if not rid:
        raise SystemExit(f"{review_row.get('photo', '?')}: a {kind} needs reporting marks and a road number.")
    image = review_row.get("image", "")
    new.update(roster_id=rid, photo=review_row.get("photo", ""),
               image=paths.rel(paths.resolve(image)) if image else "", batch=batch, recorded=today(),
               notes=review_row.get("note", "") or "")  # description rules read words in the notes
    existing = next((r for r in rows if r["roster_id"] == rid), None)
    if existing is None and dry_run and planned is not None and rid in planned:
        return f"skipped: {rid} already has a picture (an earlier photo in this batch)"
    label = "loco" if kind == "loco" else "car"
    if existing is None:
        if kind == "loco":
            new["loco_type"] = cfg.loco_default_type
        if not dry_run:
            rows.append(new)
            write_rows(path, columns, rows)
        elif planned is not None and new["image"]:
            planned.add(rid)
        outcome = f"new {label} {rid}"
        if kind == "loco":
            outcome += "; needs " + ", ".join(missing_loco_fields(new) or ["nothing"])
        return outcome
    if existing["image"]:
        return f"skipped: {rid} already has a picture"
    if not dry_run:
        for key, value in new.items():
            if value:
                existing[key] = value
        existing["card_built"] = existing["card_printed"] = ""  # the new picture needs a new card
        write_rows(path, columns, rows)
    return f"photo added to {rid}"
