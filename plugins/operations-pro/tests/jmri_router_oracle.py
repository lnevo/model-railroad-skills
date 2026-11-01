"""Ask real JMRI's car router about the fixture and write tests/fixtures/demo/jmri_router_oracle.json.

For every car on a track, every track as its final destination, and no train or each
train named, this calls Router.setDestination on a copy of the car, as
Router.isCarRouteable does, and records what it returned, its status, the destination
it set and the trains in the route it showed. Each scenario changes a few settings in
memory first, the same way ops_router's test applies them, and keeps only the answers
that differ from the plain demo. In a "building" scenario the named train has the
building status, so route moves and train length count for it.

Run under JMRI's jython against a scratch copy of the operations directory:

  java -Djava.awt.headless=true -Dops.home=<dir holding operations/> \
       -Duser.home=<dir> -Djmri.prefsdir=<dir> -Doracle.out=<json> -Dpython.cachedir.skip=false \
       -cp <jmri.jar and each lib/*.jar> org.python.util.jython tests/jmri_router_oracle.py
"""
import json
import re

import java
from jmri import InstanceManager as IM
from jmri.jmrit.roster import RosterConfigManager
from jmri.util import FileUtil

FileUtil.setUserFilesPath(None, java.lang.System.getProperty("ops.home") + "/")

from jmri.jmrit.operations.locations import LocationManager, LocationManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.cars import CarManager, CarManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.engines import EngineManagerXml  # noqa: E402
from jmri.jmrit.operations.router import Router  # noqa: E402
from jmri.jmrit.operations.routes import RouteManager, RouteManagerXml  # noqa: E402
from jmri.jmrit.operations.setup import OperationsSetupXml, Setup  # noqa: E402
from jmri.jmrit.operations.trains import Train, TrainManager, TrainManagerXml  # noqa: E402

IM.setDefault(RosterConfigManager, RosterConfigManager())
for xml in (OperationsSetupXml, LocationManagerXml, RouteManagerXml, CarManagerXml, EngineManagerXml,
            TrainManagerXml):
    IM.getDefault(xml)

# Each scenario: router settings, track changes, route stop maximum lengths, train options.
SCENARIOS = [
    {"name": "demo"},
    {"name": "yards off", "router": {"carRoutingViaYards": False}},
    {"name": "staging on", "router": {"carRoutingViaStaging": True}},
    {"name": "scrap shed full", "tracks": {"3s3": {"length": 50}}},
    {"name": "scrap shed full, no forward", "tracks": {"3s3": {"length": 50}},
     "router": {"forwardToYard": False}},
    {"name": "scrap shed full, yard alternate", "tracks": {"3s3": {"length": 50, "alternate": "3s2"}}},
    {"name": "service all", "trains": {"3": {"serviceAll": True}, "6": {"serviceAll": True}}},
    {"name": "only active", "router": {"onlyActiveTrains": True}, "trains": {"6": {"build": False}}},
    {"name": "building, short turn", "building": True, "stops": {"3r1": 40, "3r2": 40, "3r3": 40}},
    {"name": "building, staging on", "building": True, "router": {"carRoutingViaStaging": True}},
]

SETUP = {"carRoutingEnabled": Setup.setCarRoutingEnabled, "carRoutingViaYards": Setup.setCarRoutingViaYardsEnabled,
         "carRoutingViaStaging": Setup.setCarRoutingViaStagingEnabled, "forwardToYard": Setup.setForwardToYardEnabled,
         "onlyActiveTrains": Setup.setOnlyActiveTrainsEnabled,
         "checkCarDestination": Setup.setCheckCarDestinationEnabled}
GET = {"carRoutingEnabled": Setup.isCarRoutingEnabled, "carRoutingViaYards": Setup.isCarRoutingViaYardsEnabled,
       "carRoutingViaStaging": Setup.isCarRoutingViaStagingEnabled, "forwardToYard": Setup.isForwardToYardEnabled,
       "onlyActiveTrains": Setup.isOnlyActiveTrainsEnabled, "checkCarDestination": Setup.isCheckCarDestinationEnabled}

