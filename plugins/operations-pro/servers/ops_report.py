"""Read a JMRI OperationsPro build report and say what the builder did and why.

The report is the builder's own account of a build, so it beats anything worked out
by reading the files. This module only reads it. Every line is matched against the message
templates JMRI 5.16 prints (ops_report_messages), the matches are folded into one
record per car, one per route stop and a verdict for the train, and each refusal is
tagged with the gate id from build-order.md where the wording decides it. A line that
matches no template is returned under unparsed rather than guessed at.

JMRI writes every detail level to the file in buildstatus and filters only when it
prints or previews, so the file is complete whatever the Build Report setting says.
Router lines depend on the router level setting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ops_gates import GATES
from ops_report_messages import STATUS, TEMPLATES, TRAINS

PREFIX = re.compile(r"^([1357])- ?(.*)$")
MAX_WRAP = 8  # pieces one wrapped line may span

# Templates that are pieces of other messages, never a line of their own.
FRAGMENTS = {"RouterRoutePath", "RouterRoutePathTrain", "RouterRoutePathTrack", "RouterRouteTrain", "RouterRouteTrack",
             "RouterDestination", "RouterTrain", "RouterNotAble", "RouterDisabled", "buildTrainNameAndDesc"}
LINE_TEMPLATES = {k: v for k, v in TEMPLATES.items() if k not in FRAGMENTS and k not in STATUS}

# What a 'due to' tail can be: a Track, Schedule, Router or Train status.
STATUS_TEMPLATES = {
    **STATUS, **{k: v for k, v in TRAINS.items() if k.startswith("train")},
    "statusType": "type ({0})", "statusRoad": "road ({0})", "statusLoad": "load ({0})",
    "statusLength": "rolling stock length ({0})",  # Track.LENGTH, TR:191-193, for a non-numeric car length (TR:1591)
    "statusDestination": "car's final destination ({0}) is not allowed by track ({1})",
    "statusNoFinalDestination": "car doesn't have a final destination", "statusOkay": "okay",
    "statusScheduleError": "schedule ERROR", "statusScheduleItem": "schedule ERROR Track {0} current schedule item is null!",
    "RouterNotAble": TEMPLATES["RouterNotAble"], "RouterDisabled": TEMPLATES["RouterDisabled"],
    "RouterTrain": TEMPLATES["RouterTrain"],
}
# Lines whose last argument is such a status, with the argument's index.
STATUS_TAILED = {"buildCanNotDropCarBecause": 4, "buildNoDestTrackNewLoad": 6, "RouterCanNotDeliverCar": 3,
                 "RouterTrainCanNotDueTo": 4, "buildNotAbleToSetDestination": 1, "trainCanNotDeliverToStaging": 4,
                 "RouterAlternateFailed": 1, "RouterCanNotUseYard": 2, "buildTrackSequentialMode": 2}
PLACEHOLDER = re.compile(r"\{(\d+)\}")
ASSIGNED, NO_DESTINATION, HELD, PICKUP_REFUSED, DEFERRED = (
    "assigned", "no_destination", "held", "pickup_refused", "deferred")

# Report lines whose wording alone names the gate. Keys are template keys.
KEY_GATES: dict[str, str] = {
    "buildExcludeCarWrongRoad": "B9", "buildExcludeCarWrongType": "B10", "buildExcludeCarTypeAtLoc": "B17",
    "buildExcludeCarAtLoc": "B20", "buildExcludeCarWrongDest": "B4", "buildExcludeCarDestNotPartRoute": "B4",
    "buildExcludeCarDropByTrain": "B6", "buildExcludeCarByTrain": "B7", "buildExcludeCarByRoute": "B7",
    "buildExcludeCarByInterchange": "B8", "buildExcludeCarLocUnknown": "B2", "buildExcludeCarOutOfService": "B3",
    "buildExcludeCarWait": "B16", "buildExcludeCarSchedule": "B15", "buildExcludeCarWithFredAtLoc": "B14",
    "buildExcludeCarLoadAtLoc": "B13", "buildExcludeCarOwnerAtLoc": "B11", "buildExcludeCarBuiltAtLoc": "B12",
    "buildWarningRsNoTrack": "B1", "buildErrorCarKernelLocation": "B18", "buildErrorCarKernelNoLead": "B18",
    "buildLocSkipped": "C1", "buildLocNoPickups": "C2", "buildNoPickupsFromStaging": "C3", "buildLocDirection": "C4",
    "buildErrorNoMoves": "C5", "buildNoPickUpCar": "C6", "buildRsCanNotPickupUsingTrain": "C9",
    "buildTrackNotNewLoad": "C10", "buildTrackNotLoadSchedule": "C10", "buildErrorCarStageLoad": "C10",
    "buildWarningQuickService": "C11", "buildTrackNotQuickService": "C11", "buildNoDivisionTrack": "C12",
    "buildRouteNoDropLocation": "D1", "buildNoAvailableMovesDest": "D3", "buildCarLocEqualDestination": "D4",
    "buildNoReturnStaging": "D4", "buildRouteNoLocalLocation": "C7", "buildRouteNoLocalLocCar": "D5",
    "buildCarHasFinalDestNoMove": "D5", "buildDestinationNotServiced": "D6", "buildCanNotDropLocation": "D7",
    "buildDestinationType": "A7", "buildDestinationDoesNotService": "D8",
    "buildCanNotPickupCarLength": "D9", "buildThroughTrafficNotAllow": "D10", "buildCarDestinationStaging": "D12",
    "buildCanNotDropCarSameTrack": "D13", "buildCanNotDropRsUsingTrain": "D14", "buildCanNotDropRsUsingTrain4": "D14",
    "buildCanNotDropTrain": "D15", "buildCanNotDropRoute": "D15", "buildTrackFullHasAlternate": "D17",
    "buildWarnTrainTiming": "D18", "buildNoSpurToSpurMove": "D19", "buildNoYardToYardMove": "D19",
    "buildNoInterchangeToInterchangeMove": "D19", "buildNoLocalMoveToTrack": "G9",
    "buildSpurFullNoAlternate": "E9", "buildTrackTooShort": "E9", "buildNoDestTrackSpace": "E9", "buildNoDestSpace": "E9",
    "buildDestTrackNoLoad": "E8", "buildSpurNoSchedule": "E10", "buildSpurScheduleNotUsed": "E10",
    "buildErrorNoScheduleItem": "E10", "buildScheduleNotActive": "F1", "buildSpurNotThisType": "E3",
    "buildScheduleRandom": "F5", "buildTrainNotNewLoad": "B13", "buildCanNotRouteCar": "G12",
    "buildRouteNotFound": "G12", "buildStagingTrackNotReachable": "G12", "RouterCouldNotFindLast": "G12",
    "RouterCouldNotFindStaging": "G12", "RouterCouldNotFindLoc": "G12", "RouterCouldNotFindTrain": "G12",
    "RouterNotAbleToRoute": "G12", "RouterNotFindTrain": "G12", "RouterSameInterchange": "G12",
    "RouterStagingExcluded": "G12", "RouterDisabled": "G12", "trainNoMoves": "G6", "trainExceedsMaximumLength": "G10",
    "trainCanNotServiceCarType": "G1", "trainCanNotServiceCarLoad": "G1", "trainCanNotServiceCarLocation": "G4",
    "trainCanNotServiceCarTrack": "G4", "trainCanNotServiceCarPickup": "G5", "trainCanNotServiceCarDestination": "G7",
    "trainCanNotDeliverNoTracks": "G8", "trainCanNotCarryCarOption": "G9", "trainCanNotPerformLocalMove": "G9",
    "trainDoesNotCarryOriginTerminal": "G9", "trainNotThisLocation": "G2", "trainRoutingDisabled": "G11",
    "buildErrorStagingEmpty": "A8", "buildStagingDepartCarType": "A8", "buildStagingDepartCarRoad": "A8",
    "buildStagingDepartCarLoad": "A8", "buildStagingDepartCarOwner": "A8", "buildStagingDepartCarBuilt": "A8",
    "buildStagingDepartCarDestination": "A8", "buildStagingDepartCarTrain": "A8", "buildStagingDepartEngineType": "A8",
    "buildStagingDepartEngineRoad": "A8", "buildStagingDepartEngineOwner": "A8", "buildStagingDepartEngineBuilt": "A8",
    "buildStagingDepartEngineModel": "A8", "buildStagingDepartEngineTrain": "A8", "buildStagingNoCaboose": "A8",
    "buildStagingNoCarFRED": "A8", "buildStagingNotEngines": "A8", "buildStagingNotDirection": "A8",
    "buildStagingNotTrain": "A8", "buildStagingEmpty": "A8", "buildStagingTooManyCars": "A8",
    "buildStagingTrainTooLong": "A8", "buildStagingDepart": "A8", "buildStagingCarsBefore": "A8",
    "buildStagingTrackRestriction": "A8", "buildErrorStagingFull": "A7", "buildStagingTrackOccupied": "A7",
    "buildStagingTrackReserved": "A7", "buildStagingTrackType": "A7", "buildStagingTrackRoad": "A7",
    "buildStagingTrackLoad": "A7", "buildStagingTrackAllRoads": "A7", "buildStagingTrackAllLoads": "A7",
    "buildErrorRoute": "A3", "buildErrorNeedRoute": "A3", "buildErrorNeedDepLoc": "A3", "buildErrorNeedTermLoc": "A3",
    "buildErrorLocMissing": "A4", "buildErrorRouteLoc": "A4", "buildErrorRandomControl": "A6",
    "buildErrorNotAllCars": "B20", "buildErrorCarNotPartRoute": "B20", "buildErrorCarStageDest": "B20",
    "buildStagingCouldNotFindDest": "B20", "buildErrorLocationUnknown": "B2", "buildErrorLocationOutOfService": "B3",
    "buildErrorReqDepature": "B17", "buildErrorReqDest": "B17", "buildErrorRequirements": "B17",
    "buildErrorCabooseNoLocation": "B17", "buildErrorCabooseNoDestination": "B17", "mbuildFail": "B19",
}
# Printed by both staging checks: departure (TBB:1718, TB:235, A8) and terminal (TBB:2040, 2093, A7).
STAGING_EITHER = ("buildStagingNotTrain", "buildStagingTrackRestriction")
# Terminal staging checks (A7) that also come up inside a car's search when a load is generated towards
# staging (TBB:2752, 2758); there they are the track's own type and road tests.
MID_SEARCH_GATES = {"buildStagingTrackType": "E3", "buildStagingTrackRoad": "E4"}

# What a refusal line means, in a few words, where the template alone does not say.
KEY_NOTES: dict[str, str] = {
    "buildTrackIsAlternate": "alternate tracks are never direct destinations; the spur must fill first",
    "buildHoldCarValidRoute": "held: a scheduled spur is reachable but not open now, so the car waits",
    "buildWarningCarNotRoutable": "the router failed, so the builder tries the car as a default load next",
    "buildNoDestForCar": "no destination this build",
    "buildCouldNotFindDestForCar": "no track at this location took the car",
    "buildCouldNotFindTrack": "no scheduled spur was reachable for this custom load",
    "buildNoStagingForCarLoad": "no staging track accepts the car and load",
    "buildNoStagingForCarCustom": "no staging track accepts a custom load",
    "buildUnableNewLoad": "no spur needing a custom load could be reached",
    "buildUnableNewLoadStaging": "no custom load could be generated towards staging",
    "buildCarNoCustomLoad": "no custom load exists for this car type",
    "buildNoLocalMoveToTrack": "the train's option to allow local moves is off. Fix: Edit Train > Build Options, "
                               "Allow local moves if car has a custom load or FD",
    "buildSpurNotThisType": "the spur's car types exclude this type, so its schedule is not read",
    "buildTrainNotNewLoad": "the train's load option refuses the load that would be generated",
    "buildReturnCarToStaging": "the search goes on; staging is the fallback if no other track takes the car",
    "buildExcludeCarTypeAtLoc": "a caboose or FRED car set aside after the caboose and FRED pass, "
                                "or one that could not be picked up in the train's direction",
    "TrainDoesNotServiceCar": "this train cannot take the car directly there; the router looks for another",
    "buildNotAbleToSetDestination": "",
    "buildCarCanDropMoves": "",
}

# Why a schedule line refused a car (Schedule.checkScheduleItem, SCH:467-505), tried first on a status
# that starts with "schedule (". Day comes before type; road and load share the requestCar template.
SCHEDULE_RULES: list[tuple[str, str, str]] = [
    ("only on (", "F1", "the line's delivery day is not the active day"),
    (") road (", "F3", "the schedule line wants another road"),
    (") load (", "F4", "the schedule line wants another load"),
]
# Why a track refused a car, from the status text Track and Schedule return.
STATUS_RULES: list[tuple[str, str, str]] = [
    ("could not route car", "G12", "the router found no chain of trains"),
    ("router is disabled", "G12", "car routing is off in Settings"),
    ("in match mode, no match", "E10", "no schedule line matched the car"),
    ("in sequential mode", "E10", "the current schedule line does not match the car"),
    ("doesn't service car type", "F2", "no line of the schedule has this car type"),
    ("only on (", "F1", "the line's delivery day is not the active day"),
    ("requests car type", "F2", "the schedule line wants another type"),
    ("random value", "F5", "the line's random draw failed"),
    ("car has a custom load", "E10", "a spur without a schedule refuses custom loads"),
    ("track capacity", "E9", "the car is longer than the track"),
    ("rolling stock length (", "E5", "the car's length is not a number"),
    ("rolling stock length", "E9", "no room on the track"),
    ("available track space", "E9", "no room on the track"),
    ("car's final destination", "E6", "the track's Destinations filter excludes the final destination"),
    ("car doesn't have a final destination", "E7", "the track takes only routed cars"),
    ("no moves left", "G6", "that train has no moves left at the destination stop"),
    ("would exceed", "G10", "that train would be too long"),
    ("type (", "E3", "the track does not take this car type"),
    ("road (", "E4", "the track's road option excludes the road"),
    ("load (", "E8", "the track's load option excludes the load"),
]

STAGING_DEPARTURE = ("buildDepartStaging", "buildStagingHas", "buildTrainCanDepartTrack", "buildStagingNoCaboose",
                     "buildStagingNoCarFRED", "buildStagingNotEngines",
                     "buildStagingEmpty", "buildStagingTooManyCars", "buildStagingTrainTooLong", "buildStagingDepart",
                     "buildStagingCarsBefore", "buildStagingNotDirection",
                     "buildStagingTrackPool", "buildUserSelectedDeparture", "buildOnlyOneDepartureTrack",
                     "buildErrorStagingEmpty", "buildStagingTrackDepart", "buildUserCanceledDeparture")
STAGING_TERMINAL = ("buildTerminateStaging", "buildStagingAvail", "buildStagingReturn", "buildTrainCanTerminateTrack",
                    "buildStagingTrackOccupied", "buildStagingTrackReserved", "buildStagingTrackType",
                    "buildStagingTrackRoad", "buildStagingTrackLoad", "buildStagingTrackAllRoads",
                    "buildStagingTrackAllLoads", "buildErrorStagingFull", "buildErrorStagingFullNote",
                    "buildUserSelectedArrival", "buildIgnoreStagingFirstPass", "buildDestinationType")
SEARCH_STARTS = {"buildFindDestinationForCar": "default", "buildSearchForSpur": "custom load",
                 "buildCarRoutingBegins": "router", "buildSearchTrackNewLoad": "generate load",
                 "buildSearchTrackLoadStaging": "generate load for staging", "buildCarDepartHomeDivision": "division",
                 "buildCarDepartForeignDivision": "division", "buildCarHasDivisionStaging": "division"}
PICKUP_REFUSALS = {"buildCanNotPickupCarLength": PICKUP_REFUSED, "buildRsCanNotPickupUsingTrain": PICKUP_REFUSED,
                   "buildNoPickUpCar": PICKUP_REFUSED, "buildWarningQuickService": PICKUP_REFUSED,
                   "buildCarOnAlternateTrack": DEFERRED}
ACCEPTED = {"buildCarCanDropMoves", "buildCarHasAssignedDest", "buildCreateNewLoadForCar", "buildCarAssignedToStaging",
            "RouterTrainCanTransport", "RouterRouteForCar", "buildStagingCanAcceptLoad", "buildAddingScheduleLoad",
            "buildTrainCanServiceWait", "buildRedirectFromAlternate", "buildPickupLaterOkay", "buildCarHasSecond",
            "buildTrackServicedLater", "buildEngineCanDrop", "RouterFoundTrack", "RouterTwoTrainsSuccess",
            "RouterTrainCanService", "buildCabooseRoadMatches", "trainCanPickUpCar", "buildTrainCanDepartTrack",
            "buildTrainCanTerminateTrack"}
# buildReturnCarToStaging (TBC:1761) and buildLeaveCarInStaging (TBC:1912) fall through to the rest of the
# search and to addCarToTrain, so they are notes inside the attempt, not outcomes.
ENDERS = {"buildCarAssignedDest": ASSIGNED, "buildCarKernelAssignedDest": ASSIGNED, "buildNoDestForCar": NO_DESTINATION}
EXCLUDE_KEYS = ("buildExcludeCar", "buildWarningRsNoTrack", "buildErrorCarKernel", "buildCarAlreadyAssigned")
ENGINE_KEYS = ("buildExcludeEngine", "buildExcludeEngConsistNumber", "buildEngineAssigned", "buildFoundLocos",
               "buildNoLocosFoundAtLocation", "buildErrorEngines", "buildErrorEngHp", "buildAssignedHpNotEnough",
               "buildAssignedHpTooMuch", "buildMaximumNumberEngines", "buildMaxNumberLocoAssigned",
               "buildTrainReqExtraHp", "buildTrainRequiresAddHp", "buildCanNotDropEngToDest",
               "buildCanNotDropEngineToTrack", "buildEngineLeadConsist", "buildTrainEngineChange",
               "buildTrainAddEngines", "buildTrainRemoveEngines", "buildTrainHelperEngines", "buildCabooseChange",
               "buildAutoBuildMsg", "buildOptionSingleLocos", "buildOptionBuildConsist", "buildTrainReqConsist",
               "buildNoTracksAtDestination")  # TrainBuilderEngines:838, an engine's destination
FAILURE_KEYS = ("buildError", "buildStagingCouldNotFindDest", "mbuildFail", "buildFailedTryNormalMode",
                "buildErrorStagingFullNote")
OPTION_HEADERS = {"MenuItemBuildOptions": "build", "buildStagingOptions": "staging", "buildCarRoutingOptions": "routing",
                  "buildOptionsForTrain": "enabled", "buildDisabledOptionsForTrain": "disabled",
                  "BorderLayoutSwitcherService": "switcher"}


@dataclass
class Line:
    number: int
    level: int
    text: str
    key: str | None = None
    fields: list[str] = field(default_factory=list)

    def f(self, index: int) -> str:
        return self.fields[index] if index < len(self.fields) else ""


class Matcher:
    """Templates compiled once, indexed by first word, most literal text first."""

    def __init__(self, templates: dict[str, str] = LINE_TEMPLATES):
        self.by_word: dict[str, list[tuple[int, str, re.Pattern]]] = {}
        self.anywhere: list[tuple[int, str, re.Pattern]] = []
        self.open_ended = {k for k, v in templates.items() if re.search(r"\{\d+\}\s*$", v)}
        for key, template in templates.items():
            norm = template.strip()  # Spacing is exact: an empty argument leaves a double space in the line.
            if not norm:
                continue
            entry = (-len(PLACEHOLDER.sub("", norm)), key, self._compile(norm))
            first = norm.split(" ", 1)[0]
            (self.anywhere if "{" in first else self.by_word.setdefault(first, [])).append(entry)
        for rows in self.by_word.values():
            rows.sort(key=lambda row: row[:2])
        self.anywhere.sort(key=lambda row: row[:2])

    @staticmethod
    def _compile(template: str) -> re.Pattern:
        parts = PLACEHOLDER.split(template)
        seen: set[str] = set()
        out = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                out.append(re.escape(part))
            elif part in seen:
                out.append(f"(?P=f{part})")
            else:
                seen.add(part)
                out.append(f"(?P<f{part}>.*?)")
        return re.compile("".join(out))

    def match(self, text: str) -> tuple[str, list[str]] | None:
        first = text.split(" ", 1)[0]
        rows = sorted(self.by_word.get(first, []) + self.anywhere, key=lambda row: row[:2])
        for _, key, regex in rows:
            found = regex.fullmatch(text)
            if found:
                values = found.groupdict()
                count = 1 + max((int(k[1:]) for k in values), default=-1)
                return key, [values.get(f"f{i}", "").strip() for i in range(count)]
        return None


MATCHER = Matcher()
STATUS_MATCHER = Matcher(STATUS_TEMPLATES)


def _complete(found: tuple[str, list[str]] | None) -> bool:
    """Is a matched piece a whole message, or could its last argument still be running on?"""
    if found is None:
        return False
    key, fields = found
    if key in STATUS_TAILED:
        index = STATUS_TAILED[key]
        return index < len(fields) and STATUS_MATCHER.match(fields[index]) is not None
    return key not in MATCHER.open_ended


def read(text: str) -> list[Line]:
    """Split a report into lines, joining the pieces JMRI wrapped.

    JMRI wraps a long line into pieces that end with a space, each as long as the width
    allows, and prints every piece with the same level prefix. Two pieces can only have
    been one line if together they were too long for the width, so a piece is joined
    with the next only when that holds, and then only until the result is a whole
    message. A message whose last argument is a status (the 'due to' lines) is whole
    once that argument is a known status; one that ends in free text is extended only
    while the longer text still matches. Pieces that never match are joined on length.
    """
    raw = []
    for number, line in enumerate(text.splitlines(), 1):
        found = PREFIX.match(line.rstrip("\r"))
        raw.append((number, int(found.group(1)), found.group(2)) if found else (number, 0, line.rstrip("\r")))
    longest = max((len(content) for _, _, content in raw), default=0)

    def continues(j: int, content: str) -> bool:
        return (content.endswith(" ") and j + 1 < len(raw) and raw[j + 1][1] == raw[j][1] and raw[j + 1][2].strip() != ""
                and len(content) + len(raw[j + 1][2].split()[0]) >= longest)

    lines: list[Line] = []
    i = 0
    while i < len(raw):
        number, level, content = raw[i]
        found = MATCHER.match(content.strip()) if content.strip() else None
        if content.strip() and not _complete(found):
            joined, j, best = content, i, (found, content, i)
            while continues(j, raw[j][2]) and j - i < MAX_WRAP:
                if best[0] is not None and best[0][0] not in STATUS_TAILED and MATCHER.match(raw[j + 1][2].strip()):
                    break  # the next piece is a line of its own, not the tail of an open-ended argument
                joined += raw[j + 1][2]
                j += 1
                longer = MATCHER.match(joined.strip())
                if longer:
                    best = (longer, joined, j)
                    if _complete(longer):
                        break
                elif best[0] is not None and best[0][0] not in STATUS_TAILED:
                    break  # free text that stopped matching: the earlier piece was whole
            found, content, i = best
            if found is None:  # never matched: join on length alone
                while continues(i, raw[i][2]) and MATCHER.match(raw[i + 1][2].strip()) is None:
                    content += raw[i + 1][2]
                    i += 1
        line = Line(number, level, content.strip())
        if found:
            line.key, line.fields = found
        lines.append(line)
        i += 1
    return lines


def status_gate(status: str) -> tuple[str | None, str]:
    """The gate and meaning of a 'due to' status from Track, Schedule, Router or Train."""
    rules = SCHEDULE_RULES + STATUS_RULES if status.startswith("schedule (") else STATUS_RULES
    for needle, gate, meaning in rules:
        if needle in status:
            return gate, meaning
    if re.fullmatch(r"Train \(.*\)", status):
        return None, "another train could carry it, so this one leaves it"
    return None, status


def gate_fix(gate: str | None) -> str:
    if gate and gate in GATES:
        test, screen, setting = GATES[gate]
        return f"{gate}: {test}. Fix: {screen}, {setting}."
    return ""


def _short(line: Line, gate: str | None = None) -> str:
    """One readable phrase for a refusal, with the gate and the screen that fixes it."""
    key = line.key or ""
    gate = gate or KEY_GATES.get(key)
    text = line.text
    if key in STATUS_TAILED:
        gate, meaning = status_gate(line.f(STATUS_TAILED[key]))
        text = f"{line.text} [{meaning}]"
    elif key in KEY_NOTES and KEY_NOTES[key]:
        text = f"{line.text} [{KEY_NOTES[key]}]"
    return f"{text} ({gate})" if gate else text


class Walker:
    """Folds the matched lines into the report dictionary."""

    def __init__(self, lines: list[Line]):
        self.lines = lines
        self.report: dict = {
            "train": None, "built_on": None, "jmri_version": None, "active_schedule": None, "railroad_comment": [],
            "levels": {}, "mode": None, "passes": None, "options": {}, "route": {"name": None, "stops": []},
            "requirements": [], "engines": {"found": None, "assigned": [], "excluded": [], "notes": []},
            "staging": {"departure": [], "terminal": []}, "excluded_cars": [], "found_cars": None,
            "car_list": [], "cars": {}, "ignored_moves_done": [], "not_routable": [],
            "outcome": {"status": None, "built": None, "failed": False, "failure": [], "warnings": 0, "ms": None},
            "unparsed": [],
        }
        self.section = "header"
        self.option_group: str | None = None
        self.stop: dict | None = None
        self.attempt: dict | None = None
        self.location: str | None = None
        self.pass_number = 1
        self.ignoring = False
        self.last_excluded: dict | None = None
        self.staging_side: str | None = None  # which staging check is open: the last of depart / terminate seen
        self.previous: Line | None = None

    def run(self) -> dict:
        for line in self.lines:
            if not line.text:
                continue
            if line.key is None:
                self._unparsed(line)
            else:
                self._line(line)
            self.previous = line
        self._close_attempt()
        levels = {line.level for line in self.lines if line.level}
        self.report["levels"] = {"present": sorted(levels), "complete": {1, 3, 5, 7} <= levels,
                                 "router_detailed": any(line.key in ("buildRouterReportLevelDetailed",
                                                                    "buildRouterReportLevelVeryDetailed")
                                                        for line in self.lines)}
        return self.report

    def _unparsed(self, line: Line):
        if self.section == "header" and line.level in (0, 1):
            self.report["railroad_comment"].append(line.text)
        elif self.section == "options" and self.option_group:
            self.report["options"].setdefault(self.option_group, []).append(line.text)
        elif self.section in ("requirements", "route") and line.level == 5:
            self.report["requirements"].append(line.text)  # a type or road list under its header
        elif self.attempt is not None:
            self.attempt["events"].append({"line": line.number, "key": None, "kind": "unknown", "text": line.text,
                                           "location": self.location})
        else:
            self.report["unparsed"].append({"line": line.number, "text": line.text})

    def _line(self, line: Line):
        key, r = line.key, self.report
        if key == "BuildReportMsg":
            r["train"], r["built_on"] = line.f(0), line.f(1)
        elif key == "BuildReportVersion":
            r["jmri_version"] = line.f(0)
        elif key == "buildActiveSchedule":
            r["active_schedule"] = line.f(0)
        elif key in ("buildReportLevelThree", "buildReportLevelFive", "buildReportLevelSeven",
                     "buildRouterReportLevelDetailed", "buildRouterReportLevelVeryDetailed"):
            pass
        elif key.startswith(FAILURE_KEYS):
            self._close_attempt()
            r["outcome"]["failure"].append({"line": line.number, "key": key, "text": line.text,
                                           "gate": KEY_GATES.get(key), "fix": gate_fix(KEY_GATES.get(key))})
        elif key in OPTION_HEADERS:
            self.section, self.option_group = "options", OPTION_HEADERS[key]
        elif key in ("BuildModeNormal", "BuildModeAggressive", "BuildModeOnTime"):
            r["mode"] = {"BuildModeNormal": "Normal", "BuildModeAggressive": "Aggressive", "BuildModeOnTime": "On Time"}[key]
            r["options"].setdefault("build", []).append(line.text)
        elif key == "BuildNumberPasses":
            r["passes"] = line.f(0)
            r["options"].setdefault("build", []).append(line.text)
        elif self.section == "options" and key not in ("buildTrainRoute", "buildTrainNameAndDesc"):
            r["options"].setdefault(self.option_group or "build", []).append(line.text)
        elif key == "buildTrainRoute":
            self.section = "route"
            r["route"]["name"] = line.f(1)
        elif key in ("buildLocRequestMoves", "buildLocTerminates", "buildLocNoDropsOrPickups", "buildLocSkippedMaxTrain"):
            self._route_stop(line)
        elif key == "buildRouteRequest":
            r["route"].update(requested_cars=line.f(1), requested_moves=line.f(2))
            self.section = "requirements"
        elif key.startswith("buildTrainReq") or key in ("buildTrainRequiresCaboose", "buildTrainRequiresFRED",
                                                       "buildTrainRoads", "buildTrainCabooseRoads",
                                                       "buildTrainLocoRoads", "buildTrainLoads", "buildTrainOwners",
                                                       "buildTrainBuiltAfter", "buildTrainBuiltBefore",
                                                       "buildTrainServicesEngineTypes", "buildTrainServicesCarTypes",
                                                       "buildTrainNoCaboose", "buildTrainNoFred", "buildTrainIsSwitcher"):
            self.section = "requirements"
            r["requirements"].append(line.text)
        elif key.startswith(ENGINE_KEYS):
            self.section = "engines"
            self._engine(line)
        elif key in MID_SEARCH_GATES and self.attempt is not None:
            self.attempt["events"].append(self._event(line, "refused", MID_SEARCH_GATES[key]))
        elif key in STAGING_EITHER:
            self._staging(self.staging_side or "departure", line)
        elif key in STAGING_TERMINAL:
            self._staging("terminal", line)
        elif key in STAGING_DEPARTURE:
            self._staging("departure", line)
        elif key.startswith(EXCLUDE_KEYS) and self.attempt is None:
            self._excluded(line)
        elif key == "buildTrainCanServiceWait" and self.last_excluded is not None:
            self.last_excluded["note"] = line.text
        elif key == "buildFoundCars":
            r["found_cars"] = line.f(0)
            self.section = "car_list"
        elif key in ("buildCarsAtLocation", "buildCarsInStaging"):
            r["car_list"].append({"location": line.f(1), "cars": line.f(0)})
        elif key == "buildMultiplePass":
            self.pass_number = int(line.f(0)) if line.f(0).isdigit() else self.pass_number + 1
            self.section = "building"
        elif key == "buildLocReqMoves":
            self._close_attempt()
            self.section = "building"
            self.ignoring = False
            self.stop = {"id": line.f(1), "location": line.f(0), "pass": self.pass_number,
                         "requested_moves": line.f(2), "available": f"{line.f(3)}/{line.f(4)}", "notes": []}
            r["route"].setdefault("passes", []).append(self.stop)
        elif key == "buildStatusMsg":
            self._close_attempt()
            if self.stop is not None:
                self.stop["result"] = {"status": line.f(0), "assigned": line.f(1), "requested": line.f(2)}
        elif key == "buildMovesCompleted":
            self._close_attempt()
            self.ignoring = True
        elif key == "buildCarIgnored" and self.ignoring:
            r["ignored_moves_done"].append({"car": line.f(0), "load": line.f(3), "at": f"{line.f(4)}, {line.f(5)}",
                                           "stop": self.stop["id"] if self.stop else None})
        elif key == "buildLocSkipped" and self.attempt is not None and line.level != 1:
            # Inside a car's search (TBC:1731, level 5) the skipped stop is one destination refused, gate D2;
            # at level 1 (TBB:3065) it is the pickup stop itself, handled as a stop note below.
            self.attempt["events"].append(self._event(line, "refused", "D2"))
        elif key in ("buildLocSkipped", "buildLocNoPickups", "buildLocDirection", "buildNoPickupsFromStaging",
                     "buildNoCarsAtLocation", "buildExtraPassForLocation", "buildRouteRandomControl",
                     "buildDepartStagingAggressive", "buildSendToTerminal", "buildCustomLoadOptions",
                     "buildLoadCarLoads", "buildLoadAnyCarLoads", "buildLoadsStaging", "buildWarnDepartStaging",
                     "buildOnlyFirstXXXCars", "buildTracksNotQuickService", "buildTrackNotQuick",
                     "buildRouteNoLocalLocation"):
            self._close_attempt()
            note = _short(line)
            if key in ("buildLoadCarLoads", "buildLoadAnyCarLoads", "buildLoadsStaging"):
                note = f"Departure staging option: {line.text}"
            elif key == "buildCustomLoadOptions":
                return
            (self.stop["notes"] if self.stop is not None else r["route"].setdefault("notes", [])).append(note)
        elif key in ("buildLocosInStaging", "buildLocosAtLocation", "buildLocoAtLocWithMoves",
                     "buildEngineRoadModelType", "BuildEngineBunit", "buildLocoHasRequiredHp"):
            self.report["engines"].setdefault("available", []).append(line.text)
        elif key in ("buildCarAtLocWithMoves", "buildCarAtLocWithMovesPriority", "buildStagingCarAtLoc",
                     "buildDepartingStagingCars", "buildCarIsCaboose", "buildCarHasFRED", "buildCarLeadKernel",
                     "buildCarPartOfKernel", "buildTrackModePriority", "buildTrackModeCarPriority",
                     "buildBypassCarServiceOrder"):
            r["car_list"].append(line.text)
        elif key in ("buildRemoveCars", "buildRemoveCarsNotNeeded", "buildRemoveCarsStaging", "buildSortCarsByLastDate",
                     "buildRouteRequest", "buildDoneAssignEnginesStaging", "buildDoneAssingEnginesTrain",
                     "buildTrain", "NormalModeWhenBuilding", "buildFailedTryNormalMode"):
            pass
        elif key in SEARCH_STARTS:
            self._start_attempt(line)
        elif key in PICKUP_REFUSALS:
            self._start_attempt(line)
            self.attempt["events"].append(self._event(line, "refused"))
            self._close_attempt(PICKUP_REFUSALS[key])
        elif key == "buildCarsNotRoutable":
            self._close_attempt()
            self.section = "summary"
        elif key == "buildCarNotRoutable":
            r["not_routable"].append({"car": line.f(0), "at": f"{line.f(1)}, {line.f(2)}",
                                      "final_destination": f"{line.f(3)}, {line.f(4)}".rstrip(", ")})
        elif key in ("StatusPartialBuilt", "StatusBuilt"):
            self._close_attempt()
            r["outcome"].update(status=line.text, built=True)
        elif key == "buildFailedMsg":
            self._close_attempt()
            r["outcome"].update(status="Build failed", built=False, failed=True)
            self._thrown_warning()
        elif key == "buildWarningMsg":
            r["outcome"]["warnings"] = int(line.f(1)) if line.f(1).isdigit() else line.f(1)
        elif key == "buildTime":
            r["outcome"]["ms"] = line.f(1)
        elif key == "TrainRequirements":
            self.section = "requirements"
        elif key == "buildSearchingLocation" and self.attempt is not None:
            self.location = line.f(0)
            self.attempt["events"].append({"line": line.number, "key": key, "kind": "location", "text": line.text,
                                           "location": line.f(0), "stop": line.f(1)})
        elif key in ENDERS:
            if self.attempt is None or self.attempt["car"] != line.f(0):
                self._start_attempt(line)
            if ENDERS[key] == ASSIGNED:
                self.attempt["destination"] = f"{line.f(1)}, {line.f(2)}" if key == "buildCarAssignedDest" \
                    else f"{line.f(2)}, {line.f(3)}"
            self.attempt["events"].append(self._event(line, "outcome"))
            self._close_attempt(ENDERS[key])
        elif self.attempt is not None:
            kind = "accepted" if key in ACCEPTED else "note" if key in ("buildCouldNotFindDestForCar",
                                                                       "buildTrackSequentialMode",
                                                                       "buildSetFinalDestDiv", "buildTrySpurLoad",
                                                                       "buildTrySendCarToStaging",
                                                                       "buildTryStagingToStaging",
                                                                       "buildCarDoesNotHaveDest",
                                                                       "buildSpurScheduleLoad",
                                                                       "buildTrackFullHasAlternate",
                                                                       "buildReturnCarToStaging",
                                                                       "buildLeaveCarInStaging") else "refused"
            if key == "buildHoldCarValidRoute":
                self.attempt["held"] = True
            if key == "buildWarningCarNotRoutable":
                self.attempt["router_failed"] = True
            self.attempt["events"].append(self._event(line, kind))
        else:
            r.setdefault("unhandled", []).append({"line": line.number, "key": key, "text": line.text})

    def _route_stop(self, line: Line):
        key = line.key
        stop = {"id": line.f(0) if key != "buildLocSkippedMaxTrain" else line.f(0), "kind": line.f(1),
                "location": line.f(2), "direction": line.f(3), "text": line.text}
        if key == "buildLocSkippedMaxTrain":
            stop.update(location=line.f(1), direction=line.f(2), kind=None, skipped=True, max_length=f"{line.f(4)} {line.f(5)}")
        elif key == "buildLocNoDropsOrPickups":
            stop.update(moves=0, max_length=f"{line.f(4)} {line.f(5)}")
        else:
            work = f"{line.f(5)}{line.f(6)}{line.f(7)}".lower()
            stop.update(moves=line.f(4), pick_ups="pick ups" in work, set_outs="set outs" in work,
                        local_moves="local moves" in work,
                        terminates=key == "buildLocTerminates",
                        max_length=None if key == "buildLocTerminates" else f"{line.f(8)} {line.f(9)}")
        self.report["route"]["stops"].append(stop)

    def _engine(self, line: Line):
        engines = self.report["engines"]
        if line.key == "buildFoundLocos":
            engines["found"] = line.f(0)
        elif line.key == "buildEngineAssigned":
            engines["assigned"].append({"engine": line.f(0), "departs": line.f(1), "destination": f"{line.f(2)}, {line.f(3)}"})
        elif line.key.startswith(("buildExcludeEng", "buildErrorEng", "buildAssignedHp")):
            engines["excluded"].append({"engine": line.f(0), "text": line.text, "line": line.number})
        else:
            engines["notes"].append(line.text)

    def _staging(self, side: str, line: Line):
        key = line.key
        if key in ("buildDepartStaging", "buildTerminateStaging"):
            self.staging_side = side
        gate = KEY_GATES.get(key)
        if side == "terminal" and key in STAGING_EITHER:
            gate = "A7"
        row = {"line": line.number, "key": key, "text": line.text}
        if key in ("buildStagingAvail", "buildTrainCanDepartTrack", "buildTrainCanTerminateTrack", "buildStagingReturn",
                   "buildUserSelectedDeparture", "buildUserSelectedArrival", "buildOnlyOneDepartureTrack"):
            row["kind"] = "accepted"
        elif key == "buildStagingTrackRestriction":
            # TB:235 and TBB:2093 print this after the specific refusal; it is the sum, not a separate check
            row.update(kind="summary", gate=gate, text=f"{line.text} [sums up the refusal above; not a separate check]")
        elif gate:
            row.update(kind="rejected", gate=gate, fix=gate_fix(gate))
        else:
            row["kind"] = "note"
        self.report["staging"][side].append(row)

    def _excluded(self, line: Line):
        gate = KEY_GATES.get(line.key)
        row = {"car": line.f(0), "text": line.text, "gate": gate, "fix": gate_fix(gate), "line": line.number}
        self.report["excluded_cars"].append(row)
        self.last_excluded = row

    def _start_attempt(self, line: Line):
        self._close_attempt()
        key = line.key
        car = line.f(0)
        if key == "buildCarRoutingBegins":
            load, origin = f"{line.f(2)} ({line.f(3)})", f"{line.f(4)} ({line.f(5)}, {line.f(6)})"
            target = f"{line.f(7)}, {line.f(8)}".rstrip(", ")
        elif key == "buildSearchForSpur":
            load, origin, target = f"custom {line.f(3)} ({line.f(4)})", f"{line.f(5)} ({line.f(6)}, {line.f(7)})", None
        elif key == "buildFindDestinationForCar":
            load, origin, target = f"{line.f(3)} ({line.f(4)})", f"{line.f(5)} ({line.f(6)}, {line.f(7)})", None
        elif key in ("buildSearchTrackNewLoad", "buildSearchTrackLoadStaging"):
            load, origin, target = f"{line.f(2)} ({line.f(3)})", f"({line.f(4)}, {line.f(5)})", line.f(6)
        else:
            load, origin, target = "", "", None
        self.attempt = {"car": car, "stop": self.stop["id"] if self.stop else None, "pass": self.pass_number,
                        "search": SEARCH_STARTS.get(key, "pick up"), "load": load, "from": origin,
                        "final_destination": target, "first_line": line.number, "events": [], "outcome": None,
                        "destination": None}
        self.location = None

    def _event(self, line: Line, kind: str, gate: str | None = None) -> dict:
        event = {"line": line.number, "key": line.key, "kind": kind, "text": line.text, "location": self.location}
        gate = gate or KEY_GATES.get(line.key or "")
        if kind == "refused":
            event["short"] = _short(line, gate)
            if line.key in STATUS_TAILED:
                gate, _ = status_gate(line.f(STATUS_TAILED[line.key]))
            if gate:
                event["gate"] = gate
        return event

    def _thrown_warning(self):
        """A buildWarningRsNoTrack is an exclusion (TBB:827) unless the builder threw it (TBB:1477); then
        buildFailed prints it as the line right before buildFailedMsg (TB:727-730) and it is the cause."""
        prev, r = self.previous, self.report
        if prev is None or prev.key != "buildWarningRsNoTrack" or r["outcome"]["failure"]:
            return
        r["excluded_cars"] = [row for row in r["excluded_cars"] if row["line"] != prev.number]
        r["outcome"]["failure"].append({"line": prev.number, "key": prev.key, "text": prev.text, "gate": "B1",
                                        "fix": gate_fix("B1")})

    def _close_attempt(self, outcome: str | None = None):
        if self.attempt is None:
            return
        attempt = self.attempt
        if outcome is None:
            outcome = NO_DESTINATION if any(e["key"] == "buildNoDestForCar" for e in attempt["events"]) else "open"
        if outcome == NO_DESTINATION and attempt.get("held"):
            outcome = HELD
        attempt["outcome"] = outcome
        attempt["last_line"] = attempt["events"][-1]["line"] if attempt["events"] else attempt["first_line"]
        self.report["cars"].setdefault(attempt["car"], []).append(attempt)
        self.attempt = None
        self.location = None


def parse(text: str) -> dict:
    return Walker(read(text)).run()


def _attempt_summary(attempt: dict, full: bool) -> dict:
    row = {"stop": attempt["stop"], "pass": attempt["pass"], "search": attempt["search"], "load": attempt["load"],
           "from": attempt["from"], "lines": f"{attempt['first_line']}-{attempt['last_line']}",
           "outcome": attempt["outcome"], "destination": attempt["destination"]}
    if attempt.get("final_destination"):
        row["final_destination"] = attempt["final_destination"]
    if full:
        row["events"] = attempt["events"]
        return row
    row["refused"] = [e["short"] for e in attempt["events"] if e["kind"] == "refused"]
    accepted = [e["text"] for e in attempt["events"] if e["kind"] == "accepted"]
    if accepted:
        row["accepted"] = accepted
    notes = [e["text"] for e in attempt["events"] if e["kind"] == "note"]
    if notes:
        row["notes"] = notes
    gates = sorted({e["gate"] for e in attempt["events"] if e.get("gate")}, key=_gate_order)
    if gates:
        row["gates"] = gates
    return row


def _gate_order(gate: str) -> tuple[str, int]:
    return gate[0], int(gate[1:] or 0)


def _car_story(car: str, attempts: list[dict], full: bool) -> dict:
    last = attempts[-1]
    outcomes = [a["outcome"] for a in attempts]
    final = ASSIGNED if ASSIGNED in outcomes else last["outcome"]
    story = {"car": car, "outcome": final, "destination": next((a["destination"] for a in attempts if a["destination"]), None),
             "attempts": [_attempt_summary(a, full) for a in attempts]}
    gates = sorted({g for a in attempts for e in a["events"] for g in [e.get("gate")] if g}, key=_gate_order)
    if gates and final != ASSIGNED:
        story["gates"] = gates
        story["fixes"] = [gate_fix(g) for g in gates]
    return story


def _why_stuck(story: dict) -> str:
    """One sentence on why a car got no destination, from the dominant gate."""
    counts: dict[str, int] = {}
    for attempt in story["attempts"]:
        for gate in attempt.get("gates", []):
            counts[gate] = counts.get(gate, 0) + 1
    if story["outcome"] == HELD:
        return "held for a scheduled spur that is not open now"
    if story["outcome"] == PICKUP_REFUSED:
        return "could not be picked up: " + "; ".join(story["attempts"][-1].get("refused", [])[:1])
    if not counts:
        last = [r for a in story["attempts"] for r in a.get("refused", [])]
        notes = [n for a in story["attempts"] for n in a.get("notes", [])]
        return last[-1] if last else notes[-1] if notes else "no track on the route took it"
    gate = max(counts, key=lambda g: (counts[g], _gate_order(g)))
    test, screen, setting = GATES.get(gate, ("", "", ""))
    return f"most refusals were {gate} ({test}); fix on {screen}: {setting}"


def summarize(report: dict, stories: list[dict]) -> list[str]:
    out = []
    outcome = report["outcome"]
    if outcome["failed"]:
        causes = [f["text"] for f in outcome["failure"]]
        gates = [f["gate"] for f in outcome["failure"] if f["gate"]]
        out.append(f"Build failed for train {report['train']}: " + " ".join(causes[:2]))
        if gates:
            out.append(gate_fix(gates[-1]))
        rejected = [row for side in ("departure", "terminal") for row in report["staging"][side] if row["kind"] == "rejected"]
        if rejected:
            out.append("Staging checks that failed: " + "; ".join(r["text"] for r in rejected[:4]))
    elif outcome["status"]:
        warnings = outcome["warnings"]
        out.append(f"{report['train']}: {outcome['status']}, {warnings} warning{'' if warnings == 1 else 's'}.")
    for stop in report["route"].get("passes", []):
        result = stop.get("result")
        if result:
            out.append(f"{stop['location']} ({stop['id']}): {result['status']}, {result['assigned']}/{result['requested']} "
                       f"moves used" + (f"; {'; '.join(stop['notes'])}" if stop["notes"] else "") + ".")
        elif stop["notes"]:
            out.append(f"{stop['location']} ({stop['id']}): {'; '.join(stop['notes'])}.")
    excluded = report["excluded_cars"]
    if excluded:
        by_gate: dict[str, list[str]] = {}
        for row in excluded:
            by_gate.setdefault(row["gate"] or "other", []).append(row["car"])
        out.append("Excluded before the search: " + "; ".join(
            f"{gate} {', '.join(cars)}" for gate, cars in sorted(by_gate.items(), key=lambda kv: _gate_order(kv[0]) if kv[0] != 'other' else ('Z', 0))) + ".")
    stuck = [s for s in stories if s["outcome"] not in (ASSIGNED, DEFERRED)]
    for story in stuck:
        out.append(f"{story['car']} {story['outcome'].replace('_', ' ')}: {_why_stuck(story)}.")
    if report["not_routable"]:
        out.append("Not routable to their final destination: " + "; ".join(
            f"{r['car']} at {r['at']} to {r['final_destination']}" for r in report["not_routable"]) + ".")
    if report["ignored_moves_done"]:
        places: dict[str, list[str]] = {}
        for row in report["ignored_moves_done"]:
            places.setdefault(row["stop"] or "", []).append(row["car"])
        out.append("Ignored because the stop's moves were used up: " + "; ".join(
            f"{stop} {', '.join(cars)}" for stop, cars in places.items()) + ". Raise Moves on the route if they should go.")
    levels = report["levels"]
    if not levels.get("present"):
        out.append("This text has no level marks, so it may be a preview with some detail levels left out; "
                   "the file JMRI wrote in buildstatus holds every level.")
    elif not levels.get("complete"):
        out.append("This text lacks some detail levels; the file JMRI wrote in buildstatus holds every level.")
    routed = report["not_routable"] or any(a["search"] in ("router", "custom load") and a["outcome"] != ASSIGNED
                                           for s in stories for a in s["attempts"])
    if routed and not levels.get("router_detailed"):
        out.append("Router lines are at Normal; set the router build report level to Detailed in Settings to see each hop.")
    return out


def explain(text: str, car: str | None = None, detail: str = "normal") -> dict:
    """The report as a diagnosis: header, outcome, stops, excluded and stuck cars, each car's story."""
    report = parse(text)
    full = detail == "full"
    stories = [_car_story(name, attempts, full) for name, attempts in report["cars"].items()]
    result = {
        "train": report["train"], "built_on": report["built_on"], "jmri_version": report["jmri_version"],
        "active_schedule": report["active_schedule"], "mode": report["mode"], "passes": report["passes"],
        "outcome": report["outcome"], "summary": summarize(report, stories),
    }
    if car:
        wanted = car.replace(" ", "").lower()
        same = lambda name: name.replace(" ", "").lower() == wanted  # noqa: E731
        result["car"] = car
        result["excluded"] = [row for row in report["excluded_cars"] if same(row["car"])]
        result["ignored_moves_done"] = [row for row in report["ignored_moves_done"] if same(row["car"])]
        result["not_routable"] = [row for row in report["not_routable"] if same(row["car"])]
        result["story"] = next((s for s in stories if same(s["car"])), None)
        if result["story"] is None and not (result["excluded"] or result["ignored_moves_done"]):
            result["note"] = f"{car} does not appear in this report: it was not at a stop of this train, or is not a car."
        return result
    result.update(route=report["route"], requirements=report["requirements"], engines=report["engines"],
                  staging=report["staging"], excluded_cars=report["excluded_cars"], found_cars=report["found_cars"],
                  cars=stories, ignored_moves_done=report["ignored_moves_done"], not_routable=report["not_routable"],
                  levels=report["levels"], unparsed=report["unparsed"])
    if full:
        result.update(options=report["options"], car_list=report["car_list"])
    return result


def report_path(ops_dir: str | Path, train: str) -> Path:
    return Path(ops_dir) / "buildstatus" / f"train ({train}).txt"


def explain_file(path: str | Path, car: str | None = None, detail: str = "normal") -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No build report at {path}. JMRI writes one in buildstatus when a train is built.")
    result = explain(path.read_text(encoding="utf-8", errors="replace"), car, detail)
    result["path"] = str(path)
    return result
