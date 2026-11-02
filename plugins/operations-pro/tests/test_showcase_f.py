"""Showcase batch F: train schedule days (U14), the Evening Session automation (U15), paperwork (U17),
on-time build order (U20) and backups (U23).

The base is the skeleton plus build/60_f.json only, replayed on a fresh copy. The other batches' objects are
not there, so each test adds a small stand-in on its own copy (marked "stand-in"); stage 4 asserts the
same behaviour on the merged railroad. JMRI-backed tests skip where JMRI is not installed.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "showcase"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_store import Refused  # noqa: E402

JMRI = unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")

TUESDAY = ["CUSTOM", "MIXED", "SWAP-E", "SWAP-W", "MODE", "LOCAL-B", "FIDDLE JOB", "LOCAL-H", "KESSOCK TRANSFER",
           "KESSOCK SWITCHER", "SAWYER SWITCHER", "EAST FREIGHT", "THRU", "NORTH JOB", "PELL SWITCHER", "HOP OUT",
           "TURN", "VALLEY FLYER"]
SATURDAY = ["SWAP-E", "SWAP-W", "EAST FREIGHT", "HOP OUT", "NORTH JOB", "VALLEY FLYER"]
# What builds while the automation runs on its own thread: enough work to outlast its five steps.
OTHERS = [t for t in TUESDAY if t not in ("LOCAL-H", "LOCAL-B", "MODE", "SWAP-E", "SWAP-W")]

BASE = None
TEMP = None


def _builder():
    spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setUpModule():
    global BASE, TEMP
    TEMP = tempfile.TemporaryDirectory()
    BASE = Path(TEMP.name) / "base"
    builder = _builder()
    shutil.copytree(ROOT / "servers" / "blank", BASE)
    with mock.patch.object(ops_store, "running_jmri", lambda *a, **k: []):
        for name in ("00_skeleton.json", "60_f.json"):
            for index, step in enumerate(json.loads((SHOWCASE / "build" / name).read_text(encoding="utf-8")), 1):
                builder.run_step(BASE, step, f"{name} step {index}")


def tearDownModule():
    TEMP.cleanup()


class Case(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ops_store, "running_jmri", lambda *a, **k: [])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)

    def copy(self, name="ops"):
        target = Path(self.work.name) / name
        shutil.copytree(BASE, target)
        return target

    def edit(self, folder, actions):
        plan = ops_store.plan(folder, actions)
        ops_store.apply(plan["plan_id"], True)

    def standin_car(self, folder, number="9901"):
        """Stand-in: one boxcar on Carrow Yard and a Dunmere spur whose only line needs Tuesday."""
        self.edit(folder, [
            {"action": "add_industry", "location": "Dunmere", "name": "Standin Dock", "length": 100,
             "lines": [{"type": "Boxcar", "receive": "E", "ship": "L", "setout_day": "Tuesday"}]},
            {"action": "add_car", "road": "JFN", "number": number, "type": "Boxcar", "length": 40,
             "location": "Carrow", "track": "Carrow Yard"}])

    def gate(self, folder, code, car="JFN 9901", destination="Dunmere", track="Standin Dock", train="LOCAL-B"):
        result = ops_gates.Gates(ops_data.load(folder)).why_not(car, destination, track, train, real_build=False)
        return next(g for g in result["gates"] if g["gate"] == code)


class U14Days(Case):
    def test_days_list_and_active_day(self):
        import operations_pro
        days = {d["name"]: d for d in operations_pro.list_items({"type": "days", "ops_dir": str(BASE)})}
        trains = {t["id"]: t["name"] for t in operations_pro.list_items({"type": "trains", "ops_dir": str(BASE)})}
        self.assertEqual(sorted(trains[i] for i in days["Tuesday"]["trains"]), sorted(TUESDAY))
        self.assertEqual(sorted(trains[i] for i in days["Saturday"]["trains"]), sorted(SATURDAY))
        self.assertEqual([n for n, d in days.items() if d["active"]], ["Tuesday"])
        listed = operations_pro.list_items({"type": "trains", "ops_dir": str(BASE)})
        self.assertTrue(all(t["build"] for t in listed))  # apply_day Tuesday left every Build box on

    def test_tuesday_line_passes_and_saturday_fails(self):
        """Stand-in spur. Merged railroad: DAYX 1 -> Tuesday Dock, same gates (F1, A1)."""
        folder = self.copy()
        self.standin_car(folder)
        self.assertEqual(self.gate(folder, "A1")["status"], "pass")
        self.assertEqual(self.gate(folder, "F1")["status"], "pass")
        self.edit(folder, [{"action": "set_active_day", "name": "Saturday"}, {"action": "apply_day", "day": "Saturday"}])
        self.assertEqual(self.gate(folder, "A1")["status"], "fail")
        self.assertEqual(self.gate(folder, "F1")["status"], "fail")

    @JMRI
    def test_jmri_builds_only_the_active_days_trains(self):
        folder = self.copy()
        self.standin_car(folder)
        tuesday = ops_jmri.run_worker(folder, {"build": True})
        self.assertEqual(sorted(tuesday["builds"]), sorted(TUESDAY))
        self.assertIn("Active schedule: Tuesday", tuesday["builds"]["LOCAL-B"]["report_text"])
        self.assertEqual(tuesday["builds"]["LOCAL-B"]["cars"], ["JFN9901 > Dunmere / Standin Dock"])
        self.edit(folder, [{"action": "set_active_day", "name": "Saturday"}, {"action": "apply_day", "day": "Saturday"}])
        saturday = ops_jmri.run_worker(folder, {"build": True})
        self.assertEqual(sorted(saturday["builds"]), sorted(SATURDAY))
        self.assertIn("Active schedule: Saturday", saturday["builds"]["SWAP-E"]["report_text"])


class U15Automation(Case):
    def test_steps_and_refusal(self):
        folder = self.copy()
        autos = {a["name"]: a for a in ops_data.read_automations(folder)}
        steps = lambda name: [(s["do"]) for s in autos[name]["steps"]]  # noqa: E731
        self.assertEqual(steps("Evening Session"), ["build_train", "build_train", "run_automation",
                                                    "wait_for_train_to_terminate", "terminate_train"])
        self.assertEqual(steps("Close Out"), ["terminate_train"])
        self.assertFalse(any(a["startup"] for a in autos.values()))
        with self.assertRaises(Refused) as caught:
            ops_store.plan(folder, [{"action": "update_automation", "automation": "Evening Session", "steps": [
                {"do": "build_train", "train": "LOCAL-H"}, {"do": "message_yes_no", "message": "Continue?"}]}])
        self.assertIn("allow_dialogs", str(caught.exception))

    @JMRI
    def test_jmri_runs_it_at_load(self):
        """Stand-in: LOCAL-H needs a caboose that batch C adds, so its requirement is dropped on this copy."""
        folder = self.copy()
        self.edit(folder, [{"action": "update_train", "train": "LOCAL-H", "requires": 0},
                           {"action": "set_startup_automation", "automation": "Evening Session"}])
        keep = Path(self.work.name) / "kept"
        # The automation runs on its own thread and run_worker saves as soon as its own job ends. Building the
        # other trains keeps the worker alive, but a loaded machine can still save too early: try up to three
        # times for a save that came after the last step. What ran is always asserted exactly.
        for _ in range(3):
            shutil.rmtree(keep, ignore_errors=True)
            keep.mkdir()
            ops_jmri.run_worker(folder, {"save": True, "build": True, "only": OTHERS}, keep)
            autos = {a["name"]: a for a in ops_data.read_automations(keep)}
            if autos["Evening Session"]["steps"][-1]["ran"]:
                break
        self.assertEqual([(s["do"], s["ran"], s["successful"]) for s in autos["Evening Session"]["steps"]],
                         [("build_train", True, True), ("build_train", True, True), ("run_automation", True, True),
                          ("wait_for_train_to_terminate", True, True), ("terminate_train", True, True)])
        self.assertTrue(autos["Close Out"]["steps"][0]["ran"])
        built = {t.name: t.built for t in ops_data.load(keep).trains.values()} \
            if isinstance(ops_data.load(keep).trains, dict) else \
            {t.name: t.built for t in ops_data.load(keep).trains}
        self.assertFalse(built["LOCAL-H"])
        self.assertFalse(built["LOCAL-B"])

    @JMRI
    def test_wait_after_own_terminate_never_finishes(self):
        """Why Close Out exists: a wait step for a train this same automation already terminated stalls."""
        folder = self.copy()
        self.edit(folder, [
            {"action": "update_train", "train": "LOCAL-H", "requires": 0},
            {"action": "update_automation", "automation": "Evening Session", "steps": [
                {"do": "build_train", "train": "LOCAL-B"}, {"do": "terminate_train", "train": "LOCAL-B"},
                {"do": "wait_for_train_to_terminate", "train": "LOCAL-B"}, {"do": "terminate_train", "train": "LOCAL-H"}]},
            {"action": "set_startup_automation", "automation": "Evening Session"}])
        keep = Path(self.work.name) / "kept"
        keep.mkdir()
        ops_jmri.run_worker(folder, {"save": True, "build": True, "only": OTHERS}, keep)
        steps = next(a for a in ops_data.read_automations(keep) if a["name"] == "Evening Session")["steps"]
        self.assertEqual([s["ran"] for s in steps], [True, True, False, False])


class U17Paperwork(Case):
    def test_settings_in_the_file(self):
        rr = ops_data.load(BASE)
        self.assertEqual(rr.manifest_texts["manifest"]["valid"], "Conductor''s copy, valid {0}")
        options = {o["name"]: o["value"] for o in json.loads(json.dumps(self._listing()))}
        self.assertEqual((options["pickup_color"], options["drop_color"], options["local_color"]),
                         ("red", "blue", "green"))
        self.assertEqual(options["pickup_car"]["fields"], ["Road", "Number", "Type", "Length", "Load", "Track"])
        self.assertEqual(options["train LOCAL-B"]["railroad_name"], "Brae Branch Lines")
        self.assertEqual(options["train LOCAL-H"]["railroad_name"], "")

    def _listing(self):
        import operations_pro
        return operations_pro.list_items({"type": "manifest", "ops_dir": str(BASE)})

    def test_unmatched_brace_is_refused(self):
        with self.assertRaises(Refused) as caught:
            ops_store.plan(BASE, [{"action": "set_manifest_text", "group": "manifest", "key": "valid",
                                   "text": "Valid {0"}])
        self.assertIn("a { must open a numbered argument", str(caught.exception))

    @JMRI
    def test_jmri_prints_it(self):
        """Stand-in car and spur so LOCAL-B has work; merged railroad: LOCAL-B's own cars."""
        folder = self.copy()
        self.standin_car(folder)
        keep = Path(self.work.name) / "kept"
        keep.mkdir()
        ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-B", "FIDDLE JOB"]}, keep)
        local_b = (keep / "manifests" / "train (LOCAL-B).txt").read_text(encoding="utf-8")
        fiddle = (keep / "manifests" / "train (FIDDLE JOB).txt").read_text(encoding="utf-8")
        self.assertTrue(local_b.startswith("Brae Branch Lines"))
        self.assertNotIn("Brae Branch Lines", fiddle)
        for text in (local_b, fiddle):
            self.assertIn("Conductor's copy, valid ", text)
            self.assertNotIn("''", text)
        self.assertIn('<FONT color="red"> [ ] Pick up JFN 9901 Boxcar 40\' E from Carrow Yard</FONT>', local_b)
        self.assertIn('<FONT color="blue"> [ ] Set out JFN 9901 Boxcar 40\' E to Standin Dock</FONT>', local_b)


