# Routing, interchanges and filters

## The router

- Runs for any car with a final destination, whatever its load. It never runs for a default E or L without one, except through a home division.
- Tries up to seven trains, in this order: one train; two through an interchange; two through a yard if "routing via yards" is on, default off; three to seven through interchanges and yards; two through staging if "routing via staging" is on, default off; three to seven including staging. Only staging tracks with no load-changing option are used.
- Each list of hop tracks covers every location, fewest moves first. Ties fall in JMRI's internal location order, a hash of the location id rather than the name, then track name. Trains are tried in name order and the first that can carry the car wins. Setting a destination bumps that track's moves, so later lists in the same build can change order. Moves are counted as JMRI holds them after loading: the stored count plus one for every car or engine already destined to the track, since JMRI stores the count without those. A schedule moves a track to the front of a location's list only on a spur; a schedule id on any other track type is ignored.
- Every hop must take the car as a set out would, length aside: type, road, load, and an interchange or staging Destinations filter that admits the car's **final** destination.
- The final track's schedule is not asked while routing, only when the last train is given that track as its destination. The final track may be full.
- Room is tested only at the first hop. In a two-train route a full first hop is skipped and the next candidate tried. Room is the track's own test: in aggressive mode cars already given a destination off the track give back their length, a pool track takes room only if another pool track can lend it, an ignore-used percentage helps only if it frees enough, and quick service counts only while a train builds in on-time mode.
- A built train keeps the staging track it was built into until it is reset. When that train carries the first hop of a route, or is the train named, the router sends a car only to that staging track, not to another staging track.
- Train length and route moves count only for the train being built, and only on its own legs. When that train could carry the car but not now, the router answers "Train (name)" and the car waits for it, unless it is on a staging track or the train services all cars with a final destination.
- One train to a full final track, or one whose schedule refuses the car when the train is given it: the car goes to that track's alternate, then, if the track was full and "forward to yard" is on (default on), to a yard at the destination. Otherwise it gets no destination this build.
- A route of three or more trains whose first hop cannot be set now: the car goes to the alternate of the spur it is on, then to a yard at its own location if "forward to yard" is on and it is not already on a yard. Either needs the train being built to take it there. Otherwise the car waits.
- If any single train can deliver the car directly, no two-train path is used. The train build option to service all cars with a final destination overrides that.
- "Could not find a first or last hop" in the report means a gap at a hop or no room there. The audit's `routing-gap` finding checks for a chain of trains between every shipping spur and every receiver.
- The router writes its lines to the report only at the Detailed and Very Detailed router levels.

## Alternates

- Only a spur can have an alternate. The alternate is used when the spur is full and shares a direction with it. For a routed car it is also used when the spur's schedule refuses the car as the last train is given the spur.
- An alternate never appears in any move-ordered track list, so it is never a direct destination and never a routing hop. "Can't send directly to alternate" is the report line.
- An interchange set as an alternate loses its exchange role and traps cars through the same-route rule. The audit reports `interchange-as-alternate` and `alternate-ignored`.
- For overflow on a yard or interchange use a pool, or move count bias.

## Interchanges

- A car set out on an interchange whose Pick ups is Any can only be pulled by a train on a **different route**. The test is by route id, so two trains on one route are both barred. Naming trains or routes in Pick ups lifts it.
- Routed, the "only cars with a final destination" option, exists on interchanges and staging. It refuses any car with no final destination, except cabooses and FRED cars. With it on, the custom search fallback cannot leave a car there.
- Pick ups and Set outs lists hold train or route ids and are read on interchanges and spurs. Yards return Any whatever is stored, and the audit reports `yard-pickup-list` and `yard-drop-list`. Changing the option from train to route clears the list.
- Interchanges can be descriptive rather than physical. That is a modelling choice.
- The `setup_interchange` action sets trains in, trains out, Routed and destinations in one step. `pulled_by` is the pick up list; `set_out_by` the set out list. Words in option fields are spelled `Any`, `trains`, `routes`, `excludeTrains`, `excludeRoutes`.
- An interchange cannot have a schedule; a car's route through a rest-of-the-world interchange that must come back loaded needs a spur instead (`loads-and-schedules.md`).

### A/D track for a yard switcher

Goal: arriving road trains leave every car on one arrival track, and a yard switcher then sorts them onto class tracks. Yards ignore pick up and set out lists, so the class tracks and the A/D track must be **interchanges**. No action changes a track's type, and a track with cars on it cannot be deleted, so:

