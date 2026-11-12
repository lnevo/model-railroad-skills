"""The approved fleet: roster ids, CSV reading and writing, and recording review rows."""
import unittest

from helpers import CardFolder
from cards import fleet, schema


def review(**kw):
    row = {c: "" for c in schema.REVIEW_COLUMNS}
    row.update(photo="a.jpg", kind="car", reporting_marks="NW", road_number="32800", car_type="Flat Car",
               length_ft="52", image="images/final/a.png", status="approved")
    row.update(kw)
    return row


class RosterId(CardFolder):
    toml = ""

    def test_code_and_digits_no_space(self):
        self.assertEqual(fleet.roster_id("nw", "32800", self.cfg), "NW32800")
        self.assertEqual(fleet.roster_id(" C S X ", "No. 379808", self.cfg), "CSX379808")

    def test_missing_part_gives_blank(self):
        self.assertEqual(fleet.roster_id("", "32800", self.cfg), "")
        self.assertEqual(fleet.roster_id("NW", "", self.cfg), "")
        self.assertEqual(fleet.roster_id("NW", "abc", self.cfg), "")

    def test_aliases_come_from_the_settings(self):
        from dataclasses import replace
        cfg = replace(self.cfg, road_aliases={"N&W": "NW"})
        self.assertEqual(fleet.roster_id("N&W", "1", cfg), "NW1")


class Csv(CardFolder):
    def test_missing_file_is_empty_and_columns_are_filled(self):
        self.assertEqual(fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS), [])
        fleet.write_rows(self.paths.cars_csv, ["roster_id", "color"], [{"roster_id": "X1", "color": "red"}])
        rows = fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS)
        self.assertEqual(set(rows[0]), set(schema.CAR_COLUMNS))
        self.assertEqual((rows[0]["roster_id"], rows[0]["color"], rows[0]["photo"]), ("X1", "red", ""))

    def test_write_is_atomic_and_leaves_no_temp_file(self):
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [{"roster_id": "X1"}])
        self.assertEqual([p.name for p in self.paths.data.iterdir()], ["cars.csv"])


class Record(CardFolder):
    def cars(self):
        return fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS)

    def test_new_car(self):
        out = fleet.record(review(), "b1", self.paths, self.cfg)
        self.assertEqual(out, "new car NW32800")
        row = self.cars()[0]
        self.assertEqual((row["roster_id"], row["car_type"], row["photo"], row["batch"]),
                         ("NW32800", "Flat Car", "a.jpg", "b1"))
        self.assertEqual(row["image"], "images/final/a.png")
        self.assertTrue(row["recorded"])
        self.assertEqual((row["card_built"], row["card_printed"]), ("", ""))

    def test_absolute_image_path_is_stored_relative(self):
        image = self.paths.final / "a.png"
        fleet.record(review(image=str(image)), "b1", self.paths, self.cfg)
        self.assertEqual(self.cars()[0]["image"], "images/final/a.png")

    def test_photo_added_to_a_car_without_one_asks_for_a_new_card(self):
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [
            {"roster_id": "NW32800", "reporting_marks": "NW", "road_number": "32800", "color": "black",
             "card_built": "2026-01-01", "card_printed": "2026-01-02"}])
        out = fleet.record(review(color=""), "b1", self.paths, self.cfg)
        self.assertEqual(out, "photo added to NW32800")
        row = self.cars()[0]
        self.assertEqual((row["image"], row["color"], row["card_printed"]), ("images/final/a.png", "black", ""))

    def test_car_with_a_picture_is_skipped(self):
        fleet.record(review(), "b1", self.paths, self.cfg)
        out = fleet.record(review(photo="b.jpg", image="images/final/b.png"), "b2", self.paths, self.cfg)
        self.assertEqual(out, "skipped: NW32800 already has a picture")
        self.assertEqual(len(self.cars()), 1)
        self.assertEqual(self.cars()[0]["photo"], "a.jpg")

    def test_dry_run_writes_nothing(self):
        out = fleet.record(review(), "b1", self.paths, self.cfg, dry_run=True)
        self.assertEqual(out, "new car NW32800")
        self.assertFalse(self.paths.cars_csv.exists())

    def test_car_without_marks_or_number_is_refused(self):
        with self.assertRaises(SystemExit):
            fleet.record(review(road_number=""), "b1", self.paths, self.cfg)

    def test_new_loco_gets_the_default_type_and_lists_what_is_missing(self):
        out = fleet.record(review(kind="loco", reporting_marks="CSX", road_number="2121"),
                           "b1", self.paths, self.cfg)
        self.assertEqual(out, "new loco CSX2121; needs model")
        row = fleet.read_rows(self.paths.locos_csv, schema.LOCO_COLUMNS)[0]
        self.assertEqual((row["loco_type"], row["model"]), ("Diesel", ""))
        self.assertFalse(self.paths.cars_csv.exists())

    def test_loco_details_survive_a_later_photo(self):
        fleet.write_rows(self.paths.locos_csv, schema.LOCO_COLUMNS, [
            {"roster_id": "CSX2121", "reporting_marks": "CSX", "road_number": "2121", "model": "GP38",
             "loco_type": "Steam"}])
        out = fleet.record(review(kind="loco", reporting_marks="CSX", road_number="2121"),
                           "b1", self.paths, self.cfg)
        self.assertEqual(out, "photo added to CSX2121")
        row = fleet.read_rows(self.paths.locos_csv, schema.LOCO_COLUMNS)[0]
        self.assertEqual((row["model"], row["loco_type"], row["photo"]), ("GP38", "Steam", "a.jpg"))

    def test_missing_loco_fields(self):
        self.assertEqual(fleet.missing_loco_fields({"reporting_marks": "CSX", "road_number": "1"}),
                         ["model", "loco_type"])


if __name__ == "__main__":
    unittest.main()
