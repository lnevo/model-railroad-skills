"""Run under JMRI's own jython, always against a scratch copy of the Operations files.

Properties: ops.home (holds operations/), worker.out (JSON result), worker.job (JSON).
Job fields: build, only (train names, build just those), terminate, save, car, location, track.
"""
import json
import os

import java
import jmri
from jmri import InstanceManager as IM
from jmri.jmrit.roster import RosterConfigManager
from jmri.util import FileUtil

FileUtil.setUserFilesPath(None, java.lang.System.getProperty("ops.home") + "/")

from jmri.jmrit.operations import OperationsXml  # noqa: E402
from jmri.jmrit.operations.automation import AutomationManager  # noqa: E402
from jmri.jmrit.operations.locations import LocationManager, LocationManagerXml, Track  # noqa: E402
from jmri.jmrit.operations.rollingstock.cars import CarManager, CarManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.engines import EngineManager, EngineManagerXml  # noqa: E402
from jmri.jmrit.operations.routes import RouteManager, RouteManagerXml  # noqa: E402
from jmri.jmrit.operations.setup import OperationsSetupXml  # noqa: E402
from jmri.jmrit.operations.trains import TrainManager, TrainManagerXml  # noqa: E402

JOB = json.loads(java.lang.System.getProperty("worker.job"))
AUTOMATION_TICKS = JOB.get("automation_ticks", 200)  # 100 ms each
XMLS = (OperationsSetupXml, LocationManagerXml, RouteManagerXml, CarManagerXml, EngineManagerXml, TrainManagerXml)

# A failed build asks for the lead engine's DCC address, which needs the roster settings.
IM.setDefault(RosterConfigManager, RosterConfigManager())
for xml in XMLS:
    IM.getDefault(xml)

cars = IM.getDefault(CarManager)
locations = IM.getDefault(LocationManager)
trains = IM.getDefault(TrainManager)
out = {"version": str(jmri.Version.name()), "cars": len(cars.getList()),
       "engines": len(IM.getDefault(EngineManager).getList()),
       "locations": len(locations.getLocationsByNameList()),
       "routes": len(IM.getDefault(RouteManager).getRoutesByNameList()),
       "trains": len(trains.getTrainsByNameList()), "builds": {}}

def settle_automations():
    """A startup automation runs on its own thread, so saving now could miss its last steps. Wait for it to start
    and go quiet, with a limit, as a wait step for a train nobody terminates never ends."""
    manager = IM.getDefault(AutomationManager)
    startup = manager.getStartupAutomation()
    started = startup is None
    quiet = 0
    for _ in range(AUTOMATION_TICKS):
        running = any(a.isRunning() or a.isActionRunning() for a in manager.getAutomationsByNameList())
        started = started or running or any(i.isActionRan() for i in startup.getItemsBySequenceList())
        quiet = quiet + 1 if started and not running else 0
        if quiet >= 5:
            return
        java.lang.Thread.sleep(100)


if JOB.get("build"):
    trains.setBuildMessagesEnabled(False)  # A failed build must not open a dialog.
    for train in trains.getTrainsByTimeList():
        if not train.isBuildEnabled() or (JOB.get("only") and train.getName() not in JOB["only"]):
            continue
        train.build()
        moved = sorted(c.getId() + " > " + c.getDestinationName() + " / " + c.getDestinationTrackName()
                       for c in cars.getByTrainList(train))
        row = {"built": bool(train.isBuilt()), "failed": bool(train.isBuildFailed()),
               "message": train.getStatus(), "cars": moved}
        # Structured state for the gates: what the build placed, and where the train departs from.
        row["placed"] = [{"car": c.getId(), "location": c.getDestinationName(),
                          "track": c.getDestinationTrackName(),
                          "track_id": c.getDestinationTrack().getId() if c.getDestinationTrack() else ""}
                         for c in cars.getByTrainList(train) if c.getDestination() is not None]
        depart = train.getDepartureTrack()
        row["departure_track"] = depart.getName() if depart is not None else ""
        row["departure_track_id"] = depart.getId() if depart is not None else ""
        row["engines"] = [e.getId() for e in IM.getDefault(EngineManager).getByTrainList(train)]
        report = os.path.join(java.lang.System.getProperty("ops.home"), "operations", "buildstatus",
                              "train (" + train.getName() + ").txt")
        row["report"] = report if os.path.isfile(report) else ""
        out["builds"][train.getName()] = row
    if JOB.get("terminate"):
        for train in trains.getTrainsByTimeList():
            if train.isBuilt():
                train.terminate()
                row = out["builds"].get(train.getName())  # A train an automation built has no row of its own.
                if row is not None:
                    row["terminated"] = not bool(train.isBuilt())

if JOB.get("car"):
    car = cars.getById(JOB["car"])
    location = locations.getLocationByName(JOB["location"])
    track = location.getTrackByName(JOB["track"], None)
    status = car.setLocation(location, track)
    if status != Track.OKAY:
        out["refused"] = "JMRI refused the move: " + status
    elif track.getSchedule() is not None:
        status = track.checkSchedule(car)
        if status != Track.OKAY:
            out["refused"] = "JMRI refused the schedule: " + status
        else:
            track.scheduleNext(car)
            car.loadNext(track)

if JOB.get("save"):
    settle_automations()
    for xml in XMLS:
        IM.getDefault(xml).setDirty(True)
    OperationsXml.save()

with open(java.lang.System.getProperty("worker.out"), "w") as handle:
    json.dump(out, handle, indent=1, sort_keys=True)
print("DONE")
java.lang.System.exit(0)