1. Empty the tracks being converted (`place_car` the cars elsewhere).
2. `delete_track` them, then `add_track` each as an interchange.
3. `setup_interchange`: the A/D track is set out by the road trains and pulled by the switcher; each class track is set out by the switcher only.
4. `set_option` group `buildOptions`, name `allowLocalInterchange`, true: interchange to interchange moves by a local switcher are off by default (D19; `allowLocalSpur` and `allowLocalYard` are the siblings in the same group).

Tested in real JMRI: the road train set out all four cars on the A/D track, and after it terminated the switcher moved them to the class tracks, two each. Audit `switcher-local-off` points at this setting.

### Routed cars through yards

If the router cannot route a car and falls back to a random staging track, check `set_option` group `router`, name `carRoutingViaYards` (default off): it lets the router hop through a yard (two trains through a yard) when no interchange chain exists.

## The Destinations filter

- Holds **location** ids, not tracks, and exists on interchange and staging only. A filter on a yard or spur is ignored on read. The audit reports `destinations-ignored`.
- Exclude only inverts the checkboxes; the stored list is always the accepted locations. Writes keep that.
- As a gate on the car's track (D6, B8): the next location the train would use must be admitted, or the car has no exit. The audit reports `interchange-no-exit`.
- As a gate on the destination track (E6): the car's **final** destination must be admitted. A car with no final destination passes.
- An interim interchange or staging track must admit the car's final destination, so a filter there closes that hop for those cars. Yards have no filter, so nothing in the yard stops a car passing through it. Either exclude every final destination reached through that yard on the tracks that feed it, or turn on the EXTREME option in car routing, which tests each hop against the car's track.
- A filter that leaves out the location a schedule names makes the builder skip that spur and fall to the route search, so cars scatter. Accept all is the usual fix.
- The filter holds locations only, so it cannot say "this type goes there". An interchange can hold a type that none of its allowed destinations takes (JMRI's Check Destinations warns of it): such a car gets no destination, while cars of other types leave. The fix is to admit a destination that takes the type (`setup_interchange` `destinations`), or take the type off the interchange. The audit's `interchange-no-exit` warning checks type and load against the destinations; `ops_why_not` D6 shows the location tested.

## Directions

- Direction is a bitmask on the location, the track and each route stop. The stop's direction must be served by the location (C4, D8) and by the track (C9, D14, G4). A local switcher is exempt.
- Enabling every direction on a location makes direction a filter tool rather than geography.
- The audit reports `route-direction-mismatch` for a stop the location cannot serve, and `track-direction-unserved` for a track no stop serves.

## Through cars, terminal and local moves

- "Allow cars to travel from origin to terminal" off blocks a car from the first stop to the last. Passenger cars, cabooses and FRED are exempt.
- "Send all car pick ups to terminal" sends cars picked up after the origin only to the terminal.
- A local switcher is a train whose stops all share one split name. Only a switcher, a passenger car, a caboose or a FRED car can be set out at the same split location; same-track moves are refused except for those cars.
- Spur to spur, yard to yard and interchange to interchange moves by a switcher each need their Settings option. Spur to spur is off by default, and so are the other two. The audit reports `switcher-local-off`.
- A car moves once per train, except through quick service tracks, which pull clones.

## Hyphen names

A location name splits only when the text after a hyphen is a whole number or starts with `(`. So `Town-(yard)` and `Town-2` print as Town, while `Town-yard` stays two words and does not split. The split name is what paperwork shows and what the same-location rules compare. Location objects stay separate, so different trains can work them. The audit reports `hyphen-no-split`.

## Divisions

Locations and cars carry a division. A car with a home division and no final destination gets one before the load test, by load type. An empty goes home: a home yard first, then home staging, then a home spur. A load on a track outside its division goes to a home spur or home staging. A load already at home goes to any spur or staging. A custom empty counts as empty. Cars with no division are unaffected.

Write actions: `add_division`, `update_division` (rename or comment; locations and cars hold the id), `delete_division` (its locations, cars and engines are left with none), `set_location_division`, `set_car_division` (a kernel follows its car, as Set Car does), and `set_load_type`, which decides whether a custom load is handled as empty or loaded. A default load's type is fixed. Only cars use a home division in the builder; an engine's division is stored but not used.

## Checking a setup

The Track Destinations tool and the check destinations tool warn about types a destination does not service. The build report is the judge. `ops_why_not` with a train named walks the router gates for a final destination, and its `router` field gives the router's answer for that train as JMRI 5.16 computes it from the files: the status, the trains in the route, and for a custom load the spur search with its hold or staging outcome.

Checked against JMRI 5.16 source, tag v5.16, or tested in JMRI 5.16, except where this file says a point was not checked.
