"""Review batches: flags, kinds, AI notes, approval, records, fill, sheet import and crop."""
import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest import mock

from PIL import Image

from helpers import CardFolder
from cards import batch, fleet, image, loco, ocr, picker, schema, sheet


def review_row(**kw):
    row = {c: "" for c in schema.REVIEW_COLUMNS}
    row.update(photo="a.jpg", kind="car", reporting_marks="NW", road_number="32800",
               roster_id="NW32800", crop_status="ok", blur="1500", status="pending")
    row.update(kw)
    return row


class Fakes:
    """Mixin: the image, OCR, loco and picker modules replaced by small stand-ins (builder 3a owns the real ones)."""

    def start_fakes(self):
        self.readings: dict[str, dict] = {}   # photo stem -> OCR fields
        self.crop_status: dict[str, str] = {}
        self.blurs: dict[str, float] = {}
        self.unreadable: set[str] = set()
        self.cut = []
        self.prepared = []

        def to_png(src, dest):
            if src.stem in self.unreadable:
                raise SystemExit("cannot open this photo")
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / f"{src.stem}.png"
            Image.new("RGB", (20, 10), "gray").save(out)
            return out

        def picture(stem, status="ok"):
            out = self.paths.final / f"{stem}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (20, 10), "gray").save(out)
            return image.CropResult(out, out, out, self.crop_status.get(stem, status))

        def read(png, final, paths, cfg):
            fields = {k: "" for k in schema.OCR_FIELDS}
            fields.update(self.readings.get(png.stem, {}))
            return fields

        def apply(batch_dir, row, box, paths, cfg):
            self.cut.append((row["photo"], box))
            row["crop"] = box
            row["image"] = "images/final/" + Path(row["photo"]).stem + ".png"
            row["blur"] = "2000"

        patches = [
            mock.patch.object(image, "to_png", side_effect=to_png),
            mock.patch.object(image, "crop_car", side_effect=lambda png, p, c: picture(png.stem)),
            mock.patch.object(image, "blur_score", side_effect=lambda p: self.blurs.get(Path(p).stem, 1500.0)),
            mock.patch.object(loco, "loco_picture", side_effect=lambda png, p, c, box=None: picture(png.stem)),
            mock.patch.object(ocr, "read", side_effect=read),
            mock.patch.object(picker, "prepare", side_effect=lambda *a, **k: self.prepared.append(k)),
            mock.patch.object(picker, "apply", side_effect=apply),
            mock.patch.object(picker, "page_parts", return_value=("", "", "")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def add_photo(self, name, **reading):
        (self.paths.incoming / name).write_bytes(b"x")
        if reading:
            self.readings[Path(name).stem] = reading

    def run_quiet(self, fn, *a, **k):
        with redirect_stdout(io.StringIO()) as out:
            fn(*a, **k)
        return out.getvalue()

    def rows(self, name="b1"):
        return fleet.read_rows(self.paths.batch(name) / "review.csv", schema.REVIEW_COLUMNS)

    def make_batch(self, rows, name="b1"):
        out = self.paths.batch(name)
        out.mkdir(parents=True, exist_ok=True)
        fleet.write_rows(out / "review.csv", schema.REVIEW_COLUMNS, rows)
        return out


class Base(Fakes, CardFolder):
    def setUp(self):
        super().setUp()
        self.start_fakes()


class FlagTests(Base):
    def flags(self, row, fleet_rows=None, seen=None, usual=None, cfg=None):
        return batch.flag_row(row, cfg or self.cfg, fleet_rows or {}, {} if seen is None else seen, usual)

    def test_clean_photo_has_no_flags(self):
        self.assertEqual(self.flags(review_row()), [])

    def test_unreadable_number_and_blur(self):
        self.assertEqual(self.flags(review_row(road_number="", roster_id="", blur="5")), ["blurry", "no-number"])

    def test_no_marks(self):
        self.assertIn("no-marks", self.flags(review_row(reporting_marks="")))

    def test_unknown_road_only_when_the_fleet_list_is_set(self):
        self.assertNotIn("road-not-in-fleet", self.flags(review_row(reporting_marks="XYZ")))
        cfg = replace(self.cfg, known_roads=("NW", "BO"))
        self.assertIn("road-not-in-fleet", self.flags(review_row(reporting_marks="XYZ"), cfg=cfg))
        self.assertNotIn("road-not-in-fleet", self.flags(review_row(), cfg=cfg))

    def test_alias_of_a_known_road_is_known(self):
        cfg = replace(self.cfg, known_roads=("NW",), road_aliases={"N&W": "NW"})
        self.assertNotIn("road-not-in-fleet", self.flags(review_row(reporting_marks="N&W"), cfg=cfg))

    def test_already_recorded_and_same_id_in_batch(self):
        recorded = {"car": [{"roster_id": "NW32800", "image": "images/final/old.png"}]}
        self.assertIn("already-recorded", self.flags(review_row(), recorded))
        self.assertIn("same-id-as-b.jpg", self.flags(review_row(), seen={"NW32800": "b.jpg"}))

    def test_car_without_a_picture_is_not_already_recorded(self):
        self.assertEqual(self.flags(review_row(), {"car": [{"roster_id": "NW32800", "image": ""}]}), [])

    def test_a_car_id_does_not_match_a_loco(self):
        self.assertEqual(self.flags(review_row(kind="loco"), {"car": [{"roster_id": "NW32800", "image": "x"}]}), [])

    def test_bad_crop(self):
        self.assertIn("crop-review", self.flags(review_row(crop_status="review")))
        self.assertIn("crop-failed", self.flags(review_row(crop_status="failed")))

    def test_flag_word_matches_whole_words_and_phrases_in_any_case(self):
        cfg = replace(self.cfg, flag_words=("blue moon", "secret"))
        self.assertIn("flag-word", self.flags(review_row(ocr_text="a BLUE  Moon boxcar"), cfg=cfg))
        self.assertIn("flag-word", self.flags(review_row(ocr_text="top Secret."), cfg=cfg))
        self.assertNotIn("flag-word", self.flags(review_row(ocr_text="secretary"), cfg=cfg))
        self.assertNotIn("flag-word", self.flags(review_row(ocr_text="blue sky moon"), cfg=cfg))
        self.assertNotIn("flag-word", self.flags(review_row(ocr_text="blue moon"), cfg=self.cfg))

    def test_number_length_differs_from_the_same_road(self):
        rows = [review_row(photo=f"{i}.jpg", road_number=n) for i, n in enumerate(["32800", "32801", "3280"])]
        usual = batch.usual_lengths(rows, self.cfg)
        self.assertEqual(usual, {"NW": 5})
        self.assertIn("number-length", self.flags(rows[2], usual=usual))
        self.assertNotIn("number-length", self.flags(rows[0], usual=usual))

    def test_number_length_needs_a_majority_and_the_same_road(self):
        rows = [review_row(photo="a", road_number="1234"), review_row(photo="b", road_number="12345"),
                review_row(photo="c", reporting_marks="BO", road_number="1")]
        self.assertEqual(batch.usual_lengths(rows, self.cfg), {})

    def test_a_road_seen_once_is_not_held_to_the_batch(self):
        rows = [review_row(photo=f"{i}.jpg", reporting_marks="CSXT", road_number=n)
                for i, n in enumerate(["379808", "379738", "379824"])]
        rows.append(review_row(photo="flat.jpg", reporting_marks="NW", road_number="32800"))
        rows.append(review_row(photo="odd.jpg", reporting_marks="CTET", road_number="4869"))
        usual = batch.usual_lengths(rows, self.cfg)
        self.assertEqual(usual, {"CSXT": 6})
        self.assertNotIn("number-length", self.flags(rows[3], usual=usual))
        # The misread mark is caught by the fleet list instead.
        cfg = replace(self.cfg, known_roads=("CSXT", "NW"))
        self.assertIn("road-not-in-fleet", self.flags(rows[4], cfg=cfg, usual=usual))
        self.assertNotIn("road-not-in-fleet", self.flags(rows[3], cfg=cfg, usual=usual))


class KindTests(Base):
    def flags(self, row, cfg=None):
        return batch.flag_row(row, cfg or self.cfg, {}, {})

    def test_loco_words_in_ocr_flag_a_car(self):
        self.assertIn("maybe-loco", self.flags(review_row(ocr_text="EMD GP20 HORSEPOWER 2000")))
        self.assertNotIn("maybe-loco", self.flags(review_row(ocr_text="LD LMT 100000 CAPY")))
        self.assertNotIn("maybe-loco", self.flags(review_row(kind="loco", ocr_text="EMD GP20")))

    def test_two_letter_prefixes_need_digits(self):
        self.assertIn("maybe-loco", self.flags(review_row(ocr_text="a gp38 unit")))
        self.assertIn("maybe-loco", self.flags(review_row(ocr_text="SD-40")))
        self.assertNotIn("maybe-loco", self.flags(review_row(ocr_text="RS SW GP stencil")))

    def test_marks_like_nw_32800_are_not_a_locomotive(self):
        cfg = replace(self.cfg, loco_model_words=(*self.cfg.loco_model_words, "NW"))
        self.assertNotIn("maybe-loco", self.flags(review_row(ocr_text="NW 32800 LD LMT"), cfg=cfg))
        self.assertNotIn("maybe-loco", self.flags(review_row(ocr_text="NW32800"), cfg=cfg))

    def test_car_type_that_names_a_locomotive(self):
        self.assertIn("maybe-loco", self.flags(review_row(car_type="Diesel")))

    def test_ai_type_disagreeing_with_kind(self):
        rows = [review_row(photo="a.png"), review_row(photo="b.png", kind="loco")]
        batch.apply_ai_notes(rows, {"a.png": {"marks": "NW", "number": "32800", "type": "Diesel"},
                                    "b.png": {"marks": "NW", "number": "32800", "type": "Boxcar"}})
        self.assertEqual(rows[0]["flags"], "ai-says-loco")
        self.assertEqual(rows[1]["flags"], "ai-says-car")

    def test_kind_command_switches_and_clears_kind_flags(self):
        self.make_batch([review_row(photo="a.jpg", flags="maybe-loco;blurry", blur="5"), review_row(photo="b.jpg")])
        self.run_quiet(batch.set_kind, self.paths, self.cfg, "b1", "loco", ["a.jpg"])
        a, b = self.rows()
        self.assertEqual((a["kind"], a["roster_id"]), ("loco", "NW32800"))
        self.assertEqual(a["flags"], "blurry")
        self.assertEqual(b["kind"], "car")
        with self.assertRaises(SystemExit):
            batch.set_kind(self.paths, self.cfg, "b1", "loco", ["zz.jpg"])
        self.assertTrue((self.paths.batch("b1") / "review.html").is_file())

    def test_kind_only_changes_pending_rows(self):
        self.make_batch([review_row(status="approved")])
        self.run_quiet(batch.set_kind, self.paths, self.cfg, "b1", "loco", ["a.jpg"])
        self.assertEqual(self.rows()[0]["kind"], "car")

    def test_kind_remakes_the_picture_when_the_converted_copy_exists(self):
        self.paths.converted.mkdir(parents=True, exist_ok=True)
        (self.paths.converted / "a.png").write_bytes(b"x")
        self.make_batch([review_row(crop="1,2,100,100")])
        with mock.patch.object(loco, "loco_picture", wraps=loco.loco_picture) as made:
            self.run_quiet(batch.set_kind, self.paths, self.cfg, "b1", "loco", ["a.jpg"])
        made.assert_called_once()
        row = self.rows()[0]
        self.assertEqual((row["crop"], row["image"]), ("", "images/final/a.png"))

    def test_picker_views_are_remade_only_when_the_batch_has_them(self):
        out = self.make_batch([review_row()])
        self.run_quiet(batch.set_kind, self.paths, self.cfg, "b1", "loco", ["a.jpg"])
        self.assertEqual(self.prepared, [])
        (out / "picker.json").write_text("{}")
        self.run_quiet(batch.set_kind, self.paths, self.cfg, "b1", "car", ["a.jpg"])
        self.assertEqual(len(self.prepared), 1)


class PhotoTests(Base):
    def test_cars_and_locos_found_and_taken_skipped(self):
        for name in ("a.png", "b.jpg", "loco_c.png", "ENGINE_d.jpg", "known.png", "notes.txt", ".hidden.jpg"):
            self.add_photo(name)
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [{"photo": "known.png"}])
        found = batch.photos_to_review(self.paths)
        self.assertEqual([(p.name, k) for p, k in found],
                         [("ENGINE_d.jpg", "loco"), ("a.png", "car"), ("b.jpg", "car"), ("loco_c.png", "loco")])

    def test_photo_in_the_loco_file_or_another_batch_is_skipped(self):
        for name in ("a.png", "b.png", "c.png"):
            self.add_photo(name)
        fleet.write_rows(self.paths.locos_csv, schema.LOCO_COLUMNS, [{"photo": "a.png"}])
        self.make_batch([review_row(photo="b.png")], "older")
        self.assertEqual([p.name for p, _ in batch.photos_to_review(self.paths)], ["c.png"])

    def test_converted_copy_is_one_photo(self):
        self.add_photo("a.heic")
        self.add_photo("a.png")
        self.assertEqual(len(batch.photos_to_review(self.paths)), 1)


class ReviewTests(Base):
    def test_review_writes_a_batch_with_flags_and_a_page(self):
        self.add_photo("a.jpg", reporting_marks="NW", road_number="32800", ocr_text="NW 32800")
        self.add_photo("loco_b.jpg", reporting_marks="CSX", road_number="2121")
        self.add_photo("c.jpg", reporting_marks="NW", road_number="32800")
        self.blurs["c"] = 10.0
        self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        a, c, b = self.rows()
        self.assertEqual((a["photo"], a["kind"], a["roster_id"], a["image"], a["status"]),
                         ("a.jpg", "car", "NW32800", "images/final/a.png", "pending"))
        self.assertEqual(a["flags"], "")
        self.assertEqual((b["kind"], b["roster_id"]), ("loco", "CSX2121"))
        self.assertEqual(c["flags"], "blurry;same-id-as-a.jpg")
        self.assertTrue((self.paths.batch("b1") / "review.html").is_file())
        self.assertEqual(len(self.prepared), 1)

    def test_loco_goes_through_the_loco_picture_and_ocr_with_no_final(self):
        self.add_photo("loco_b.jpg")
        with mock.patch.object(image, "crop_car") as car:
            self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        car.assert_not_called()
        self.assertEqual(ocr.read.call_args.args[1], None)

    def test_one_failed_photo_does_not_stop_the_batch(self):
        self.add_photo("a.jpg", reporting_marks="NW", road_number="1")
        self.add_photo("bad.jpg")
        self.unreadable = {"bad"}
        self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        a, bad = self.rows()
        self.assertEqual((a["flags"], bad["flags"], bad["image"]), ("", "process-failed", ""))
        self.assertIn("cannot open", bad["note"])

    def test_process_failed_survives_a_later_flag_refresh(self):
        self.make_batch([review_row(photo="bad.jpg", flags="process-failed", image="", reporting_marks="",
                                    road_number="", roster_id="")])
        rows = self.rows()
        batch.set_flags(rows, self.cfg, self.paths)
        self.assertTrue(rows[0]["flags"].startswith("process-failed"))

    def test_number_length_is_flagged_on_the_first_review(self):
        for i, number in enumerate(["32800", "32801", "32802", "3280"]):
            self.add_photo(f"p{i}.jpg", reporting_marks="NW", road_number=number)
        self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        self.assertEqual([r["flags"] for r in self.rows()], ["", "", "", "number-length"])

    def test_default_batch_name_is_today_and_an_existing_one_is_refused(self):
        self.add_photo("a.jpg", reporting_marks="NW", road_number="1")
        self.run_quiet(batch.review, self.paths, self.cfg)
        name = date.today().isoformat()
        self.assertTrue((self.paths.batch(name) / "review.csv").is_file())
        (self.paths.incoming / "a.jpg").unlink()
        self.add_photo("z.jpg")
        with self.assertRaises(SystemExit) as err:
            batch.review(self.paths, self.cfg)
        self.assertIn("--batch", str(err.exception))
        self.run_quiet(batch.review, self.paths, self.cfg, "other")
        self.assertTrue((self.paths.batch("other") / "review.csv").is_file())

    def test_no_new_photos_says_where_to_put_them(self):
        self.assertIn("photos", self.run_quiet(batch.review, self.paths, self.cfg))
        self.assertEqual(list(self.paths.batches.iterdir()), [])

    def test_an_interrupted_review_leaves_no_half_made_batch(self):
        self.add_photo("a.jpg")
        with mock.patch.object(ocr, "read", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        self.assertFalse(self.paths.batch("b1").exists())

    def test_photo_in_the_fleet_is_not_reviewed_again(self):
        self.add_photo("a.jpg")
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [{"photo": "a.jpg"}])
        self.assertIn("No new photos", self.run_quiet(batch.review, self.paths, self.cfg, "b1"))

    def test_batch_that_is_remade_gets_a_new_storage_stamp(self):
        self.add_photo("a.jpg")
        self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        first = sheet.stamp(self.paths.batch("b1"))
        import shutil
        shutil.rmtree(self.paths.batch("b1"))
        self.run_quiet(batch.review, self.paths, self.cfg, "b1")
        self.assertNotEqual(first, sheet.stamp(self.paths.batch("b1")))


class ApproveRecordTests(Base):
    def setUp(self):
        super().setUp()
        self.make_batch([review_row(photo="ok.jpg", image="images/final/ok.png"),
                         review_row(photo="bad.jpg", flags="blurry", roster_id="NW1", road_number="1")])

    def test_approve_takes_only_unflagged(self):
        self.run_quiet(batch.approve, self.paths, self.cfg, "b1", True)
        self.assertEqual({r["photo"]: r["status"] for r in self.rows()}, {"ok.jpg": "approved", "bad.jpg": "pending"})

    def test_approve_waits_for_ai_unless_told(self):
        with self.assertRaises(SystemExit):
            batch.approve(self.paths, self.cfg, "b1", False)
        rows = self.rows()
        batch.apply_ai_notes(rows, {"ok.jpg": {"marks": "NW", "number": "32800"},
                                    "bad.jpg": {"marks": "NW", "number": "1"}})
        self.make_batch(rows)
        self.run_quiet(batch.approve, self.paths, self.cfg, "b1", False)
        self.assertEqual(self.rows()[0]["status"], "approved")

    def test_records_refuses_while_pending(self):
        self.run_quiet(batch.approve, self.paths, self.cfg, "b1", True)
        with self.assertRaises(SystemExit):
            batch.records(self.paths, self.cfg, "b1")
        self.assertFalse(self.paths.cars_csv.exists())

    def test_records_writes_fleet_and_manifest_and_marks_recorded(self):
        self.run_quiet(batch.approve, self.paths, self.cfg, "b1", True)
        self.run_quiet(batch.records, self.paths, self.cfg, "b1", False, True)
        cars = fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS)
        self.assertEqual([(c["roster_id"], c["photo"], c["batch"]) for c in cars], [("NW32800", "ok.jpg", "b1")])
        manifest = fleet.read_rows(self.paths.batch("b1") / "manifest.csv", schema.MANIFEST_COLUMNS)
        self.assertEqual([(m["photo"], m["outcome"], m["roster_id"]) for m in manifest],
                         [("ok.jpg", "new car NW32800", "NW32800")])
        self.assertEqual({r["photo"]: r["status"] for r in self.rows()},
                         {"ok.jpg": "recorded", "bad.jpg": "pending"})
        self.run_quiet(batch.records, self.paths, self.cfg, "b1", False, True)  # nothing recorded twice
        self.assertEqual(len(fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS)), 1)
        self.assertEqual(len(fleet.read_rows(self.paths.batch("b1") / "manifest.csv", schema.MANIFEST_COLUMNS)), 1)

    def test_dry_run_writes_nothing(self):
        self.run_quiet(batch.approve, self.paths, self.cfg, "b1", True)
        out = self.run_quiet(batch.records, self.paths, self.cfg, "b1", True, True)
        self.assertIn("new car NW32800", out)
        self.assertFalse(self.paths.cars_csv.exists())
        self.assertFalse((self.paths.batch("b1") / "manifest.csv").exists())
        self.assertEqual(self.rows()[0]["status"], "approved")

    def test_approved_row_without_marks_stops_before_anything_is_written(self):
        self.make_batch([review_row(photo="a.jpg", status="approved"),
                         review_row(photo="n.jpg", road_number="", status="approved")])
        with self.assertRaises(SystemExit) as err:
            batch.records(self.paths, self.cfg, "b1")
        self.assertIn("n.jpg", str(err.exception))
        self.assertFalse(self.paths.cars_csv.exists())

    def test_loco_row_is_recorded_as_a_loco(self):
        self.make_batch([review_row(photo="l.jpg", kind="loco", reporting_marks="CSX", road_number="2121",
                                    status="approved")])
        out = self.run_quiet(batch.records, self.paths, self.cfg, "b1")
        self.assertIn("new loco CSX2121; needs model", out)
        self.assertEqual(len(fleet.read_rows(self.paths.locos_csv, schema.LOCO_COLUMNS)), 1)

    def test_missing_batch_is_named(self):
        with self.assertRaises(SystemExit) as err:
            batch.approve(self.paths, self.cfg, "nope")
        self.assertIn("nope", str(err.exception))


