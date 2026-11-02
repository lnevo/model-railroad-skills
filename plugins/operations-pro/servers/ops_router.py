"""Car routing as JMRI 5.16 does it, read from the files.

A port of jmrit/operations/router/Router.java (R), the parts of Train.java (T) and
TrainManager.java (TM) the router calls, and the custom load spur search in
trainbuilder/TrainBuilderCars.java (TBC). Method names follow the Java so a line here
can be checked against the source. Line numbers are tag v5.16.

Entry points:

  route_car(gates, car, location, track=None, train=None, build=None)
      Router.setDestination for a copy of the car with this final destination.
  route_path(gates, car, target, check_target=True)
      The chain of trains to the target with no train named, or None.
  find_spur_for_load(gates, car, train, build=None)
      TBC.findFinalDestinationForCarLoad: scheduled spurs by moves, hold, staging.
  router_detail(gates, car, target, train)
      Both of the above for one why_not answer.

A Build describes the train being built. Without one no train is building, as
when the router is asked outside a build: route moves and train length are then
never tested (T:2108, 2121). With one, the named train starts empty unless lengths
and moves are given, and its termination staging track is the one named.

What files cannot settle is listed in "uncertain" rather than guessed: quick
service timing during a build, a schedule's random draw. Pool lending (judged against the files as they stand, not after earlier set outs in the same build), planned
pick ups and aggressive mode are worked out from the files as Track does.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ops_data import INTERCHANGE, QUICK_SERVICE, SPUR, STAGING, YARD, Car, Location, Track, Train

OKAY = "okay"
# How a JMRI status string starts decides what the router does next. These are the English
# Track constants (Track.java 190-201), so a status here starts as JMRI's does.
LENGTH, CAPACITY, TYPE, ROAD = "rolling stock length", "track capacity", "type", "road"
DESTINATION, NO_FD = "car's final destination", "car doesn't have a final destination"
LOAD, SCHEDULE, CUSTOM, ERROR_TRACK = "load", "schedule", "custom", "ERROR wrong track for location"
NOT_THIS_TRAIN = "Train"  # RouterTrain "Train ({0})"; STATUS_NOT_THIS_TRAIN_PREFIX is "Train ".
NOT_ABLE, DISABLED = "could not route car", "router is disabled"
# canSpecifiedTrainService answers (R:1311-1314).
NO, YES, NOT_NOW, NO_SPECIFIED_TRAIN = "no", "yes", "not now", "no specified train"

_GATE_STATUS = {"E1": ERROR_TRACK, "E2": TYPE, "E3": TYPE, "E4": ROAD, "E5": LENGTH, "E6": DESTINATION,
                "E7": NO_FD, "E8": LOAD}
_NULL = object()  # R:1163 caches a "null" train for a pair no train serves.


def not_this_train(train: Train) -> str:
    return f"{NOT_THIS_TRAIN} ({train.name})"


@dataclass
class Build:
    """The train being built. Lengths and moves are per route stop id, as RouteLocation holds them."""
    train_length: dict[str, int] = field(default_factory=dict)
    car_moves: dict[str, int] = field(default_factory=dict)
    termination_track_id: str = ""


def java_hashtable_order(keys: list[str]) -> list[str]:
    """The order java.util.Hashtable enumerates String keys put in this order.

    LocationManager.getList and Location.getTracksList enumerate a Hashtable, so ties in
    move counts fall in this order (LM:285, 302). Capacity 11, load factor 0.75, a rehash
    doubles plus one, new entries go to the head of a bucket, enumeration runs from the
    last bucket down.
    """
    def java_hash(text: str) -> int:
        data = text.encode("utf-16-be")
        h = 0
        for i in range(0, len(data), 2):
            h = (31 * h + (data[i] << 8 | data[i + 1])) & 0xFFFFFFFF
        return h

    capacity, count = 11, 0
    threshold = int(capacity * 0.75)
    table: list[list[str]] = [[] for _ in range(capacity)]
    for key in keys:
        h = java_hash(key)
        if any(key in bucket for bucket in table):
            continue
        if count >= threshold:
            old = table
            capacity = capacity * 2 + 1
            threshold = int(capacity * 0.75)
            table = [[] for _ in range(capacity)]
            for i in range(len(old) - 1, -1, -1):
                for entry in old[i]:
                    table[(java_hash(entry) & 0x7FFFFFFF) % capacity].insert(0, entry)
            h = java_hash(key)
        table[(h & 0x7FFFFFFF) % capacity].insert(0, key)
        count += 1
    return [key for i in range(capacity - 1, -1, -1) for key in table[i]]


def _minutes(time: str) -> int | None:
    """TrainCommon.convertStringTime for "days:hours:minutes" or "hours:minutes"; None for other forms."""
    parts = time.split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    day, hour, minute = ([0] if len(parts) == 2 else []) + [int(p) for p in parts]
    return day * 24 * 60 + hour * 60 + minute


def _ignore_case(text: str) -> str:
    return text.upper().lower()  # String.compareToIgnoreCase folds each character both ways.


class Router:
    """One Router.setDestination at a time; the lists and the train cache live for one call, as in R."""

    def __init__(self, gates, build: Build | None = None):
        self.g = gates
        self.rr = gates.rr
        self.build = build
        self._train: Train | None = None
        self.status = ""
        self.path: list[dict] | None = None
        self.how = ""
        self.steps: list[str] = []
        self.uncertain: list[str] = []
        self._service_status: dict[str, str] = {}
        self._bumped: dict[str, int] = {}  # Track.addDropRS bumps moves on each new destination (TR:818).
        self._loaded_moves = gates.loaded_moves()  # Moves as JMRI holds them after a load.
        self.shown: list[dict] | None = None  # Car.getRoutePath: cleared with the final destination (C:390).
        locations = java_hashtable_order(list(self.rr.locations))
        self._location_order = [self.rr.locations[i] for i in locations]

    # Lists the Java builds from the managers.
    def _trains_by_name(self) -> list[Train]:
        return sorted(self.rr.trains.values(), key=lambda t: _ignore_case(t.name))  # TM:604, 677

    def _tracks_by_name(self, location: Location, kind: str | None) -> list[Track]:
        by_id = sorted(location.tracks, key=lambda t: t.id)  # LOC:850 sorts ids as strings.
        return sorted([t for t in by_id if kind is None or t.type == kind], key=lambda t: _ignore_case(t.name))

    def _is_alternate(self, track: Track) -> bool:
        location = self.rr.locations.get(track.location_id)
        return bool(location) and any(t.alternate_id == track.id for t in location.tracks)  # TR:2486

    def tracks_by_moves(self, kind: str | None) -> list[Track]:
        """LocationManager.getTracksByMoves: every location, alternates dropped, fewest moves first (LM:323)."""
        tracks = [t for loc in self._location_order for t in self._tracks_by_name(loc, kind)]
        return sorted([t for t in tracks if not self._is_alternate(t)], key=self._moves)

    def _moves(self, track: Track) -> int:
        return self._loaded_moves.get(track.id, track.moves) + self._bumped.get(track.id, 0)

    def all_tracks(self, kind: str | None) -> list[Track]:
        """LocationManager.getTracks (LM:302)."""
        return [t for loc in self._location_order for t in self._tracks_by_name(loc, kind)]

    def location_tracks_by_moves(self, location: Location, kind: str | None) -> list[Track]:
        """Location.getTracksByMoves: scheduled tracks first, alternates dropped (LOC:925)."""
        moved = sorted([t for t in sorted(location.tracks, key=lambda t: t.id) if kind is None or t.type == kind],
                       key=self._moves)
        moved = [t for t in moved if not self._is_alternate(t)]
        # Track.getScheduleId is empty on any track but a spur (TR:1906), whatever the file holds.
        return ([t for t in moved if t.schedule_id and t.is_spur]
                + [t for t in moved if not (t.schedule_id and t.is_spur)])

    # Car state, as the Java setters change it.
    @staticmethod
    def _set_track(car: Car, track: Track) -> None:
        car.location_id, car.track_id = track.location_id, track.id

    @staticmethod
    def _set_destination_track(car: Car, track: Track | None) -> None:
        if track is not None:
            car.destination_id = track.location_id
        car.dest_track_id = track.id if track else ""

    def _clone(self, car: Car) -> Car:
        """R:1240 clone: Car.copy keeps no kernel, schedule item, train or final destination track."""
        length = car.length
        if car.kernel:
            length = str(self.rr.kernel_length(car) - self.rr.coupler)
        return replace(car, length=length, kernel="", lead=False, schedule_item="", train_id="", fd_track_id="",
                       destination_id=car.fd_id, dest_track_id=car.fd_track_id, wait=0)

    # Track.isRollingStockAccepted, Car.checkDestination and Car.setDestination.
    def _gates(self, car: Car, location: Location, track: Track) -> dict[str, dict]:
        return {g["gate"]: g for g in self.g.check_destination(car, location, track)}

    def _space(self, car: Car, track: Track) -> str:
        """The space part of Track.isRollingStockAccepted (TR:1631-1660), with the Gates' own counts:
        reserved less pick ups in aggressive mode (TR:786), set outs, pool lending and planned pick ups."""
        rr, g = self.rr, self.g
        if track.id in (car.track_id, car.dest_track_id):
            return OKAY
        need = rr.kernel_length(car)
        used, reserved, setouts = rr.used_length(track), g._reserved(track), g._setouts(track)
        if used + reserved + need <= track.length and setouts + need <= track.length:
            return OKAY
        if track.pool and g._pool_lends(track, need):  # Pool.requestTrackLength
            return OKAY
        if track.ignore_used and g._available(track) >= need:  # checkPlannedPickUps
            return OKAY
        pool_length = sum(t.length for t in g._pool(track))
        if (not track.pool and track.length < need) or (track.pool and pool_length < need):
            return f"{CAPACITY} ({need} longer than track {track.length})"
        quick = self._quick_service(track, need)
        if quick is not None:
            return quick
        return f"{LENGTH} ({need} needed, {g._available(track)} available of {track.length})"

    def _quick_service(self, track: Track, need: int) -> str | None:
        """Track.checkQuickServiceTrack (TR:1691-1785); None where JMRI answers DISABLED. Only a train being
        built counts (TrainManager.getTrainBuilding), and only rolling stock a train will pull frees room."""
        rr, g = self.rr, self.g
        if not track.load_options & QUICK_SERVICE or not rr.option("buildOptions", "onTime"):
            return None
        if self.build is None:
            return None
        train = self._train
        depart = g.depart_minutes(train) if train is not None else None
        if depart is None:
            self.uncertain.append(f"{track.name}: quick service timing, no train or departure time to test")
            return f"{LENGTH} (quick service)"
        self.uncertain.append(f"{track.name}: quick service counts pick up times as the files hold them, "
                              f"not those this build sets")
        dwell = rr.setup.get("buildOptions", {}).get("dwellTime", "60")
        dwell = int(dwell) if dwell.isdigit() else 60
        space = track.length - rr.used_length(track) - rr.used_length(track, clones=True)  # getTotalUsedLength
        on = ([(c, g.x.car.get(c.id, {}), rr.car_length(c) or 0, c.train_id)
               for c in (rr.cars[i] for i in java_hashtable_order(list(rr.cars))) if c.track_id == track.id],
              [(e, g.x.engine.get(e.id, {}), g._engine_length(e), g.x.engine.get(e.id, {}).get("trainId", ""))
               for e in (rr.engines[i] for i in java_hashtable_order(list(rr.engines))) if e.track_id == track.id])
        for group in on:
            for _, raw, length, train_id in group:
                pulled = self._route_destination(raw, train_id)
                pickup = raw.get("pickupTime", "")
                if pulled and pickup:
                    minutes = _minutes(pickup)
                    if minutes is None:
                        self.uncertain.append(f"{track.name}: pick up time {pickup} cannot be read")
                        return f"{LENGTH} (quick service)"
                    if minutes + dwell > depart:
                        return f"{LENGTH} ({need} needed, pulled at {pickup} after {train.name} departs)"
                    space += length
                elif pulled and train_id == train.id and raw.get("lastTrainId", "") != train.id:
                    space += length
                if space >= need:
                    break
            if space >= need:
                break
        return OKAY if space >= need else f"{LENGTH} ({need} needed, {space} available of {track.length})"

    def _route_destination(self, raw: dict, train_id: str) -> bool:
        """RollingStock.getRouteDestination after a load: a stop on the route of the car's train (RS:1522)."""
        stop_id, train = raw.get("routeDestinationId", ""), self.rr.trains.get(train_id)
        return bool(stop_id) and train is not None and any(s.id == stop_id for s in self.rr.stops(train))

    def accepted(self, car: Car, track: Track) -> str:
        """Track.isRollingStockAccepted (TR:1572): type, road, length, destination filter, routed, load, space."""
        results = self._gates(car, self.rr.locations[track.location_id], track)
        for code in ("E3", "E4", "E5", "E6", "E7", "E8"):
            if results[code]["status"] == "fail":
                return f"{_GATE_STATUS[code]} ({results[code]['reason']})"
        return self._space(car, track)

    def _schedule(self, car: Car, location: Location, track: Track) -> str:
        e10 = self._gates(car, location, track)["E10"]
        if e10["status"] == "fail":
            custom = not track.schedule_id and track.is_spur
            if custom:
                return f"car has a {CUSTOM} {LOAD} ({car.load})"  # TR:2069 carHasA
            return f"{SCHEDULE} ({e10['reason']})"
        if any(g["status"] == "not_checked" and g["gate"] == "F5"
               for g in self.g.check_destination(car, location, track)):
            self.uncertain.append(f"{track.name}: schedule line has a random draw")
        return OKAY

    def check_destination(self, car: Car, location: Location | None, track: Track | None) -> str:
        """Car.checkDestination (C:801): RollingStock checks, then the spur's schedule over length."""
        if location is None:
            return OKAY
        if track is not None and track.location_id != location.id:
            return ERROR_TRACK
        if car.type not in location.types:
            return f"{TYPE} ({car.type})"
        if track is None:
            return OKAY
        status = self.accepted(car, track)
        if status != OKAY and not status.startswith(LENGTH):
            return status
        schedule = self._schedule(car, location, track)
        return status if status.startswith(LENGTH) and schedule == OKAY else schedule

    def set_destination(self, car: Car, location: Location | None, track: Track | None) -> str:
        """Car.setDestination (C:847). The destination is set before the schedule is asked (C:858-866)."""
        if location is not None:
            if track is not None and track.location_id != location.id:
                return ERROR_TRACK
            if car.type not in location.types:
                return f"{TYPE} ({car.type})"
            if track is not None:
                status = self.accepted(car, track)
                if status != OKAY:
                    return status
        old_location, old_track = car.destination_id, car.dest_track_id
        car.destination_id = location.id if location else ""
        car.dest_track_id = track.id if track else ""
        if track is not None and (old_location, old_track) != (car.destination_id, car.dest_track_id):
            self._bumped[track.id] = self._bumped.get(track.id, 0) + 1
        if car.destination_id and car.destination_id == car.fd_id and car.dest_track_id and (
                car.dest_track_id == car.fd_track_id or not car.fd_track_id):
            car.fd_id = car.fd_track_id = ""  # removeCarFinalDestination (C:901)
            self.shown = None
        if track is not None and old_track != track.id and track.schedule_id and track.is_spur:
            # Track.scheduleNext (TR:2101): a held schedule line passes; otherwise the current line or a match.
            schedule = self.rr.schedules.get(track.schedule_id)
            if schedule is None:
                return OKAY
            if car.schedule_item and any(i.id == car.schedule_item for i in schedule.items):
                return OKAY
            return self._schedule(replace(car, dest_track_id=""), location, track)
        return OKAY

    # Train.isServiceable (T:1766) and TrainManager.getTrainForCar (TM:547).
    def _building(self, train: Train) -> bool:
        return self.build is not None and self._train is not None and train.id == self._train.id

    def _termination_track(self, train: Train | None) -> Track | None:
        """Train.getTerminationTrack. The train being built has the one its build picked (a build clears
        the old one first, TrainBuilder:256); any other train keeps the one saved when it was last built,
        looked up at the location its route ends at (T:4274-4281)."""
        if train is None:
            return None
        if self._building(train):
            return self.rr.tracks.get(self.build.termination_track_id)
        track = self.rr.tracks.get(train.termination_track_id)
        stops = self.rr.stops(train)
        if track is None or not stops:
            return None
        end, here = self.rr.locations.get(stops[-1].location_id), self.rr.locations.get(track.location_id)
        return track if end is not None and here is not None and here.name == end.name else None

    def able(self, train: Train, car: Car) -> bool:
        """Train.isTrainAbleToService (T:1985)."""
        road = train.accepts_caboose_road(car.road) if car.caboose else train.accepts_road(car.road)
        return (car.type in train.types and train.accepts_load(car.load, car.type)
                and train.accepts_built(car.built) and train.accepts_owner(car.owner) and road)

    def _switcher(self, train: Train) -> bool:
        stops = self.rr.stops(train)
        return not stops or all(s.split == stops[0].split for s in stops)

    def _local(self, car: Car) -> bool:
        """Car.isLocalMove with no train: same split name (C:619)."""
        here, dest = self.rr.locations.get(car.location_id), self.rr.locations.get(car.destination_id)
        return here is not None and dest is not None and here.split == dest.split

    def service_status(self, train: Train) -> str:
        return self._service_status.get(train.id, "")

    def serviceable(self, train: Train, car: Car) -> bool:
        rr = self.rr
        self._service_status[train.id] = ""
        if not self.able(train, car):
            return False
        stops = rr.stops(train)
        here, track = rr.locations.get(car.location_id), rr.tracks.get(car.track_id)
        if not stops or here is None or track is None:
            return False
        ids = {s.location_id for s in stops}
        if car.location_id not in ids:
            return False
        dest = rr.locations.get(car.destination_id)
        if dest is not None and (dest.id not in ids or (dest.is_staging and stops[-1].location_id != dest.id)):
            return False
        local, switcher = self._local(car), self._switcher(train)
        for index, stop in enumerate(stops):
            if stop.location_id != car.location_id:
                continue
            if (stop.max_moves <= 0 or stop.id in train.skips or (not stop.pickups and not local)
                    or (not stop.local and local)):
                continue
            if not here.dir & stop.direction and not switcher:
                continue
            if not track.dir & stop.direction and not switcher:
                continue
            if not track.accepts_pickup(train):
                continue
            if dest is None:
                return True
            if self._serviceable_destination(train, car, index, stops, dest, track, local, switcher):
                return True
        return False

    def _serviceable_destination(self, train, car, start, stops, dest, track, local, switcher) -> bool:
        """Train.isServiceableDestination (T:1871). Length counts only for the train being built."""
        rr = self.rr
        length = rr.kernel_length(car)
        origin = stops[start]
        dest_track = rr.tracks.get(car.dest_track_id)
        for k in range(start, len(stops)):
            stop = stops[k]
            here_ok = (stop.location_id == dest.id and ((stop.drops and not local) or (stop.local and local))
                       and stop.max_moves > 0 and stop.id not in train.skips
                       and (not rr.option("router", "checkCarDestination") or track.accepts_destination(dest.id)))
            if here_ok:
                if not dest.dir & stop.direction and not switcher:
                    continue
                if dest_track is not None:
                    if not self._servicable_track(train, stop, dest_track, switcher):
                        continue
                elif not self._car_to_staging(train, stop, car):
                    continue
                elif not any(self._servicable_track(train, stop, t, switcher)
                             and self._ok_or_length(self.accepted(car, t)) for t in dest.tracks):
                    continue
                if not self._only_to_terminal(train, car, stops, local):
                    continue
                turn = not switcher and stops[0].split == stops[-1].split
                if not turn and track.is_staging and dest.id == car.location_id:
                    continue
                if train.allow_return and track.is_staging and dest.id == car.location_id:
                    return True
                exempt = car.caboose or car.fred or car.passenger
                if (not train.local_moves or not origin.local or not stop.local) and not switcher \
                        and not exempt and local:
                    continue
                if (not train.through_cars and stops[0].split == origin.split and stops[-1].split == stop.split
                        and stops[0].split != stops[-1].split and not switcher and not exempt):
                    continue
                if self._building(train) and stop.max_moves - self.build.car_moves.get(stop.id, 0) <= 0:
                    self._service_status[train.id] = f"no moves left at {stop.name}"
                    continue
                return True
            if self._building(train) and self.build.train_length.get(stop.id, 0) + length > stop.max_length:
                self._service_status[train.id] = (f"train would exceed the {stop.max_length} maximum length "
                                                  f"departing {stop.name}")
                return False
        return False

    @staticmethod
    def _servicable_track(train: Train, stop, track: Track, switcher: bool) -> bool:
        return bool(track.dir & stop.direction or switcher) and track.accepts_drop(train)  # T:2007

    def _car_to_staging(self, train: Train, stop, car: Car) -> bool:
        """Train.isCarToStaging (T:2023): only while building with a termination track picked."""
        rr = self.rr
        terminal = rr.tracks.get(self.build.termination_track_id) if self._building(train) else None
        location = rr.locations.get(stop.location_id)
        if location is None or not location.is_staging or terminal is None or terminal.location_id != location.id:
            return True
        status = self.check_destination(car, location, terminal)
        if status != OKAY:
            self._service_status[train.id] = status
            return False
        return True

    def _only_to_terminal(self, train: Train, car: Car, stops, local: bool) -> bool:
        rr = self.rr
        here, dest = rr.locations[car.location_id], rr.locations[car.destination_id]
        return not (train.to_terminal and not local and here.split != stops[0].split
                    and dest.split != stops[-1].split)  # T:2046

    @staticmethod
    def _ok_or_length(status: str) -> bool:
        return status == OKAY or status.startswith(LENGTH)

    def train_for_car(self, car: Car, exclude: list, exclude_routes: bool) -> Train | None:
        """TrainManager.getTrainForCar (TM:547): first train by name that can carry the car."""
        only_active = self.rr.option("router", "onlyActiveTrains")
        for train in self._trains_by_name():
            if any(t is not None and t.id == train.id for t in exclude):
                continue
            if only_active and not train.build:
                continue
            if exclude_routes and any(t is not None and t.route_id == train.route_id for t in exclude):
                continue
            if self.serviceable(train, car):
                return train
        return None

    def _exclude_trains(self, car: Car) -> list[Train]:
        """TrainManager.getExcludeTrainListForCar (TM:578)."""
        only_active = self.rr.option("router", "onlyActiveTrains")
        return [t for t in self._trains_by_name() if (only_active and not t.build) or not self.able(t, car)]

    def _specified(self, car: Car) -> str:
        """R:1316 canSpecifiedTrainService."""
        if self._train is None:
            return NO_SPECIFIED_TRAIN
        if self.serviceable(self._train, car):
            return YES
        return NOT_NOW if self.service_status(self._train) else NO

    # Router.setDestination (R:119).
    def set_car_destination(self, car: Car, train: Train | None, check_target: bool = True) -> bool:
        rr = self.rr
        if car.track_id not in rr.tracks or car.fd_id not in rr.locations:
            return False
        self.status, self._train, self.path, self.how = OKAY, train, None, ""
        if car.kernel and not rr.is_kernel_lead(car):
            return False
        clone = self._clone(car)
        fd, fd_track = rr.locations[car.fd_id], rr.tracks.get(car.fd_track_id)
        # No length test here, and no schedule test because the clone is already destined to the track.
        if check_target:
            self.status = self.check_destination(clone, fd, fd_track)
            if self.status != OKAY:
                self.steps.append(f"cannot deliver to the final destination: {self.status}")
                return False
            if not self._check_for_destination_track(clone):
                return False
        if self._check_for_single_train(car, clone):
            return True
        if not rr.option("router", "carRoutingEnabled", True):
            self.status = DISABLED
            car.fd_id = car.fd_track_id = ""
            return False
        self._next: list[Track] = []
        self._next_trains: list[Train] = []
        self._last: list[Track] = []
        self._last_trains: list[Train] = []
        self._other: list[Track] = []
        self._next2: list[Track] = []
        self._next3: list[Track] = []
        self._next4: list[Track] = []
        self._pairs: dict[str, object] = {}
        self._excluded = self._exclude_trains(car)
        if self._two_trains(car, INTERCHANGE):
            if not car.destination_id:
                self._two_trains_yard(car)
        elif self._two_trains_yard(car):
            pass
        elif self._multiple_trains(car, False):
            pass
        elif self._two_trains_staging(car):
            pass
        elif self._multiple_trains(car, True):
            pass
        else:
            self.status = NOT_ABLE
            return False
        return True

    def _check_for_destination_track(self, clone: Car) -> bool:
        """R:235: a final destination with no track needs one track that takes the car, length aside."""
        if clone.destination_id and not clone.dest_track_id:
            location = self.rr.locations[clone.destination_id]
            if not any(self._ok_or_length(self.accepted(clone, t)) for t in location.tracks):
                self.status = f"no track at {location.name} takes the car"
                self.steps.append(self.status)
                return False
        return True

    def _show_route(self, car: Car, trains: list[Train], tracks: list[Track | None]) -> None:
        """R:1172 showRoute; the last one shown is the car's route path."""
        rr = self.rr
        fd = rr.locations.get(car.fd_id)
        fd_track = rr.tracks.get(car.fd_track_id)
        path = []
        for train, track in zip(trains, tracks):
            if track is None:
                track = fd_track
            where = f"{rr.locations[track.location_id].name}, {track.name}" if track else (fd.name if fd else "")
            path.append({"train": train.name, "to": where})
        self.path = self.shown = path

    def _check_for_single_train(self, car: Car, clone: Car) -> bool:
        """R:261."""
        train, rr = self._train, self.rr
        services = bool(train) and self.serviceable(train, clone)
        test = train if services else None
        here = rr.tracks[car.track_id]
        if train is not None and not services and self.service_status(train):
            self.steps.append(f"{train.name} cannot carry the car now: {self.service_status(train)}")
            if not here.is_staging and not train.service_all:
                self.status = not_this_train(train)
                self.how = "single train, not now"
                return True
        if here.is_staging and train is not None and not services:
            self.steps.append(f"{train.name} cannot take the car straight from staging; trying other routes")
        elif not services:
            test = self.train_for_car(clone, [train], True)
        if test is not None and train is not None and not services and train.service_all:
            self.steps.append(f"{train.name} services all cars with a final destination, so {test.name} is not used")
            test = None
        if test is not None:
            return self._finish_route_using_one_train(test, car, clone)
        return False

    def _finish_route_using_one_train(self, test: Train, car: Car, clone: Car) -> bool:
        """R:332: one train; then the final track's alternate, then a yard at the destination."""
        rr, train = self.rr, self._train
        self._show_route(car, [test], [rr.tracks.get(car.fd_track_id)])
        self.how = "single train"
        if train is None:
            return True
        if train.id != test.id:
            self.status = not_this_train(test)
            return True
        dest, dest_track = rr.locations.get(clone.destination_id), rr.tracks.get(clone.dest_track_id)
        self.status = self.set_destination(car, dest, dest_track)
        if self.status == OKAY:
            return True
        self.steps.append(f"cannot set out at {dest_track.name if dest_track else dest.name}: {self.status}")
        alternate = rr.tracks.get(dest_track.alternate_id) if dest_track else None
        if ((self.status.startswith(LENGTH) or self.status.startswith(SCHEDULE)) and alternate
                and alternate.id != car.track_id):
            status = self.set_destination(car, dest, alternate)
            if status == OKAY:
                if self.serviceable(train, car):
                    self.how = "single train, to the final track's alternate"
                    self.steps.append(f"sent to alternate {alternate.name}")
                    return True
                self.steps.append(f"{train.name} cannot set out on alternate {alternate.name}")
            else:
                self.steps.append(f"alternate {alternate.name} refused: {status}")
        elif alternate and alternate.id == car.track_id:
            self.steps.append(f"car is already on the alternate {alternate.name}")
        elif car.location_id == clone.destination_id:
            self.steps.append("car is at its final destination; no alternate or yard is tried")
        if (rr.option("router", "forwardToYard", True) and self.status.startswith(LENGTH)
                and car.location_id != clone.destination_id):
            for yard in self.location_tracks_by_moves(dest, YARD):
                status = self.set_destination(car, dest, yard)
                if status == OKAY:
                    if not self.serviceable(train, car):
                        continue
                    self.how = "single train, forwarded to a yard"
                    self.steps.append(f"spur full, forwarded to yard {yard.name}")
                    return True
                self.steps.append(f"yard {yard.name} refused: {status}")
            self.steps.append(f"no yard at {dest.name} takes the car")
        car.destination_id = car.dest_track_id = ""
        if rr.tracks[car.track_id].is_staging:
            return False  # R:416: try two or more trains to get out of staging.
        return True

    def _two_trains_yard(self, car: Car) -> bool:
        return self.rr.option("router", "carRoutingViaYards") and self._two_trains(car, YARD)

    def _two_trains_staging(self, car: Car) -> bool:
        return self.rr.option("router", "carRoutingViaStaging") and self._two_trains(car, STAGING)

    def _tracks(self, car: Car, test: Car, kind: str) -> list[Track]:
        """R:707 getTracks."""
        out = []
        for track in self.tracks_by_moves(kind):
            if track.id in (car.track_id, car.fd_track_id):
                continue
            if kind == STAGING and track.modifies_loads:
                continue
            if self._ok_or_length(self.accepted(test, track)):
                out.append(track)
        return out

    def _two_trains(self, car: Car, kind: str) -> bool:
        """R:522: a last train from an interim track to the final destination, then a first train to it."""
        rr, train = self.rr, self._train
        test = self._clone(car)
        found = False
        # The final destination can be gone here: Car.setDestination clears it on reaching it (C:901).
        fd, fd_track = rr.locations.get(car.fd_id), rr.tracks.get(car.fd_track_id)
        origin = rr.tracks[car.track_id]
        for track in self._tracks(car, test, kind):
            self._set_track(test, track)
            test.destination_id = fd.id if fd else ""
            self._set_destination_track(test, fd_track)
            second = self.train_for_car(test, self._excluded, False)
            if second is None:
                if self._specified(test) == NOT_NOW:
                    second = train
                else:
                    continue
            self._last.append(track)
            self._last_trains.append(second)
            self._set_track(test, origin)
            test.destination_id = track.location_id
            self._set_destination_track(test, track)
            first = None
            specified = self._specified(test)
            if specified == YES:
                first = train
            elif specified == NOT_NOW:
                self._show_route(car, [train, second], [track, fd_track])
                self.how = f"two trains through {kind.lower()} {track.name}, {train.name} not now"
                self.steps.append(f"{train.name} cannot reach {track.name} now: {self.service_status(train)}")
                found = True
            else:
                first = self.train_for_car(test, self._excluded, False)
            if (first is not None and first.route_id == second.route_id and track.is_interchange
                    and track.pickup_option == "Any"):
                first = self.train_for_car(test, [first], True)  # R:597: the same route may not drop and pull.
            if train is not None and origin.is_staging and specified != YES:
                continue
            if first is not None and train is not None and train.service_all and specified != YES:
                continue
            if first is not None:
                found = True
                self._show_route(car, [first, second], [track, fd_track])
                self.how = f"two trains through {kind.lower()} {track.name}"
                self.status = self.check_destination(car, rr.locations[track.location_id], track)
                if self.status.startswith(LENGTH):
                    self.steps.append(f"interim {track.name} has no room: {self.status}")
                    continue
                if self.status == OKAY:
                    if train is not None and train.id != first.id:
                        self.status = not_this_train(first)
                        continue
                    terminal = self._termination_track(first)  # R:669-671
                    if track.is_staging and terminal is not None and terminal.id != track.id:
                        continue
                    self.status = self.set_destination(car, rr.locations[track.location_id], track)
                    return True
        if found:
            self.status = not_this_train(train) if train is not None else NOT_ABLE
        return found

    def _multiple_trains(self, car: Car, staging: bool) -> bool:
        """R:750: next, other and last track sets, then three to seven trains."""
        rr = self.rr
        if staging and not rr.option("router", "carRoutingViaStaging"):
            return False
        if not self._last:
            self.steps.append(f"no {'staging ' if staging else ''}track found that a last train can pull "
                              f"to the final destination")
            return False
        test = self._clone(car)
        if not self._next and not self._other:
            self._load_tracks_and_trains(car, test, self.tracks_by_moves(INTERCHANGE))
            if rr.option("router", "carRoutingViaYards"):
                self._load_tracks_and_trains(car, test, self.tracks_by_moves(YARD))
        if staging:
            self._load_tracks_and_trains(car, test, [t for t in self.tracks_by_moves(STAGING)
                                                     if not t.modifies_loads])
        if not self._next:
            self.steps.append(f"no first hop from {rr.locations[car.location_id].name}")
            return False
        for n in range(3, 8):
            self._n = n
            if getattr(self, f"_route_using_{n}")(car):
                return True
        self.steps.append("no chain of up to seven trains")
        return False

    def _load_tracks_and_trains(self, car: Car, test: Car, tracks: list[Track]) -> None:
        """R:1264."""
        train = self._train
        here = self.rr.tracks[car.track_id]
        for track in tracks:
            if track.id == car.track_id or any(t.id == track.id for t in self._last):
                continue
            if not self._ok_or_length(self.accepted(test, track)):
                continue
            self._set_destination_track(test, track)
            specified = self._specified(test)
            if specified in (YES, NOT_NOW):
                carrier = train
            else:
                carrier = self.train_for_car(test, [], False)
            if here.is_staging and specified == NO:
                carrier = None
            if (carrier is not None and train is not None and carrier.id != train.id
                    and train.service_all and specified != YES):
                carrier = None
            if carrier is not None:
                self._next.append(track)
                self._next_trains.append(carrier)
            else:
                self._other.append(track)

    def _between(self, test: Car, start: Track, end: Track, from_train, to_train) -> Train | None:
        """R:1145: a train from one hop to the next, cached by the pair of track ids."""
        self._set_track(test, start)
        self._set_destination_track(test, end)
        exclude = []
        if start.is_interchange and start.pickup_option == "Any":
            exclude.append(from_train)
        if end.is_interchange and end.pickup_option == "Any":
            exclude.append(to_train)
        key = start.id + end.id
        cached = self._pairs.get(key)
        if cached is None:
            cached = self.train_for_car(test, exclude, True) or _NULL
            self._pairs[key] = cached
        return None if cached is _NULL else cached

    def _next_train(self, track: Track) -> Train:
        return self._next_trains[self._next.index(track)]

    def _last_train(self, track: Track) -> Train:
        return self._last_trains[self._last.index(track)]

    def _route_using_3(self, car: Car) -> bool:
        test, found = self._clone(car), False
        fd_track = self.rr.tracks.get(car.fd_track_id)
        for nlt in self._next:
            for llt in self._last:
                middle = self._between(test, nlt, llt, self._next_train(nlt), self._last_train(llt))
                if middle is not None:
                    found = True
                    self._show_route(car, [self._next_train(nlt), middle, self._last_train(llt)], [nlt, llt, fd_track])
                    if self._finish_setting_route_for(car, nlt):
                        return True
                    break
        return self._try_redirect_to_alternate_or_yard(found, car)

    def _route_using_4(self, car: Car) -> bool:
        test, found = self._clone(car), False
        fd_track = self.rr.tracks.get(car.fd_track_id)
        for nlt in self._next:
            for mlt in self._other:
                middle2 = self._between(test, nlt, mlt, self._next_train(nlt), None)
                if middle2 is None:
                    continue
                if mlt not in self._next2:
                    self._next2.append(mlt)
                done = False
                for llt in self._last:
                    middle3 = self._between(test, mlt, llt, middle2, self._last_train(llt))
                    if middle3 is None:
                        continue
                    found = True
                    self._show_route(car, [self._next_train(nlt), middle2, middle3, self._last_train(llt)],
                                     [nlt, mlt, llt, fd_track])
                    if self._finish_setting_route_for(car, nlt):
                        return True
                    done = True
                    break
                if done:
                    break
        return self._try_redirect_to_alternate_or_yard(found, car)

    def _route_using_5(self, car: Car) -> bool:
        test, found = self._clone(car), False
        fd_track = self.rr.tracks.get(car.fd_track_id)
        for nlt in self._next:
            done = False
            for mlt1 in list(self._next2):
                middle2 = self._between(test, nlt, mlt1, self._next_train(nlt), None)
                if middle2 is None:
                    continue
                for mlt2 in self._other:
                    if mlt2 in self._next2:
                        continue
                    middle3 = self._between(test, mlt1, mlt2, middle2, None)
                    if middle3 is None:
                        continue
                    if mlt2 not in self._next3:
                        self._next3.append(mlt2)
                    for llt in self._last:
                        middle4 = self._between(test, mlt2, llt, middle3, self._last_train(llt))
                        if middle4 is None:
                            continue
                        found = True
                        self._show_route(car, [self._next_train(nlt), middle2, middle3, middle4, self._last_train(llt)],
                                         [nlt, mlt1, mlt2, llt, fd_track])
                        if self._finish_setting_route_for(car, nlt):
                            return True
                        done = True
                        break
                    if done:
                        break
                if done:
                    break
        return self._try_redirect_to_alternate_or_yard(found, car)

    def _route_using_6(self, car: Car) -> bool:
        test, found = self._clone(car), False
        fd_track = self.rr.tracks.get(car.fd_track_id)
        for nlt in self._next:
            done = False
            for mlt1 in list(self._next2):
                middle2 = self._between(test, nlt, mlt1, self._next_train(nlt), None)
                if middle2 is None:
                    continue
                for mlt2 in list(self._next3):
                    middle3 = self._between(test, mlt1, mlt2, middle2, None)
                    if middle3 is None:
                        continue
                    for mlt3 in self._other:
                        if mlt3 in self._next2 or mlt3 in self._next3:
                            continue
                        middle4 = self._between(test, mlt2, mlt3, middle3, None)
                        if middle4 is None:
                            continue
                        if mlt3 not in self._next4:
                            self._next4.append(mlt3)
                        for llt in self._last:
                            middle5 = self._between(test, mlt3, llt, middle4, self._last_train(llt))
                            if middle5 is None:
                                continue
                            found = True
                            self._show_route(car, [self._next_train(nlt), middle2, middle3, middle4, middle5,
                                                   self._last_train(llt)], [nlt, mlt1, mlt2, mlt3, llt, fd_track])
                            if self._finish_setting_route_for(car, nlt):
                                return True
                            done = True
                            break
                        if done:
                            break
                    if done:
                        break
                if done:
                    break
        return self._try_redirect_to_alternate_or_yard(found, car)

    def _route_using_7(self, car: Car) -> bool:
        test, found = self._clone(car), False
        fd_track = self.rr.tracks.get(car.fd_track_id)
        for nlt in self._next:
            done = False
            for mlt1 in list(self._next2):
                middle2 = self._between(test, nlt, mlt1, self._next_train(nlt), None)
                if middle2 is None:
                    continue
                for mlt2 in list(self._next3):
                    middle3 = self._between(test, mlt1, mlt2, middle2, None)
                    if middle3 is None:
                        continue
                    for mlt3 in list(self._next4):
                        middle4 = self._between(test, mlt2, mlt3, middle3, None)
                        if middle4 is None:
                            continue
                        for mlt4 in self._other:
                            if mlt4 in self._next2 or mlt4 in self._next3 or mlt4 in self._next4:
                                continue
                            middle5 = self._between(test, mlt3, mlt4, middle4, None)
                            if middle5 is None:
                                continue
                            for llt in self._last:
                                middle6 = self._between(test, mlt4, llt, middle5, self._last_train(llt))
                                if middle6 is None:
                                    continue
                                found = True
                                self._show_route(car, [self._next_train(nlt), middle2, middle3, middle4, middle5,
                                                       middle6, self._last_train(llt)],
                                                 [nlt, mlt1, mlt2, mlt3, mlt4, llt, fd_track])
                                if self._finish_setting_route_for(car, nlt):
                                    return True
                                done = True
                                break
                            if done:
                                break
                        if done:
                            break
                    if done:
                        break
                if done:
                    break
        return self._try_redirect_to_alternate_or_yard(found, car)

    def _finish_setting_route_for(self, car: Car, track: Track) -> bool:
        """R:1205: the first hop must be the named train's, have room, and be its staging track."""
        train, rr = self._train, self.rr
        test = self._clone(car)
        self._set_destination_track(test, track)
        specified = self._specified(test)
        if specified == NO:
            self.status = not_this_train(train)
            return False
        if specified == NOT_NOW:
            self.steps.append(f"{train.name} cannot reach {track.name} now: {self.service_status(train)}")
            return False
        terminal = self._termination_track(train)  # R:1221-1224
        if track.is_staging and train is not None and terminal is not None and terminal.id != track.id:
            return False
        self.status = self.set_destination(car, rr.locations[track.location_id], track)
        if self.status != OKAY:
            self.steps.append(f"first hop {track.name}: {self.status}")
            return False
        self.how = f"{self._n} trains"
        return True

    def _try_redirect_to_alternate_or_yard(self, found: bool, car: Car) -> bool:
        """R:1339: a route exists but the first hop is full; move the car to its spur's alternate or a yard."""
        rr = self.rr
        if not found:
            return False
        self.how = f"{self._n} trains; the first hop could not be set now"
        here = rr.tracks[car.track_id]
        alternate = rr.tracks.get(here.alternate_id)
        if alternate is not None:
            test = self._clone(car)
            self._set_destination_track(test, alternate)
            if self._specified(test) == YES:
                status = self.set_destination(car, rr.locations[alternate.location_id], alternate)
                if status == OKAY:
                    self.how = "route found, first hop full: to the spur's alternate"
                    return True
                self.steps.append(f"alternate {alternate.name} refused: {status}")
        if not here.is_yard and rr.option("router", "forwardToYard", True):
            test = self._clone(car)
            for yard in self.location_tracks_by_moves(rr.locations[car.location_id], YARD):
                self._set_destination_track(test, yard)
                if self._specified(test) == YES:
                    status = self.set_destination(car, rr.locations[yard.location_id], yard)
                    if status == OKAY:
                        self.how = "route found, first hop full: to a yard here"
                        return True
                    self.steps.append(f"yard {yard.name} refused: {status}")
        return found

    def is_car_routeable(self, car: Car, train: Train | None, track: Track) -> bool:
        """R:96: route a copy to the track; the car itself is unchanged."""
        copy = replace(car, kernel="", lead=False, train_id="", fd_id=track.location_id, fd_track_id=track.id,
                       destination_id="", dest_track_id="")
        return self.set_car_destination(copy, train)


