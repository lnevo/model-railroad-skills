"""Run under JMRI's own jython, always against a scratch copy of the Operations files.

Properties: ops.home (holds operations/), worker.out (JSON result), worker.job (JSON).
Job fields: build, terminate, save, car, location, track.
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
from jmri.jmrit.operations.locations import LocationManager, LocationManagerXml, Track  # noqa: E402
from jmri.jmrit.operations.rollingstock.cars import CarManager, CarManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.engines import EngineManager, EngineManagerXml  # noqa: E402
from jmri.jmrit.operations.routes import RouteManager, RouteManagerXml  # noqa: E402
from jmri.jmrit.operations.setup import OperationsSetupXml  # noqa: E402
from jmri.jmrit.operations.trains import TrainManager, TrainManagerXml  # noqa: E402

JOB = json.loads(java.lang.System.getProperty("worker.job"))
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

if JOB.get("build"):
    trains.setBuildMessagesEnabled(False)  # A failed build must not open a dialog.
    for train in trains.getTrainsByTimeList():
        if not train.isBuildEnabled():
            continue
        train.build()
        moved = sorted(c.getId() + " > " + c.getDestinationName() + " / " + c.getDestinationTrackName()
                       for c in cars.getByTrainList(train))
        row = {"built": bool(train.isBuilt()), "failed": bool(train.isBuildFailed()),
               "message": train.getStatus(), "cars": moved}
        report = os.path.join(java.lang.System.getProperty("ops.home"), "operations", "buildstatus",
                              "train (" + train.getName() + ").txt")
        row["report"] = report if os.path.isfile(report) else ""
        out["builds"][train.getName()] = row
    if JOB.get("terminate"):
        for train in trains.getTrainsByTimeList():
            if train.isBuilt():
                train.terminate()
                out["builds"][train.getName()]["terminated"] = not bool(train.isBuilt())

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
    for xml in XMLS:
        IM.getDefault(xml).setDirty(True)
    OperationsXml.save()

with open(java.lang.System.getProperty("worker.out"), "w") as handle:
    json.dump(out, handle, indent=1, sort_keys=True)
print("DONE")
java.lang.System.exit(0)