class U20OnTime(Case):
    def _on_time_copy(self, late_hour=None):
        folder = self.copy()
        actions = [{"action": "update_train", "train": "LOCAL-H", "requires": 0},  # stand-in: batch C's caboose
                   {"action": "set_option", "group": "buildOptions", "name": "onTime", "value": True}]
        if late_hour:
            actions.append({"action": "update_train", "train": "LOCAL-B", "depart_hour": late_hour})
        self.edit(folder, actions)
        self.standin_car(folder, "9902")
        return folder

    def test_ships_with_on_time_off(self):
        self.assertFalse(ops_data.load(BASE).option("buildOptions", "onTime") in (True, "true"))

    @JMRI
    def test_earlier_train_aborts_after_a_later_one(self):
        folder = self._on_time_copy()
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        first = ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        self.assertTrue(first["builds"]["LOCAL-H"]["built"])
        gate = self.gate(saved, "A2", car="JFN 9902")
        self.assertEqual(gate["status"], "fail")
        self.assertIn("LOCAL-B departs at minute 540; last built train LOCAL-H departs at minute 600", gate["reason"])
        second = ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})
        row = second["builds"]["LOCAL-B"]
        self.assertFalse(row["built"])
        self.assertEqual(row["message"], "Error")  # JMRI aborts before it writes a report
        self.assertEqual(row["report_text"], "")
        self.assertTrue(any("Train (LOCAL-B) departs at 0:09:00, train (LOCAL-H) already built departs at 0:10:00"
                            in line for line in second["log_errors"]), second["log_errors"])

    @JMRI
    def test_later_departure_time_builds(self):
        folder = self._on_time_copy(late_hour=11)
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        self.assertEqual(self.gate(saved, "A2", car="JFN 9902")["status"], "pass")
        second = ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})
        self.assertTrue(second["builds"]["LOCAL-B"]["built"])

    @JMRI
    def test_same_order_works_when_on_time_is_off(self):
        folder = self.copy()
        self.edit(folder, [{"action": "update_train", "train": "LOCAL-H", "requires": 0}])
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        second = ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})
        self.assertTrue(second["builds"]["LOCAL-B"]["built"])


class U23Backups(Case):
    def test_backup_delete_restore(self):
        folder = self.copy()
        self.standin_car(folder)
        made = ops_store.backup(folder, "manual")
        name = made if isinstance(made, str) else made.get("backup", made.get("set"))
        self.assertTrue(str(name).startswith("opspro_manual_"), name)
        self.assertIn(str(name), [s["set"] for s in ops_store.backups(folder)])
        self.edit(folder, [{"action": "delete_car", "car": "JFN 9901"}])
        self.assertEqual([c for c in ops_data.load(folder).cars if "9901" in str(getattr(c, "id", c))], [])
        ops_store.restore(folder, str(name), "backups")
        self.assertTrue(ops_data.load(folder).find_car("JFN 9901"))
        self.assertEqual(ops_gates.Gates(ops_data.load(folder)).audit()["findings"], [])


if __name__ == "__main__":
    unittest.main()