def _result(router: Router, car: Car, ok: bool) -> dict:
    rr = router.rr
    dest, dest_track = rr.locations.get(car.destination_id), rr.tracks.get(car.dest_track_id)
    return {
        "routable": ok, "status": router.status, "how": router.how or None, "path": router.path,
        "destination": dest.name if dest else None, "destination_track": dest_track.name if dest_track else None,
        "steps": router.steps, "uncertain": sorted(set(router.uncertain)),
    }


def route_car(gates, car: Car, location: Location, track: Track | None = None, train: Train | None = None,
              build: Build | None = None) -> dict:
    """Router.setDestination for a copy of the car given this final destination.

    "routable" is what setDestination returns: True also when another train, or this
    train later, can take the car ("status" then names the train). "destination" is
    what JMRI would set on the car now, which needs the named train.
    """
    router = Router(gates, build)
    copy = replace(car, train_id="", fd_id=location.id, fd_track_id=track.id if track else "",
                   destination_id="", dest_track_id="")
    ok = router.set_car_destination(copy, train)
    return _result(router, copy, ok)


def route_path(gates, car: Car, target: Track, check_target: bool = True) -> list[dict] | None:
    """The trains JMRI's router chains to take the car to the target, with no train named.

    check_target False skips the target's own acceptance (R:146) and asks only whether
    trains connect; the audit uses it for loads a schedule would ship.
    """
    rr = gates.rr
    if car.track_id not in rr.tracks:
        return None
    router = Router(gates)
    copy = replace(car, kernel="", lead=False, train_id="", fd_id=target.location_id, fd_track_id=target.id,
                   destination_id="", dest_track_id="")
    if not router.set_car_destination(copy, None, check_target) or not router.path:
        return None
    return router.path


