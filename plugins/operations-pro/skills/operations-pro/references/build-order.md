# Build order and gates

The builder tests a car against gates in a fixed order, and the first failure decides what the report says. `ops_why_not` walks the same order and prints these ids. Use this file to read its output and to find the screen that fixes a gate.

## Gates a build settles

E9 (quick service and aggressive pulls), D3, D9, G10 and an AUTO locomotive count at A8 (and A9) cannot be decided from the files alone. With JMRI installed, `ops_why_not` runs four real builds of copies (they differ, because the builder draws at random) and reads the results, so each such gate says where its answer came from in `source`: `port` (the files only), `real JMRI build` (every enabled train built in order) or `real JMRI build of this train alone` (asked when another train took the car first). Pass means a build set the car out at that track with that train, which proves the gate can pass. Fail means every build's report names that gate as the refusal at that location. Builds that split, or that did something else with the car, leave the gate `not_checked` and `build_note` says what they did. Without JMRI, or when the railroad in memory differs from the saved files, these stay `not_checked`.

## The order for one car at one stop

1. Pick up allowed from this track type, then pick up direction.
2. In the first aggressive pass, a car on an alternate track is deferred once the build has completed a move at this stop.
3. Departing staging: generate a load from staging, then staging to staging, then the ship check.
4. Quick service departure timing.
5. Home division search. A car with a division and no final destination gets one here, default load included.
6. Custom load with no destination and no final destination: the scheduled spur search, then staging, then the route search.
7. Final destination present: the router. Otherwise a destination present: that destination is checked. Otherwise the default search along the train's route.

Default E and L cars with no final destination skip step 6 and never reach the router. They only ever see the building train's own route.

## Gates

Setter names are the Java methods, useful when reading a build report or the source. The XML column is the attribute in the named file: CR car roster, LR location roster, RR route roster, TRN train roster, OPS `Operations.xml`.

### A. Train level, before any car

| Id | Test | On failure | Fix on screen |
|---|---|---|---|
| A1 | Build box ticked. Only Build All and automations honour it | Not built | Trains window, Build |
| A2 | On-time mode: departs no earlier than the latest departure among built trains. In every mode a build waits up to 120 s for another train still building, then fails. The departure is the first stop's time if the route sets one, else the train's. Decided from the files; only a train still building is not | Build aborts | Settings, Build on time; train departure times |
| A3 | Route exists, has stops, departure and terminal resolve | Build fails | Edit Train, Route |
| A4 | Every stop's location still exists | Build fails | Edit Route |
| A5 | Skipped stop or staging mid-route: no work there, moves consumed | No work at the stop | Edit Train, skip list |
| A6 | Random move reduction at every worked stop: a value N takes between 0 and moves times N/100 moves. A value that is not a whole number fails the build. `not_checked` only when the draw could take every move at a stop the car needs | Fewer moves, or build fails | Edit Route, Random |
| A7 | Terminal staging: a track whose Set outs admit this train; empty, or with planned pick ups, or in aggressive mode with staging immediately available only if every car and locomotive on it is leaving and it is not quick service; nothing else destined to it unless on-time with quick service. A track naming the train or route skips the rest; otherwise, with the staging restriction option on (the default), the location and track must take every car and locomotive type, road and load the train carries. Aggressive mode with immediate availability and a train returning to its own staging picks no track | Build fails | Staging track Set outs; empty the track or set its planned pick ups to 100 (two trains swapping tracks); the car and locomotive type lists; Settings, staging restriction |
| A8 | Departure staging: a track with pick ups for this train, not empty, length within the route, cars within moves, loco count, direction; every locomotive free and of the train's type, model, road, owner and built range; every car (clones and non-lead kernel cars skipped) free, of the train's type, road, load, owner and built range, and able to reach its destination on this train; caboose and FRED; and, on a pool track set to FIFO or LIFO, its turn: FIFO refuses a track while another pool track's cars came first, LIFO while another's came last. Outside a pool the service order means nothing in staging. `not_checked` when only an AUTO locomotive count, pool dates that overlap, or locomotives on the track that no track takes where they come off are left to decide (the count depends on the cars the build loads, the dates on which car the build lists first, and a refused locomotive sets that departure track aside) | Track rejected; the first track that passes, by moves, is the only one used; no track means build fails. So does a car lost from the track used: A8 also fails for what B20 finds there, even a non-lead kernel car | Staging track Pick ups and the cars on it |
| A9 | Locomotives: the count the train asks for (a number, Auto or Auto HPT), of its model and road, found at the departure and able to be set out at the terminal; otherwise `buildErrorEngines` | Build fails | Edit Train, Locomotives; the engines and their tracks (`engine-no-train`) |

