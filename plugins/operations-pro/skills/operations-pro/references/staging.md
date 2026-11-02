# Staging

## The departure rule

- Every car on the departure staging track must get a destination, or the build fails, in every build mode. On-time build mode only drops the check that all the cars on the track are in the car list.
- The track is chosen by lowest move count among tracks this train may use, or the user is prompted when Prompt for Departure is on. `ops_train` builds with prompts off, so JMRI chooses.
- A track is rejected (gate A8) if it is empty, its cars do not fit the route length or moves, the loco count or direction is wrong, or any car fails the train's type, road, load, owner, built, destination, caboose, FRED or pool checks. A car with location unknown or out of service on the departure track fails the build.
- Departure track selection tests every car's load against the train, so the car list skips that test for staging cars. A default E is exempt from it only when a generate option is on; with none on, a train that does not carry E rejects the track.
- In aggressive mode the departure staging adjustment runs on the first pass only. Normal mode from staging is on by default.
- Staging can share a location only with staging in the GUI. The model allows mixed tracks; keep to the GUI rule.
- Terminating a train into staging fills that track, so the next build of that train can fail. That is correct behaviour.

## A default empty can leave staging

With every generate option off, a default E goes straight to the ship check, then the default search along the route, and takes any accepting track. It is blocked only by:

| Block | Where |
|---|---|
| Ship Load Options exclude E and no generator replaced it | Staging track, Ship Load Options |
| The train does not carry E and no generate option is on | Edit Train, Loads |
| No reachable track on the route accepts E: load option, schedule with no line, length, direction | Tracks ahead |
| Through cars off and the only target is the terminal | Build Options |
| The staging track's Destinations filter | Staging track, Track Destinations |

Generators replace only a default E. A default L or a custom load is never given a generated load. When a generator fails, the car stays E and still tries the default search.

## Generating custom loads

Three options on a departure staging track:

| Option | What it does |
|---|---|
| Generate custom loads for spurs serviced by this train | Loads for scheduled spurs at locations on this route |
| Generate custom loads for any spur | Loads for scheduled spurs anywhere, which another train may deliver |
| Generate custom loads for any staging track | Loads for a staging-to-staging move |

For a car to get a load:

- The car must carry the default E, have no destination and no final destination.
- The car type must have at least one custom load.
- Spurs are tried in lowest move count order across all locations, alternates excluded. Interchanges are never used by the generator.
- The schedule line must match type and road, name a custom receive load (blank, E and L are rejected), and the train must carry that load and staging must ship it. The set out day must match and the random draw must pass.
- Then the destination test ignoring length, the home division rule, room with the reservation factor, and the router.
- Once a location is found unreachable through the filter or staging paths, it leaves the list. A router failure on one spur does not drop the location in the generator.

Room at the spur: cars present plus cars en route, scaled by the track's "% from staging" reservation factor. Raising it to 200 or 300 lets more cars head for one spur. The alternate's length is **not** counted for staging cars; that only applies elsewhere. Pool minimum length counts, so raising it makes room.

## Home divisions and departure staging

A car with a home division and no final destination gets one before any load test (`build-order.md`, step 5). A divisional empty can leave staging only if some reachable location in its division takes it. JMRI applies the division rule to a generated load as well, so the older advice to "load the empties in staging" does not rescue the build: a generated load is refused at a spur in another division ("wrong division"), and the build fails with the car departing staging with a load that the track restricts. What works, tested in real JMRI:

| Fix | Effect |
|---|---|
| Put a location the trains reach into the car's division (`set_location_division`) | The empties get a home destination there |
| Clear the cars' division (`set_car_division` with none) | Behaves as before divisions |

The audit reports `staging-division-unreachable`. The build summary may blame the router (G12); the car's own story shows the division lines (C12).

## Ship Load Options

- Exist on staging only. The panel appears once a generate option is on.
- They are the gate after generation. Excluding E means any E that failed to get a load fails the build. That is the price of a strict all-custom setup.
- The audit reports `staging-ship-excludes-empty` and `generator-no-target`.

The `setup_custom_staging` action sets a track for all-custom loads: convert arriving custom loads and default loads to empty, generate for any spur and any staging, and ship only the custom loads. Arriving default L cars must be converted too, because the generators replace only a default E, and an L that stays L would be refused at departure. With `ship_empties` the track also ships E, so an empty that finds no load leaves as an empty instead of failing the build.

## Arrivals

What happens to the load of a car that arrives in staging depends on the track's load options. The options are `swap_default` (exchange default loads), `empty_custom` (empty cars with custom loads) and `empty_default`, set with `update_track` `load_options`.

| Option | Car arriving | Result |
|---|---|---|
| `swap_default` | Default E | Becomes loaded (seen in JMRI: an empty set out in staging turned L) |
| `swap_default` | Default L | Becomes empty (Car.java:935-955) |
| `empty_custom` | A custom load | Branches in the table below |
| `empty_default` | Default L | Becomes empty (Car.java:935-955) |

`empty_custom` converts a custom load in one of three ways (Car.java:941-955), tested in this order:

| The car's load | Result |
|---|---|
| Load type Empty, and the car has a return-when-loaded (RWL) load | The RWL load. If the car already holds that load nothing changes, so the load is kept |
| Equals the car's return-when-empty (RWE) load name | Default E. Setting RWE to the load you want to keep therefore strips it |
| Anything else | The RWE load, or default E |

- To keep a permanent load through staging, make the load's type Empty (`set_load_type`) and give the car the same load as its RWL load (`update_car` `return_when_loaded` with `load`; a destination is not needed). The audit then warns `load-flagged-empty`, because load type also drives the blank-Ship flip and the division rules. Or keep such cars off the option: a separate staging track without it is a modelling choice.
- Downstream tracks must accept E after a conversion, and the staging track must accept the arriving loads.
- The terminal track must be empty, or have planned pick ups (see below), and have set outs that admit this train and no drops pending (gate A7). The builder uses only the assigned track.
- With the staging restriction on (the default), the terminal location and track must take every car and locomotive type, road and load the train carries, or A7 fails. `add_train` gives a train every car and locomotive type, so list the same types on the staging location and track (`add_location` with no `types` takes them all). The audit reports `terminal-staging-refuses-train`; the other way out is Settings, staging restriction off.
- Return to staging at the same location needs the train or Settings option.

### Two full trains swapping staging tracks

Each train fills its staging track and terminates on the other's, so both fail A7: the terminal track is full. Normal mode fails, and so does aggressive with staging immediately available, because each track counts as leaving only once the other train is built (a deadlock). What works in JMRI 5.16 is planned pick ups on both staging tracks: `update_track` `ignore_used_percent` 100. Both then build, in normal and in aggressive mode. The same setting widens a full industry for a swap; see `moves-and-balance.md`.

## Staging as a destination

- For a custom-load car, staging is tried after the scheduled spurs, chosen at random among tracks, so bigger staging locations take more cars. The final destination is the location only.
- The staging track's Destinations filter stops staging-to-staging moves when it excludes the other staging.
- The router uses staging as a hop only when routing via staging is on, default off, and the track has no load-changing option.
- A staging track as a schedule destination is not offered.

## Alternatives to staging

Spurs in a fiddle yard do not carry the all-cars-must-leave rule. A storage spur with a mirror schedule, or an Out of Service flag to park part of the fleet, are modelling choices the builder supports.

Checked against JMRI 5.16 source, tag v5.16, or tested in JMRI 5.16, except where this file says a point was not checked.