def find_spur_for_load(gates, car: Car, train: Train, build: Build | None = None) -> dict:
    """TBC.findFinalDestinationForCarLoad (TBC:1051) for one car as the named train builds.

    Scheduled spurs everywhere, fewest moves first; a spur's Hold option or another train
    able to take the car keeps the car where it is; otherwise staging, picked at random;
    otherwise the car falls to the search along the train's own route. Moves and
    schedule pointers change as a real build goes on, so this is the answer for the
    first car the build considers.
    """
    rr = gates.rr
    build = build or Build()
    router = Router(gates, build)
    out = {"searched": False, "spurs": [], "spur": None, "hold": False, "staging": [], "outcome": None}
    if rr.is_default_load(car.load) or car.destination_id or car.fd_id:
        out["outcome"] = "not searched: default load, or the car already has a destination"
        return out
    out["searched"] = True
    here = rr.tracks.get(car.track_id)
    if here is None:
        out["outcome"] = "car has no track"
        return out
    state = {"route_found": False}
    unserved: set[str] = set()
    for track in router.tracks_by_moves(SPUR):
        if track.id == car.track_id:
            continue
        name = f"{rr.locations[track.location_id].name}, {track.name}"
        if track.schedule_id not in rr.schedules:
            continue  # TBC:1078, no schedule.
        if track.location_id in unserved:
            continue
        if not here.accepts_destination(track.location_id):
            unserved.add(track.location_id)
            out["spurs"].append({"spur": name, "result": "departure track's destinations filter refuses it"})
            continue
        ok, why, routed = _send_car_to_destination_spur(router, car, track, train, state)
        out["spurs"].append({"spur": name, "result": why, **({"router": routed} if routed else {})})
        if ok:
            out["spur"] = name
            out["outcome"] = f"final destination {name}"
            return out
    location = rr.locations.get(car.location_id)
    stops = rr.stops(train)
    departing = here.is_staging and bool(stops) and car.location_id == stops[0].location_id
    if state["route_found"] and not train.send_custom_staging and not (location and location.is_staging):
        out["hold"] = True
        out["outcome"] = ("held where it is: a spur with Hold set, or another train, has a route for it; "
                          "the train's own route is not searched")
        return out
    terminal = rr.tracks.get(build.termination_track_id)
    for track in router.all_tracks(STAGING):  # JMRI picks from this list at random (TBC:1114).
        name = f"{rr.locations[track.location_id].name}, {track.name}"
        if track.location_id == car.location_id or track.location_id in unserved:
            continue
        if terminal is not None and stops and track.location_id == stops[-1].location_id and track.id != terminal.id:
            continue
        if not here.accepts_destination(track.location_id):
            continue
        status = router.accepted(car, track)
        if not router._ok_or_length(status):
            continue
        probe = replace(car, fd_id=track.location_id, fd_track_id="")
        routed = Router(gates, build)
        ok = routed.set_car_destination(probe, train)
        result = _result(routed, probe, ok)
        out["staging"].append({"staging": name, "routable": ok, "status": routed.status,
                               "destination": result["destination_track"] or result["destination"],
                               "path": routed.path})
    reachable = [s for s in out["staging"] if s["destination"]]
    if reachable:
        out["outcome"] = ("final destination staging, picked at random from: "
                          + ", ".join(s["staging"] for s in reachable))
    elif (state["route_found"] or any(s["routable"] for s in out["staging"])) and not departing:
        # TBC:1163 returns routeToTrackFound, and TBC:574 then holds the car.
        out["hold"] = True
        out["outcome"] = "held where it is: a route exists, but not with this train now"
    else:
        out["outcome"] = ("no spur or staging: the car falls to the search along the train's route, where only "
                          "tracks that take a custom load accept it (yards, interchanges, staging)")
    return out


