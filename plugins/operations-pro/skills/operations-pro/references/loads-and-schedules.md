# Loads and schedules

## Default loads

- E and L are one global pair of names for every car type. They cannot be deleted. Renaming one keeps it the default, and the Load Type box stays greyed.
- Load Type, Load or Empty, is a label on a load name, stored per car type and name. The default for a new custom name is Load. Changing it for one car type changes every car of that type.
- Routing tests the load **name** against the two defaults, never the load type. A custom load called MTY with type Empty is a custom load for routing, and it does not make a car able to leave staging.
- Load type matters only for division rules, the blank Ship flip, weight, and report text.
- Load names are case sensitive, so `Grain` and `grain` can both exist. A default renamed to look like a custom name may show both in reports. The audit flags that as `renamed-default-collision`.

## What a default-load car does

A car with E or L and no final destination is not routed. It searches only the building train's own route and takes the first accepting track. That search is biased: tracks with schedules sort first at each location, and a scheduled track or the terminal gets a squared ratio bonus between locations. So a schedule listing E or L does not pull a car there, but it does win ties.

A schedule still gates default cars. A spur with a schedule and no line matching the car refuses it.

Exception: a car with a home division and no final destination gets one before the load test, and the router runs for it.

## What a custom-load car does

A car with a custom load, no destination and no final destination runs the custom search, in this order: scheduled spurs everywhere by move count, then a hold decision, then staging at random, then any accepting track on the building train's route. See `build-order.md` for the detail. The last step means a custom-load car can land on a yard or interchange with no final destination, which is where it sticks if nothing can pull it. That is not a bug. Setting Routed on every interchange stops it, if every car is routed; with default cars mixed in, leave Routed off.

## Schedules act three times

| Stage | When | What |
|---|---|---|
| Gate | Any destination test | A spur with a schedule refuses a car with no matching line; a spur without one refuses custom loads |
| Line assignment | At build, when the destination is set | The car gets the schedule item id, the line counts a hit, the sequential pointer advances |
| Load effect | On delivery | Wait and pick up day first, then the new load, the ship destination, and the id is cleared |

Further cases:

- Load generation from staging applies the receive load at build. The car leaves with the load the schedule asked for.
- Quick service tracks apply both at build.
- Set Car applies a schedule only when the track changes and the user answers yes (CarSetFrame:600-630). Nothing else revisits parked cars, so adding a schedule does not touch cars already on the spur. `ops_deliver_car` and `ops_live_car` do what Set Car does, so `ops_deliver_car` refuses a car that is already on that track. To load a car parked before the schedule existed, set its load with `update_car` (`ops_session`), or deliver it to another track and back. The audit reports `schedule-not-applied` for a parked car holding the load a line receives.
- Wait counts builds, not visits: it falls by one each time a train that could serve the car builds, and the load changes when it reaches zero. A car departing staging ignores wait.
- Disable Load Change skips the ship load, the ship destination and the id clear. Wait and pick up day still apply.
- Moving a car with a JSON location change does not apply a schedule.

## Worked example: convert a default track to custom loads

There is no single action. It is two actions in one `ops_plan`: `add_schedule` first, then `update_track` naming the new schedule. One plan keeps them together, so the files never hold a track pointing at a schedule that is not there. The example is checked by a test that plans, applies and has real JMRI load and save the result.

```json
[
  {"action": "add_schedule", "name": "Team Track Loads",
   "lines": [{"type": "Boxcar", "receive": "Feed", "ship": "Mty", "count": 2}]},
  {"action": "update_track", "track": "Brackwater Team Track", "location": "Brackwater",
   "schedule": "Team Track Loads", "schedule_mode": "sequential"}
]
```

- `add_schedule` takes `name`, `lines` and an optional `comment`. A line takes `type` (required) and any of `road`, `receive`, `ship`, `random`, `wait`, `count`, `setout_day`, `pickup_day`, `destination`, `track`, `comment`.
- `update_track` takes `track`, `location` (to tell same-named tracks apart), `schedule` and `schedule_mode` (`sequential` or `match`). Other fields leave the track alone.
- The track must be a spur. Name the car types and loads the lines use before the plan, with `add_car_type` and `add_load` earlier in the same plan if they do not exist.
- `delete_load` removes a custom load only once no car, schedule line, track or train load list or manual build line names it. `rename_load` onto a name the type already has is refused unless `merge` is set; it then merges the two, as JMRI's Replace does.
- Plan first and read the findings. Converting a track can add routing findings such as "No chain of trains takes Feed from ... to ...": the new receive or ship load has no train path. Fix the routes, or choose loads the trains already connect, before `ops_apply`; a plan with new errors is blocked.
- Cars already on the track keep their loads. A schedule does not revisit parked cars.

