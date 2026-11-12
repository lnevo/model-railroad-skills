"""A review batch: batches/<name>/review.csv (schema.REVIEW_COLUMNS) and its stages.

Ported from the source pipeline's intake stages. Every command that changes review.csv rewrites
review.html (sheet.write_page). Gates: review refuses an existing batch; approve needs an AI note on
every pending row unless --no-ai and approves only unflagged rows; records refuses pending rows
unless --allow-pending and records only approved rows.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

from . import fleet, image, loco, ocr, picker, sheet
from .config import Config
from .paths import Paths
from .schema import (APPROVED, EDIT_FIELDS, MANIFEST_COLUMNS, OCR_FIELDS, PENDING, RECORDED, REJECTED,
                     REVIEW_COLUMNS)

LOCO_PREFIXES = ("loco_", "engine_")
LOCO_TYPES = ("locomotive", "diesel", "engine", "switcher", "electric", "steam")
KIND_FLAGS = ("maybe-loco", "ai-says-loco", "ai-says-car")
AI_FLAGS = ("ai-disagrees", "ai-says-loco", "ai-says-car")
# Details one car shares with the rest of its batch (a string of hoppers, say). Not the description:
# that override belongs to one car.
DETAIL_FIELDS = ["car_type", "car_class", "color", "length_ft", "capy_lbs", "ld_lmt_lbs", "lt_wt_lbs", "built"]


# ---- reading and writing

def batch_dir(paths: Paths, name: str) -> Path:
    return paths.batch(name)


def load(paths: Paths, name: str) -> tuple[Path, list[dict]]:
    out = batch_dir(paths, name)
    if not (out / "review.csv").is_file():
        raise SystemExit(f"No batch {name} in {paths.batches}. `cards status` lists the batches.")
    return out, fleet.read_rows(out / "review.csv", REVIEW_COLUMNS)


def save(out: Path, rows: list[dict]) -> Path:
    """Write review.csv and the page that shows it."""
    fleet.write_rows(out / "review.csv", REVIEW_COLUMNS, rows)
    return sheet.write_page(out, rows)


def fleet_rows(paths: Paths) -> dict[str, list[dict]]:
    from .schema import CAR_COLUMNS, LOCO_COLUMNS
    return {"car": fleet.read_rows(paths.cars_csv, CAR_COLUMNS),
            "loco": fleet.read_rows(paths.locos_csv, LOCO_COLUMNS)}


def today() -> str:
    return date.today().isoformat()


# ---- which photos, which kind

def photo_kind(path: Path) -> str:
    return "loco" if path.name.lower().startswith(LOCO_PREFIXES) else "car"


def photos_already_taken(paths: Paths, keep_batch: str | None = None) -> set[str]:
    """File names in the fleet or in any batch's review.csv."""
    names = {r["photo"] for rows in fleet_rows(paths).values() for r in rows if r["photo"]}
    if paths.batches.is_dir():
        for review in paths.batches.glob("*/review.csv"):
            if review.parent.name != keep_batch:
                names |= {r["photo"] for r in fleet.read_rows(review, REVIEW_COLUMNS)}
    return names


def photos_to_review(paths: Paths) -> list[tuple[Path, str]]:
    """New photos in photos/incoming/. A converted copy of the same photo is not a second photo."""
    taken = photos_already_taken(paths)
    found, listed = [], set()
    folder = paths.incoming
    for p in sorted(folder.iterdir()) if folder.is_dir() else []:
        if (p.is_file() and not p.name.startswith(".") and p.suffix.lower() in image.IMAGE_SUFFIXES
                and p.name not in taken and p.stem not in listed):
            found.append((p, photo_kind(p)))
            listed.add(p.stem)
    return found


# ---- flags

def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


ANY_ROAD = "*"