def _send_car_to_destination_spur(router: Router, car: Car, track: Track, train: Train,
                                  state: dict) -> tuple[bool, str, dict | None]:
    """TBC:1177 sendCarToDestinationSpur."""
    rr = router.rr
    router._train = train
    location = rr.locations[track.location_id]
    problem = _basic_moves(rr, car, track, train)
    if problem:
        return False, problem, None
    status = router.check_destination(car, location, track)
    if status != OKAY:
        if not status.startswith(LENGTH):
            return False, f"refused: {status}", None
        alternate = rr.tracks.get(track.alternate_id)
        if alternate is None:
            return False, "full and has no alternate", None
        if not router._switcher(train) and not track.dir & alternate.dir:
            return False, f"full; alternate {alternate.name} shares no direction with it", None
    if not _space_available(rr, car, track):
        why = "no room for more cars in route to it"
        if track.hold_custom:
            if Router(router.g, router.build).is_car_routeable(car, train, track):
                state["route_found"] = True
                why += "; Hold is set and a route exists, so the car may be held"
        return False, why, None
    probe = replace(car, fd_id=track.location_id, fd_track_id=track.id)
    routed = Router(router.g, router.build)
    ok = routed.set_car_destination(probe, train)
    detail = _result(routed, probe, ok)
    if ok and track.hold_custom:
        state["route_found"] = True
    if not probe.destination_id:
        if routed.status.startswith(NOT_THIS_TRAIN + " "):
            state["route_found"] = True
        return False, f"router: {routed.status}", detail
    return True, "chosen", detail