class AiNotesTests(Base):
    def test_agreement_and_disagreement(self):
        rows = [review_row(photo="a.png"), review_row(photo="b.png")]
        unknown = batch.apply_ai_notes(rows, {
            "a.png": {"marks": "N W", "number": "32800", "type": "Flatcar"},
            "b.png": {"marks": "NW", "number": "32808", "note": "last digit is an 8"}})
        self.assertEqual(unknown, [])
        self.assertEqual(rows[0]["flags"], "")
        self.assertEqual(rows[1]["flags"], "ai-disagrees")
        self.assertEqual((rows[1]["status"], rows[1]["road_number"]), ("pending", "32800"))  # OCR untouched
        self.assertEqual((rows[0]["ai_note"], rows[1]["ai_note"]), ("reviewed", "last digit is an 8"))

    def test_rerun_does_not_duplicate_flag(self):
        rows = [review_row(photo="b.png")]
        for _ in range(2):
            batch.apply_ai_notes(rows, {"b.png": {"marks": "NW", "number": "1"}})
        self.assertEqual(rows[0]["flags"], "ai-disagrees")

    def test_unknown_photo_reported(self):
        self.assertEqual(batch.apply_ai_notes([review_row()], {"zz.png": {}}), ["zz.png"])

    def test_command_reads_the_json_file(self):
        self.make_batch([review_row(photo="a.jpg")])
        notes = self.tmp / "notes.json"
        notes.write_text(json.dumps({"a.jpg": {"marks": "NW", "number": "32800", "type": "Flat Car"}}))
        self.run_quiet(batch.ai_notes, self.paths, self.cfg, "b1", str(notes))
        self.assertEqual(self.rows()[0]["ai_note"], "reviewed")
        notes.write_text(json.dumps({"zz.jpg": {}}))
        with self.assertRaises(SystemExit):
            batch.ai_notes(self.paths, self.cfg, "b1", str(notes))

    def test_flag_refresh_keeps_ai_flags_current(self):
        rows = [review_row(photo="a.jpg", ai_note="reviewed", ai_marks="NW", ai_number="32808")]
        batch.set_flags(rows, self.cfg, self.paths)
        self.assertEqual(rows[0]["flags"], "ai-disagrees")
        rows[0]["road_number"] = "32808"  # the reader fixed the number
        batch.set_flags(rows, self.cfg, self.paths)
        self.assertEqual(rows[0]["flags"], "")


