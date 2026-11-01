"""Build every demo train with real JMRI and keep the build reports as test fixtures.

Writes tests/fixtures/demo/buildstatus/train (NAME).txt for each train and builds.json
with what the builder itself returned for the same run, so test_report.py can hold the
report reader to JMRI's own answer. Needs JMRI installed (JMRI_HOME if not found).

  python3 tests/report_fixtures.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_jmri  # noqa: E402

DEMO = ROOT / "tests" / "fixtures" / "demo"
OUT = DEMO / "buildstatus"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="opspro-reports-") as scratch:
        keep = Path(scratch)
        result = ops_jmri.run_worker(DEMO / "operations", {"build": True}, keep)
        if OUT.is_dir():
            shutil.rmtree(OUT)
        shutil.copytree(keep / "buildstatus", OUT)
    builds = {name: {"built": row["built"], "failed": row["failed"], "status": row["message"], "cars": row["cars"]}
              for name, row in result["builds"].items()}
    (OUT / "builds.json").write_text(json.dumps({"jmri": result["version"], "builds": builds}, indent=1, sort_keys=True))
    for name, row in sorted(builds.items()):
        print(name, row["status"])


if __name__ == "__main__":
    main()
