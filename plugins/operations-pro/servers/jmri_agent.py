"""Runs inside a live JMRI. Takes commands from one Memory and answers in another.

JMRI's JSON server cannot build a train, reset one or run a schedule, but it can set a
Memory. This script listens to that Memory, so one small script covers every train.

JMRI's dialogs are why commands are not run through Automations: a failed build, or a
good build with warnings, opens a modal window on the JMRI computer, and a remote caller
would wait forever. Each command that can do that runs with those dialogs switched off,
and they go back as they were afterwards.

Only the commands in COMMANDS can run. Nothing here evaluates text it is sent.
"""
import json
import os

import java
import jmri
from java.beans import PropertyChangeListener
from java.util.concurrent import LinkedBlockingQueue
from jmri import InstanceManager as IM
from jmri import MemoryManager
from jmri.jmrit.operations import OperationsManager, OperationsXml
from jmri.jmrit.operations.automation import AutomationManager
from jmri.jmrit.operations.locations import LocationManager, Track
from jmri.jmrit.operations.rollingstock.cars import CarManager
from jmri.jmrit.operations.setup import Setup
from jmri.jmrit.operations.trains import TrainManager

AGENT_VERSION = 1
TAIL = 4000
WHOLE = 400000  # a report longer than this is sent as its tail only
AUTOMATION_WAIT = 120

memories = IM.getDefault(MemoryManager)
request_memory = memories.provideMemory("IMOPSPRO_REQUEST")
reply_memory = memories.provideMemory("IMOPSPRO_REPLY")
ready_memory = memories.provideMemory("IMOPSPRO_AGENT")
jobs = LinkedBlockingQueue()


class Problem(Exception):
    pass


class Quiet(object):
    """Switch off everything that would stop a remote caller on a dialog."""

    def __enter__(self):
        self.trains = IM.getDefault(TrainManager)
        self.messages = self.trains.isBuildMessagesEnabled()
        self.prompt_from = Setup.isStagingPromptFromEnabled()
        self.prompt_to = Setup.isStagingPromptToEnabled()
        self.trains.setBuildMessagesEnabled(False)
        Setup.setStagingPromptFromEnabled(False)
        Setup.setStagingPromptToEnabled(False)
        return self

    def __exit__(self, *ignored):
        self.trains.setBuildMessagesEnabled(self.messages)
        Setup.setStagingPromptFromEnabled(self.prompt_from)
        Setup.setStagingPromptToEnabled(self.prompt_to)
        return False


def find_train(name):
    train = IM.getDefault(TrainManager).getTrainByName(name)
    if train is None:
        train = IM.getDefault(TrainManager).getTrainById(name)
    if train is None:
        raise Problem("No train " + name)
    return train


def find_car(text):
    for car in IM.getDefault(CarManager).getList():
        if text in (car.getId(), car.getRoadName() + " " + car.getNumber()):
            return car
    raise Problem("No car " + text)


def tail(path):
    if not os.path.isfile(path):
        return ""
    with open(path) as handle:
        return handle.read()[-TAIL:]


def whole(path):
    if not os.path.isfile(path):
        return ""
    with open(path) as handle:
        text = handle.read()
    return text if len(text) <= WHOLE else ""


def report_path(folder, train):
    return IM.getDefault(OperationsManager).getPath(os.path.join(folder, "train (" + train.getName() + ").txt"))


def train_row(train):
    return {"name": train.getName(), "status": train.getStatus(), "built": bool(train.isBuilt()),
            "failed": bool(train.isBuildFailed()), "en_route": bool(train.isTrainEnRoute()),
            "location": train.getCurrentLocationName(), "departs": train.getFormatedDepartureTime(),
            "build_enabled": bool(train.isBuildEnabled())}


def build_one(train, rebuild):
    # Train.build resets the train first and ignores a refused reset, so check here.
    if train.isTrainEnRoute():
        raise Problem(train.getName() + " is en route. Terminate it before building it again.")
    if train.isBuilt() and not rebuild:
        raise Problem(train.getName() + " is already built. Building again resets it first.")
    train.build()
    row = train_row(train)
    row["cars"] = sorted(car.getId() + " > " + car.getDestinationName() + " / " + car.getDestinationTrackName()
                         for car in IM.getDefault(CarManager).getByTrainList(train))
    path = report_path("buildstatus", train)
    row["report_text"] = whole(path)
    row["report_tail"] = tail(path)
    return row


def cmd_status(job):
    trains = IM.getDefault(TrainManager)
    return {"jmri": str(jmri.Version.name()), "agent": AGENT_VERSION,
            "ops_dir": IM.getDefault(OperationsManager).getPath(),
            "build_messages": bool(trains.isBuildMessagesEnabled()),
            "staging_prompts": bool(Setup.isStagingPromptFromEnabled() or Setup.isStagingPromptToEnabled()),
            "trains": [train_row(train) for train in trains.getTrainsByTimeList()]}


