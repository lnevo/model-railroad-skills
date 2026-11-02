"""Make the variant railroads from the demo, and with JMRI installed ask real JMRI about them.

Each variant is the demo railroad with a few settings changed, so that gates the demo never
reaches are held to JMRI's answer as well:

- build: on-time build order with a built train (A2), a random value that is not a number (A6),
  terminal staging checks on (A7), a locomotive model the departure track lacks (A8), and a manual
  build line set to fail (B19).
- space: a track pool and planned pick ups (E9), a short train length leaving one stop (D9, G10),
  a car whose home division has no track (C12), a caboose no train asks for (B17), a random draw
  (A6) and a manual build line with a destination (B19).
- aggressive: aggressive mode with staging immediately available, and both terminal staging tracks
  holding cars that are not leaving (A7).

  python3 tests/variant_fixtures.py

writes tests/fixtures/<variant>/operations, then tests/fixtures/<variant>/jmri_oracle.json by
running tests/jmri_oracle.py under JMRI's jython (skipped, with a note, if JMRI is not found).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_jmri  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
DEMO = FIXTURES / "demo" / "operations"
ORACLE = ROOT / "tests" / "jmri_oracle.py"


def once(text: str, old: str, new: str) -> str:
    """Replace old with new, and insist old appears exactly once."""
    if text.count(old) != 1:
        raise ValueError(f"expected one {old!r}, found {text.count(old)}")
    return text.replace(old, new)


def element(text: str, start: str, edit) -> str:
    """Apply edit to the one XML start tag that begins with start."""
    match = re.search(re.escape(start) + r"[^>]*>", text)
    if match is None or text.count(start) != 1:
        raise ValueError(f"expected one tag starting {start!r}")
    return text[:match.start()] + edit(match.group(0)) + text[match.end():]


def attr(name: str, value: str):
    """An edit that sets one attribute on a start tag."""
    def edit(tag: str) -> str:
        if re.search(rf' {name}="[^"]*"', tag):
            return re.sub(rf' {name}="[^"]*"', f' {name}="{value}"', tag)
        return re.sub(r"(\s*/?>)$", f' {name}="{value}"\\1', tag)
    return edit


def manual(train_id: str, **item: str) -> str:
    fields = {"id": "1m1", "sequenceId": "1", "trainScheduleId": "", "type": "", "road": "", "load": "",
              "count": "1", "warn": "false", "fail": "false", "remove": "false", **item}
    line = " ".join(f'{k}="{v}"' for k, v in fields.items())
    return (f'  <manualBuilds>\n    <manualBuild id="1" trainId="{train_id}" comment="">\n'
            f'      <mbItem {line} />\n    </manualBuild>\n  </manualBuilds>\n</operations-config>')


def build_variant(files: dict[str, str]) -> None:
    ops = "Operations.xml"
    files[ops] = element(files[ops], "<buildOptions", attr("stagingRestrictionEnabled", "true"))
    files[ops] = element(files[ops], "<buildOptions", attr("onTime", "true"))
    trains = "OperationsTrainRoster.xml"
    for train_id, hour in (("1", "12"), ("2", "12"), ("3", "08"), ("4", "12"), ("5", "12"), ("6", "10")):
        files[trains] = element(files[trains], f'<train id="{train_id}" ', attr("departHour", hour))
    files[trains] = element(files[trains], '<train id="6" ', attr("built", "true"))
    files[trains] = element(files[trains], '<train id="1" ', attr("engineModel", "SD40"))
    files[trains] = once(files[trains], "</operations-config>", manual("4", type="Gondola", count="5", fail="true"))
    routes = "OperationsRouteRoster.xml"
    files[routes] = element(files[routes], '<location id="6r2" ', attr("randomControl", "abc"))
    # East Staging takes every type BV1 carries, so only BV2's West Staging fails the terminal checks.
    locations = "OperationsLocationRoster.xml"
    head, tail = files[locations].split('<location id="5" ', 1)
    block, rest = tail.split("</location>", 1)
    block = block.replace('<carType name="Tank" />', '<carType name="Tank" />\n        <carType name="Scalecar" />')
    files[locations] = head + '<location id="5" ' + block + "</location>" + rest


def space_variant(files: dict[str, str]) -> None:
    locations = "OperationsLocationRoster.xml"
    for track in ("1s2", "1s5"):
        files[locations] = element(files[locations], f'<track id="{track}" ', attr("pool", "Brackwater Pool"))
        files[locations] = element(files[locations], f'<track id="{track}" ', attr("minLength", "0"))
    files[locations] = element(files[locations], '<track id="1s1" ', attr("ignoreUsedPercentage", "100"))
    files[locations] = once(files[locations], "  <schedules>",
                            '  <divisions>\n    <division id="1" name="Far" comment="" />\n  </divisions>\n  <schedules>')
    routes = "OperationsRouteRoster.xml"
    files[routes] = element(files[routes], '<location id="1r4" ', attr("maxTrainLength", "100"))
    files[routes] = element(files[routes], '<location id="1r2" ', attr("randomControl", "50"))
    cars = "OperationsCarRoster.xml"
    files[cars] = element(files[cars], '<car id="BVR3006" ', attr("divisionId", "1"))
    files[cars] = once(files[cars], "  </cars>",
                       '    <car id="BVR9001" roadName="BVR" roadNumber="9001" type="Caboose" length="30" color="Red" '
                       'weight="2.0" weightTons="20" built="1962" locationId="1" secLocationId="1s2" moves="0" '
                       'date="" selected="false" owner="BV" load="Mty" caboose="true" />\n  </cars>')
    trains = "OperationsTrainRoster.xml"
    files[trains] = once(files[trains], "</operations-config>", manual(
        "4", type="Boxcar", load="Mty", routeLocationId="4r1", locTrackId="1s1", destinationId="1",
        destTrackId="1s3", count="1"))


def aggressive_variant(files: dict[str, str]) -> None:
    ops = "Operations.xml"
    files[ops] = element(files[ops], "<buildOptions", attr("aggressive", "true"))
    files[ops] = element(files[ops], "<buildOptions", attr("stagingTrackAvail", "true"))
    cars = "OperationsCarRoster.xml"
    files[cars] = element(files[cars], '<car id="BVR1103" ', attr("secLocationId", "5s2"))


VARIANTS = {"build": build_variant, "space": space_variant, "aggressive": aggressive_variant}


def make(name: str) -> Path:
    files = {p.name: p.read_text() for p in DEMO.glob("*.xml")}
    VARIANTS[name](files)
    out = FIXTURES / name / "operations"
    if out.parent.is_dir():
        shutil.rmtree(out.parent)
    out.mkdir(parents=True)
    for file, text in files.items():
        (out / file).write_text(text)
    return out


def oracle(operations: Path) -> None:
    home = ops_jmri.jmri_home()
    if home is None:
        print("JMRI not found; set JMRI_HOME to write", operations.parent / "jmri_oracle.json")
        return
    jars = [home / "jmri.jar", *sorted((home / "lib").glob("*.jar"))]
    with tempfile.TemporaryDirectory(prefix="opspro-oracle-") as scratch:
        root = Path(scratch)
        shutil.copytree(operations, root / "operations")
        out = operations.parent / "jmri_oracle.json"
        subprocess.run([ops_jmri.java_command(), ops_jmri.QUICK_JIT, "-Djava.awt.headless=true", f"-Duser.home={root}",
                        f"-Djmri.prefsdir={root}", f"-Dops.home={root}",
                        f"-Dpython.cachedir={ops_jmri.jython_cache(home, root)}",
                        "-Dpython.cachedir.skip=false", f"-Doracle.out={out}", "-cp",
                        os.pathsep.join(str(j) for j in jars), "org.python.util.jython", str(ORACLE)],
                       cwd=root, capture_output=True, timeout=300, check=False)
        builds = json.loads(out.read_text())["builds"]
        for train, row in sorted(builds.items()):
            print(operations.parent.name, train, row["status"])


def main() -> None:
    for name in sys.argv[1:] or VARIANTS:
        oracle(make(name))


if __name__ == "__main__":
    main()