class FillTests(Base):
    def test_best_row_has_most_details_then_sharpest(self):
        a = review_row(photo="a", car_type="Hopper", lt_wt_lbs="42600", blur="100")
        b = review_row(photo="b", car_type="Hopper", lt_wt_lbs="42600", blur="900")
        c = review_row(photo="c", blur="5000")
        self.assertIs(batch.best_row([a, b, c]), b)

    def test_fill_copies_empty_details_from_the_same_road_and_type(self):
        self.make_batch([review_row(photo="a.jpg", road_number="1", car_type="Hopper", color="red",
                                    built="5-70", description="mine"),
                         review_row(photo="b.jpg", road_number="2", car_type="hopper", color="blue"),
                         review_row(photo="f.jpg", road_number="3", car_type="Flat Car")])
        out = self.run_quiet(batch.fill, self.paths, self.cfg, "b1", [], [])
        a, b, f = self.rows()
        self.assertEqual((b["built"], b["color"], b["description"]), ("5-70", "blue", ""))
        self.assertIn("b.jpg color reads blue", out)
        self.assertEqual((f["built"], f["color"]), ("", ""))  # a flat car takes nothing from a hopper

    def test_set_applies_to_the_named_photos_only(self):
        self.make_batch([review_row(photo="a.jpg", road_number="1", car_type="Hopper", built="5-70"),
                         review_row(photo="b.jpg", road_number="2", car_type="Hopper"),
                         review_row(photo="c.jpg", road_number="3", car_type="Hopper")])
        self.run_quiet(batch.fill, self.paths, self.cfg, "b1", ["b.jpg"], ["color = red"])
        a, b, c = self.rows()
        self.assertEqual((a["color"], b["color"], c["color"]), ("", "red", ""))
        self.assertEqual((b["built"], c["built"]), ("5-70", ""))  # only the named photo is filled
        self.assertEqual(b["description"], "")

    def test_set_without_photos_and_bad_column(self):
        self.make_batch([review_row(photo="a.jpg", road_number="1")])
        with self.assertRaises(SystemExit):
            batch.fill(self.paths, self.cfg, "b1", [], ["nope=1"])
        with self.assertRaises(SystemExit):
            batch.fill(self.paths, self.cfg, "b1", [], ["color"])
        with self.assertRaises(SystemExit):
            batch.fill(self.paths, self.cfg, "b1", ["zz.jpg"], ["color=red"])

    def test_recorded_and_loco_rows_are_left_alone(self):
        self.make_batch([review_row(photo="a.jpg", road_number="1", color="red"),
                         review_row(photo="l.jpg", kind="loco", road_number="2"),
                         review_row(photo="r.jpg", road_number="3", status="recorded")])
        self.run_quiet(batch.fill, self.paths, self.cfg, "b1", [], [])
        self.assertEqual([r["color"] for r in self.rows()], ["red", "", ""])

    def test_fill_flags_a_number_length_outlier(self):
        self.make_batch([review_row(photo=f"{i}.jpg", road_number=n)
                         for i, n in enumerate(["32800", "32801", "3280"])])
        self.run_quiet(batch.fill, self.paths, self.cfg, "b1", [], [])
        self.assertEqual([r["flags"] for r in self.rows()], ["", "", "number-length"])


