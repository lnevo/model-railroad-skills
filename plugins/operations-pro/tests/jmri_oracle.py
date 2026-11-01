"""Ask real JMRI what it thinks of the fixture and write tests/fixtures/demo/jmri_oracle.json.

Run under JMRI's jython against a scratch copy of the operations directory, never
against real data, because a build changes cars in memory:

  java -Djava.awt.headless=true -Dops.home=<dir holding operations/> \
       -Duser.home=<dir> -Djmri.prefsdir=<dir> -Doracle.out=<json> \
       -cp <jmri.jar and lib/*.jar> org.python.util.jython tests/jmri_oracle.py
"""
import json

import java
import jmri
from jmri import InstanceManager as IM
from jmri.jmrit.roster import RosterConfigManager
from jmri.util import FileUtil

FileUtil.setUserFilesPath(None, java.lang.System.getProperty("ops.home") + "/")

from jmri.jmrit.operations.locations import LocationManager  # noqa: E402
from jmri.jmrit.operations.locations import LocationManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.cars import CarManager, CarManagerXml  # noqa: E402
from jmri.jmrit.operations.rollingstock.engines import EngineManager, EngineManagerXml  # noqa: E402
from jmri.jmrit.operations.routes import RouteManager, RouteManagerXml  # noqa: E402
from jmri.jmrit.operations.setup import OperationsSetupXml  # noqa: E402
from jmri.jmrit.operations.trains import TrainManager, TrainManagerXml  # noqa: E402

# A failed build asks for the lead engine's DCC address, which needs the roster settings.
IM.setDefault(RosterConfigManager, RosterConfigManager())

for xml in (OperationsSetupXml, LocationManagerXml, RouteManagerXml, CarManagerXml,
            EngineManagerXml, TrainManagerXml):
    IM.getDefault(xml)

cars = list(IM.getDefault(CarManager).getByIdList())
locations = list(IM.getDefault(LocationManager).getLocationsByNameList())
trains = list(IM.getDefault(TrainManager).getTrainsByNameList())
out = {"cars": len(cars), "engines": len(IM.getDefault(EngineManager).getList()),
       "locations": len(locations), "routes": len(IM.getDefault(RouteManager).getRoutesByNameList()),
       "trains": len(trains), "destination": {}, "serviceable": {}, "builds": {}}

OKAY = jmri.jmrit.operations.locations.Track.OKAY
for car in cars:
    row = {}
    for location in locations:
        for track in location.getTracksByNameList(None):
            row[track.getId()] = car.checkDestination(location, track)
    out["destination"][car.getId()] = row
    out["serviceable"][car.getId()] = dict((t.getId(), bool(t.isServiceable(car))) for t in trains)

IM.getDefault(TrainManager).setBuildMessagesEnabled(False)  # A failed build must not open a dialog.
for train in trains:
    train.build()
    moved = sorted(c.getId() + " > " + c.getDestinationTrackName()
                   for c in IM.getDefault(CarManager).getByTrainList(train))
    out["builds"][train.getName()] = {
        "built": bool(train.isBuilt()), "failed": bool(train.isBuildFailed()),
        "status": train.getStatus(), "cars": moved}
    if train.isBuilt():
        train.reset()

with open(java.lang.System.getProperty("oracle.out"), "w") as handle:
    json.dump(out, handle, indent=1, sort_keys=True)
print("DONE")
java.lang.System.exit(0)