locations = list(IM.getDefault(LocationManager).getLocationsByNameList())
tracks = [t for location in locations for t in location.getTracksByNameList(None)]
by_id = dict((t.getId(), t) for t in tracks)
trains = list(IM.getDefault(TrainManager).getTrainsByNameList())
train_by_id = dict((t.getId(), t) for t in trains)
stops = dict((rl.getId(), rl) for r in IM.getDefault(RouteManager).getRoutesByNameList()
             for rl in r.getLocationsBySequenceList())
cars = [c for c in IM.getDefault(CarManager).getByIdList() if c.getTrack() is not None]
router = IM.getDefault(Router)


def apply(scenario):
    """Change settings for a scenario; return a function that puts them back."""
    undo = []
    for name, value in scenario.get("router", {}).items():
        old = GET[name]()
        SETUP[name](value)
        undo.append(lambda n=name, o=old: SETUP[n](o))
    for track_id, change in scenario.get("tracks", {}).items():
        track = by_id[track_id]
        if "length" in change:
            old = track.getLength()
            track.setLength(change["length"])
            undo.append(lambda t=track, o=old: t.setLength(o))
        if "alternate" in change:
            old = track.getAlternateTrack()
            track.setAlternateTrack(by_id[change["alternate"]])
            undo.append(lambda t=track, o=old: t.setAlternateTrack(o))
    for stop_id, length in scenario.get("stops", {}).items():
        stop = stops[stop_id]
        old = stop.getMaxTrainLength()
        stop.setMaxTrainLength(length)
        undo.append(lambda s=stop, o=old: s.setMaxTrainLength(o))
    for train_id, change in scenario.get("trains", {}).items():
        train = train_by_id[train_id]
        if "serviceAll" in change:
            old = train.isServiceAllCarsWithFinalDestinationsEnabled()
            train.setServiceAllCarsWithFinalDestinationsEnabled(change["serviceAll"])
            undo.append(lambda t=train, o=old: t.setServiceAllCarsWithFinalDestinationsEnabled(o))
        if "build" in change:
            old = train.isBuildEnabled()
            train.setBuildEnabled(change["build"])
            undo.append(lambda t=train, o=old: t.setBuildEnabled(o))

    def restore():
        for step in reversed(undo):
            step()
    return restore


def ask(car, track, train, building):
    """Router.isCarRouteable (R:96), keeping the status and the destination it set."""
    # Car.setDestination bumps the track's moves (Track.addDropRS) and a sequential schedule; put both back.
    saved = [(t, t.getScheduleItemId(), t.getMoves()) for t in tracks]
    code = train.getStatusCode() if train else None
    if building and train:
        train.setStatusCode(Train.CODE_BUILDING)
    copy = car.copy()
    copy.setTrack(car.getTrack())
    copy.setFinalDestination(track.getLocation())
    copy.setFinalDestinationTrack(track)
    copy.setScheduleItemId(car.getScheduleItemId())
    ok = router.setDestination(copy, train, None)
    answer = [bool(ok), router.getStatus(),
              copy.getDestinationTrack().getId() if copy.getDestinationTrack() else (
                  copy.getDestination().getId() if copy.getDestination() else ""),
              re.findall(r"-> \[([^\]]*)\]", copy.getRoutePath() or "")]
    copy.setDestination(None, None)
    copy.setFinalDestination(None)
    copy.setFinalDestinationTrack(None)
    if building and train:
        train.setStatusCode(code)
    for t, item, moves in saved:
        t.setScheduleItemId(item)
        t.setMoves(moves)
    return answer


out = {"scenarios": SCENARIOS, "answers": {}}
base = {}
for scenario in SCENARIOS:
    restore = apply(scenario)
    rows = {}
    for car in cars:
        for track in tracks:
            for train in [None] + trains:
                key = "%s|%s|%s" % (car.getId(), track.getId(), train.getId() if train else "")
                answer = ask(car, track, train, scenario.get("building", False))
                if scenario["name"] == "demo":
                    base[key] = answer
                    rows[key] = answer
                elif answer != base[key]:
                    rows[key] = answer
    restore()
    out["answers"][scenario["name"]] = rows

with open(java.lang.System.getProperty("oracle.out"), "w") as handle:
    json.dump(out, handle, sort_keys=True, separators=(",", ":"))
print("DONE")
java.lang.System.exit(0)