def usual_lengths(rows: list[dict], cfg: Config) -> dict[str, int]:
    """The digit count most cars have (only when more than half agree): per road for a road with two
    or more cars in the batch, and for the whole batch under ANY_ROAD. A road seen once is held to
    the batch's count, so a misread mark such as CTET for CSXT does not hide a short number."""
    groups: dict[str, list[int]] = {}
    for r in rows:
        if r["kind"] == "car" and _digits(r["road_number"]):
            n = len(_digits(r["road_number"]))
            groups.setdefault(cfg.road_code(r["reporting_marks"]), []).append(n)
            groups.setdefault(ANY_ROAD, []).append(n)
    usual = {}
    for code, lengths in groups.items():
        best = max(set(lengths), key=lengths.count)
        if lengths.count(best) > len(lengths) / 2 and (code == ANY_ROAD or len(lengths) > 1):
            usual[code] = best
    return usual


def loco_pattern(cfg: Config) -> re.Pattern | None:
    """Words from locos.model_words. Three letters or more match as words; shorter ones (model
    prefixes like GP or SD) match only when digits follow, so a reporting mark like NW 32800 is not one."""
    words = [w.strip() for w in cfg.loco_model_words if w.strip()]
    parts = [rf"\b{re.escape(w)}\b" for w in words if len(w) >= 3]
    short = [re.escape(w) for w in words if len(w) < 3]
    if short:
        parts.append(rf"\b(?:{'|'.join(short)})\s?-?\d{{1,2}}[A-Z]?\b")
    return re.compile("|".join(parts), re.I) if parts else None


def flag_word_hit(text: str, cfg: Config) -> bool:
    for word in cfg.flag_words:
        phrase = r"\s+".join(re.escape(p) for p in word.split())
        if phrase and re.search(rf"(?<![A-Za-z0-9]){phrase}(?![A-Za-z0-9])", text, re.I):
            return True
    return False


def ai_flags(r: dict) -> list[str]:
    """Flags from the photo reader's note: it suggests, it never changes the fields."""
    flags = []
    ai_loco = r["ai_type"].lower() in LOCO_TYPES
    if ai_loco and r["kind"] == "car":
        flags.append("ai-says-loco")
    elif r["ai_type"] and not ai_loco and r["kind"] == "loco":
        flags.append("ai-says-car")
    if norm(r["ai_marks"]) != norm(r["reporting_marks"]) or norm(r["ai_number"]) != norm(r["road_number"]):
        flags.append("ai-disagrees")
    return flags


def flag_row(row: dict, cfg: Config, fleet_by_kind: dict, seen: dict, usual: dict | None = None) -> list[str]:
    """The reasons a human should look at this photo before it is approved."""
    flags = []
    if row["crop_status"] not in ("ok", ""):
        flags.append(f"crop-{row['crop_status']}")
    try:
        sharp = float(row["blur"]) if row["blur"] else None
    except ValueError:
        sharp = None
    if sharp is not None and sharp < cfg.blur_threshold:
        flags.append("blurry")
    marks = row["reporting_marks"]
    known = {k.upper() for k in cfg.known_roads}
    if not marks:
        flags.append("no-marks")
    elif known and marks.upper() not in known and cfg.road_code(marks) not in known:
        flags.append("road-not-in-fleet")
    if not row["road_number"]:
        flags.append("no-number")
    elif usual and row["kind"] == "car":
        want = usual.get(cfg.road_code(marks), usual.get(ANY_ROAD))
        if want and len(_digits(row["road_number"])) != want:
            flags.append("number-length")
    rid = row["roster_id"]
    if rid:
        if rid in seen:
            flags.append(f"same-id-as-{seen[rid]}")
        seen.setdefault(rid, row["photo"])
        have = next((f for f in fleet_by_kind.get(row["kind"], []) if f["roster_id"] == rid), None)
        if have is not None and have["image"]:
            flags.append("already-recorded")
    if flag_word_hit(f"{row['ocr_text']} {row['description']}", cfg):
        flags.append("flag-word")
    pattern = loco_pattern(cfg)
    if row["kind"] == "car" and ((pattern and pattern.search(row["ocr_text"]))
                                 or row["car_type"].lower() in LOCO_TYPES):
        flags.append("maybe-loco")
    return flags


