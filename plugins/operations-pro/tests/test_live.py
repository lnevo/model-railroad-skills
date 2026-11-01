"""The live lane. Everything but the first class needs JMRI: it starts a real one on a scratch folder.

The agent is installed the way a user would: a plan applied with JMRI exited, then JMRI
runs it as an Operations startup script. Nothing is told to run it.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
import ops_live  # noqa: E402
import ops_store  # noqa: E402
from ops_store import Refused  # noqa: E402

DEMO = ROOT / "tests" / "fixtures" / "demo" / "operations"
HOST = ROOT / "tests" / "live_host.py"


class Offline(unittest.TestCase):
    def test_no_server_says_how_to_fix_it(self):
        with self.assertRaisesRegex(Refused, "web server"):
            ops_live.status("http://127.0.0.1:9")

    def test_action_names_are_checked(self):
        with self.assertRaisesRegex(Refused, "action must be"):
            ops_live.train_action("explode", "T", url="http://127.0.0.1:9")

    def test_move_needs_a_location(self):
        with self.assertRaisesRegex(Refused, "needs a location"):
            ops_live.train_action("move", "T", url="http://127.0.0.1:9")

    def test_install_plans_a_profile_relative_startup_entry(self):
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch) / "operations"
            shutil.copytree(DEMO, base)
            with mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(Path(scratch) / "plans")}):
                result = ops_live.install_agent(base)
            self.assertTrue((base / ops_live.INSTALLED).is_file())
            self.assertIn('startUp name="preference:operations/opspro_agent.py"', result["diff"])
            self.assertFalse(result["blocked"])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class Live(unittest.TestCase):
    """Each test gets its own JMRI: terminating a train fills staging, so tests would steer each other."""

    @classmethod
    def setUpClass(cls):
        cls.prepared = tempfile.TemporaryDirectory(prefix="opspro-live-")
        cls.addClassCleanup(cls.prepared.cleanup)
        root = Path(cls.prepared.name)
        cls.source = root / "operations"
        shutil.copytree(DEMO, cls.source)
        with mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(root / "plans")}), \
                mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_store.apply(ops_live.install_agent(cls.source)["plan_id"])

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="opspro-live-")
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        self.ops = root / "operations"
        shutil.copytree(self.source, self.ops)
        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        home = ops_jmri.jmri_home()
        jars = [home / "jmri.jar", *sorted((home / "lib").glob("*.jar"))]
        process = subprocess.Popen(
            [ops_jmri.java_command(), "-Djava.awt.headless=true", f"-Duser.home={root}", f"-Djmri.prefsdir={root}",
             f"-Dops.home={root}", f"-Dweb.port={port}", f"-Dpython.cachedir={root / 'jc'}",
             "-Dpython.cachedir.skip=false", "-cp", os.pathsep.join(map(str, jars)), "org.python.util.jython",
             str(HOST)], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        deadline = time.monotonic() + 90
        while True:
            try:
                ops_live.call(self.url, "railroad")
                return
            except Refused:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.25)

    def build(self, train, **fields):
        return ops_live.train_action("build", train, url=self.url, **fields)["builds"][0]

    def row(self, train):
        return next(t for t in ops_live.status(self.url)["trains"] if t["name"] == train)

    def test_startup_script_started_the_agent(self):
        status = ops_live.status(self.url)
        self.assertEqual(status["agent"], ops_live.AGENT_VERSION)
        self.assertEqual(len(status["trains"]), 6)
        self.assertNotIn("warning", status)

    def test_build_answers_with_the_cars_and_report(self):
        row = self.build("BV1")
        self.assertTrue(row["built"])
        self.assertTrue(row["cars"])
        self.assertIn("BV1", row["report_tail"])

    def test_failed_build_answers_and_leaves_the_dialog_setting_alone(self):
        before = ops_live.status(self.url)["build_messages"]
        row = self.build("X99")
        self.assertFalse(row["built"])
        self.assertTrue(row["failed"])
        self.assertTrue(row["report_tail"])
        self.assertEqual(ops_live.status(self.url)["build_messages"], before)

    def test_build_all_covers_every_enabled_train(self):
        rows = ops_live.train_action("build", "all", url=self.url)["builds"]
        self.assertEqual(sorted(r["name"] for r in rows), ["BV1", "BV2", "T10", "T30", "X99", "Y20"])

    def test_built_train_needs_rebuild(self):
        self.build("BV1")
        with self.assertRaisesRegex(Refused, "already built"):
            self.build("BV1")
        self.assertTrue(self.build("BV1", rebuild=True)["built"])

    def test_move_then_terminate_over_stock_json(self):
        self.build("BV1")
        first = self.row("BV1")["location"]
        ops_live.train_action("move", "BV1", location="Ashgrove", url=self.url)
        row = self.row("BV1")
        self.assertNotEqual(row["location"], first)
        self.assertTrue(row["en_route"])
        ops_live.train_action("terminate", "BV1", url=self.url)
        self.assertFalse(self.row("BV1")["built"])

    def test_en_route_train_cannot_build_or_reset(self):
        self.build("BV1")
        ops_live.train_action("move", "BV1", location="Ashgrove", url=self.url)
        with self.assertRaisesRegex(Refused, "en route"):
            self.build("BV1", rebuild=True)
        self.assertEqual(ops_live.train_action("reset", "BV1", url=self.url)["en_route_not_reset"], ["BV1"])

    def test_car_on_a_train_cannot_be_set(self):
        car = self.build("BV1")["cars"][0].split(" > ")[0]
        with self.assertRaisesRegex(Refused, "assigned to a train"):
            ops_live.ask(self.url, "set_car", car=car, location="Ashgrove", track="x")

    def test_set_car_runs_the_schedule(self):
        rr = ops_data.load(self.ops)
        mill = rr.find_track("Ashgrove Feed Mill")
        car = next(c for c in rr.cars.values() if c.type == "Boxcar" and c.load == "Grain"
                   and not c.kernel and not c.train_id and c.track_id != mill.id)
        result = ops_live.ask(self.url, "set_car", car=car.id, location="Ashgrove", track=mill.name)
        self.assertEqual((result["load_before"], result["load"]), ("Grain", "Feed"))
        ops_live.ask(self.url, "save")
        after = ops_data.load(self.ops)
        self.assertEqual(after.cars[car.id].track_id, mill.id)
        self.assertEqual(after.cars[car.id].load, "Feed")

    def test_refused_set_car_leaves_the_car_where_it_was(self):
        rr = ops_data.load(self.ops)
        mill = rr.find_track("Ashgrove Feed Mill")
        car = next(c for c in rr.cars.values() if c.type == "Boxcar" and c.load != "Grain"
                   and not c.kernel and not c.train_id and c.track_id != mill.id)
        with self.assertRaisesRegex(Refused, "refused"):
            ops_live.ask(self.url, "set_car", car=car.id, location="Ashgrove", track=mill.name)
        ops_live.ask(self.url, "save")
        after = ops_data.load(self.ops).cars[car.id]
        self.assertEqual((after.track_id, after.load), (car.track_id, car.load))

    def test_save_writes_what_the_running_jmri_holds(self):
        self.build("BV1")
        ops_live.ask(self.url, "save")
        text = (self.ops / "OperationsTrainRoster.xml").read_text()
        self.assertIn("opspro_agent.py", text, "JMRI must keep the startup entry when it saves")
        cars = (self.ops / "OperationsCarRoster.xml").read_text()
        self.assertIn('trainId="1"', cars)

    def test_report_returns_the_build_report(self):
        self.build("BV1")
        self.assertIn("BV1", ops_live.ask(self.url, "report", train="BV1")["tail"])

    def test_unknown_command_is_refused_and_the_agent_keeps_working(self):
        with self.assertRaisesRegex(Refused, "Unknown command"):
            ops_live.ask(self.url, "exec")
        self.assertEqual(ops_live.ask(self.url, "status")["agent"], ops_live.AGENT_VERSION)

    def test_unknown_automation_is_refused(self):
        with self.assertRaisesRegex(Refused, "No automation"):
            ops_live.ask(self.url, "automation", name="Nothing")


if __name__ == "__main__":
    unittest.main()