### B. Car list, car removed from this build

| Id | Test | Fix on screen |
|---|---|---|
| B0 | Car's location is a stop on this route; car has no train or this train; not at the last stop unless the route revisits it or local moves are allowed there | Set Car, Location; or Edit Route |
| B1 | Car has a track | Set Car, Track |
| B2 | Location not unknown. On departure staging this fails the build | Set Car, Location Unknown |
| B3 | In service. On departure staging this fails the build | Set Car, Out of Service |
| B4 | Car's destination is on this route | Set Car, Destination |
| B5 | A caboose or FRED car may only be destined for the terminal | Set Car, Destination |
| B6 | Interchange: Pick ups is Any and the car's last route is this route | Track Pick ups: name trains or routes |
| B7 | Interchange or spur Pick ups list admits this train or route. Yards return Any. Staging is tested at A8 only | Track Pick ups list |
| B8 | Interchange Destinations filter admits at least one location on this route, unless the car has a final destination | Track Destinations |
| B9 | Train road list, or caboose road list for a caboose | Edit Train, Roads |
| B10 | Train carries the type | Edit Train, Car types |
| B11 | Train owner list | Build Options, Owners |
| B12 | Built year strictly between the train's start and end years | Build Options, Built dates |
| B13 | Train load list. Skipped for cabooses, passenger cars and cars on departure staging | Edit Train, Loads |
| B14 | FRED car on a train that does not need FRED | Edit Train, Requires |
| B15 | Car's pick up day matches the active train schedule | Train Schedules, active; or the car's pick up day |
| B16 | Wait count is zero. It falls by one for each build by a train that could serve the car, and the car stays | Set Car, Wait |
| B17 | Cabooses and FRED cars move only as the train's own: a caboose when the train requires one at departure, or a leg adds one, at that stop, of the right road, to the end of its leg; a FRED car only when the train requires FRED, at departure. Every other caboose and FRED car is removed, after the manual lines have run: a line that matches a caboose, or a FRED car on a train requiring FRED, leaves it to B19, and when more cars match than the lines take, B17 stays `not_checked`. Several that qualify: the builder takes one, preferring the lead locomotive's road | Edit Train, Requires |
| B18 | Kernel: lead exists and all members are on one track. Non-lead members are removed; a split kernel fails the build | Edit Car, Kernel |
| B19 | Manual build lines take matching cars first (no train, destination or final destination; type, road, load, stop, track, pick up day). A line with a destination sends the car there; with Remove set, matching cars it does not place leave the build. A line set to fail that asks for more cars than can match it fails the build. Written with `set_manual_build` | Edit Train, manual build |
| B20 | Departure staging: only the cars on the track used, the first that passes A8 by moves, and all of them must stay in the list: every car there, non-lead kernel cars included, passes the B tests above but the load, FRED need, pick up day and wait. Unknown location, out of service and a destination off the route fail the build always; anything else only with on-time mode off | Staging track Pick ups |

### C. Pick up, per stop