def norm(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def set_flags(rows: list[dict], cfg: Config, paths: Paths, only: set[str] | None = None,
              only_pending: bool = True) -> None:
    """Work out roster ids and flags again after rows were edited."""
    by_kind = fleet_rows(paths)
    usual = usual_lengths(rows, cfg)
    seen: dict = {}
    for r in rows:
        if r["status"] == RECORDED or (only_pending and r["status"] != PENDING):
            continue
        if only is not None and r["photo"] not in only:
            continue
        r["roster_id"] = fleet.roster_id(r["reporting_marks"], r["road_number"], cfg)
        flags = flag_row(r, cfg, by_kind, seen, usual)
        if "process-failed" in r["flags"] and not r["image"]:
            flags.insert(0, "process-failed")
        if r["ai_note"]:
            flags += ai_flags(r)
        r["flags"] = ";".join(flags)


# ---- review

def process_photo(photo: Path, kind: str, paths: Paths, cfg: Config) -> dict:
    """One new row: converted copy, picture, OCR, blur. Raises on a photo that cannot be read."""
    row = {c: "" for c in REVIEW_COLUMNS}
    row.update(photo=photo.name, kind=kind, status=PENDING)
    png = image.to_png(photo, paths.converted)
    if kind == "loco":
        result = loco.loco_picture(png, paths, cfg)
        fields = ocr.read(png, None, paths, cfg)
    else:
        result = image.crop_car(png, paths, cfg)
        fields = ocr.read(png, result.final, paths, cfg)
    row.update({k: fields.get(k, "") for k in OCR_FIELDS})
    row["crop_status"] = result.status
    if result.final and Path(result.final).is_file():
        row["image"] = paths.rel(result.final)
        row["blur"] = f"{image.blur_score(result.final):.0f}"
    return row


def review(paths: Paths, cfg: Config, batch: str | None = None) -> int:
    photos = photos_to_review(paths)
    if not photos:
        print(f"No new photos in {paths.incoming}. Put phone photos there, then run `cards review`.")
        return 0
    name = batch or today()
    out = batch_dir(paths, name)
    if out.exists():
        raise SystemExit(f"Batch {name} already exists. Pass --batch with another name.")
    out.mkdir(parents=True)
    try:
        rows = []
        for photo, kind in photos:
            print(f"{photo.name} ({kind})")
            try:
                rows.append(process_photo(photo, kind, paths, cfg))
            except (Exception, SystemExit) as err:  # one bad photo must not stop the batch
                row = {c: "" for c in REVIEW_COLUMNS}
                row.update(photo=photo.name, kind=kind, status=PENDING, flags="process-failed",
                           note=str(err)[:200])
                print(f"  failed: {row['note']}")
                rows.append(row)
        failed = {r["photo"] for r in rows if r["flags"] == "process-failed"}
        for r in rows:
            r["roster_id"] = fleet.roster_id(r["reporting_marks"], r["road_number"], cfg)
        by_kind, usual, seen = fleet_rows(paths), usual_lengths(rows, cfg), {}
        for r in rows:
            if r["photo"] not in failed:
                r["flags"] = ";".join(flag_row(r, cfg, by_kind, seen, usual))
        sheet.stamp(out)
        fleet.write_rows(out / "review.csv", REVIEW_COLUMNS, rows)
        picker.prepare(out, rows, paths, cfg)
        sheet.write_page(out, rows)
    except BaseException:
        if not (out / "review.csv").exists():
            shutil.rmtree(out, ignore_errors=True)
        raise
    flagged = sum(1 for r in rows if r["flags"])
    print(f"\n{len(rows)} photos, {flagged} flagged. Page: {out / 'review.html'}")
    print(f"Open the page, fix the flagged rows, then run: cards ai-notes {name} FILE  (or cards approve {name} --no-ai)")
    return 0


# ---- AI notes

def apply_ai_notes(rows: list[dict], notes: dict) -> list[str]:
    """Merge the photo reader's readings. A reading that differs from the OCR flags the row.

    ``notes`` maps photo name to {"marks", "number", "type", "note"}. The reader only suggests:
    it never changes the OCR fields or the status. Returns photo names that are not in the batch."""
    unknown = [p for p in notes if p not in {r["photo"] for r in rows}]
    for r in rows:
        n = notes.get(r["photo"])
        if n is None:
            continue
        r["ai_marks"], r["ai_number"] = n.get("marks", ""), str(n.get("number", ""))
        r["ai_type"], r["ai_note"] = n.get("type", ""), n.get("note", "") or "reviewed"
        r["flags"] = ";".join([f for f in r["flags"].split(";") if f and f not in AI_FLAGS] + ai_flags(r))
    return unknown


def ai_notes(paths: Paths, cfg: Config, name: str, file: str) -> int:
    out, rows = load(paths, name)
    try:
        notes = json.loads(Path(file).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise SystemExit(f"Cannot read {file}: {err}") from None
    unknown = apply_ai_notes(rows, notes)
    if unknown:
        raise SystemExit(f"Not in the batch: {' '.join(unknown)}")
    save(out, rows)
    disagree = [r["photo"] for r in rows if "ai-disagrees" in r["flags"]]
    print(f"Notes merged. Disagree with the OCR: {' '.join(disagree) or 'none'}")
    print(f"Next: check the flagged rows on the page, then run: cards approve {name}")
    return 0


# ---- kind

def remake_picture(r: dict, paths: Paths, cfg: Config) -> None:
    """A photo that changed kind gets the other kind's picture. Skipped when the converted copy is gone."""
    png = paths.converted / f"{Path(r['photo']).stem}.png"
    if not png.is_file():
        return
    try:
        result = loco.loco_picture(png, paths, cfg) if r["kind"] == "loco" else image.crop_car(png, paths, cfg)
    except (Exception, SystemExit) as err:
        r["note"] = f"picture not remade: {err}"[:200]
        return
    r["crop"], r["crop_status"] = "", result.status
    if result.final and Path(result.final).is_file():
        r["image"] = paths.rel(result.final)
        r["blur"] = f"{image.blur_score(result.final):.0f}"


def set_kind(paths: Paths, cfg: Config, name: str, kind: str, photos: list[str]) -> int:
    """Set the kind of pending photos. The roster id is worked out again; kind flags are cleared."""
    out, rows = load(paths, name)
    unknown = [p for p in photos if p not in {r["photo"] for r in rows}]
    if unknown:
        raise SystemExit(f"Not in the batch: {' '.join(unknown)}")
    changed = 0
    for r in rows:
        if r["photo"] in photos and r["status"] == PENDING:
            if r["kind"] != kind:
                r["kind"] = kind
                remake_picture(r, paths, cfg)
            r["flags"] = ";".join(f for f in r["flags"].split(";") if f and f not in KIND_FLAGS)
            changed += 1
    set_flags(rows, cfg, paths, only=set(photos))
    fleet.write_rows(out / "review.csv", REVIEW_COLUMNS, rows)
    if (out / "picker.json").is_file():  # the picker shows a loco as taken
        picker.prepare(out, rows, paths, cfg)
    sheet.write_page(out, rows)
    print(f"Set {changed} photos to {kind}.")
    skipped = len(photos) - changed
    if skipped:
        print(f"{skipped} were not pending and were left alone.")
    return 0


# ---- fill

def best_row(rows: list[dict]) -> dict:
    """The row with the most detail filled in; ties go to the sharper photo."""
    return max(rows, key=lambda r: (sum(bool(r[f]) for f in DETAIL_FIELDS), float(r["blur"] or 0)))


def fill(paths: Paths, cfg: Config, name: str, photos: list[str], sets: list[str]) -> int:
    """Set fields on the named photos (every pending row when none are named), then fill each of those
    cars' empty details from the best row of the same road and car type. A batch can mix car types,
    so details never cross from a flat car to a hopper; a row with no marks or type is not filled."""
    out, rows = load(paths, name)
    unknown = [p for p in photos if p not in {r["photo"] for r in rows}]
    if unknown:
        raise SystemExit(f"Not in the batch: {' '.join(unknown)}")
    values = parse_sets(sets)
    for key in values:
        if key not in REVIEW_COLUMNS or key == "photo":
            raise SystemExit(f"Unknown column {key}. Columns: {' '.join(c for c in EDIT_FIELDS)}")
    for r in rows:
        if r["status"] == PENDING and (not photos or r["photo"] in photos):
            r.update(values)
    def group(r: dict) -> tuple[str, str] | None:
        code, kind = cfg.road_code(r["reporting_marks"]), cfg.car_type(r["car_type"]).lower()
        return (code, kind) if code and kind else None

    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r["kind"] == "car" and r["status"] == PENDING and group(r):
            groups.setdefault(group(r), []).append(r)
    filled, used = 0, []
    for key, members in groups.items():
        targets = [r for r in members if not photos or r["photo"] in photos]
        if not targets or len(members) < 2:
            continue
        best = best_row(members)
        used.append(best["photo"])
        for r in targets:
            for f in DETAIL_FIELDS:
                if not r[f] and best[f]:
                    r[f], filled = best[f], filled + 1
                elif r[f] and best[f] and r[f] != best[f]:
                    print(f"  {r['photo']} {f} reads {r[f]}, best row {best['photo']} has {best[f]}")
    set_flags(rows, cfg, paths)
    save(out, rows)
    print(f"Best row {', '.join(used) or 'none (no two cars share marks and type)'}. Filled {filled} empty details.")
    print(f"Next: check the page, then run: cards approve {name}")
    return 0


def parse_sets(pairs: list[str]) -> dict[str, str]:
    values = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Needs COLUMN=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        values[key.strip()] = value.strip()
    return values


# ---- sheet import and crop

def sheet_import(paths: Paths, cfg: Config, name: str, file: str) -> int:
    """Take the review.csv downloaded from the review page. Only the page's own fields (the edit
    fields, status and crop) are taken; a recorded row is left as it was."""
    out, old = load(paths, name)
    downloaded = fleet.read_rows(Path(file).expanduser(), REVIEW_COLUMNS)
    if [r["photo"] for r in downloaded] != [r["photo"] for r in old]:
        raise SystemExit("The downloaded sheet is not for this batch (the photos differ).")
    rows = []
    for new, before in zip(downloaded, old):
        if before["status"] == RECORDED:
            rows.append(dict(before))
            continue
        if new["status"] not in (PENDING, APPROVED, REJECTED):
            raise SystemExit(f"{new['photo']}: status must be pending, approved or rejected.")
        row = dict(before)
        row.update({k: new[k] for k in (*EDIT_FIELDS, "status", "crop")})
        rows.append(row)
    for row, before in zip(rows, old):  # a crop picked on the page re-cuts the card picture
        if row["status"] != RECORDED and row["crop"] and row["crop"] != before["crop"]:
            if not cut_picture(out, row, row["crop"], paths, cfg):
                row["crop"] = before["crop"]
    set_flags(rows, cfg, paths, only_pending=False)  # approved rows may have been edited too
    save(out, rows)
    print(f"Imported {len(rows)} rows. Approved: {sum(r['status'] == APPROVED for r in rows)}.")
    print(f"Next: cards approve {name}  (when every flagged row is dealt with)")
    return 0


def cut_picture(out: Path, row: dict, box: str, paths: Paths, cfg: Config) -> bool:
    """Re-cut one row's picture with the box. A person looked at it, so the crop counts as checked."""
    try:
        picker.apply(out, row, box, paths, cfg)
    except (Exception, SystemExit) as err:
        print(f"  {row['photo']}: crop failed: {err}")
        return False
    row["crop_status"] = "ok"
    print(f"  {row['photo']}: new crop {box} -> {row['image']} (blur {row['blur']}). Check it by eye.")
    return True


def crop(paths: Paths, cfg: Config, name: str, photo: str | None = None, box: str | None = None,
         refresh: bool = False) -> int:
    out, rows = load(paths, name)
    if photo is None:
        picker.prepare(out, rows, paths, cfg, force=refresh)
        sheet.write_page(out, rows)
        print(f"Picker ready. Open {out / 'review.html'} and use Adjust crop.")
        return 0
    if box is None:
        raise SystemExit(f"Give the box too: cards crop {name} {photo} X,Y,W,H[,ANGLE]")
    row = next((r for r in rows if r["photo"] == photo), None)
    if row is None:
        raise SystemExit(f"Not in the batch: {photo}")
    if row["status"] == RECORDED:
        raise SystemExit(f"{photo} is already recorded; its picture is not changed here.")
    row["crop"] = box
    if not cut_picture(out, row, box, paths, cfg):
        raise SystemExit("The picture was not changed.")
    set_flags(rows, cfg, paths, only={photo})
    save(out, rows)
    return 0


# ---- approve and records

def approve(paths: Paths, cfg: Config, name: str, no_ai: bool = False) -> int:
    out, rows = load(paths, name)
    unreviewed = [r["photo"] for r in rows if r["status"] == PENDING and not r["ai_note"]]
    if unreviewed and not no_ai:
        raise SystemExit(f"{len(unreviewed)} photos have no photo-reader note yet ({' '.join(unreviewed)}). "
                         f"Merge one with `cards ai-notes {name} FILE`, or pass --no-ai.")
    count = 0
    for r in rows:
        if r["status"] == PENDING and not r["flags"]:
            r["status"] = APPROVED
            count += 1
    save(out, rows)
    left = [r["photo"] for r in rows if r["status"] == PENDING]
    print(f"Approved {count} unflagged photos.")
    if left:
        print(f"Still pending ({len(left)}): set status to approved or rejected on the page")
        print("  " + " ".join(left))
        print(f"then run `cards sheet-import {name} FILE`, or pass --allow-pending to `cards records`.")
    else:
        print(f"Next: cards records {name}")
    return 0


def records(paths: Paths, cfg: Config, name: str, dry_run: bool = False, allow_pending: bool = False) -> int:
    """Write approved rows into the fleet and the batch manifest."""
    out, review_rows = load(paths, name)
    waiting = [r["photo"] for r in review_rows if r["status"] == PENDING]
    if waiting and not allow_pending:
        raise SystemExit(f"{len(waiting)} photos are still pending: {' '.join(waiting)}\n"
                         f"Approve or reject them, or pass --allow-pending to leave them for later.")
    todo = [r for r in review_rows if r["status"] == APPROVED]
    nameless = [r["photo"] for r in todo
                if not fleet.roster_id(r["reporting_marks"], r["road_number"], cfg)]
    if nameless:
        raise SystemExit(f"These approved photos need reporting marks and a road number first: "
                         f"{' '.join(nameless)}")
    manifest_path = out / "manifest.csv"
    manifest = fleet.read_rows(manifest_path, MANIFEST_COLUMNS)
    for r in todo:
        outcome = fleet.record(r, name, paths, cfg, dry_run=dry_run)
        print(f"  {r['photo']}: {outcome}")
        if not dry_run:
            r["status"] = RECORDED
            manifest.append({"photo": r["photo"], "kind": r["kind"],
                             "roster_id": fleet.roster_id(r["reporting_marks"], r["road_number"], cfg),
                             "outcome": outcome, "recorded": today()})
    if dry_run:
        print("Dry run: nothing written.")
        return 0
    fleet.write_rows(manifest_path, MANIFEST_COLUMNS, manifest)
    save(out, review_rows)
    print(f"Recorded {len(todo)}. Manifest: {manifest_path}")
    print("Next: cards print  (cards for everything not yet printed)")
    return 0