class SheetImportTests(Base):
    def download(self, rows, name="down.csv"):
        path = self.tmp / name
        fleet.write_rows(path, schema.REVIEW_COLUMNS, rows)
        return str(path)

    def test_only_changed_crops_are_cut(self):
        old = [review_row(photo="a.jpg", crop="1,1,100,100", road_number="1"), review_row(photo="b.jpg", road_number="2"),
               review_row(photo="c.jpg", crop="5,5,100,100", road_number="3")]
        self.make_batch(old)
        new = [dict(r) for r in old]
        new[1]["crop"] = "2,2,200,100"   # newly picked
        new[2]["crop"] = "6,6,100,100"   # changed
        self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1", self.download(new))
        self.assertEqual([c[0] for c in self.cut], ["b.jpg", "c.jpg"])
        self.assertEqual([r["crop"] for r in self.rows()], ["1,1,100,100", "2,2,200,100", "6,6,100,100"])
        self.assertEqual(self.rows()[1]["crop_status"], "ok")

    def test_sheet_without_a_crop_column_still_imports(self):
        self.make_batch([review_row(photo="a.jpg")])
        cols = [c for c in schema.REVIEW_COLUMNS if c != "crop"]
        path = self.tmp / "down.csv"
        fleet.write_rows(path, cols, [review_row(photo="a.jpg")])
        self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1", str(path))
        self.assertEqual(self.rows()[0]["crop"], "")

    def test_recorded_rows_survive_the_import(self):
        old = [review_row(photo="a.jpg", status="recorded", color="red", road_number="1"),
               review_row(photo="b.jpg", road_number="2")]
        self.make_batch(old)
        new = [dict(r) for r in old]
        new[0].update(status="pending", color="blue", crop="9,9,99,99")  # the page could not have meant this
        new[1].update(status="approved", color="green")
        self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1", self.download(new))
        a, b = self.rows()
        self.assertEqual((a["status"], a["color"], a["crop"]), ("recorded", "red", ""))
        self.assertEqual((b["status"], b["color"]), ("approved", "green"))
        self.assertEqual(self.cut, [])

    def test_a_recorded_status_in_the_download_for_a_pending_row_is_refused(self):
        self.make_batch([review_row(photo="a.jpg")])
        with self.assertRaises(SystemExit):
            batch.sheet_import(self.paths, self.cfg, "b1", self.download([review_row(photo="a.jpg", status="recorded")]))

    def test_a_sheet_for_another_batch_is_refused(self):
        self.make_batch([review_row(photo="a.jpg")])
        with self.assertRaises(SystemExit):
            batch.sheet_import(self.paths, self.cfg, "b1", self.download([review_row(photo="zz.jpg")]))

    def test_only_the_pages_fields_are_taken(self):
        self.make_batch([review_row(photo="a.jpg", image="images/final/a.png", ocr_text="real")])
        edited = review_row(photo="a.jpg", image="stale.png", ocr_text="changed", color="red", road_number="32800")
        self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1", self.download([edited]))
        row = self.rows()[0]
        self.assertEqual((row["image"], row["ocr_text"], row["color"]), ("images/final/a.png", "real", "red"))

    def test_flags_and_ids_are_worked_out_again(self):
        self.make_batch([review_row(photo="a.jpg", road_number="", roster_id="", flags="no-number")])
        self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1",
                       self.download([review_row(photo="a.jpg", road_number="77")]))
        row = self.rows()[0]
        self.assertEqual((row["roster_id"], row["flags"]), ("NW77", ""))

    def test_failed_cut_keeps_the_old_crop(self):
        self.make_batch([review_row(photo="a.jpg", crop="1,1,100,100")])
        with mock.patch.object(picker, "apply", side_effect=SystemExit("box too small")):
            out = self.run_quiet(batch.sheet_import, self.paths, self.cfg, "b1",
                                 self.download([review_row(photo="a.jpg", crop="1,1,10,10")]))
        self.assertIn("crop failed", out)
        self.assertEqual(self.rows()[0]["crop"], "1,1,100,100")


