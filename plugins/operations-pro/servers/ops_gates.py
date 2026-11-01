"""Why a car will or will not move in JMRI OperationsPro, and whole-railroad checks.

why_not walks the build gates in the order JMRI 5.16 applies them, tables A to G.
Everything here reads a Railroad and changes nothing. A gate that depends on what
happens during a build (random draws, timing against other trains, moves already
used) cannot be decided from files and reports not_checked rather than guessing.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import replace

from ops_data import (
    ALL, ANY, MATCH, QUICK_SERVICE, REQUIRES_CABOOSE, REQUIRES_FRED, TRAINS, ANY_DAY, GENERATE,
    GENERATE_ANY_SPUR, EXCLUDE_ROUTES, EXCLUDE_TRAINS,
    Car, Location, Railroad, ScheduleItem, Stop, Track, Train, built_year, directions, split_name,
)

PASS, FAIL, NOT_CHECKED = "pass", "fail", "not_checked"
MAX_ROUTER_TRAINS = 7  # Router tries up to this many trains in one route.

# Failures here hold the car whichever train or chain of trains is tried.
ANY_TRAIN = {"B1", "B2", "B3", "B15", "B16", "B18", *(f"E{n}" for n in range(1, 11)),
             *(f"F{n}" for n in range(1, 6))}

CAR, CAR_SET = "Edit Car", "Set Car"
TRAIN, BUILD_OPTIONS = "Edit Train", "Edit Train > Train Build Options"
TRAIN_ROADS, TRAIN_LOADS = "Edit Train > Train Road Options", "Edit Train > Train Load Options"
ROUTE, LOCATION = "Edit Route", "Edit Location"
TRACK, TRACK_LOADS = "Edit Location > track", "Edit Location > track > Load Options"
TRACK_ROADS, TRACK_DESTS = "Edit Location > track > Road Options", "Edit Location > track > Track Destinations"
SCHEDULE, SETTINGS = "Edit Schedule for the spur", "OperationsPro Settings"

# code: (what the gate tests, screen that fixes it, setting). Order is code order.
GATES: dict[str, tuple[str, str, str]] = {
    "A1": ("Train build enabled", "Trains", "Build checkbox (only Build All and automations honour it)"),
    "A2": ("On-time build order", SETTINGS, "Build on time, train departure times"),
    "A3": ("Route exists and resolves", TRAIN, "Route"),
    "A4": ("Every route stop still exists", ROUTE, "Replace the deleted location"),
    "A5": ("Stop usable: not skipped, not staging mid-route", TRAIN, "Skip list, or route order"),
    "A6": ("Random move reduction", ROUTE, "Random"),
    "A7": ("Terminal staging has a free track", TRACK, "Set outs; empty a staging track"),
    "A8": ("Departure staging has a track this train can take whole", TRACK, "Pick ups and the cars on the track"),
    "B0": ("Car at a stop on this route and free to be picked", CAR_SET, "Location, or Route stops"),
    "B1": ("Car has a track", CAR_SET, "Track"),
    "B2": ("Location known", CAR_SET, "Location Unknown"),
    "B3": ("In service", CAR_SET, "Out of Service"),
    "B4": ("Car's destination on this route", CAR_SET, "Destination"),
    "B5": ("FRED or caboose only to the terminal", CAR_SET, "Destination"),
    "B6": ("Interchange: not set out by this same route", TRACK, "Pick ups: name trains or routes rather than any"),
    "B7": ("Track pick up list admits this train", TRACK, "Pick ups list"),
    "B8": ("Interchange filter has an exit on this route", TRACK_DESTS, "Accept the route's locations, or give the car a final destination"),
    "B9": ("Train takes this road", TRAIN_ROADS, "Road option; caboose road for a caboose"),
    "B10": ("Train takes this type", TRAIN, "Car types"),
    "B11": ("Train takes this owner", BUILD_OPTIONS, "Owner option"),
    "B12": ("Built inside the train's years, both ends exclusive", BUILD_OPTIONS, "Built dates"),
    "B13": ("Train takes this load", TRAIN_LOADS, "Load option"),
    "B14": ("FRED car only on a train that needs FRED", TRAIN, "Requires FRED"),
    "B15": ("Pick up day matches the active train schedule", "Train Schedules", "Active schedule, or the car's pick up day"),
    "B16": ("No wait count", CAR_SET, "Wait, which falls as trains that can serve the car build"),
    "B17": ("Caboose and FRED handled first", TRAIN, "Requires"),
    "B18": ("Kernel together on one track", CAR, "Kernel, or move the members together"),
    "B19": ("Manual build lines", TRAIN, "Manual build lines"),
    "B20": ("Departure staging: car is on the track that departs", TRACK, "Pick ups list"),
    "C1": ("Pick up stop not skipped", TRAIN, "Skip list"),
    "C2": ("Pick ups or local moves on at the stop", ROUTE, "Pick ups?, Local moves?"),
    "C3": ("Staging pick ups only at the start of the route", ROUTE, "Route order"),
    "C4": ("Stop direction served by the location", LOCATION, "Train direction, or the stop's direction in Edit Route"),
    "C5": ("Moves requested at the stop", ROUTE, "Moves"),
    "C6": ("Pick ups on, unless local move or final destination here", ROUTE, "Pick ups?"),
    "C7": ("Second pass rule for local moves", ROUTE, "Local moves?"),
    "C8": ("Pick up rules repeat at each stop", TRACK, "Pick ups list"),
    "C9": ("Stop direction served by the car's track", TRACK, "Train direction"),
    "C10": ("Staging ships this load", TRACK, "Ship load options on the staging track"),
    "C11": ("Quick service timing", TRACK, "Quick service"),
    "C12": ("Home division", CAR, "Division"),
    "D1": ("A later stop at the destination with set outs on", ROUTE, "A stop after the car's, Set outs?"),
    "D2": ("Destination stop not skipped", TRAIN, "Skip list"),
    "D3": ("Moves available at the destination stop", ROUTE, "Moves"),
    "D4": ("Not the same split location, unless a switcher", BUILD_OPTIONS, "Local switcher route, or Allow cars to return to staging"),
    "D5": ("Local moves on, for a final destination at the same location", ROUTE, "Local moves? at both stops"),
    "D6": ("Departure track's filter admits this location", TRACK_DESTS, "Accept the destination on the car's current track"),
    "D7": ("Location takes this type", LOCATION, "Car types"),
    "D8": ("Stop direction served by the destination", LOCATION, "Train direction"),
    "D9": ("Train length through the leg", ROUTE, "Max Length"),
    "D10": ("Through cars allowed, origin to terminal", BUILD_OPTIONS, "Allow cars to travel from origin to terminal"),
    "D11": ("Send to terminal rule", BUILD_OPTIONS, "Send all car pick ups to terminal"),
    "D12": ("Terminal staging track is free", TRACK, "Empty the staging track"),
    "D13": ("Not the same split track name", TRACK, "Track name"),
    "D14": ("Stop direction served by the track", TRACK, "Train direction"),
    "D15": ("Track set out list admits this train", TRACK, "Set outs list"),
    "D16": ("Car passes table E", TRACK, "See gates E1 to E10"),
    "D17": ("Length failure can fall to the spur's alternate", TRACK, "Alternate track"),
    "D18": ("Timing against pulls by other trains", TRAIN, "Departure time"),
    "D19": ("Local switcher track-to-track rule", SETTINGS, "Switcher Service Options"),
    "E1": ("Track is at the location", CAR_SET, "Track"),
    "E2": ("Location takes this type", LOCATION, "Car types"),
    "E3": ("Track takes this type", TRACK, "Car types"),
    "E4": ("Track takes this road", TRACK_ROADS, "Road option"),
    "E5": ("Car length is a number", CAR, "Length"),
    "E6": ("Track filter admits the final destination", TRACK_DESTS, "Accept the final destination"),
    "E7": ("Track that takes only routed cars", TRACK, "Routed"),
    "E8": ("Track takes this load", TRACK_LOADS, "Load option, plain or type & load"),
    "E9": ("Room on the track", TRACK, "Length, or free the track"),
    "E10": ("Schedule admits the car", SCHEDULE, "A line for this car, or a schedule for a custom load"),
    "F1": ("Line's set out day", SCHEDULE, "Delivery day"),
    "F2": ("Line's type", SCHEDULE, "Type"),
    "F3": ("Line's road", SCHEDULE, "Road"),
    "F4": ("Line's receive load", SCHEDULE, "Receive"),
    "F5": ("Line's random", SCHEDULE, "Random"),
    "G1": ("Train can carry: type, load, built, owner, road", TRAIN, "Car types and road and load options"),
    "G2": ("Car's location and destination on the route", ROUTE, "Stops; a staging destination must be the last"),
    "G3": ("Moves and pick ups at the car's stop", ROUTE, "Moves, Pick ups?, Local moves?"),
    "G4": ("Direction at the car's location and track", TRACK, "Train direction"),
    "G5": ("Track pick up list admits this train", TRACK, "Pick ups list"),
    "G6": ("Destination stop: set outs, moves, not skipped", ROUTE, "Set outs?, Moves"),
    "G7": ("Direction at the destination location", LOCATION, "Train direction"),
    "G8": ("Destination track direction and set out list", TRACK, "Train direction, Set outs list"),
    "G9": ("Terminal, local, return and through rules", BUILD_OPTIONS, "Terminal and through options"),
    "G10": ("Train length before the destination", ROUTE, "Max Length"),
    "G11": ("Only active trains", SETTINGS, "Car Routing Options"),
    "G12": ("Router can chain trains to the destination", SETTINGS, "Car Routing Options, and connecting interchanges"),
}


def _custom(rr: Railroad, car: Car) -> bool:
    return not rr.is_default_load(car.load)


def _exempt(car: Car) -> bool:
    """Passenger cars, cabooses and FRED cars skip the same-place rules."""
    return car.passenger or car.caboose or car.fred


class Gates:
    def __init__(self, railroad: Railroad):
        self.rr = railroad

    @staticmethod
    def _gate(code: str, status: str | bool, reason: str = "") -> dict:
        if isinstance(status, bool):
            status = PASS if status else FAIL
        title, screen, setting = GATES[code]
        result = {"gate": code, "status": status, "tests": title, "reason": reason}
        if status != PASS:
            result["fix"] = {"screen": screen, "setting": setting}
        return result

    def _is_switcher(self, train: Train) -> bool:
        stops = self.rr.stops(train)
        return bool(stops) and len({s.split for s in stops}) == 1

    def _is_turn(self, train: Train) -> bool:
        stops = self.rr.stops(train)
        return bool(stops) and not self._is_switcher(train) and stops[0].split == stops[-1].split

    def _mid_staging(self, train: Train, stop: Stop) -> bool:
        stops = self.rr.stops(train)
        location = self.rr.locations.get(stop.location_id)
        return bool(location) and location.is_staging and stop is not stops[0] and stop is not stops[-1]

    # Table E and F: Car.checkDestination, Track.isRollingStockAccepted, Track.checkSchedule.
    def check_destination(self, car: Car, location: Location, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        out = [gate("E1", track.location_id == location.id, f"{track.name} at {location.name}")]
        out.append(gate("E2", car.type in location.types, f"{location.name}: type {car.type}"))
        out.append(gate("E3", car.type in location.types and car.type in track.types,
                        f"{track.name}: type {car.type}"))
        out.append(gate("E4", track.accepts_road(car.road), f"{track.name} {track.road_option}: road {car.road}"))
        length = rr.car_length(car)
        out.append(gate("E5", length is not None, f"length {car.length}"))
        fd_name = rr.locations[car.fd_id].name if car.fd_id in rr.locations else "none"
        out.append(gate("E6", track.accepts_destination(car.fd_id or None),
                        f"{track.name} {track.destination_option}: final destination {fd_name}"))
        out.append(gate("E7", not track.only_fd or bool(car.fd_id) or car.caboose or car.fred,
                        f"car has final destination {fd_name}; only routed cars: {track.only_fd}"))
        out.append(gate("E8", track.accepts_load(car.load, car.type),
                        f"{track.name} {track.load_option}: {car.type} {car.load}"))
        out.append(self._space(car, track))
        out.extend(self._schedule(car, track))
        return out

    def _space(self, car: Car, track: Track) -> dict:
        rr = self.rr
        if track.id in (car.track_id, car.dest_track_id):
            return self._gate("E9", PASS, "car already belongs to this track")
        used, reserved = rr.used_length(track), rr.reserved_length(track)
        need = rr.kernel_length(car)
        room = f"needs {need}, used {used}, reserved {reserved}, length {track.length}"
        if used + reserved + need <= track.length:
            return self._gate("E9", PASS, room)
        if track.pool:
            return self._gate("E9", NOT_CHECKED, f"{room}; pool {track.pool} may lend length during the build")
        if track.ignore_used or track.load_options & QUICK_SERVICE:
            return self._gate("E9", NOT_CHECKED, f"{room}; planned pick ups or quick service may free it")
        if need > track.length:
            return self._gate("E9", FAIL, f"car is longer than the track: {room}")
        return self._gate("E9", FAIL, f"track is full: {room}")

    def _line(self, car: Car, item: ScheduleItem, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        day = item.setout_day
        day_ok = car.schedule_item == item.id or not day or day == rr.active_schedule \
            or day not in rr.train_schedules
        out = [gate("F1", day_ok, f"line {item.id} set out day {rr.train_schedules.get(day, day or 'any')}, "
                                  f"active {rr.train_schedules.get(rr.active_schedule, rr.active_schedule or 'any')}")]
        out.append(gate("F2", car.type == item.type, f"line {item.id} wants type {item.type}, car is {car.type}"))
        out.append(gate("F3", not item.road or car.road == item.road, f"line {item.id} road {item.road or 'any'}"))
        out.append(gate("F4", not item.receive or car.load == item.receive,
                        f"line {item.id} receives {item.receive or 'any load'}, car has {car.load}"))
        # Schedule.checkScheduleItem: the draw is skipped when the car's final destination track is this
        # spur or the car already holds the line. Only a blank means no draw; "0" is drawn and never passes.
        drawn = item.random != "" and car.schedule_item != item.id and car.fd_track_id != track.id
        if not drawn:
            out.append(gate("F5", PASS, "no random draw"))
        elif not re.fullmatch(r"-?\d+", item.random):
            out.append(gate("F5", FAIL, f"line {item.id} random {item.random!r} is not a number, so the draw never passes"))
        else:
            out.append(gate("F5", NOT_CHECKED, f"line {item.id} random {item.random}%"))
        return out

    def _schedule(self, car: Car, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        passing = [gate(c, PASS, "no schedule line applies") for c in ("F1", "F2", "F3", "F4", "F5")]
        if car.dest_track_id == track.id:
            return [gate("E10", PASS, "car is already destined here"), *passing]
        if not track.is_spur:
            return [gate("E10", PASS, f"{track.type} tracks do not use schedules"), *passing]
        schedule = rr.schedules.get(track.schedule_id)
        if schedule is None:
            custom = _custom(rr, car)
            reason = (f"spur has no schedule, so it refuses custom load {car.load}"
                      if custom else "no schedule and a default load")
            return [gate("E10", not custom, reason), *passing]
        if not schedule.items:
            return [gate("E10", FAIL, f"schedule {schedule.name} has no lines"), *passing]
        if track.schedule_mode == MATCH:
            items = schedule.items
        else:
            items = [i for i in schedule.items if i.id == track.item_id] or schedule.items[:1]
        lines = [self._line(car, item, track) for item in items]
        lines.sort(key=lambda gates: sum(g["status"] == FAIL for g in gates))
        best = lines[0]
        ok = not any(g["status"] == FAIL for g in best)
        mode = "match, any line" if track.schedule_mode == MATCH else f"sequential, current line {items[0].id} only"
        return [gate("E10", ok, f"schedule {schedule.name} ({mode})"), *best]

    def destination_status(self, car: Car, location: Location, track: Track) -> tuple[bool, str]:
        """Same answer as Car.checkDestination: first failing gate, or OK."""
        for result in self.check_destination(car, location, track):
            if result["status"] == FAIL:
                return False, result["gate"]
        return True, ""

    # Table G: Train.isServiceable, as the router sees a car. dest is the what-if destination.
    def _can_carry(self, car: Car, train: Train) -> bool:
        road = train.accepts_caboose_road(car.road) if car.caboose else train.accepts_road(car.road)
        return (car.type in train.types and train.accepts_load(car.load, car.type)
                and train.accepts_built(car.built) and train.accepts_owner(car.owner) and road)

    def serviceable(self, car: Car, train: Train, dest: Location | None = None,
                    dest_track: Track | None = None) -> list[dict]:
        rr, gate = self.rr, self._gate
        out: list[dict] = []
        dest_id = dest.id if dest else car.destination_id
        dest_track = dest_track or rr.tracks.get(car.dest_track_id)
        out.append(gate("G1", self._can_carry(car, train), f"{train.name}: {car.type} {car.load}, {car.road}, "
                                                           f"owner {car.owner}, built {car.built}"))
        stops = rr.stops(train)
        here = rr.locations.get(car.location_id)
        track = rr.tracks.get(car.track_id)
        on_route = any(s.location_id == car.location_id for s in stops)
        dest_loc = rr.locations.get(dest_id)
        dest_ok = dest_loc is None or (any(s.location_id == dest_id for s in stops) and (
            not dest_loc.is_staging or stops[-1].location_id == dest_id))
        ok = bool(stops) and here is not None and track is not None and on_route and dest_ok
        out.append(gate("G2", ok, f"route {train.route_id or 'none'}; staging must be the last stop"))
        if not ok:
            return out
        local = dest_loc is not None and dest_loc.split == here.split
        switcher = self._is_switcher(train)
        best: list[dict] = []
        for start, stop in enumerate(stops):
            if stop.location_id != car.location_id:
                continue
            moves = stop.max_moves > 0 and stop.id not in train.skips
            allowed = stop.local if local else stop.pickups
            attempt = [gate("G3", moves and allowed, f"{stop.id}: moves {stop.max_moves}, pick ups {stop.pickups}")]
            way = switcher or (stop.direction & here.dir and stop.direction & track.dir)
            attempt.append(gate("G4", bool(way), f"{stop.id} {directions(stop.direction)}; "
                                                 f"location {directions(here.dir)}, track {directions(track.dir)}"))
            attempt.append(gate("G5", track.accepts_pickup(train), f"{track.name}: {track.pickup_option}"))
            if not any(g["status"] == FAIL for g in attempt):
                if dest_loc is None:
                    return out + attempt
                attempt += self._serviceable_dest(car, train, stops, start, dest_loc, dest_track, local)
                if not any(g["status"] == FAIL for g in attempt):
                    return out + attempt
            if not best or len(attempt) > len(best):
                best = attempt
        return out + best

    def _serviceable_dest(self, car: Car, train: Train, stops: list[Stop], start: int, dest: Location,
                          dest_track: Track | None, local: bool) -> list[dict]:
        rr, gate = self.rr, self._gate
        best: list[dict] = []
        switcher = self._is_switcher(train)
        for index in range(start, len(stops)):
            stop = stops[index]
            if stop.location_id != dest.id:
                continue
            ok = (stop.local if local else stop.drops) and stop.max_moves > 0 and stop.id not in train.skips
            if rr.option("router", "checkCarDestination"):
                ok = ok and rr.tracks[car.track_id].accepts_destination(dest.id)
            attempt = [gate("G6", bool(ok), f"{stop.id}: drops {stop.drops}, moves {stop.max_moves}")]
            attempt.append(gate("G7", bool(switcher or stop.direction & dest.dir),
                                f"{stop.id} {directions(stop.direction)}, {dest.name} {directions(dest.dir)}"))
            tracks = [dest_track] if dest_track else dest.tracks
            def fits(t: Track) -> bool:
                return bool(switcher or stop.direction & t.dir) and t.accepts_drop(train)
            # With no destination track, Train uses track.isRollingStockAccepted, which has no schedule test.
            usable = [t for t in tracks if fits(t) and (
                dest_track or self._accepts_ignoring_length(car, dest, t, schedule=False))]
            attempt.append(gate("G8", bool(usable), f"{len(usable)} of {len(tracks)} tracks at {dest.name}"))
            attempt.append(self._g9(car, train, stops, stops[start], stop, dest))
            length = rr.kernel_length(car)
            attempt.append(gate("G10", all(length <= s.max_length for s in stops[start:index]),
                                f"car or kernel {length}, train empty; other cars count during a build"))
            if not any(g["status"] == FAIL for g in attempt):
                return attempt
            best = best or attempt
        return best or [gate("G6", FAIL, f"no stop at {dest.name} from the car's stop onward")]

    def _g9(self, car: Car, train: Train, stops: list[Stop], origin: Stop, stop: Stop, dest: Location) -> dict:
        rr = self.rr
        here = rr.locations.get(car.location_id)
        track = rr.tracks[car.track_id]
        local = dest.split == here.split
        reasons = []
        if train.to_terminal and not local and here.split != stops[0].split and dest.split != stops[-1].split:
            reasons.append("train sends every later pick up to the terminal")
        if not self._is_turn(train) and track.is_staging and dest.id == here.id:
            reasons.append("no local move inside staging")
        # Train.isServiceableDestination returns true here, before the local-move, through-car and moves tests.
        if not reasons and train.allow_return and track.is_staging and dest.id == here.id:
            return self._gate("G9", PASS, "the train may return the car to its own staging")
        switcher = self._is_switcher(train)
        if local and not switcher and not _exempt(car) and not (
                train.local_moves and origin.local and stop.local):
            reasons.append("local moves are off for this train or stop")
        if (not train.through_cars and origin.split == stops[0].split and stop.split == stops[-1].split
                and stops[0].split != stops[-1].split and not switcher and not _exempt(car)):
            reasons.append("through cars are off")
        return self._gate("G9", not reasons, "; ".join(reasons) or "terminal, local and through rules allow it")

    def _accepts_ignoring_length(self, car: Car, location: Location, track: Track, schedule: bool = True) -> bool:
        """Table E with a length failure tolerated; schedule=False also drops E10 and the F lines."""
        skipped = {"E9"} if schedule else {"E9", "E10", "F1", "F2", "F3", "F4", "F5"}
        results = self.check_destination(car, location, track)
        return not any(r["status"] == FAIL and r["gate"] not in skipped for r in results)

    # Tables A to D, one train, one car, one track.
    def _train_gates(self, train: Train) -> tuple[list[dict], list[Stop]]:
        rr, gate = self.rr, self._gate
        out = [gate("A1", train.build, f"{train.name} build {train.build}")]
        out.append(gate("A2", NOT_CHECKED, "depends on the order trains build in"))
        stops = rr.stops(train)
        out.append(gate("A3", bool(stops), f"route {train.route_id or 'none'} has {len(stops)} stops"))
        missing = [s.name for s in stops if s.location_id not in rr.locations]
        out.append(gate("A4", not missing, ", ".join(missing) or "all stops exist"))
        return out, stops

    def staging_problems(self, train: Train, track: Track) -> list[str]:
        """Why this staging track cannot depart on this train (checkDepartureStagingTrack)."""
        rr = self.rr
        stops = rr.stops(train)
        first = stops[0]
        cars, engines = rr.rolling_stock_on(track)
        problems = []
        if not track.accepts_pickup(train):
            problems.append("pick up list refuses the train")
        if not cars and not engines and first.max_moves > 0:
            problems.append("track is empty")
        if rr.used_length(track) > first.max_length:
            problems.append(f"{rr.used_length(track)} long, route allows {first.max_length}")
        if len(cars) > first.max_moves:
            problems.append(f"{len(cars)} cars, route allows {first.max_moves} moves")
        if train.engines.isdigit() and int(train.engines) and int(train.engines) != len(engines):
            problems.append(f"{len(engines)} locomotives, train needs {train.engines}")
        if not track.dir & first.direction:
            problems.append("track direction does not match the route")
        caboose = fred = False
        for car in cars:
            if car.kernel and not car.lead:
                continue
            problems.extend(self._staging_car(car, train, track))
            right_road = not train.caboose_road or train.caboose_road == car.road
            caboose = caboose or (car.caboose and right_road)
            fred = fred or (car.fred and right_road)
        if train.requires & REQUIRES_CABOOSE and not caboose:
            problems.append(f"no caboose of road {train.caboose_road or 'any'}")
        if train.requires & REQUIRES_FRED and not fred:
            problems.append(f"no FRED car of road {train.caboose_road or 'any'}")
        return problems

    def _staging_car(self, car: Car, train: Train, track: Track) -> list[str]:
        problems = []
        if car.train_id and car.train_id != train.id:
            problems.append(f"{car} is assigned to another train")
        if car.type not in train.types:
            problems.append(f"train does not take {car} type {car.type}")
        if not car.caboose and not train.accepts_road(car.road):
            problems.append(f"train does not take {car} road {car.road}")
        generated = car.load == self.rr.default_empty and track.generates_loads
        if not car.caboose and not car.passenger and not generated and not train.accepts_load(car.load, car.type):
            problems.append(f"train does not take {car} load {car.load}")
        if not train.accepts_owner(car.owner):
            problems.append(f"train does not take {car} owner {car.owner}")
        if not train.accepts_built(car.built):
            problems.append(f"train does not take {car} built {car.built}")
        return problems

    def terminal_track_problems(self, train: Train, track: Track) -> list[str]:
        """Why this staging track cannot take the train at its terminal (checkTerminateStagingTrack).

        Occupied fails unless the track ignores used length, or the build is aggressive with staging
        tracks immediately available. Cars already destined here fail on their own, unless on-time
        building with quick service.
        """
        rr = self.rr
        problems = []
        if not track.accepts_drop(train):
            problems.append("set out list refuses the train")
        cars, engines = rr.rolling_stock_on(track)
        if (cars or engines) and not track.ignore_used and not (
                rr.option("buildOptions", "aggressive") and rr.option("buildOptions", "stagingTrackAvail")):
            problems.append(f"occupied by {len(cars)} cars and {len(engines)} locomotives")
        pending = [c for c in rr.cars.values() if c.dest_track_id == track.id and c.track_id != track.id]
        if pending and not (rr.option("buildOptions", "onTime") and track.load_options & QUICK_SERVICE):
            problems.append(f"{len(pending)} cars already destined here")
        return problems

    def _staging_gates(self, train: Train, stops: list[Stop]) -> list[dict]:
        rr, gate = self.rr, self._gate
        out = []
        last = rr.locations.get(stops[-1].location_id)
        if last is not None and last.is_staging and len(stops) > 1:
            usable = [t for t in last.tracks if not self.terminal_track_problems(train, t)]
            out.append(gate("A7", bool(usable), f"free at {last.name}: {', '.join(t.name for t in usable) or 'none'}"))
        else:
            out.append(gate("A7", PASS, "train does not end in staging"))
        first = rr.locations.get(stops[0].location_id)
        if first is not None and first.is_staging:
            report = {t.name: self.staging_problems(train, t) for t in first.tracks}
            good = [name for name, problems in report.items() if not problems]
            reason = (f"can depart from {', '.join(good)}" if good else
                      "; ".join(f"{name}: {', '.join(problems)}" for name, problems in report.items()))
            out.append(gate("A8", bool(good), reason))
        else:
            out.append(gate("A8", PASS, "train does not start in staging"))
        return out

    def _car_list_gates(self, car: Car, train: Train, stops: list[Stop], target: Track | None) -> list[dict]:
        rr, gate = self.rr, self._gate
        track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        placed = [s for s in stops if s.location_id == car.location_id]
        last = stops[-1] if stops else None
        at_last_only = bool(placed) and len(stops) > 1 and placed == [last] and not (
            last.local and here is not None and not here.is_staging)
        free = not car.train_id or car.train_id == train.id
        out = [gate("B0", bool(placed) and not at_last_only and free and here is not None,
                    f"car at {here.name if here else 'no location'}; "
                    f"{'not on this route' if not placed else 'last stop' if at_last_only else 'on route'}; "
                    f"assigned train {car.train_id or 'none'}")]
        out.append(gate("B1", track is not None, track.name if track else "no track set"))
        out.append(gate("B2", not car.unknown, f"location unknown {car.unknown}"))
        out.append(gate("B3", not car.out_of_service, f"out of service {car.out_of_service}"))
        on_route = not car.destination_id or any(s.location_id == car.destination_id for s in stops)
        out.append(gate("B4", on_route, f"car destination {car.destination_id or 'none'}"))
        # createCarList tests only the car's assigned destination, never a what-if target. A caboose is
        # let through when a leg option adds or removes the caboose along the route.
        held = car.fred or (car.caboose and not train.changes_caboose)
        if not held:
            out.append(gate("B5", PASS, "only FRED cars and cabooses are held to the terminal"))
        elif not car.destination_id:
            out.append(gate("B5", PASS, "the car has no assigned destination; the target asked about is not one"))
        else:
            terminal = bool(stops) and car.destination_id == stops[-1].location_id
            out.append(gate("B5", terminal, f"assigned destination {car.destination_id}, "
                                            f"terminal {stops[-1].location_id if stops else 'none'}"))
        same_route = bool(track) and track.is_interchange and track.pickup_option == ANY \
            and car.last_route_id == train.route_id
        out.append(gate("B6", not same_route, f"last route {car.last_route_id or 'none'}, this route {train.route_id}"))
        pulled = track is None or not (track.is_interchange or track.is_spur) or track.accepts_pickup(train)
        out.append(gate("B7", pulled, f"{track.name}: {track.pickup_option}" if track else "no track"))
        exit_ok = True
        if track and track.is_interchange and track.destination_option != ALL and not car.fd_id:
            exit_ok = any(track.accepts_destination(s.location_id) for s in stops)
        out.append(gate("B8", exit_ok, f"{track.name}: {track.destination_option}" if track else "no track"))
        road = train.accepts_caboose_road(car.road) if car.caboose else train.accepts_road(car.road)
        out.append(gate("B9", road, f"{train.name} {train.road_option}: road {car.road}"))
        out.append(gate("B10", car.type in train.types, f"{train.name}: type {car.type}"))
        out.append(gate("B11", train.accepts_owner(car.owner), f"{train.name}: owner {car.owner}"))
        years = f"{train.built_start or 'any'} < {built_year(car.built)} < {train.built_end or 'any'}"
        out.append(gate("B12", train.accepts_built(car.built), years))
        on_departure = bool(stops) and bool(track) and track.is_staging and car.location_id == stops[0].location_id
        load_ok = car.caboose or car.passenger or on_departure or train.accepts_load(car.load, car.type)
        out.append(gate("B13", load_ok, f"{train.name} {train.load_option}: {car.type} {car.load}"))
        out.append(gate("B14", on_departure or not car.fred or bool(train.requires & REQUIRES_FRED),
                        f"FRED {car.fred}; train requires {train.requires}"))
        day = car.pickup_day
        day_ok = on_departure or not day or rr.active_schedule == ANY_DAY or day == rr.active_schedule \
            or day not in rr.train_schedules
        out.append(gate("B15", day_ok, f"pick up day {rr.train_schedules.get(day, day or 'any')}, "
                                       f"active {rr.train_schedules.get(rr.active_schedule, rr.active_schedule or 'any')}"))
        out.append(gate("B16", on_departure or car.wait <= 0, f"wait {car.wait}"))
        out.append(gate("B17", PASS, "cabooses and FRED cars are taken first, then left out of the general list"))
        out.append(self._kernel(car))
        out.append(gate("B19", NOT_CHECKED, "manual build lines are not read in this release"))
        out.append(self._departure_track(car, train, stops))
        return out

    def _kernel(self, car: Car) -> dict:
        if not car.kernel:
            return self._gate("B18", PASS, "not in a kernel")
        # checkKernel: a lead that is in service, every member at one location with a track, and the
        # track names equal once split.
        rr = self.rr
        members = [c for c in rr.cars.values() if c.kernel == car.kernel]
        leads = [c for c in members if c.lead and not c.out_of_service]
        places = {(c.location_id, rr.tracks[c.track_id].split if c.track_id in rr.tracks else None)
                  for c in members}
        ok = bool(leads) and len(places) == 1 and None not in {p[1] for p in places}
        return self._gate("B18", ok, f"kernel {car.kernel}: {len(leads)} lead in service, {len(places)} track "
                                     "names. A split kernel fails the whole build, not only the car.")

    def _departure_track(self, car: Car, train: Train, stops: list[Stop]) -> dict:
        rr = self.rr
        track = rr.tracks.get(car.track_id)
        if not stops or track is None or not track.is_staging or car.location_id != stops[0].location_id:
            return self._gate("B20", PASS, "car is not on departure staging")
        problems = self.staging_problems(train, track)
        return self._gate("B20", not problems, ", ".join(problems) or f"{track.name} can depart")

    def _pickup_gates(self, car: Car, train: Train, stops: list[Stop], stop: Stop | None,
                      goal: Stop | None) -> list[dict]:
        rr, gate = self.rr, self._gate
        codes = [f"C{n}" for n in range(1, 13)]
        track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        if stop is None or track is None or here is None:
            return [gate(c, NOT_CHECKED, "no pick up stop on this route") for c in codes]
        local = goal is not None and goal.split == stop.split
        switcher = self._is_switcher(train)
        out = [gate("C1", stop.id not in train.skips, f"stop {stop.id}")]
        out.append(gate("C2", stop.pickups or stop.local, f"pick ups {stop.pickups}, local {stop.local}"))
        out.append(gate("C3", not here.is_staging or stop is stops[0], f"{here.name} staging {here.is_staging}"))
        out.append(gate("C4", switcher or bool(stop.direction & here.dir),
                        f"{stop.id} {directions(stop.direction)}, {here.name} {directions(here.dir)}"))
        out.append(gate("C5", stop.max_moves > 0, f"moves {stop.max_moves}"))
        out.append(gate("C6", stop.pickups or local or car.fd_id == stop.location_id, f"pick ups {stop.pickups}"))
        out.append(gate("C7", not local or stop.local or switcher, f"local {stop.local}"))
        out.append(gate("C8", PASS, "repeats B6 and B7, needed for quick service"))
        out.append(gate("C9", switcher or bool(stop.direction & track.dir),
                        f"{stop.id} {directions(stop.direction)}, {track.name} {directions(track.dir)}"))
        # The ship check runs whenever both generators fail. A generator only replaces a default empty with
        # no destination or final destination, and only when the type has a custom load to give.
        if track.ships_load(car.load, car.type):
            out.append(gate("C10", PASS, f"{track.ship_option}: {car.load}"))
        elif (track.is_staging and track.generates_loads and car.load == rr.default_empty
              and not car.destination_id and not car.fd_id and rr.custom_loads(car.type)):
            out.append(gate("C10", NOT_CHECKED, f"{track.ship_option}: {car.load}; fails the build if load "
                                                "generation finds nothing"))
        else:
            out.append(gate("C10", FAIL, f"{track.ship_option}: {car.load}, and no generator replaces it"))
        quick = bool(track.load_options & QUICK_SERVICE)
        out.append(gate("C11", NOT_CHECKED if quick else PASS, "quick service timing" if quick else "no quick service"))
        division = bool(car.division_id)
        out.append(gate("C12", NOT_CHECKED if division else PASS,
                        "a car with a division gets a final destination first, and is then routed" if division
                        else "no home division"))
        return out

    def _drop_gates(self, car: Car, train: Train, stops: list[Stop], origin: Stop | None, stop: Stop | None,
                    dest: Location, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        here_track = rr.tracks.get(car.track_id)
        here = rr.locations.get(car.location_id)
        if stop is None or origin is None or here_track is None or here is None:
            reason = f"no stop at {dest.name} after the car's stop on this route"
            first = gate("D1", FAIL, reason)
            return [first] + [gate(f"D{n}", NOT_CHECKED, reason) for n in range(2, 20)]
        exempt = _exempt(car)
        switcher = self._is_switcher(train)
        same = origin.split == stop.split
        mid = self._mid_staging(train, stop)
        out = [gate("D1", stop.drops or car.fred or car.caboose, f"drops {stop.drops}")]
        out.append(gate("D2", stop.id not in train.skips, f"stop {stop.id}"))
        out.append(gate("D3", stop.max_moves > 0 and not mid,
                        "staging mid-route uses all its moves" if mid else f"moves {stop.max_moves}"))
        returning = (train.allow_return or rr.option("buildOptions", "allowReturnStaging")) and dest.is_staging
        out.append(gate("D4", not same or switcher or exempt or returning,
                        f"{origin.split} to {stop.split}, switcher {switcher}"))
        out.append(gate("D5", not same or not car.fd_id or exempt or (stop.local and origin.local),
                        f"local {origin.local} and {stop.local}"))
        out.append(gate("D6", here_track.accepts_destination(dest.id),
                        f"{here_track.name} {here_track.destination_option}: {dest.name}"))
        out.append(gate("D7", car.type in dest.types, f"{dest.name}: type {car.type}"))
        out.append(gate("D8", switcher or bool(stop.direction & dest.dir),
                        f"{stop.id} {directions(stop.direction)}, {dest.name} {directions(dest.dir)}"))
        length = rr.kernel_length(car)
        leg = stops[stops.index(origin):stops.index(stop)]
        out.append(gate("D9", all(length <= s.max_length for s in leg),
                        f"car or kernel {length} against an empty train; other cars count during a build"))
        through = (not train.through_cars and not switcher and not exempt and here.split == stops[0].split
                   and stop.split == stops[-1].split and stops[0].split != stops[-1].split)
        out.append(gate("D10", not through, f"allow through cars {train.through_cars}"))
        terminal = train.to_terminal and origin.split != stops[0].split and stop.split != stops[-1].split
        out.append(gate("D11", not terminal, f"send to terminal {train.to_terminal}"))
        # The train terminates only on a track A7 accepts; there tryStaging refuses a local switcher's own
        # track and otherwise answers through car.checkDestination (D16).
        staged = dest.is_staging and stop is stops[-1] and track.is_staging
        problems = self.terminal_track_problems(train, track) if staged else []
        if staged and switcher and not exempt and car.track_id == track.id:
            problems.append("a switcher cannot set the car out on its own staging track")
        out.append(gate("D12", not problems, "; ".join(problems) or (
            "the train can terminate here; table E decides" if staged else "not terminal staging")))
        same_name = here.split == dest.split and here_track.split == track.split and not exempt
        out.append(gate("D13", not same_name, f"{here_track.name} to {track.name}"))
        final = rr.tracks.get(car.fd_track_id)
        shared = not (final and final.alternate_id == track.id and not track.dir & final.dir)
        out.append(gate("D14", (switcher or bool(stop.direction & dest.dir & track.dir)) and shared,
                        f"{stop.id} {directions(stop.direction)}, {track.name} {directions(track.dir)}"))
        listed = not (track.is_interchange or track.is_spur) or track.accepts_drop(train)
        out.append(gate("D15", listed, f"{track.name}: {track.drop_option}"))
        table_e = self.check_destination(car, dest, track)
        bad = [r["gate"] for r in table_e if r["status"] == FAIL]
        out.append(gate("D16", not bad, f"fails {', '.join(bad)}" if bad else "passes table E"))
        alternate = rr.tracks.get(track.alternate_id)
        full = any(r["gate"] == "E9" and r["status"] == FAIL and "full" in r["reason"] for r in table_e)
        if full and alternate:
            # checkForAlternate: the alternate must take the train and pass table E for the car, which
            # depends on its own space at that moment in the build.
            out.append(gate("D17", NOT_CHECKED, f"track is full; the car goes to alternate {alternate.name} "
                                                "only if that track takes the train and the car during the build"))
        else:
            out.append(gate("D17", PASS, "no alternate needed" if not full else "track is full and has no alternate"))
        out.append(gate("D18", NOT_CHECKED, "depends on which trains pull from the track and when"))
        allowed = self._local_track_rule(car, train, here_track, track)
        out.append(gate("D19", allowed, f"switcher {switcher}: {here_track.type} to {track.type}"))
        return out

    def _local_track_rule(self, car: Car, train: Train, here: Track, there: Track) -> bool:
        if not self._is_switcher(train):
            return True
        options = self.rr.option
        spur = options("buildOptions", "allowLocalSpur", options("buildOptions", "allowLocalSiding"))
        if not spur and here.is_spur and there.is_spur:
            return False
        if (not options("buildOptions", "allowLocalYard") and here.is_yard and there.is_yard
                and not car.caboose and not car.fred):
            return False
        return options("buildOptions", "allowLocalInterchange") or not (here.is_interchange and there.is_interchange)

    def _router_gates(self, car: Car, train: Train, dest: Location, track: Track) -> list[dict]:
        rr, gate = self.rr, self._gate
        codes = [f"G{n}" for n in range(1, 11)]
        if not (car.fd_id or _custom(rr, car) or car.division_id):
            return [gate(c, PASS, "router not used: default load and no final destination") for c in codes]
        results = {r["gate"]: r for r in self.serviceable(car, train, dest, track)}
        return [results.get(c) or gate(c, NOT_CHECKED, "stopped at an earlier G gate") for c in codes]

    def evaluate(self, car: Car, train: Train, dest: Location, track: Track) -> list[dict]:
        """Every gate in code order for one train and one destination track."""
        out, stops = self._train_gates(train)
        if not stops:
            head = [self._gate(c, NOT_CHECKED, "no route") for c in ("A5", "A6", "A7", "A8")]
            return out + head + self._rest(car, train, stops, None, None, dest, track)
        switcher = self._is_switcher(train)
        pickups = [s for s in stops if s.location_id == car.location_id]
        pairs = [(a, b) for a in pickups for b in stops
                 if b.location_id == dest.id and (stops.index(b) > stops.index(a) or (switcher and a is b))]
        if not pairs:
            pairs = [(pickups[0] if pickups else None, None)]
        best = None
        for pickup, drop in pairs:
            used = [s for s in (pickup, drop) if s]
            bad = [s.name for s in used if s.id in train.skips or self._mid_staging(train, s)]
            head = [self._gate("A5", not bad, ", ".join(bad) or "stops in use are worked")]
            drawn = [s.id for s in used if s.random not in ("Off", "0", "")]
            head.append(self._gate("A6", NOT_CHECKED if drawn else PASS,
                                   f"random at {', '.join(drawn)}" if drawn else "random off at these stops"))
            head += self._staging_gates(train, stops)
            attempt = head + self._rest(car, train, stops, pickup, drop, dest, track)
            if best is None or _rank(attempt) < _rank(best):
                best = attempt
        return out + best

    def _rest(self, car: Car, train: Train, stops: list[Stop], pickup: Stop | None, drop: Stop | None,
              dest: Location, track: Track) -> list[dict]:
        out = self._car_list_gates(car, train, stops, track)
        out += self._pickup_gates(car, train, stops, pickup, drop)
        out += self._drop_gates(car, train, stops, pickup, drop, dest, track)
        out += self.check_destination(car, dest, track)
        out += self._router_gates(car, train, dest, track)
        out.append(self._g11(train))
        return out

    def _g11(self, train: Train) -> dict:
        """TrainManager.getTrainForCar skips trains with build off when only active trains are used."""
        if not self.rr.option("router", "onlyActiveTrains"):
            return self._gate("G11", PASS, "option off")
        return self._gate("G11", train.build, f"{train.name} build {train.build}")

    # Router: breadth-first across trains, the shape of Router.setDestination.
    def route_path(self, car: Car, target: Track, check_target: bool = True) -> list[dict] | None:
        """Trains chaining the car to the target, or None. Length is ignored, as at a first look."""
        rr = self.rr
        if not rr.option("router", "carRoutingEnabled", True):
            return None
        start = rr.tracks.get(car.track_id)
        if start is None:
            return None
        goal_location = rr.locations[target.location_id]
        if check_target and not self._accepts_ignoring_length(car, goal_location, target):
            return None
        queue = deque([(start, [], "")])
        seen = {start.id}
        while queue:
            track, path, last_route = queue.popleft()
            if len(path) >= MAX_ROUTER_TRAINS:
                continue
            moved = rr.at(car, track.location_id, track.id)
            for train in rr.trains.values():
                if self._hop_ok(moved, train, goal_location, target, last_route, track):
                    return path + [{"train": train.name, "to": f"{goal_location.name}, {target.name}"}]
                for via in self._connecting(moved):
                    if via.id in seen:
                        continue
                    location = rr.locations[via.location_id]
                    if self._hop_ok(moved, train, location, via, last_route, track):
                        seen.add(via.id)
                        step = {"train": train.name, "to": f"{location.name}, {via.name}"}
                        queue.append((via, path + [step], train.route_id))
        return None

    def _hop_ok(self, car: Car, train: Train, location: Location, track: Track, last_route: str,
                origin: Track) -> bool:
        if last_route == train.route_id and origin.is_interchange and origin.pickup_option == ANY:
            return False  # The same route may not drop and then pull an open interchange.
        if self._g11(train)["status"] == FAIL:
            return False
        if track.location_id == origin.location_id and not self._is_switcher(train):
            return False
        return not any(g["status"] == FAIL for g in self.serviceable(car, train, location, track))

    def _connecting(self, car: Car) -> list[Track]:
        rr = self.rr
        alternates = {t.alternate_id for t in rr.tracks.values() if t.alternate_id}
        out = []
        for track in rr.tracks.values():
            if track.id in alternates:
                continue
            usable = track.is_interchange or (track.is_yard and rr.option("router", "carRoutingViaYards")) or (
                track.is_staging and rr.option("router", "carRoutingViaStaging") and not track.modifies_loads)
            if usable and self._accepts_ignoring_length(car, rr.locations[track.location_id], track):
                out.append(track)
        # The router tries interchanges before yards, and staging last.
        return sorted(out, key=lambda t: (not t.is_interchange, t.is_staging))

    def routing_mode(self, car: Car) -> str:
        if car.fd_id:
            return "final destination: the router may chain up to seven trains"
        if car.division_id:
            return "home division: gets a final destination, then the router runs"
        if _custom(self.rr, car):
            return "custom load: global search of scheduled spurs, then staging, then this train's route"
        return "default load: only the building train's own route, the router never runs"

    def why_not(self, car: str | Car, destination: str | Location, track: str | Track | None = None,
                train: str | Train | None = None) -> dict:
        rr = self.rr
        car = rr.find_car(car) if isinstance(car, str) else car
        dest = rr.find_location(destination) if isinstance(destination, str) else destination
        tracks = [rr.find_track(track, dest) if isinstance(track, str) else track] if track else dest.tracks
        trains = [rr.find_train(train) if isinstance(train, str) else train] if train else list(rr.trains.values())
        if not trains:
            raise ValueError("The railroad has no trains")
        if not tracks:
            raise ValueError(f"{dest.name} has no tracks")
        table = []
        for candidate in trains:
            for target in tracks:
                gates = self.evaluate(car, candidate, dest, target)
                gates.append(self._g12(car, target))
                table.append((candidate, target, gates))
        table.sort(key=lambda row: _rank(row[2]))
        chosen_train, chosen_track, gates = table[0]
        failed = [g for g in gates if g["status"] == FAIL and g["gate"] != "G12"]
        path = self.route_path(car, chosen_track) if self._router_eligible(car) else None
        stuck = [g["gate"] for g in failed if g["gate"] in ANY_TRAIN]
        return {
            "car": str(car), "type": car.type, "load": car.load,
            "at": self._where(car), "destination": dest.name, "track": chosen_track.name,
            "train": chosen_train.name, "can_move": not failed or (bool(path) and not stuck),
            "direct": not failed, "routing": self.routing_mode(car), "router_path": path,
            "first_failure": failed[0] if failed else None,
            "gates": gates,
            "other_trains": [
                {"train": t.name, "track": k.name, "first_failure": _first(g)} for t, k, g in table[1:]],
            "note": "Files only. Disk can lag a running JMRI by a minute or two, and gates marked "
                    "not_checked depend on the build itself.",
        }

    def _router_eligible(self, car: Car) -> bool:
        return bool(car.fd_id or car.division_id or _custom(self.rr, car))

    def _where(self, car: Car) -> str:
        location = self.rr.locations.get(car.location_id)
        track = self.rr.tracks.get(car.track_id)
        return ", ".join(x.name for x in (location, track) if x) or "nowhere"

    def _g12(self, car: Car, target: Track) -> dict:
        if not self._router_eligible(car):
            return self._gate("G12", PASS, "router not used: default load and no final destination")
        if car.track_id not in self.rr.tracks:
            return self._gate("G12", NOT_CHECKED, "car has no track")
        path = self.route_path(car, target)
        reason = " then ".join(f"{p['train']} to {p['to']}" for p in path) if path else "no chain of trains found"
        return self._gate("G12", path is not None, reason)

    def audit(self) -> dict:
        findings: list[dict] = []
        for rule in Audit(self).rules():
            findings.extend(rule())
        order = {"error": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda f: order[f["severity"]])
        counts = {name: sum(f["severity"] == name for f in findings) for name in order}
        return {"railroad": self.rr.name, "counts": counts, "findings": findings,
                "load_warnings": self.rr.warnings}


def _rank(gates: list[dict]) -> tuple[int, int]:
    """Fewer failures first, then the failure furthest down the gates."""
    fails = [i for i, g in enumerate(gates) if g["status"] == FAIL]
    return (len(fails), -(fails[0] if fails else len(gates)))


def _first(gates: list[dict]) -> str | None:
    for g in gates:
        if g["status"] == FAIL:
            return f"{g['gate']}: {g['reason']}"
    return None


def _finding(rule: str, severity: str, subject: str, message: str, screen: str, setting: str) -> dict:
    return {"rule": rule, "severity": severity, "subject": subject, "message": message,
            "fix": {"screen": screen, "setting": setting}}


class Audit:
    """Whole-railroad checks. Each rule yields findings and stands alone."""

    def __init__(self, gates: Gates):
        self.g = gates
        self.rr = gates.rr

    def rules(self) -> list:
        return [getattr(self, name) for name in dir(self) if name.startswith("rule_")]

    def _fed_types(self) -> set[str]:
        return {car.type for car in self.rr.cars.values()}

    def rule_type_carriage(self):
        rr = self.rr
        for kind in sorted(self._fed_types()):
            if not any(kind in t.types for t in rr.trains.values()):
                yield _finding("type-no-train", "error", kind, f"No train takes car type {kind}.",
                               TRAIN, "Car types")
            if not any(kind in t.types and kind in rr.locations[t.location_id].types for t in rr.tracks.values()):
                yield _finding("type-no-track", "error", kind, f"No track takes car type {kind}.",
                               TRACK, "Car types, and the location's car types")

    def rule_load_carriage(self):
        rr = self.rr
        for kind in sorted(rr.loads):
            for load in rr.custom_loads(kind):
                if not any(kind in t.types and t.accepts_load(load.name, kind) for t in rr.trains.values()):
                    yield _finding("load-no-train", "error", f"{kind} {load.name}",
                                   f"No train takes {kind} with {load.name}.", TRAIN_LOADS, "Load option")
                if not any(self._track_takes(track, kind, load.name) for track in rr.tracks.values()):
                    yield _finding("load-no-track", "error", f"{kind} {load.name}",
                                   f"No track can take {kind} with {load.name}.", SCHEDULE,
                                   "A receive line on a spur, or a yard that takes the load")

    def _track_takes(self, track: Track, kind: str, load: str) -> bool:
        if kind not in track.types or kind not in self.rr.locations[track.location_id].types:
            return False
        if not track.accepts_load(load, kind):
            return False
        if not track.is_spur:
            return True
        schedule = self.rr.schedules.get(track.schedule_id)
        return bool(schedule) and any(i.type == kind and i.receive in ("", load) for i in schedule.items)

    def _spur_lines(self):
        for track in self.rr.tracks.values():
            schedule = self.rr.schedules.get(track.schedule_id)
            if track.is_spur and schedule:
                for item in schedule.items:
                    yield track, schedule, item

    def rule_load_balance(self):
        rr = self.rr
        lines = list(self._spur_lines())
        seen: set[tuple[str, str, str]] = set()
        for track, schedule, item in lines:
            if not item.ship or rr.is_default_load(item.ship) or item.destination_id:
                continue
            if item.ship not in {x.name for x in rr.loads.get(item.type, [])}:
                continue
            receivers = [t for t, _, other in lines if t is not track and other.type == item.type
                         and other.receive == item.ship]
            if not receivers:
                yield _finding("load-no-receiver", "error", f"{item.type} {item.ship}",
                               f"{schedule.name} ships {item.ship} and no schedule receives it.", SCHEDULE,
                               "A receive line for this load on another spur")
                continue
            if len({t.id for t in receivers}) == 1:
                yield _finding("single-receiver-load", "info", f"{item.type} {item.ship}",
                               f"Only {receivers[0].name} receives {item.ship}, so cars hold when it is full.",
                               SCHEDULE, "A second receiver, or an alternate track")
            for target in receivers:
                if (track.id, target.id, item.ship) in seen:
                    continue
                seen.add((track.id, target.id, item.ship))
                car = rr.at(self._sample(item.type, item.ship), track.location_id, track.id)
                # A sequential schedule's pointer moves, so ask only whether trains connect.
                if self.g.route_path(car, target, check_target=False) is None:
                    yield _finding("routing-gap", "error", f"{item.type} {item.ship}",
                                   f"No chain of trains takes {item.ship} from {track.name} to {target.name}.",
                                   ROUTE, "A train serving both ends, or a connecting interchange")

    def _sample(self, kind: str, load: str) -> Car:
        for car in self.rr.cars.values():
            if car.type == kind:
                return replace(car, load=load, fd_id="", fd_track_id="", last_route_id="")
        return Car(id="sample", road="", number="0", type=kind, length="40", load=load)

    def rule_schedule_destinations(self):
        rr = self.rr
        used = {t.schedule_id for t in rr.tracks.values()}
        for schedule in rr.schedules.values():
            if schedule.id not in used:
                yield _finding("schedule-unused", "info", schedule.name, "No track uses this schedule.",
                               "Schedules", "Assign it or delete it")
            dests = {i.destination_id for i in schedule.items}
            if schedule.items and len(dests) == 1 and "" not in dests:
                name = rr.locations.get(next(iter(dests)))
                yield _finding("single-destination-schedule", "warning", schedule.name,
                               f"Every line sends cars to {name.name if name else 'one place'}, so all output "
                               "goes there and nowhere else.", SCHEDULE,
                               "Leave Destination blank on a line so the search picks one")

    def rule_track_traps(self):
        rr = self.rr
        for t in rr.tracks.values():
            if t.is_yard and t.raw_pickup_option != ANY:
                yield _finding("yard-pickup-list", "warning", t.name,
                               "Yards ignore the pick up list, so every train can pull here. JMRI drops it at the next save.", TRACK,
                               "Make it an interchange, or use a train's own restrictions")
            if t.is_yard and t.raw_drop_option != ANY:
                yield _finding("yard-drop-list", "warning", t.name,
                               "Yards ignore the set out list, so every train can drop here. JMRI drops it at the next save.", TRACK,
                               "Make it an interchange, or use a train's own restrictions")
            if not (t.is_interchange or t.is_staging) and t.raw_destination_option != ALL:
                yield _finding("destinations-ignored", "warning", t.name,
                               "Track Destinations work only on interchange and staging tracks. JMRI drops them at the next save.", TRACK_DESTS,
                               "Move the filter to an interchange or staging track")
            if not (t.is_interchange or t.is_staging) and t.raw_only_fd:
                yield _finding("only-fd-ignored", "warning", t.name,
                               "Routed works only on interchange and staging tracks. JMRI drops it at the next save.",
                               TRACK, "Remove it")
            if not t.is_staging and t.raw_ship_option != ALL:
                yield _finding("ship-option-ignored", "warning", t.name,
                               "Ship load options work only on staging tracks. JMRI drops them at the next save.", TRACK, "Remove them")
            if not t.is_spur and t.schedule_id:
                yield _finding("schedule-on-non-spur", "warning", t.name,
                               "Only spurs use schedules, so this one does nothing here. JMRI drops it at the next save.", TRACK, "Move it to a spur")
            if not t.is_spur and t.raw_alternate_id:
                yield _finding("alternate-ignored", "warning", t.name,
                               "Only spurs have alternate tracks. JMRI drops this one at the next save.", TRACK, "Remove it")
            target = rr.tracks.get(t.alternate_id)
            if target and target.is_interchange:
                yield _finding("interchange-as-alternate", "warning", target.name,
                               f"{target.name} is the alternate for {t.name}. The router skips every alternate "
                               "track, so it is no longer a connection between trains, and with pick ups set to "
                               "Any the train that overflows a car onto it cannot pull that car back on the same "
                               "route.", TRACK, "Use a yard as the alternate")

    def rule_interchange_exit(self):
        rr = self.rr
        for t in rr.tracks.values():
            if not t.is_interchange or t.destination_option == ALL:
                continue
            if not any(t.accepts_destination(stop.location_id) and stop.location_id != t.location_id
                       for train in rr.trains.values() if t.accepts_pickup(train)
                       for stop in self._stops_after(train, t.location_id)):
                yield _finding("interchange-no-exit", "error", t.name,
                               "The destination filter admits no place any train from here goes, so cars stick.",
                               TRACK_DESTS, "Accept a location a pulling train serves")

    def _stops_after(self, train: Train, location_id: str) -> list[Stop]:
        stops = self.rr.stops(train)
        calls = [i for i, s in enumerate(stops) if s.location_id == location_id]
        return stops[calls[0] + 1:] if calls else []

    def rule_load_types(self):
        rr = self.rr
        emptyish = re.compile(r"\b(e|mt|mty|empty|empties)\b", re.I)
        for kind, loads in rr.loads.items():
            for load in loads:
                if rr.is_default_load(load.name):
                    continue
                if emptyish.search(load.name) and load.load_type != "Empty":
                    yield _finding("custom-empty-flagged-load", "warning", f"{kind} {load.name}",
                                   "Looks like an empty but has Load Type Load, so a blank Ship flips it to the "
                                   "default empty rather than the default load.", "Edit Car Loads", "Load Type")
                elif load.load_type == "Empty" and not emptyish.search(load.name):
                    yield _finding("load-flagged-empty", "warning", f"{kind} {load.name}",
                                   "Has Load Type Empty but does not look like an empty; check blank Ship "
                                   "flips, weight and division rules.", "Edit Car Loads", "Load Type")
                for default in (rr.default_empty, rr.default_load):
                    if load.name.lower() == default.lower():
                        yield _finding("renamed-default-collision", "warning", f"{kind} {load.name}",
                                       f"Differs from the default {default} only by case. Names are case "
                                       "sensitive, so both exist and reports look alike.", "Edit Car Loads",
                                       "Rename the custom load")

    def rule_blank_receive(self):
        rr = self.rr
        for track, schedule, item in self._spur_lines():
            if item.receive:
                continue
            fed = [t.name for t in rr.tracks.values() if t.is_staging and self._feeds(t, track)]
            if fed:
                yield _finding("blank-receive-on-staging-fed-spur", "warning", track.name,
                               f"{schedule.name} line {item.id} has a blank Receive, and {fed[0]} generates "
                               "loads. Generation ignores blank lines.", SCHEDULE, "Set a custom Receive load")

    def _feeds(self, staging: Track, spur: Track) -> bool:
        if staging.load_options & GENERATE_ANY_SPUR:
            return True
        if not staging.load_options & GENERATE:
            return False
        return any(s.location_id == spur.location_id
                   for r in self.rr.routes.values() if r.stops and r.stops[0].location_id == staging.location_id
                   for s in r.stops)

    def rule_generators(self):
        rr = self.rr
        for t in rr.tracks.values():
            if not t.is_staging or not t.generates_loads:
                continue
            for kind in sorted({c.type for c in rr.rolling_stock_on(t)[0]}):
                wanted = [i for spur, _, i in self._spur_lines() if i.type == kind and i.receive
                          and not rr.is_default_load(i.receive) and self._feeds(t, spur)]
                if not wanted:
                    yield _finding("generator-no-target", "info", t.name,
                                   f"Generates loads, but no spur it can reach wants a custom load in a {kind}.",
                                   TRACK, "Custom Receive line, or widen the generate option")

    def rule_staging_ship(self):
        rr = self.rr
        for t in rr.tracks.values():
            empties = [c for c in rr.rolling_stock_on(t)[0] if c.load == rr.default_empty]
            if t.is_staging and empties and not t.ships_load(rr.default_empty, empties[0].type):
                yield _finding("staging-ship-excludes-empty", "warning", t.name,
                               f"Ship options refuse {rr.default_empty}, so any such car a generator cannot "
                               "fill stays and fails the build.", TRACK, "Ship load options")

    def rule_staging_departure(self):
        rr = self.rr
        for train in rr.trains.values():
            stops = rr.stops(train)
            first = rr.locations.get(stops[0].location_id) if stops else None
            if first is None or not first.is_staging:
                continue
            report = {t.name: self.g.staging_problems(train, t) for t in first.tracks}
            if all(report.values()):
                text = "; ".join(f"{k}: {', '.join(v)}" for k, v in report.items())
                yield _finding("staging-departure-blocked", "error", train.name,
                               f"No track at {first.name} can depart, so the build will fail. {text}",
                               TRACK, "Pick ups and the cars on the track")

    def rule_caboose(self):
        rr = self.rr
        for train in rr.trains.values():
            if not train.requires & REQUIRES_CABOOSE or not train.caboose_road:
                continue
            stops = {s.location_id for s in rr.stops(train)}
            if not any(c.caboose and c.road == train.caboose_road and c.location_id in stops
                       for c in rr.cars.values()):
                yield _finding("caboose-road-mismatch", "error", train.name,
                               f"Requires a {train.caboose_road} caboose and none is on its route.",
                               TRAIN, "Caboose road")

    def rule_directions(self):
        rr = self.rr
        for route in rr.routes.values():
            for stop in route.stops:
                location = rr.locations.get(stop.location_id)
                if location and not stop.direction & location.dir and len({s.split for s in route.stops}) > 1:
                    yield _finding("route-direction-mismatch", "error", f"{route.name}, {stop.name}",
                                   f"Stop runs {directions(stop.direction)}, the location serves "
                                   f"{directions(location.dir)}, so no work happens there.",
                                   LOCATION, "Train direction, or the stop's direction")
        served = {s.direction for r in rr.routes.values() for s in r.stops}
        for t in rr.tracks.values():
            location = rr.locations[t.location_id]
            live = {s.direction for r in rr.routes.values() for s in r.stops if s.location_id == location.id}
            if live and not any(d & t.dir for d in live) and served:
                yield _finding("track-direction-unserved", "warning", t.name,
                               f"Serves {directions(t.dir)}, and no stop at {location.name} runs that way.",
                               TRACK, "Train direction")

    def rule_route_stops(self):
        rr = self.rr
        for route in rr.routes.values():
            for stop in route.stops:
                if stop.max_moves <= 0 or not (stop.pickups or stop.drops or stop.local):
                    yield _finding("route-stop-dead", "warning", f"{route.name}, {stop.name}",
                                   "No moves are possible at this stop.", ROUTE, "Moves, Pick ups, Drops")

    def rule_lists(self):
        rr = self.rr
        for t in rr.tracks.values():
            for option, ids, label in ((t.raw_drop_option, t.drop_ids, "set out"),
                                       (t.raw_pickup_option, t.pickup_ids, "pick up")):
                if option == ANY:
                    continue
                known = rr.trains if option in (TRAINS, EXCLUDE_TRAINS) else rr.routes
                for stale in [i for i in ids if i not in known]:
                    yield _finding("list-stale-id", "error", t.name,
                                   f"The {label} list names id {stale}, which no longer exists.", TRACK,
                                   f"{label.capitalize()} list")
                if t.is_yard or option in (EXCLUDE_TRAINS, EXCLUDE_ROUTES):
                    continue
                for train in rr.trains.values():
                    calls = any(s.location_id == t.location_id for s in rr.stops(train))
                    member = train.id in ids if option == TRAINS else train.route_id in ids
                    if calls and not member:
                        yield _finding("train-not-on-list", "info", t.name,
                                       f"{train.name} calls at this location and is not on the {label} list.",
                                       TRACK, f"{label.capitalize()} list")

    def rule_built_boundary(self):
        rr = self.rr
        for train in rr.trains.values():
            bounds = {train.built_start, train.built_end} - {""}
            for car in rr.cars.values():
                if str(built_year(car.built)) in bounds:
                    yield _finding("built-boundary", "warning", str(car),
                                   f"Built {car.built}, exactly {train.name}'s limit. Both ends are "
                                   "exclusive, so the train refuses it.", BUILD_OPTIONS, "Built dates")

    def rule_rwe(self):
        rr = self.rr
        for car in rr.cars.values():
            target = rr.tracks.get(car.rwe_track_id)
            if car.rwe_load and not rr.is_default_load(car.rwe_load) and target and target.is_spur \
                    and not target.schedule_id:
                yield _finding("rwe-to-unscheduled-spur", "warning", str(car),
                               f"Return-when-empty sends custom load {car.rwe_load} to {target.name}, a spur "
                               "with no schedule, which refuses custom loads.", CAR,
                               "Return when empty destination or load")

    def rule_kernels(self):
        rr = self.rr
        for kernel in sorted({c.kernel for c in rr.cars.values() if c.kernel}):
            members = [c for c in rr.cars.values() if c.kernel == kernel]
            places = {(c.location_id, rr.tracks[c.track_id].split if c.track_id in rr.tracks else None)
                      for c in members}
            if len(places) > 1:
                yield _finding("kernel-split", "error", kernel,
                               "Members are on different tracks. Any train that sees them fails to build.",
                               CAR, "Move the members together")
            elif not any(c.lead and not c.out_of_service for c in members):
                yield _finding("kernel-split", "error", kernel,
                               "No lead car in service. Any train that sees the kernel fails to build.",
                               CAR, "Lead car, or Out of Service on the lead")

    def rule_cars(self):
        rr = self.rr
        for car in rr.cars.values():
            track = rr.tracks.get(car.track_id)
            if not car.location_id or not track:
                yield _finding("car-unplaced", "warning", str(car), "Car has no location or no track, so no "
                               "train will see it.", CAR_SET, "Location and track")
            elif car.type not in track.types:
                yield _finding("car-on-refusing-track", "warning", str(car),
                               f"Sits on {track.name}, which does not take type {car.type}.", CAR_SET, "Track")

    def rule_service(self):
        rr = self.rr
        served = {s.location_id for r in rr.routes.values() for s in r.stops}
        for location in rr.locations.values():
            if location.id not in served:
                yield _finding("location-unserved", "warning", location.name, "No route stops here.",
                               ROUTE, "Add a stop")
        names = {split_name(x.name) for x in rr.locations.values()}
        for location in rr.locations.values():
            head = location.name.split("-")[0].strip()
            if "-" in location.name and location.split == location.name and head in names:
                yield _finding("hyphen-no-split", "warning", location.name,
                               f"Only a hyphen followed by a number or ( splits a name, so this is not part "
                               f"of {head}.", LOCATION, f"Name it {head}-(north) or {head}-2")

    def rule_switchers(self):
        rr = self.rr
        spur = rr.option("buildOptions", "allowLocalSpur", rr.option("buildOptions", "allowLocalSiding"))
        off = [n for n, v in (("spur", spur), ("yard", rr.option("buildOptions", "allowLocalYard")),
                              ("interchange", rr.option("buildOptions", "allowLocalInterchange"))) if not v]
        if not off:
            return
        for train in rr.trains.values():
            if self.g._is_switcher(train):
                yield _finding("switcher-local-off", "info", train.name,
                               f"A local switcher, but {', '.join(off)} moves to the same kind of track are off.",
                               SETTINGS, "Switcher Service Options")
