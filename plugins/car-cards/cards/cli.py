"""The `cards` command. Subcommands:

  init [--name NAME] [--short NAME]   make cards.toml and the folders here
  review [--batch NAME]               crop and read new photos in photos/incoming/, write a batch
  ai-notes BATCH FILE                 merge the photo-reader agent's JSON into the batch
  sheet-import BATCH FILE             take the review.csv downloaded from review.html
  fill BATCH PHOTO --set COL=VALUE..  set fields from the command line
  kind BATCH car|loco PHOTO..         switch photos between car and locomotive
  crop BATCH [PHOTO BOX] [--refresh]  re-cut one picture (box from the page), or rebuild the views
  approve BATCH [--no-ai]             approve the unflagged rows
  records BATCH [--dry-run] [--allow-pending]   write approved rows to data/
  locos set ID COL=VALUE.. | locos status       locomotive details a photo cannot give
  print [--all] [--calibrate] [--mark-printed]  cards not yet printed -> output/cards_<date>.docx
  status                              batches, fleet counts and cards waiting to print
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import batch, config, fleet, layout
from .paths import Paths, find_root
from .schema import CAR_COLUMNS, LOCO_COLUMNS, PENDING, REVIEW_COLUMNS


# Kept by the commands themselves: the id follows marks and number; the rest is card bookkeeping.
LOCO_KEPT = {"roster_id", "photo", "image", "batch", "recorded", "card_built", "card_printed"}

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cards", description="Car and locomotive cards from phone photos.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="make cards.toml and the folders in this directory")
    s.add_argument("--name", default="My Railroad", help="the railroad's name, printed on each card")
    s.add_argument("--short", default="MRR", help="a short form of the name")

    s = sub.add_parser("review", help="crop and read the new photos, write a batch")
    s.add_argument("--batch", help="batch name (default: today's date)")

    s = sub.add_parser("ai-notes", help="merge the photo reader's JSON into a batch")
    s.add_argument("batch")
    s.add_argument("file")

    s = sub.add_parser("sheet-import", help="take the review.csv downloaded from review.html")
    s.add_argument("batch")
    s.add_argument("file")

    s = sub.add_parser("fill", help="set fields, then fill empty details from the best row")
    s.add_argument("batch")
    s.add_argument("photos", nargs="*", help="photos to set (default: every pending row)")
    s.add_argument("--set", action="append", default=[], metavar="COL=VALUE")

    s = sub.add_parser("kind", help="switch photos between car and locomotive")
    s.add_argument("batch")
    s.add_argument("kind", choices=["car", "loco"])
    s.add_argument("photos", nargs="+")

    s = sub.add_parser("crop", help="re-cut one picture, or rebuild the picker views")
    s.add_argument("batch")
    s.add_argument("photo", nargs="?")
    s.add_argument("box", nargs="?", help="X,Y,W,H[,ANGLE] from the page's copy button")
    s.add_argument("--refresh", action="store_true", help="rebuild every picker view")

    s = sub.add_parser("approve", help="approve the unflagged rows")
    s.add_argument("batch")
    s.add_argument("--no-ai", action="store_true", help="approve without a photo-reader note")

    s = sub.add_parser("records", help="write approved rows into data/")
    s.add_argument("batch")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--allow-pending", action="store_true")

    s = sub.add_parser("locos", help="locomotive details a photo cannot give")
    ls = s.add_subparsers(dest="action", required=True)
    one = ls.add_parser("set", help="set columns on one locomotive")
    one.add_argument("roster_id")
    one.add_argument("fields", nargs="+", metavar="COL=VALUE")
    ls.add_parser("status", help="list locomotives and what each still needs")

    s = sub.add_parser("print", help="build the sheet of cards not yet printed")
    s.add_argument("--all", action="store_true", help="every car and locomotive, printed or not")
    s.add_argument("--calibrate", action="store_true", help="a plain-paper page to hold against the stock")
    s.add_argument("--mark-printed", action="store_true", help="record that the last sheet was printed")

    sub.add_parser("status", help="batches, fleet counts and cards waiting to print")
    return p


def cmd_init(args) -> int:
    root = Path.cwd()
    target = root / config.FILE_NAME
    if target.exists():
        raise SystemExit(f"{target} already exists; edit it instead. Nothing was changed.")
    target.write_text(config.template(args.name, args.short), encoding="utf-8")
    Paths(root).ensure()
    print(f"Made {target} and the card folders.")
    print(f"Next: put phone photos in {Paths(root).incoming}, then run: cards review")
    return 0


def cmd_locos(args, paths: Paths, cfg) -> int:
    rows = fleet.read_rows(paths.locos_csv, LOCO_COLUMNS)
    if args.action == "status":
        print(f"Locomotives: {len(rows)}")
        for r in rows:
            missing = fleet.missing_loco_fields(r)
            print(f"  {r['roster_id']:<12} " + (f"needs: {' '.join(missing)}" if missing else "complete"))
        if any(fleet.missing_loco_fields(r) for r in rows):
            print("Fill the gaps with: cards locos set ID COLUMN=VALUE ...")
        return 0
    row = next((r for r in rows if r["roster_id"] == args.roster_id), None)
    if row is None:
        raise SystemExit(f"{args.roster_id} is not in {paths.locos_csv}. `cards locos status` lists them.")
    values = batch.parse_sets(args.fields)
    settable = [c for c in LOCO_COLUMNS if c not in LOCO_KEPT]
    unknown = [k for k in values if k not in settable]
    if unknown:
        raise SystemExit(f"Cannot set {' '.join(unknown)}. Columns: {' '.join(settable)}")
    marks, number = values.get("reporting_marks", row["reporting_marks"]), values.get("road_number", row["road_number"])
    new_id = fleet.roster_id(marks, number, cfg) or row["roster_id"]
    if new_id != row["roster_id"] and any(r["roster_id"] == new_id for r in rows):
        raise SystemExit(f"{new_id} is already a locomotive. Change that one, or pick another number.")
    row.update(values)
    row["roster_id"] = new_id
    row["card_built"] = row["card_printed"] = ""  # the card changed
    fleet.write_rows(paths.locos_csv, LOCO_COLUMNS, rows)
    missing = fleet.missing_loco_fields(row)
    print(f"Updated {row['roster_id']}; still needs: {' '.join(missing) or 'nothing'}")
    return 0


def cmd_print(args, paths: Paths, cfg) -> int:
    if args.calibrate:
        out = layout.calibration_page(paths.output / "calibration.docx", cfg)
        print(f"Wrote {out}. Print it at 100% scale and hold it against your card stock.")
        return 0
    cars = fleet.read_rows(paths.cars_csv, CAR_COLUMNS)
    locos = fleet.read_rows(paths.locos_csv, LOCO_COLUMNS)
    if args.mark_printed:
        count = 0
        for rows, columns, path in ((cars, CAR_COLUMNS, paths.cars_csv), (locos, LOCO_COLUMNS, paths.locos_csv)):
            for r in rows:
                if r["card_built"] and not r["card_printed"]:
                    r["card_printed"] = fleet.today()
                    count += 1
            if rows:
                fleet.write_rows(path, columns, rows)
        print(f"Marked {count} cards printed.")
        return 0
    chosen_cars = [r for r in cars if args.all or not r["card_printed"]]
    chosen_locos = []
    for r in locos:
        if not (args.all or not r["card_printed"]):
            continue
        missing = fleet.missing_loco_fields(r)
        if missing:
            print(f"  skipped {r['roster_id']}: needs {' '.join(missing)} (cards locos set {r['roster_id']} ...)")
            continue
        chosen_locos.append(r)
    if not chosen_cars and not chosen_locos:
        print("No cards waiting. Record new photos with `cards records`, or use `cards print --all`.")
        return 0
    cards = []
    for r in chosen_cars:
        card = layout.card_for_car(r, paths, cfg)
        cards.append(card)
        print(f"  {card.road_name} {card.road_number}: {'picture' if card.image else 'no picture'}")
    for r in chosen_locos:
        card = layout.card_for_loco(r, paths, cfg)
        cards.append(card)
        print(f"  {card.road_name} {card.road_number} (loco): {'picture' if card.image else 'no picture'}")
    out = layout.build_sheet(cards, paths.output / f"cards_{fleet.today()}.docx", cfg)
    for r in (*chosen_cars, *chosen_locos):
        r["card_built"] = fleet.today()
    if cars:
        fleet.write_rows(paths.cars_csv, CAR_COLUMNS, cars)
    if locos:
        fleet.write_rows(paths.locos_csv, LOCO_COLUMNS, locos)
    print(f"Wrote {out}. After printing, run: cards print --mark-printed")
    return 0


def cmd_status(paths: Paths) -> int:
    names = sorted(p.parent.name for p in paths.batches.glob("*/review.csv")) if paths.batches.is_dir() else []
    print(f"Batches: {len(names)}")
    open_batches = []
    for name in names:
        rows = fleet.read_rows(paths.batch(name) / "review.csv", REVIEW_COLUMNS)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print(f"  {name}: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
        if counts.get(PENDING) or counts.get("approved"):
            open_batches.append(name)
    cars = fleet.read_rows(paths.cars_csv, CAR_COLUMNS)
    locos = fleet.read_rows(paths.locos_csv, LOCO_COLUMNS)
    print(f"Fleet: {len(cars)} cars, {len(locos)} locomotives")
    waiting = [r for r in (*cars, *locos) if not r["card_printed"]]
    unfinished = [r["roster_id"] for r in locos if fleet.missing_loco_fields(r)]
    print(f"Cards waiting to print: {len(waiting)}")
    new = len(batch.photos_to_review(paths))
    if new:
        print(f"New photos waiting: {new}. Next: cards review")
    elif open_batches:
        print(f"Next: finish batch {open_batches[0]} (cards approve, then cards records)")
    elif waiting:
        print("Next: cards print")
    if unfinished:
        print(f"Locomotives that need details: {' '.join(unfinished)} (cards locos status)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        return cmd_init(args)
    root = find_root()
    paths, cfg = Paths(root), config.load(root)
    paths.ensure()
    c = args.command
    if c == "review":
        return batch.review(paths, cfg, args.batch)
    if c == "ai-notes":
        return batch.ai_notes(paths, cfg, args.batch, args.file)
    if c == "sheet-import":
        return batch.sheet_import(paths, cfg, args.batch, args.file)
    if c == "fill":
        return batch.fill(paths, cfg, args.batch, args.photos, args.set)
    if c == "kind":
        return batch.set_kind(paths, cfg, args.batch, args.kind, args.photos)
    if c == "crop":
        return batch.crop(paths, cfg, args.batch, args.photo, args.box, args.refresh)
    if c == "approve":
        return batch.approve(paths, cfg, args.batch, args.no_ai)
    if c == "records":
        return batch.records(paths, cfg, args.batch, args.dry_run, args.allow_pending)
    if c == "locos":
        return cmd_locos(args, paths, cfg)
    if c == "print":
        return cmd_print(args, paths, cfg)
    return cmd_status(paths)