| Id | Test | Fix on screen |
|---|---|---|
| C1 | Stop not skipped | Edit Train, skip list |
| C2 | Pick ups or local moves on at the stop | Edit Route, Pick ups?, Local moves? |
| C3 | Staging not at the start of the route gets no pick ups | Edit Route, order |
| C4 | Stop direction served by the location | Edit Location, Train direction; or the stop's direction |
| C5 | Moves left at the stop, reduced per pass | Edit Route, Moves |
| C6 | Pick ups on, unless a local move or the car's final destination is here | Edit Route, Pick ups? |
| C7 | Second pass, aggressive mode only: retries cars whose final destination is this stop, with local moves on, after the first pass placed a car there. It adds a try and never refuses a car, so it always passes and says whether the car gets one | Edit Route, Local moves? |
| C8 | B6 and B7 again at the stop, against the car's track at that moment | Track Pick ups list |
| C9 | Stop direction served by the car's track. A local switcher is exempt | Track Train direction |
| C10 | Staging ships this load | Staging track Ship Load Options |
| C11 | Quick service departure: only a car whose clone a built train set out on this track waits. Pulled by the stop that set it out fails; otherwise the pull must come after the clone's set out time | Track Quick service |
| C12 | Home division, for a car with no destination or final destination: a final destination from a fixed order of track types (empties toward the home division; loads home if away, anywhere if home; staging first when the train ends in staging). The first track in that order, fewest moves first, that takes the car and that the router reaches with this train is chosen. None holds the car | Edit Car, Division |

### D. Destination, the default search along the route

| Id | Test | Fix on screen |
|---|---|---|
| D1 | A later stop with set outs on, or the car is a caboose or FRED, or its assigned destination is a local move, which needs no set outs | Edit Route, Set outs? |
| D2 | Destination stop not skipped | Edit Train, skip list |
| D3 | Moves left at the destination stop: none at a skipped or mid-route staging stop, fewer after a random draw, and fewer again for each car the build places first. Passes only when the moves exceed every other car that could be placed before this one | Edit Route, Moves |
| D4 | Not the same split location, unless a local switcher, passenger, caboose or FRED, or a staging return option | Build Options, Allow return to staging |
| D5 | Local moves on at both stops when the final destination is the same location. A car with an assigned destination takes another path: a local move needs local moves on at the destination stop, with or without a final destination, and a passenger car is not exempt | Edit Route, Local moves? |
| D6 | The departure track's Destinations filter admits this location. Interchange and staging only | Track Destinations on the car's current track |
| D7 | Location takes the type | Edit Location, Car types |
| D8 | Stop direction served by the destination location | Edit Location, Train direction |
| D9 | Train length through the leg. The locomotives and a required caboose or FRED car are aboard before any car, so they count from the start. A failure ends the search for this car | Edit Route, Max Length |
| D10 | Through cars allowed, origin to terminal | Build Options, Allow cars to travel from origin to terminal |
| D11 | Send to terminal: cars picked up after the origin go only to the terminal | Build Options, Send all car pick ups to terminal |
| D12 | Terminal staging: only the one track the train terminates on, the first by moves that passes A7. A train returning to its own staging in aggressive mode with immediate availability terminates on its departure track, occupied or not | Empty the staging track |
| D13 | Not the same split track name, unless passenger, caboose or FRED | Track name |
| D14 | Track direction, and an alternate must share a direction with its spur. A local switcher is exempt from both, and the train's terminating staging track from both: only the location's direction (D8) counts there | Track Train direction |
| D15 | Interchange or spur Set outs list admits this train. Yards return Any | Track Set outs list |
| D16 | The car passes table E on this track | See E |
| D17 | A length failure on a spur tries its alternate | Track Alternate |
| D18 | Timing against pulls by other trains: only when the track lacks room counting its reserved length and a car on it belongs to another train | Edit Train, Departure time |
| D19 | Local switcher: spur to spur, yard to yard and interchange to interchange each need their Settings option | Settings, Switcher Service Options |

Track order at a location: alternates removed, tracks with schedules first, then lowest moves. The first accepting track ends the search at that location. Between locations the lowest ratio of moves used to moves allowed wins, squared for the terminal and for a track with a schedule, which favours both. A tie goes to the later stop (TrainBuilderCars:1885, strict less-than), so passing the gates is not the same as being picked. `ops_why_not` without a track prints `track_order` and names the first track that passes; give a track to test one. Counts can be negative, and `set_track_moves` takes any whole number.

### E. Can this car go on this track

Used by every path, including Set Car and the router.