def cmd_build(job):
    name = job["train"]
    if name != "all":
        with Quiet():
            return {"builds": [build_one(find_train(name), job.get("rebuild", False))]}
    rows = []
    with Quiet():
        for train in IM.getDefault(TrainManager).getTrainsByTimeList():
            if train.isBuildEnabled() and not train.isBuilt():
                rows.append(build_one(train, False))
    return {"builds": rows}


def cmd_reset(job):
    trains = IM.getDefault(TrainManager)
    chosen = trains.getTrainsByTimeList() if job["train"] == "all" else [find_train(job["train"])]
    done, refused = [], []
    for train in reversed(list(chosen)):
        (done if train.reset() else refused).append(train.getName())
    return {"reset": done, "en_route_not_reset": refused}


def cmd_set_car(job):
    """What Set Car does: place the car, then run the track's schedule. Undone if refused."""
    car = find_car(job["car"])
    if car.getTrain() is not None or car.getDestination() is not None:
        raise Problem(str(car) + " is assigned to a train. Reset or terminate that train first.")
    location = IM.getDefault(LocationManager).getLocationByName(job["location"])
    if location is None:
        raise Problem("No location " + job["location"])
    track = location.getTrackByName(job["track"], None)
    if track is None:
        raise Problem("No track " + job["track"] + " at " + job["location"])
    old_location, old_track, load = car.getLocation(), car.getTrack(), car.getLoadName()
    status = car.setLocation(location, track)
    if status != Track.OKAY:
        raise Problem("JMRI refused the move: " + status)
    if track.getSchedule() is not None:
        status = track.checkSchedule(car)
        if status != Track.OKAY:
            car.setLocation(old_location, old_track, True)
            raise Problem("JMRI refused the schedule, so the car was put back: " + status)
        track.scheduleNext(car)
        car.loadNext(track)
    return {"car": str(car), "location": location.getName(), "track": track.getName(),
            "load_before": load, "load": car.getLoadName(), "final_destination": car.getFinalDestinationName()}


def cmd_save(job):
    OperationsXml.save()
    return {"saved": True, "ops_dir": IM.getDefault(OperationsManager).getPath()}


def cmd_report(job):
    folder = {"build": "buildstatus", "manifest": "manifests"}[job.get("kind", "build")]
    path = report_path(folder, find_train(job["train"]))
    if not os.path.isfile(path):
        raise Problem("No such report yet: " + path)
    return {"path": path, "tail": tail(path)}


def cmd_automation(job):
    automation = IM.getDefault(AutomationManager).getAutomationByName(job["name"])
    if automation is None:
        raise Problem("No automation " + job["name"])
    with Quiet():
        automation.run()
        for _ in range(AUTOMATION_WAIT * 2):
            if not automation.isRunning():
                break
            java.lang.Thread.sleep(500)
    return {"name": automation.getName(), "still_running": bool(automation.isRunning()),
            "status": automation.getCurrentActionString()}


COMMANDS = {"status": cmd_status, "build": cmd_build, "reset": cmd_reset, "set_car": cmd_set_car,
            "save": cmd_save, "report": cmd_report, "automation": cmd_automation}


def answer(text):
    job = {}
    try:
        job = json.loads(text)
        if job.get("command") not in COMMANDS:
            raise Problem("Unknown command " + str(job.get("command")))
        reply = {"id": job.get("id"), "ok": True, "result": COMMANDS[job["command"]](job)}
    except Exception as exc:  # A bad command must not stop the agent.
        reply = {"id": job.get("id"), "ok": False, "error": str(exc)}
    except java.lang.Exception as exc:
        reply = {"id": job.get("id"), "ok": False, "error": str(exc)}
    reply_memory.setValue(json.dumps(reply))


def work():
    while True:
        answer(jobs.take())


class RequestListener(PropertyChangeListener):
    """Queue the text and return, so the JSON caller and the Memory are not held up."""

    def propertyChange(self, event):
        if event.getPropertyName() == "value" and event.getNewValue():
            jobs.put(str(event.getNewValue()))


# Running the script a second time must not answer every command twice.
for old in request_memory.getPropertyChangeListeners():
    if "RequestListener" in str(old):
        request_memory.removePropertyChangeListener(old)

thread = java.lang.Thread(work)
thread.setName("OperationsPro agent")
thread.setDaemon(True)
thread.start()
request_memory.addPropertyChangeListener(RequestListener())
ready_memory.setValue(str(AGENT_VERSION))
