"""The cards command: init, print and mark-printed, locos, status, and a run from init to print."""
import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from helpers import CardFolder, PHOTOS
from test_batch import Fakes
from cards import cli, config, fleet, layout, schema


def run(*argv) -> str:
    with redirect_stdout(io.StringIO()) as out:
        code = cli.main(list(argv))
    assert code == 0, out.getvalue()
    return out.getvalue()


class InFolder:
    """Mixin: run commands with the card folder as the current directory."""

    def enter(self, folder: Path):
        self.before = Path.cwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, self.before)


class Init(InFolder, unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cards-init-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.enter(self.tmp)

    def test_init_makes_settings_and_folders(self):
        out = run("init", "--name", "Test Valley Railroad", "--short", "TVR")
        cfg = config.load(self.tmp)
        self.assertEqual((cfg.railroad_name, cfg.short_name), ("Test Valley Railroad", "TVR"))
        for folder in ("photos/incoming", "batches", "images/final", "data", "output"):
            self.assertTrue((self.tmp / folder).is_dir(), folder)
        self.assertIn("cards review", out)

    def test_init_refuses_an_existing_cards_toml(self):
        (self.tmp / "cards.toml").write_text("# mine\n")
        with self.assertRaises(SystemExit):
            cli.main(["init"])
        self.assertEqual((self.tmp / "cards.toml").read_text(), "# mine\n")
        self.assertFalse((self.tmp / "batches").exists())

    def test_other_commands_need_a_card_folder(self):
        with self.assertRaises(SystemExit) as err:
            cli.main(["status"])
        self.assertIn("cards init", str(err.exception))

    def test_commands_find_the_folder_from_a_subfolder(self):
        run("init")
        self.enter(self.tmp / "photos")
        self.assertIn("Batches: 0", run("status"))


class FakeLayout:
    """Stands in for layout (builder 3c): cards are plain, the sheet is a text file listing them."""

    def __init__(self):
        self.built = []

    def start(self, case):
        def card(kind):
            return lambda row, paths, cfg: layout.Card(kind, kind.upper(), row["reporting_marks"], row["road_number"],
                                                       row["description"], None)

        def build(cards, out, cfg):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(f"{c.road_name} {c.road_number}" for c in cards))
            self.built.append([c.road_number for c in cards])
            return out

        def calibration(out, cfg):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("calibration")
            return out

        for target, fn in (("card_for_car", card("car")), ("card_for_loco", card("loco")),
                           ("build_sheet", build), ("calibration_page", calibration)):
            p = mock.patch.object(layout, target, side_effect=fn)
            p.start()
            case.addCleanup(p.stop)