class CropTests(Base):
    def test_box_cuts_one_picture_and_rewrites_the_page(self):
        self.make_batch([review_row(photo="a.jpg", crop_status="review", flags="crop-review", blur="5")])
        self.run_quiet(batch.crop, self.paths, self.cfg, "b1", "a.jpg", "1,2,300,200")
        self.assertEqual(self.cut, [("a.jpg", "1,2,300,200")])
        row = self.rows()[0]
        self.assertEqual((row["crop"], row["blur"], row["flags"]), ("1,2,300,200", "2000", ""))

    def test_refresh_rebuilds_the_views(self):
        self.make_batch([review_row()])
        self.run_quiet(batch.crop, self.paths, self.cfg, "b1", None, None, True)
        self.assertEqual(self.prepared, [{"force": True}])

    def test_bad_requests(self):
        self.make_batch([review_row(), review_row(photo="r.jpg", status="recorded")])
        for args in (("zz.jpg", "1,1,100,100"), ("a.jpg", None), ("r.jpg", "1,1,100,100")):
            with self.assertRaises(SystemExit):
                batch.crop(self.paths, self.cfg, "b1", *args)


if __name__ == "__main__":
    unittest.main()


class ReviewFindings(Base):
    """Cases from the code review of the first full build."""

    def test_fill_takes_only_page_fields_and_a_valid_named_status(self):
        self.make_batch([review_row(photo="a.jpg"), review_row(photo="b.jpg", road_number="2")])
        for sets, photos in ((["status=aproved"], ["a.jpg"]), (["status=approved"], []),
                             (["status=recorded"], ["a.jpg"]), (["kind=loco"], ["a.jpg"]),
                             (["image=x.png"], ["a.jpg"]), (["roster_id=Z"], ["a.jpg"])):
            with self.assertRaises(SystemExit, msg=sets):
                batch.fill(self.paths, self.cfg, "b1", photos, sets)
        self.run_quiet(batch.fill, self.paths, self.cfg, "b1", ["a.jpg"], ["status=approved"])
        self.assertEqual([r["status"] for r in self.rows()], ["approved", "pending"])

    def test_a_pending_row_is_flagged_against_an_approved_one(self):
        rows = [review_row(photo="a.jpg", road_number="1234", roster_id="NW1234", status="approved"),
                review_row(photo="b.jpg", road_number="1234")]
        batch.set_flags(rows, self.cfg, self.paths)
        self.assertIn("same-id-as-a.jpg", rows[1]["flags"])
        rows[0]["status"] = "rejected"
        batch.set_flags(rows, self.cfg, self.paths)
        self.assertNotIn("same-id", rows[1]["flags"])

    def test_a_copy_of_a_reviewed_photo_under_another_suffix_is_not_new(self):
        for name in ("IMG_1.png", "IMG_1.jpg", "IMG_2.jpg"):
            self.add_photo(name)
        self.make_batch([review_row(photo="IMG_1.png")])
        self.assertEqual([p.name for p, _ in batch.photos_to_review(self.paths)], ["IMG_2.jpg"])

    def test_null_and_bad_ai_notes(self):
        rows = [review_row(photo="a.jpg")]
        batch.apply_ai_notes(rows, {"a.jpg": {"marks": None, "number": None, "type": "Hopper", "note": None}})
        self.assertEqual((rows[0]["ai_marks"], rows[0]["ai_number"], rows[0]["ai_note"]), ("", "", "reviewed"))
        with self.assertRaises(SystemExit):
            batch.apply_ai_notes(rows, ["a.jpg"])
        with self.assertRaises(SystemExit):
            batch.apply_ai_notes(rows, {"a.jpg": "NW 32800"})

    def test_dry_run_reports_a_second_photo_of_one_car_as_skipped(self):
        self.make_batch([review_row(photo="a.jpg", status="approved", image="images/final/a.png"),
                         review_row(photo="b.jpg", status="approved", image="images/final/b.png")])
        out = self.run_quiet(batch.records, self.paths, self.cfg, "b1", dry_run=True)
        self.assertIn("a.jpg: new car NW32800", out)
        self.assertIn("b.jpg: skipped: NW32800 already has a picture", out)