def _basic_moves(rr, car: Car, track: Track, train: Train) -> str:
    """TBB:2164 checkBasicMoves; empty when the move is allowed."""
    here, there = rr.locations[car.location_id], rr.locations[track.location_id]
    stops = rr.stops(train)
    switcher = not stops or all(s.split == stops[0].split for s in stops)
    own = rr.tracks.get(car.track_id)
    if car.track_id == track.id:
        return "car is on it"
    if here.split == there.split and own is not None and own.split == track.split:
        return "same split location and track name"
    if track.is_staging and car.location_id == track.location_id:
        return "same staging location"
    exempt = car.caboose or car.fred or car.passenger
    if (stops and not train.through_cars and not switcher and not exempt and here.split == stops[0].split
            and there.split == stops[-1].split and stops[0].split != stops[-1].split):
        return "through cars are off for this train"
    if not switcher and not train.local_moves and here.split == there.split:
        return "local moves are off for this train"
    return ""


def _space_available(rr, car: Car, track: Track) -> bool:
    """Track.isSpaceAvailable (TR:622): track length less cars already routed to it."""
    need = rr.kernel_length(car)
    length = track.length
    if length < need and not track.pool:
        return False
    in_route = sum(rr.car_length(c) or 0 for c in rr.cars.values() if c.fd_track_id == track.id)
    here = rr.tracks.get(car.track_id)
    if here is not None and here.is_staging:
        return length * track.factor // 100 - (in_route + need) >= 0
    alternate = rr.tracks.get(track.alternate_id)
    if alternate is not None:
        length += alternate.length
    return length - (in_route + need) >= 0


def router_detail(gates, car: Car, target: Track, train: Train) -> dict:
    """What the router does with this car, this target and this train, as the train builds empty."""
    rr = gates.rr
    if car.track_id not in rr.tracks:
        return {"used": False, "reason": "car has no track"}
    out: dict = {}
    if car.fd_id or car.division_id or not rr.is_default_load(car.load):
        fd = rr.locations.get(car.fd_id) if car.fd_id else rr.locations[target.location_id]
        fd_track = rr.tracks.get(car.fd_track_id) if car.fd_id else target
        out["route"] = route_car(gates, car, fd, fd_track, train, Build())
    if not rr.is_default_load(car.load) and not car.fd_id and not car.destination_id:
        out["spur_search"] = find_spur_for_load(gates, car, train)
    return out or {"used": False, "reason": "default load and no final destination: the router never runs"}