class Printing(InFolder, CardFolder):
    def setUp(self):
        super().setUp()
        self.enter(self.tmp)
        self.layout = FakeLayout()
        self.layout.start(self)
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [
            {"roster_id": "NW1", "reporting_marks": "NW", "road_number": "1"},
            {"roster_id": "NW2", "reporting_marks": "NW", "road_number": "2", "card_built": "2026-01-01",
             "card_printed": "2026-01-02"}])
        fleet.write_rows(self.paths.locos_csv, schema.LOCO_COLUMNS, [
            {"roster_id": "CSX9", "reporting_marks": "CSX", "road_number": "9", "model": "GP38", "loco_type": "Diesel"},
            {"roster_id": "CSX10", "reporting_marks": "CSX", "road_number": "10", "loco_type": "Diesel"}])

    def cars(self):
        return {r["roster_id"]: r for r in fleet.read_rows(self.paths.cars_csv, schema.CAR_COLUMNS)}

    def locos(self):
        return {r["roster_id"]: r for r in fleet.read_rows(self.paths.locos_csv, schema.LOCO_COLUMNS)}

    def test_print_builds_cards_not_yet_printed_cars_then_locos(self):
        out = run("print")
        self.assertEqual(self.layout.built, [["1", "9"]])
        today = date.today().isoformat()
        self.assertTrue((self.paths.output / f"cards_{today}.docx").is_file())
        self.assertEqual((self.cars()["NW1"]["card_built"], self.cars()["NW2"]["card_built"]), (today, "2026-01-01"))
        self.assertEqual(self.locos()["CSX9"]["card_built"], today)
        self.assertIn("skipped CSX10: needs model", out)
        self.assertEqual(self.locos()["CSX10"]["card_built"], "")
        self.assertIn("cards print --mark-printed", out)

    def test_all_includes_printed_cards(self):
        run("print", "--all")
        self.assertEqual(self.layout.built, [["1", "2", "9"]])

    def test_mark_printed_builds_nothing_and_marks_only_built_cards(self):
        run("print")
        self.layout.built.clear()
        out = run("print", "--mark-printed")
        self.assertEqual(self.layout.built, [])
        today = date.today().isoformat()
        self.assertEqual((self.cars()["NW1"]["card_printed"], self.cars()["NW2"]["card_printed"]), (today, "2026-01-02"))
        self.assertEqual(self.locos()["CSX9"]["card_printed"], today)
        self.assertEqual(self.locos()["CSX10"]["card_printed"], "")  # never built
        self.assertIn("Marked 2", out)
        self.assertIn("No cards waiting", run("print"))  # NW1 and CSX9 are done; the rest are skipped or printed

    def test_nothing_waiting_says_what_to_do(self):
        fleet.write_rows(self.paths.cars_csv, schema.CAR_COLUMNS, [])
        fleet.write_rows(self.paths.locos_csv, schema.LOCO_COLUMNS, [])
        self.assertIn("No cards waiting", run("print"))
        self.assertEqual(self.layout.built, [])

    def test_calibrate_writes_the_page_and_touches_no_rows(self):
        out = run("print", "--calibrate")
        self.assertTrue((self.paths.output / "calibration.docx").is_file())
        self.assertEqual(self.cars()["NW1"]["card_built"], "")
        self.assertIn("calibration.docx", out)

    def test_status_counts_fleet_and_waiting_cards(self):
        out = run("status")
        self.assertIn("Fleet: 2 cars, 2 locomotives", out)
        self.assertIn("Cards waiting to print: 3", out)
        self.assertIn("CSX10", out)

    def test_locos_set_and_status(self):
        self.assertIn("CSX10", run("locos", "status"))
        out = run("locos", "set", "CSX10", "model=SW1500", "hp=1500")
        self.assertIn("still needs: nothing", out)
        row = self.locos()["CSX10"]
        self.assertEqual((row["model"], row["hp"], row["card_built"]), ("SW1500", "1500", ""))
        run("print")
        self.assertEqual(self.layout.built, [["1", "9", "10"]])

    def test_locos_set_refuses_unknown_loco_or_column(self):
        with self.assertRaises(SystemExit):
            cli.main(["locos", "set", "XX1", "model=A"])
        with self.assertRaises(SystemExit):
            cli.main(["locos", "set", "CSX10", "wheels=8"])
        with self.assertRaises(SystemExit):
            cli.main(["locos", "set", "CSX10", "roster_id=Z"])

    def test_locos_set_keeps_bookkeeping_and_ids_unique(self):
        for field in ("image=x.png", "photo=x.jpg", "card_printed=2026-01-01", "batch=b9"):
            with self.assertRaises(SystemExit, msg=field):
                cli.main(["locos", "set", "CSX10", field])
        other = dict(self.locos()["CSX10"], roster_id="CSX11", road_number="11")
        rows = list(self.locos().values()) + [other]
        fleet.write_rows(self.paths.locos_csv, schema.LOCO_COLUMNS, rows)
        with self.assertRaises(SystemExit):
            cli.main(["locos", "set", "CSX10", "road_number=11"])

    def test_locos_set_marks_and_number_change_the_id(self):
        run("locos", "set", "CSX10", "road_number=11")
        self.assertIn("CSX11", self.locos())


class EndToEnd(Fakes, InFolder, unittest.TestCase):
    """init, review, ai-notes, approve, records, print, mark-printed, with image/OCR/layout replaced."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cards-e2e-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.enter(self.tmp)
        run("init", "--name", "Test Valley Railroad")
        from cards.paths import Paths
        self.paths = Paths(self.tmp)
        self.start_fakes()
        self.layout = FakeLayout()
        self.layout.start(self)

    def test_from_init_to_print(self):
        shutil.copy(PHOTOS / "flatcar.jpg", self.paths.incoming / "flatcar.jpg")
        shutil.copy(PHOTOS / "loco.jpg", self.paths.incoming / "loco_2121.jpg")
        self.readings = {"flatcar": {"reporting_marks": "NW", "road_number": "32800", "car_type": "Flat Car"},
                         "loco_2121": {"reporting_marks": "CSX", "road_number": "2121"}}
        self.assertIn("2 photos, 0 flagged", run("review", "--batch", "b1"))
        self.assertIn("pending", run("status"))
        with self.assertRaises(SystemExit):
            cli.main(["approve", "b1"])  # no photo-reader note yet
        notes = self.tmp / "notes.json"
        notes.write_text('{"flatcar.jpg": {"marks": "NW", "number": "32800"}, '
                         '"loco_2121.jpg": {"marks": "CSX", "number": "2121", "type": "Diesel"}}')
        run("ai-notes", "b1", str(notes))
        self.assertIn("Approved 2", run("approve", "b1"))
        self.assertIn("new car NW32800", run("records", "b1", "--dry-run"))
        self.assertFalse(self.paths.cars_csv.exists())
        out = run("records", "b1")
        self.assertIn("new loco CSX2121; needs model", out)
        self.assertIn("Cards waiting to print: 2", run("status"))
        self.assertIn("skipped CSX2121: needs model", run("print"))
        self.assertEqual(self.layout.built[-1], ["32800"])
        run("print", "--mark-printed")
        run("locos", "set", "CSX2121", "model=GP38")
        run("print")
        self.assertEqual(self.layout.built[-1], ["2121"])
        self.assertIn("Marked 1", run("print", "--mark-printed"))
        self.assertIn("No cards waiting", run("print"))
        self.assertTrue(self.paths.batch("b1").joinpath("manifest.csv").is_file())
        self.assertEqual(run("status").count("Cards waiting to print: 0"), 1)


if __name__ == "__main__":
    unittest.main()