## Match and sequential

- Match mode tests every line and advances the pointer on each test, so lines rotate per test, not per delivered car.
- Sequential mode tests only the current line, and advances after `count` hits.
- One line behaves the same in both modes.
- Random is a percentage per line. Aggressive mode scales it by the number of passes, so 25 with two passes is about 12.5 per try. Random is skipped when the car already holds this line or its final destination track is this track.
- Changing a track's schedule from the schedule edit window resets move counts at every location. Setting a schedule by script does not.
- Two spurs can share one schedule. A new schedule with an existing name returns the existing one, hits included.
- A schedule only works on a spur. One set on another track type is dropped on save. The audit reports `schedule-on-non-spur`.

## Receive, ship and destination

- Blank receive matches any load. It is fine for cars arriving from other tracks, but load generation from staging rejects blank, E and L, so a spur fed only from staging needs a custom receive. The audit reports `blank-receive-on-staging-fed-spur`.
- Blank ship flips by load type: an empty becomes the car's RWL load, or default L; a load becomes the RWE load, or default E. A custom empty flagged Load therefore flips to E. The audit reports `custom-empty-flagged-load` and `load-flagged-empty`.
- The same flip happens when a car is delivered to a spur that has **no** schedule: a default E arriving there turns L, and an L turns E. So making a track a spur is enough to turn empties into loads; no schedule is needed. A rest-of-the-world track that must send cars back loaded can be a spur with a one-line schedule (receive E, ship L), a modelling choice that works in JMRI. An interchange cannot have a schedule, and no action changes a track's type: empty the track, `delete_track`, then `add_track` the new type.
- `load_options` `disable_load_change` on a spur stops the flip (and the ship load), so a loaded car delivered to a RIP-style spur with no schedule keeps its load.
- A ship destination with a blank track sets the final destination to the location only. The builder then tries that location's tracks, scheduled first, the rest by moves, all types mixed, so a yard can win over an unscheduled spur.
- Staging cannot be chosen as a schedule destination track; the schedule window removes staging tracks.
- A schedule needs at least one line with a car type.
- Every load a schedule ships should be received somewhere, or the car has only staging and the route fallback. The audit reports `load-no-receiver`, `single-receiver-load` and `routing-gap`.

## RWE and RWL

Return when empty and return when loaded hold a load, a location and a track, each optional. On delivery the order is: the ship load is set; RWE or RWL fires if the new load equals its load name and the car has no final destination; then a schedule line's destination overwrites the final destination. So a schedule destination beats RWE, and a ship load beats the RWE load.

- A final destination already on the car stops load generation from staging.
- In staging, the "Empty cars with custom loads" option converts arrivals, in three branches that `staging.md` (Arrivals) sets out. Giving the car a RWE load equal to its current load strips it to E; keeping a load needs load type Empty plus the same load as RWL.
- `update_car` `return_when_empty` and `return_when_loaded` take a `destination`, a `track`, a `load`, or any of them; a load alone is kept, as JMRI allows.
- RWE sending a custom empty to a spur with no schedule converts the car to a default load on arrival and drops it out of routing. The audit reports `rwe-to-unscheduled-spur`.
- A RWE location with no track avoids the reserved-in-route accounting.

## Divisions

A car with a home division behaves differently by load type: an empty cannot leave its division without a load first, and a car with a custom empty counts as empty. A car with no division is unchanged, so divisions can be left unused. The home division search runs before the load test and uses the router.

What departure staging needs for divisional empties is a reachable location **in the car's division** that takes them. Giving staging a custom load for them does not fix a failing build: JMRI applies the division rule to generated loads too and refuses a spur in another division. See `staging.md`, Home divisions and departure staging.

`set_load_type` changes a custom load's Load or Empty type; `routing.md` has the division actions.

## Mirror schedules and storage spurs

A storage spur with a schedule that receives what the industry spurs ship, and ships what they receive, gives every custom load a home. The `mirror_schedule` action builds that schedule. Set a large move count on such a spur so the builder tries it last. Whether this suits a layout is a modelling choice.

Checked against JMRI 5.16 source, tag v5.16.