| Id | Test | Fix on screen |
|---|---|---|
| E1 | Track is at the location | Set Car, Track |
| E2 | Location takes the type | Edit Location, Car types |
| E3 | Track takes the type | Track, Car types |
| E4 | Track road list | Track Roads |
| E5 | Car length is a number | Edit Car, Length |
| E6 | This track's Destinations filter admits the car's final destination. No final destination passes | Track Destinations |
| E7 | Track takes only cars with a final destination. Interchange and staging only; caboose and FRED exempt | Track, Routed |
| E8 | Track Load Option, plain load or type and load | Track Loads |
| E9 | Room: used plus reserved plus this car within length, and set outs plus this car within length. Reserved is what is destined here less, in aggressive mode, what is leaving. Then a pool lends length, planned pick ups widen the space, a car longer than the track (or the pool) fails on capacity, and quick service in on-time mode waits on pulls. In aggressive mode a build can open room by pulling cars off the track first | Track Length; planned pick ups; aggressive mode; route Moves covering set outs plus pick ups; or free the track |
| E10 | Schedule. Already destined here passes. Non-spur passes. No schedule refuses a custom load. Sequential mode tests the current line only; match mode tests every line | Track Schedule |

### F. Schedule line

A blank road or receive matches anything. Setters are on the schedule item; XML is in the location roster under the schedule's `item`.

| Id | Test | Fix on screen |
|---|---|---|
| F1 | Set out day matches the active train schedule, unless the car already holds this line | Edit Schedule, Delivery day |
| F2 | Car type | Edit Schedule, Type |
| F3 | Road | Edit Schedule, Road |
| F4 | Receive load | Edit Schedule, Receive |
| F5 | Random draw passes. Skipped if the car's final destination track is this track or the car holds this line | Edit Schedule, Random |

### G. Router, for each hop

| Id | Test |
|---|---|
| G1 | The train can carry the car: type, load, built, owner, road. No staging or caboose exemption here |
| G2 | Car's location and destination are on the route; a staging destination must be the last stop |
| G3 | A stop at the car's location with moves, not skipped, pick ups or local moves on |
| G4 | Location and track direction; a local switcher is exempt |
| G5 | Track Pick ups list admits the train |
| G6 | Destination stop with set outs or local moves, moves left, not skipped; with the EXTREME option the car's track must accept this hop |
| G7 | Destination location direction |
| G8 | Destination track direction and Set outs list, or some track there accepts |
| G9 | Send to terminal, local rule, return to staging, local move, through car, and for the train being built, moves left at the destination stop |
| G10 | Train length before the destination, tested only for the train being built, as D9 |
| G11 | Only active trains, when that option is on |
| G12 | Router's own rules: interchanges first, then yards if enabled, then staging if enabled and the track has no load-changing option. Alternates never appear. An interchange pulled and set out by the same route with Pick ups Any is excluded |

The router serves any car with a final destination, up to seven trains. It needs room only at the first hop, and tests length at the first hop only.

## Custom load search, step 6

a. **Scheduled spurs, everywhere, by move count.** All spurs at all locations, lowest moves first, alternates dropped. Skips the car's own track, spurs with no schedule, locations already found unreachable, and locations the departure track's Destinations filter excludes. Each candidate is tested for basic moves, then table E including the schedule, then room, then the router. The first success ends the search.
b. **Hold.** If a spur was routable but full and has Hold set, or the router says another train could do it, and the car is not in staging and the train has no staging option for custom loads, the car is held with no staging attempt.
c. **Staging, at random.** Staging tracks drawn without replacement. Skips the same location, unreachable locations, at the terminus every track but the assigned one, the Destinations filter, and tracks that refuse the car. The final destination is set to the location only. A routing failure drops the whole location.
d. **Any accepting track on this train's route**, like a default car. Not unrestricted: spurs need a matching schedule line, so in practice yards, interchanges and staging. A car departing staging skips the hold at b and always reaches d.

## Departure time

Departure time gates a build only in on-time build order (A2), the timing check against other trains' pulls (D18) and quick service (C11). Otherwise it feeds expected times on paperwork.

Checked against JMRI 5.16 source, tag v5.16, or tested in JMRI 5.16, except where this file says a point was not checked.
