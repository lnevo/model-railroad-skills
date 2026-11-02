# Operations Pro showcase: guide

A tour of an invented railroad, the Juniper Falls & Northern, built to show what JMRI Operations Pro can do. Every case below is a setup that people on the user list found hard, shown done correctly, plus every kind of routing the plugin's skill uses. What each case says is what real headless JMRI 5.16 did here, asserted in `tests/test_showcase.py`; `RESULTS.md` has the per-case record.

"Every train builds" means the shipped state: in the first session after you open the folder all 18 trains build. Staging trains use up their departure track, so in later sessions some have nothing to run: `CUSTOM`, `MIXED` and `MODE` fail to build from session 2 on (their staging track is empty), and `HOP OUT` joins them in session 3. That is by design; the test `test_every_train_builds_in_session_one_and_staging_trains_run_out_after` records it.

## How to use it

1. Copy `examples/showcase/operations/` into a scratch JMRI profile, or open it with the plugin's reading tools (`ops_list`, `ops_audit`, `ops_why_not`, `ops_explain_build`). Nothing in it needs changing to work. The active day is Tuesday, and `buildstatus/` holds a build report for every train from a clean build.
2. Pick a case. `U` is a use-case, `R` is a routing variation.
3. Read **The difficulty**, find the objects under **Find it**, then use the tool under **Confirm it**. Name the train in `ops_why_not`: with none named the tool picks one itself, and its first failure may differ.
4. **Try this** names one plugin action to run on a scratch copy that breaks the pattern, with what the tool then said. The shipped folder is never in that state. The action names and fields in this guide are shorthand, so check `ops_actions` before copying one (for example `update_track` takes `pickup` and a numeric `directions` bitmask). `ops_dry_run` keeps no state and does not refresh `buildstatus/`, so where a Try this quotes `ops_explain_build`, run a real build on the copy first; after a dry run it reads the old report.

Objects a case uses carry its code in their comment, for example `[U07]`: cars, locations, trains, routes, automations and most schedules. Ten schedules have no code: Linden Steel, Linden Pier, Linden Glazier, Linden Pipe Yard, Linden Westside, Carrow Salt Works, Carrow Glass Works, Sawyer Pasta Plant, Brae Depot and Dunmere Depot. Tracks here carry no case code, so a track is pointed at by its name (all track names are unique). Cars of different cases are kept apart by their own roads and by train lists on the spurs, so one car is never served by two cases in the first session. After session 1 some cars shuttle on (default-E JFN boxcars of the Brae and Dunmere cases are drawn to the Fiddle yard, Carrow Box Factory and Carrow Glass Works, and empty JFN covered hoppers to Carrow Salt Works); each case says which session it is asserted in.

## Intended audit findings

`ops_audit` on the shipped folder returns three findings, none an error. They are kept on purpose:

| Finding | Why it stays |
|---|---|
| `staging-ship-excludes-empty` warning on `West Custom` | U06: an all-custom staging track refuses empties by design |
| `train-not-on-list` info (two) on `Ferris Transfer` | R07: the pick up list names one route on purpose, so the other two routes that call at Ferris Junction are not on it |

Every other train list in the railroad uses an `excludeTrains` list (a list of trains that may not use the track), which does not trip `train-not-on-list`.

---

## Part 1: use-cases

### U01. Industries that receive empties

**The difficulty:** cars held with "can't send to spur due to load (E)".
**How it's done here:** the spur's load options let an empty in, and the schedule's first line receives E. The mill loads the hopper with Feed for the dairy.
**Find it:** `Brae Feed Mill`, `Dunmere Dairy`, `Feed Mill Loading`, `Dairy Receiving`, `LOCAL-B`, `JFN 101`, `JFN 102`
**Confirm it:** `ops_why_not` JFN 101 to Brae Feed Mill with `LOCAL-B` named: can_move true, E8 pass and E10 pass. In every chain session 1 leaves JFN 101 on Brae Feed Mill with load Feed and final destination Dunmere Dairy, and JFN 102 at Dunmere Dairy as an empty; session 2 puts JFN 101 at the dairy.
**Try this:** `update_track` Brae Feed Mill loads to Include `Feed` (empties no longer accepted). `ops_why_not` then fails D16, caused by E8 "Brae Feed Mill Include: Covered Hopper E".

### U02. A schedule applied to a car already on a spur

**The difficulty:** adding a schedule later seemed to do nothing.
**How it's done here:** `ops_deliver_car` set JFN 201 on Brae Cannery as Set Car with "apply schedule" does, so it carries the line's load and final destination.
**Find it:** `Brae Cannery`, `Cannery`, `Grocery Dock`, `Grocery Receiving`, `JFN 201`
**Confirm it:** `ops_list` cars: JFN 201 has load Canned and final destination Grocery Dock. After session 1 it is at Grocery Dock as an empty, and the `LOCAL-B` manifest says "Set out JFN 201 Boxcar 40' Canned to Grocery Dock".
**Try this:** place a boxcar on Brae Cannery with `place_car` and do not deliver it. `ops_audit` then reports `schedule-not-applied` for that car.

### U03. Custom loads give cars a purpose

**The difficulty:** default E and L cars wander.
**How it's done here:** JFN 301 and JFN 302 are delivered to Brae Lumber with load Lumber and a final destination, so they go to Lumber Dealer. `WNDR 1` and `WNDR 2` are default cars with no schedule; Dunmere Yard takes them, and they only ever sit on a yard.
**Find it:** `Brae Lumber`, `Lumber Dealer`, `Lumber Shipping`, `Lumber Receiving`, `Dunmere Yard`, `JFN 301`, `JFN 302`, `WNDR 1`, `WNDR 2`
**Confirm it:** after session 1 both Lumber cars are at Lumber Dealer as empties. `ops_why_not` WNDR 1 to Brae Lumber with `LOCAL-B` named fails D7 first, then E2, E3, E4, E10 and F2 (type, road and load).
**Try this:** remove the schedule from Lumber Dealer. The plan only reports `schedule-unused` (info); in a session the Lumber cars still reach the plain spur, because it is their final destination track.

### U04. A local move inside one location

**The difficulty:** a car cannot move within a location.
**How it's done here:** the one-stop route `SAWYER SWITCHER` runs inside Sawyer. JFN 401 (load Semolina) moves from Sawyer Yard to the spur that receives Semolina.
**Find it:** `Sawyer`, `Sawyer Yard`, `Sawyer Pasta Plant`, `Sawyer Pasta Plant Schedule`, `SAWYER SWITCHER`, `JFN 401`
**Confirm it:** after session 1 JFN 401 is on Sawyer Pasta Plant; `ops_why_not` JFN 401 to Sawyer Pasta Plant with `SAWYER SWITCHER`: can_move true, no failing gate.
**Try this:** `update_stop` on stop 1 with pick ups off and local moves off: `ops_why_not` fails C2 and the build moves no cars. Local moves off alone does not stop it: the router refuses the local move, the car falls to the train's own route, and `ops_why_not` says so at G3 with can_move true.

### U05. Move counts and priority

**The difficulty:** priority did not make the car move.
**How it's done here:** Hollis Track 1 has priority High but 100 moves; Hollis Track 2 has none. The lowest move count wins.
**Find it:** `Hollis Mill`, `Hollis Track 1`, `Hollis Track 2`, `LOCAL-H`, `GNDX 501`, `GNDX 502`, `GNDX 503`
**Confirm it:** after session 1 all three gondolas are on Hollis Track 2. `ops_why_not` GNDX 501 to Hollis Mill with `LOCAL-H` lists `track_order` with Hollis Track 2 before Hollis Track 1 (schedule tracks first, then lowest moves).
**Try this:** `set_track_moves` with the map `{"Hollis Track 2": 200}`. `track_order` then ends with Hollis Track 1 then Hollis Track 2, and session 1 puts all three cars on Hollis Track 1.

### U06. Departure staging with generated custom loads

**The difficulty:** builds from staging failed.
**How it's done here:** `West Custom` holds only cars that leave with a generated load (Machinery) and refuses empties; `West Mixed` ships Machinery and empties. Two depots receive Machinery.
**Find it:** `West Custom`, `West Mixed`, `East Mixed`, `Brae Depot`, `Dunmere Depot`, `CUSTOM`, `MIXED`, `JFN 601`, `JFN 611`, `JFN 614`
**Confirm it:** `ops_explain_build` CUSTOM car JFN 601: search "generate load" from West Custom, load Machinery, outcome assigned to Carrow Yard with final destination Brae Depot; eleven departure-track refusals C10 for other loads, then "try routing car to (Brae, Brae Depot) using two or more trains" and the route West Custom, Carrow Yard, Brae Depot. The car sits on Carrow Yard after session 1 and in session 2 `LOCAL-B` delivers it to Brae Depot (load E). `MIXED` carries JFN 611 to 613 to a depot with Machinery on the manifest, and JFN 614 (a gondola with no custom load) leaves as E to East Mixed.
**Try this:** remove both depot schedules. `ops_plan` reports only `schedule-unused` (info), twice. The dry run does not fail: West Custom also generates for any staging track, so the car is given a load and sent toward East Mixed (the build report lines "Could not find a route to a spur that needs a custom load" and "Try to send car to staging").

### U07. Two staging tracks swapping full trains

**The difficulty:** a staging track that is both destination and origin blocks the other train.
**How it's done here:** `West Swap` and `East Swap` both have planned pick ups (ignore_used_percent 100), so both trains build in one session.
**Find it:** `West Swap`, `East Swap`, `SWAP-E`, `SWAP-W`, `SWPX 1`, `SWPX 11`, `JFN 51`, `JFN 53`
**Confirm it:** session 1: `SWAP-E` carries SWPX 1 to 6 to East Swap and `SWAP-W` carries SWPX 11 to 16 to West Swap, 12 cars in one session; session 2 reverses them. `ops_why_not` SWPX 1 to East Swap with `SWAP-E`: A7 pass.
**Try this:** set East Swap ignore_used_percent to 0. `ops_plan` reports `staging-departure-blocked` (error); `SWAP-E` fails A7 ("East Swap: occupied by 6 cars and 2 locomotives"), `SWAP-W` still builds.

### U08. A fiddle yard of virtual spurs

**The difficulty:** spreading traffic evenly.
**How it's done here:** `Fiddle North` and `Fiddle South` are spurs whose schedule lines name the downstream track (Parts Depot, Tool Depot); the south line has random 25 and wait 1.
**Find it:** `Fiddle North`, `Fiddle South`, `Parts Depot`, `Tool Depot`, `Parts Receiving`, `Tools Receiving`, `FIDDLE JOB`, `JFN 801`, `JFN 802`, `JFN 803`, `JFN 804`, `JFN 805`, `JFN 806`
**Confirm it:** `FIDDLE JOB` (08:45) takes all six to the fiddle yard. Cars on Fiddle North carry Parts with final destination Parts Depot; cars on Fiddle South carry Tools with Tool Depot as final destination from session 2. Over 3 chains by session 3 every chain has at least one JFN 80x on Parts Depot and Parts cars delivered outnumber Tools cars. `ops_why_not` JFN 801 to Fiddle South: F5 not_checked "line 9c1 random 25%".
**Try this:** `replace_schedule_lines` on Fiddle South without the random line: the plan is clean and both lines then fire like Fiddle North.

### U09. One schedule for several spurs

**The difficulty:** copying a schedule per spur.
**How it's done here:** `Grain Receiving` is on both elevators; nothing is copied.
**Find it:** `Elevator A`, `Elevator B`, `Grain Receiving`, `JFN 901`, `JFN 902`
**Confirm it:** `ops_list` tracks: both have the same schedule id. After session 1 one car sits on each 50 ft elevator, load E.
**Try this:** copy the schedule with `add_schedule` and point Elevator B at the copy: plan and apply are clean, no finding.

### U10. A mixed default and custom spur

**The difficulty:** one spur that takes both default and custom cars.
**How it's done here:** a second virtual spur `Freight House-(2)` takes the Crates line; paperwork prints one name.
**Find it:** `Freight House`, `Freight House-(2)`, `Crates Receiving`, `FRHX 1`, `JFN 1001`
**Confirm it:** after session 1 FRHX 1 is on Freight House and JFN 1001 (load Crates) on Freight House-(2). The `LOCAL-B` manifest says "to Freight House" for both and never "-(2)". `ops_why_not` FRHX 1 to Freight House-(2) fails E10 and F4 ("line 13c1 receives Crates, car has E") and D16.
**Try this:** `rename_track` (field `new`) to `Freight House-2`: plan clean, audit unchanged (no hyphen finding for a track name).

### U11. Spurs and yards in balance

**The difficulty:** a spur that fills and then refuses cars.
**How it's done here:** `Mill Spur` holds two cars; planned pick ups let it take new cars while the same train pulls the old ones. Cars of road MILX return to their own lead.
**Find it:** `Mill Spur`, `Bakery`, `Carrow Mill Lead`, `Mill Flour`, `Bakery Receiving`, `MILX 1101`, `MILX 1102`, `MILX 1103`, `MILX 1104`
**Confirm it:** session 1: two cars on Mill Spur with Flour and final destination Bakery, two on Carrow Mill Lead. Session 2: the first pair is at Bakery (load E) and the second pair is on Mill Spur. Session 3: the second pair is at Bakery and the first pair is back on the lead. `ops_explain_build` `LOCAL-H` session 1 names MILX 1101 and 1102 with E9 at the full spur.
**Try this:** `update_track` Mill Spur ignore_used_percent 0 on the session 1 state: `ops_why_not` fails D16 with E9 "track is full: needs 44, used 88, length 100"; session 2 delivers the Bakery pair but Mill Spur ends empty.

### U12. Normal and aggressive mode

**The difficulty:** a staging train that builds in one mode only.
**How it's done here:** `MODE` has a locomotive change at Brae and ends in staging; it builds in normal and aggressive mode.
**Find it:** `West Mode`, `East Mode`, `Brae Stockyard`, `MODE`, `MODX 1`, `MODX 2`, `MODX 3`, `MODX 4`, `MODX 5`
**Confirm it:** session 1: five cars leave West Mode, one to Brae Stockyard and four to East Mode (the loco change uses none of Brae's three moves; the builder sends the rest on to staging). `ops_build_check` with `aggressive` on: `now_fail` empty, `changed` empty.
**Try this:** with aggressive on, set the MODE stop at Brae max_length 100: MODE fails; `ops_explain_build` shows D9 "would exceed train's maximum length (100) feet by 4 feet when departing (Brae)" and the failure line B20 "could not find destinations for 2 car(s) departing from staging".

### U13. Caboose, kernel, locomotive change and consist

**The difficulty:** equipment that must travel together.
**How it's done here:** `LOCAL-H` requires a caboose; kernel `Brae Set` moves together; `MODE` changes locomotives at Brae; consists `West Pair` and `East Pair` swap ends.
**Find it:** `Carrow Caboose Track`, `Dunmere Team`, `Brae Set`, `Brae Engine Track`, `LOCAL-H`, `LOCAL-B`, `MODE`, `SWAP-E`, `SWAP-W`, `JFN 1301`, `JFN 1302`, `KRNX 1`, `KRNX 2`, `KRNX 3`, `JFN 51`, `JFN 55`, `JFN 56`, `JFN 57`
**Confirm it:** every `LOCAL-H` build carries exactly one of the two cabooses and sets it out on Carrow Caboose Track (they alternate). KRNX 1 to 3 stay together on Dunmere Team with three set outs on the manifest. The `MODE` manifest says "Locomotive change at Brae", "Pick up JFN 56 ... from Brae Engine Track", "Set out JFN 55 ... to Brae Engine Track". `SWAP-E` takes JFN 51, 52 and `SWAP-W` JFN 53, 54 in session 1. `ops_explain_build` `MODE` lists engines JFN 56 and JFN 55.
**Try this:** (a) `update_track` Carrow Caboose Track pick ups Any: `ops_plan` reports `caboose-interchange-same-route`; over three sessions `LOCAL-H` takes 1302, then 1301, then fails to build; `ops_why_not` JFN 1301 B6 "last route 8, this route 8". (b) Brae Engine Track ignore_used_percent 0: `MODE` fails A8, and `ops_why_not` with `real_build` false leaves A8 not_checked with "no track at Brae has room for the locomotives set out at the change there". (c) `place_car` on KRNX 3 is refused: "KRNX3 is in kernel Brae Set. Place the lead."

### U14. Train schedule days

**The difficulty:** a day applied, but the Build boxes do not follow.
**How it's done here:** days were added with `add_default_days`; Tuesday lists all 18 trains and Saturday six; Tuesday is active and applied. The schedule line `Tuesday Dock` sets cars out on Tuesday only.
**Find it:** `Tuesday`, `Saturday`, `Tuesday Dock`, `Brae Day Track`, `DAYX 1`, `LOCAL-B`
**Confirm it:** `ops_list` days: Tuesday has 18 trains, Saturday 6, Tuesday is active. The build report header says "Active schedule: Tuesday". After session 1 DAYX 1 is on Tuesday Dock. `ops_why_not` DAYX 1 to Tuesday Dock with `LOCAL-B`: A1 pass, F1 pass.
**Try this:** `set_active_day` Saturday and `apply_day` Saturday ("Applied Saturday: 6 trains to build, 12 not"): `ops_why_not` fails A1 "LOCAL-B build False" and F1 "line 15c1 set out day Tuesday, active Saturday"; JMRI then builds exactly the six Saturday trains.

### U15. An automation

**The difficulty:** automations that wait forever or open dialogs.
**How it's done here:** `Evening Session` builds `LOCAL-H` and `LOCAL-B`, runs `Close Out` (which terminates `LOCAL-B`), waits for `LOCAL-B` to terminate, then terminates `LOCAL-H`. No dialog step. It is not the startup automation.
**Find it:** `Evening Session`, `Close Out`, `LOCAL-H`, `LOCAL-B`
**Confirm it:** `ops_list` automations shows the five steps. With it set as startup on a copy, real JMRI ran all five steps successfully and both trains ended not built.
**Try this:** `update_automation` with a `message_yes_no` step is refused ("open a window or a print dialog ... Pass allow_dialogs true"). A `wait_for_train_to_terminate` for a train the same automation already terminated never finishes (steps 3 and 4 stay unrun), which is why `Close Out` exists.

### U16. Manual build lines

**The difficulty:** forcing one car onto a train.
**How it's done here:** a manual build line makes `LOCAL-H` take TEMX 1 from Hollis Team.
**Find it:** `Hollis Team`, `Oakhaven Team`, `LOCAL-H`, `TEMX 1`
**Confirm it:** `ops_list` manual_builds shows line 1m1 on stop 8r2, track Hollis Team. Session 1 puts TEMX 1 on Oakhaven Team and the build report says "Manual build line id 1m1 was able to assign to train (LOCAL-H) 1 of 1 requested cars". `ops_explain_build` TEMX 1 shows search "default", assigned to Oakhaven Team, and the line under `manual_build`.
**Try this:** `delete_manual_build` for `LOCAL-H` and set the Hollis stop to 1 move: TEMX 1 stays on Hollis Team.

### U17. Paperwork

**The difficulty:** lines overwritten, apostrophes and braces breaking text.
**How it's done here:** red pick ups, blue set outs, green local moves, font 10, the valid line printed, a pick up line with a Track field, a doubled apostrophe in the valid phrase, one switch list phrase changed, and a railroad name on `LOCAL-B` only.
**Find it:** `LOCAL-B`, `FIDDLE JOB`
**Confirm it:** `ops_list` manifest shows the settings. The `LOCAL-B` manifest starts "Brae Branch Lines", prints "Conductor's copy, valid ..." with one apostrophe, and its pick ups are red and set outs blue. `FIDDLE JOB` prints JMRI's default, "My JMRI Railroad", because no railroad name is set in `Operations.xml`.
**Try this:** `set_manifest_text` valid "Valid {0" is refused by the plugin: "a { must open a numbered argument such as {0}". The changed switch list phrase was not read from a printed switch list.

### U18. Passenger blocking

**The difficulty:** passenger cars out of order.
**How it's done here:** blocking numbers -5, 10, 20, 40, 70 on FLYX 1 to 5, and the station spurs only serve `VALLEY FLYER`.
**Find it:** `Carrow Station`, `Northwood Station`, `VALLEY FLYER`, `FLYX 1`, `FLYX 2`, `FLYX 3`, `FLYX 4`, `FLYX 5`
**Confirm it:** the `VALLEY FLYER` manifest picks up FLYX 1, 2, 3, 4, 5 in that order and sets all five out at Northwood Station.
**Try this:** `update_car` FLYX 5 blocking -9: FLYX 5 is picked up first.

### U19. Track pools

**The difficulty:** pool minimum and maximum.
**How it's done here:** pool `Hollis Pool`: Pool 1 is 100 ft (min 100, max 150), Pool 2 is 300 ft (min 100).
**Find it:** `Hollis Pool 1`, `Hollis Pool 2`, `Hollis Pool`, `POOX 1901`, `POOX 1902`, `POOX 1903`, `POOX 1904`, `POOX 1905`, `POOX 1906`
**Confirm it:** session 1 spreads six 40 ft flatcars three and three (the builder alternates by move count), and Pool 1 borrows: saved length Pool 1 132, Pool 2 268 (sum 400, Pool 1 between 100 and 150). `ops_list` tracks shows the pool name; the minimum and maximum lengths are in `OperationsLocationRoster.xml`.
**Try this:** raise Pool 1 min_length to 350: refused, "its minimum lengths add up to 450, more than its tracks' 400". Removing the pool (`pool {}` on both) gives 2 cars on Pool 1 and 4 on Pool 2.

### U20. On-time build order

**The difficulty:** a train that departs earlier than one already built fails.
**How it's done here:** departure times 08:45 (`FIDDLE JOB`), 09:00 (`LOCAL-B`), 10:00 (`LOCAL-H`); the option is shipped off.
**Find it:** `LOCAL-B`, `LOCAL-H`, `FIDDLE JOB`
**Confirm it:** with on-time off, building `LOCAL-H` and then `LOCAL-B` in separate sessions builds both.
**Try this:** turn on "Build on time", build `LOCAL-H`, save, then build `LOCAL-B`: `ops_why_not` fails A2 "LOCAL-B departs at minute 540; last built train LOCAL-H departs at minute 600", and JMRI gives status "Error" with no build report (one log line only). `ops_dry_run` on that state gives `refused_before_build` on the train with JMRI's log line. Setting `LOCAL-B` to depart at 11 passes A2. The A2 text and the fix come from a state with `LOCAL-H` built and `LOCAL-B` not, which the session tools do not leave behind; the JMRI half is `Train.java` returning before the build.

### U21. Divisions

**The difficulty:** sending cars to their home division.
**How it's done here:** Northwood is in division `North`; the NWRX cars are given a home division so empties go to the home yard and the load to the home spur.
**Find it:** `North`, `Northwood Yard`, `Malt House`, `Malt House Receiving`, `NWRX 1`, `NWRX 2`, `NWRX 3`
**Confirm it:** `EAST FREIGHT` takes NWRX 1 to 3 to Ferris Yard; final destinations NWRX 1, 2 Northwood Yard, NWRX 3 Malt House (set at build). Session 2 `NORTH JOB` delivers them. `ops_why_not` NWRX 1 to Northwood Yard with `EAST FREIGHT`: router "two trains through yard Ferris Yard"; C12 fails "the car gets final destination Northwood, Northwood Yard".
**Try this:** `set_car_division` NWRX 1 none: C12 passes, the final destination stays blank after session 1, but the car still reaches Northwood Yard in session 2.

### U22. Hazmat, buffer and idler cars, LCL

**The difficulty:** special cars losing their order or going home.
**How it's done here:** on `TURN`, HZMX 9 is a Buffer first out of staging; HZMX 1 to 3 carry hazardous tank cars to Linden Refinery; HZMX 11 to 13 are a kernel `Girder Load` to Linden Steel (the idlers print as Girder). LCLX 1 is a passenger-flagged boxcar that works as less-than-carload on a dock.
**Find it:** `Turn A`, `Turn B`, `Linden Refinery`, `Linden Steel`, `Girder Load`, `Carrow LCL Dock`, `TURN`, `HZMX 9`, `HZMX 3`, `HZMX 12`, `LCLX 1`
**Confirm it:** the `TURN` manifest lists HZMX 9 Buffer as the first pick up and "HZMX 3 Tank Gas 40' L (Hazardous)"; HZMX 1 to 3 end on Linden Refinery, 11 to 13 on Linden Steel, HZMX 9 on Turn B. LCLX 1 is on Carrow LCL Dock after every session and the `LOCAL-B` manifest has both the pick up and the set out.
**Try this:** HZMX 9 passenger false: the car no longer rides; the manifest reads "Move HZMX 9 Buffer E from Turn A to Turn B". `ops_why_not` says can_move true, as the car does reach Turn B, and its `notes` say the car does not ride. LCLX 1 passenger false: `ops_why_not` fails D4.

### U23. Backups

**The difficulty:** nothing to go back to.
**How it's done here:** the folder holds one manual backup set taken with `ops_backup_now`.
**Find it:** (the `backups/` folder, no object)
**Confirm it:** `ops_backups` lists the set, six files, complete. To restore on a scratch copy: delete a car with `delete_car` (a before-change set is made), then `ops_restore` with the set name and folder `backups`: the car is back and `ops_audit` is as before. JMRI's own automatic backup sets are made when it first opens a folder, so none are shipped.
**Try this:** none; the test deletes `DAYX 1`, restores, and checks the audit.

### U24. A RIP track

**The difficulty:** a load disappears on arrival.
**How it's done here:** `Carrow RIP` has Disable load change set, so a loaded car keeps its load.
**Find it:** `Carrow RIP`, `Hollis Shop Lead`, `LOCAL-H`, `RIPX 1`
**Confirm it:** session 1: `LOCAL-H` carries RIPX 1 from Hollis Shop Lead to Carrow RIP and its load stays L.
**Try this:** `update_track` Carrow RIP load_options to empty: RIPX 1 arrives with load E.

---

## Part 2: routing variations

Each has a car whose route is the example. `ops_why_not` with the train named gives a `router` field with the route JMRI 5.16 takes.

### R01. One train direct

**How it's done here:** `LOCAL-H` reaches the spur and the schedule turns the peas into an empty.
**Find it:** `Oakhaven Cannery`, `Cannery Peas`, `LOCAL-H`, `JFN 5101`
**Confirm it:** `ops_why_not` JFN 5101 to Oakhaven Cannery with `LOCAL-H`: can_move true, router "single train". Session 1 puts it on the spur with load E.
**Try this:** `update_stop` `LOCAL-H` at Oakhaven drops false: first failure D1 "drops False", G6 fails "8r3: drops False, moves 20".

### R02. Two trains through an interchange

**Find it:** `Ferris Exchange`, `Carrow Packing`, `Cold Store`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5201`
**Confirm it:** `ops_why_not` JFN 5201 to Cold Store with `EAST FREIGHT`: can_move true, router "two trains through interchange Ferris Exchange", path `EAST FREIGHT` then `NORTH JOB`, E7, E8, E9 and G12 pass. first_failure is empty; direct_failure says D1 "no stop at Northwood after the car's stop on this route", because one train alone cannot do it. Session 1 leaves it on Ferris Exchange with load Produce; session 2 puts it on Cold Store (load E).
**Try this:** `setup_interchange` Ferris Exchange destinations Include Linden: `ops_plan` is blocked by `interchange-no-exit` and warns `single-destination-schedule`; `ops_why_not` fails G12 "no chain of trains found". In a build the car stays at Carrow Packing with no destination.

### R03. Two trains through a yard

**How it's done here:** routing via yards is on; the foundry car goes `LOCAL-H` to Carrow Transfer, then `EAST FREIGHT` to the pipe yard.
**Find it:** `Oakhaven Foundry`, `Carrow Transfer`, `Linden Pipe Yard`, `Foundry Casting`, `LOCAL-H`, `EAST FREIGHT`, `JFN 5301`
**Confirm it:** `ops_why_not` JFN 5301 to Linden Pipe Yard with `LOCAL-H`: can_move true, router "two trains through yard Carrow Transfer", path `LOCAL-H` then `EAST FREIGHT`, G12 pass (direct_failure D1, as in R02). Session 1: Carrow Transfer; session 2: Linden Pipe Yard. Keep Carrow Transfer's moves at 0: it is the hop because it has fewer moves than Carrow Yard.
**Try this:** set the router option `carRoutingViaYards` false: `ops_why_not` says "could not route car" and fails G12, but the build still puts the car on Carrow Transfer and `EAST FREIGHT` delivers it in session 2 (from Carrow it is a one-train route). The option changes the router's answer, not this railroad's outcome.

### R04. A chain of three trains

**Find it:** `Hollis Coil Mill`, `Carrow Relay`, `Ferris Relay`, `Northwood Steel`, `Coil Mill Shipping`, `LOCAL-H`, `EAST FREIGHT`, `NORTH JOB`, `JFN 5401`
**Confirm it:** `ops_why_not` JFN 5401 to Northwood Steel with `LOCAL-H`: can_move true, router "3 trains", path `LOCAL-H` to Carrow Relay, `EAST FREIGHT` to Ferris Relay, `NORTH JOB` to Northwood Steel (direct_failure D1 as in R02). Session 1 Carrow Relay, session 2 Ferris Relay, session 3 Northwood Steel (load E).
**Try this:** `update_track` Ferris Relay destinations Include Linden: `ops_plan` is blocked by `interchange-no-exit`; `ops_why_not` fails G12; the build leaves the car on Carrow Relay.

### R05. A route through staging

**Find it:** `Hop`, `Linden Pier`, `Carrow Salt Works`, `EAST FREIGHT`, `HOP OUT`, `JFN 5501`, `JFN 5502`
**Confirm it:** `ops_why_not` JFN 5501 to Linden Pier: router "two trains through staging Hop", can_move true and first_failure empty. direct_failure is D14 ("12r3 East, Linden Pier West"), which is why `EAST FREIGHT` cannot do it alone. The router's `steps` list searches it tried before the one that worked, so "no track found that a last train can pull to the final destination" is the route through a yard failing before the route through staging. Session 1 `EAST FREIGHT` sets it on Hop; session 2 `HOP OUT` takes it to Linden Pier.
**Try this:** router option `carRoutingViaStaging` false: router "could not route car" and G12 fails; `EAST FREIGHT` no longer takes the car, and in a full session `LOCAL-B` carries it to Dunmere Yard instead.

### R06. A Destinations filter as a gate

**How it's done here:** `Ferris Gate` admits only Pell Creek-(yard), so the car goes to `Pell Tank Track`, not `Gate Yard`.
**Find it:** `Ferris Gate`, `Pell Tank Track`, `Gate Yard`, `NORTH JOB`, `GTEX 1`
**Confirm it:** `ops_why_not` GTEX 1 to Gate Yard with `NORTH JOB`: D6 fails "Ferris Gate Include filter lets cars go only to Pell Creek-(yard); Northwood is not"; to Pell Tank Track D6 passes. Session 1 sets it on Pell Tank Track; the build report says "Destination (Northwood) not serviced by departure track (Ferris Gate) (D6)".
**Try this:** `setup_interchange` Ferris Gate destinations to all: D6 passes and session 1 puts the car on Gate Yard.

### R07. Pick ups named by route

**Find it:** `Ferris Transfer`, `Northwood Shed`, `NORTH JOB`, `XFRX 1`
**Confirm it:** session 1 `NORTH JOB` sets XFRX 1 on Ferris Transfer; session 2 the same route pulls it back to Northwood Shed. `ops_why_not` XFRX 1 to Northwood Shed with `NORTH JOB` on the session 1 state: B6 pass "last route 14, this route 14".
**Try this:** Ferris Transfer pick ups Any on the session 1 state: B6 fails "last route 14, this route 14" and the session 2 build leaves XFRX 1 behind.

### R08. The Routed option

**How it's done here:** `Ferris Routed` and `Hop` take routed cars only.
**Find it:** `Ferris Routed`, `Hop`, `Routed Siding`, `Carrow Box Factory`, `Box Factory Loads`, `JFN 5801`, `BOXX 1`
**Confirm it:** `ops_why_not` BOXX 1 to Ferris Routed: E7 fails "car has final destination none; only routed cars: True", D16 fails; JFN 5801 passes E7. The same for Hop. Session 1 puts JFN 5801 on Ferris Routed and BOXX 1 on Ferris Yard; session 2 JFN 5801 reaches Routed Siding (load E).
**Try this:** `update_track` Ferris Routed only_final_destination false: E7 passes and session 1 puts BOXX 1 on Ferris Routed.

### R09. An alternate, then forward to yard

**Find it:** `Oakhaven Plant`, `Plant Overflow`, `Oakhaven Yard`, `Plant Stone`, `LOCAL-H`, `JFN 5901`, `JFN 5902`, `JFN 5903`, `JFN 5904`
**Confirm it:** session 1 of four hoppers: two on Oakhaven Plant, one on Plant Overflow, one on Oakhaven Yard (which numbers is build order). `ops_explain_build` `LOCAL-H` car JFN 5901: E9 at the full plant and overflow, "Sending car ... to yard", final destination Oakhaven Plant. The report says "Delivering car (JFN 5902) to alternate track (Plant Overflow)" and "Track (Oakhaven, Oakhaven Plant) full, searching for a yard at destination". `ops_why_not` on the shipped state leaves E9 not_checked: the plant is empty before the build, but the other hoppers bound for it need more room than it has, and the real build refuses the plant at E9 ("available track space 12 feet").
**Try this:** router option `forwardToYard` false: the first car stays on Hollis Quarry; the other three are as before.

### R10. Overflow handled by a pool

**Find it:** `Ferris Pool 1`, `Ferris Pool 2`, `Ferris Pool`, `Carrow Grain Co`, `Grain Elevator`, `OAKX 1`, `OAKX 2`, `OAKX 3`, `OAKX 4`, `OAKX 5`
**Confirm it:** five 44 ft cars all fit on two 120 ft interchanges (three and two); none is left at Carrow Grain Co. Session 2: all five at Grain Elevator. `ops_list` tracks shows the pool name; the lengths are in `OperationsLocationRoster.xml`.
**Try this:** remove the pool from both tracks: only OAKX 2 to 5 move (two each) and OAKX 1 is left behind.

### R11. An A/D track with a switcher

**Find it:** `Kessock A/D`, `Kessock Class 1`, `Kessock Class 2`, `KESSOCK TRANSFER`, `KESSOCK SWITCHER`, `KESX 1`, `KESX 2`, `KESX 3`, `KESX 4`
**Confirm it:** session 1 `KESSOCK TRANSFER` sets KESX 1 to 4 on Kessock A/D; session 2 `KESSOCK SWITCHER` moves all four to the class tracks, two each. `ops_why_not` KESX 1 to Kessock Class 1 on the session 1 state: D19 pass (on the shipped state it stops at B0, because the car is still at Carrow).
**Try this:** build option `allowLocalInterchange` false: D19 fails ("switcher True: Interchange to Interchange"), `ops_audit` reports `switcher-local-off` three times and the build moves no cars.

### R12. A local switcher

**Find it:** `Sawyer Warehouse`, `Sawyer Yard 1`, `Sawyer Yard 2`, `SAWYER SWITCHER`, `SWYX 1`, `SWYX 2`
**Confirm it:** session 1: SWYX 1 spur to spur on Sawyer Warehouse, SWYX 2 yard to yard on Sawyer Yard 2. `ops_why_not` SWYX 1 to Sawyer Warehouse: can_move true, no failing gate.
**Try this:** `allowLocalSpur` false: D19 fails; the build keeps SWYX 1 and still moves SWYX 2 (yard to yard has its own option).

### R13. Through-car rules

**Find it:** `Dunmere Oil`, `Ferris Yard`, `THRU`, `OILX 1`, `OILX 2`
**Confirm it:** session 1 `THRU`: OILX 1 on Dunmere Oil, OILX 2 on Ferris Yard. `ops_why_not` OILX 1 to Ferris Junction with `THRU`: D10 fails; OILX 2 to Dunmere: D11 fails.
**Try this:** `update_train` `THRU` allow_through_cars true: D10 passes and the build puts both cars on Ferris Yard.

### R14. Service all cars with a final destination

**Find it:** `Carrow Glass Works`, `Linden Glazier`, `EAST FREIGHT`, `JFN 6401`, `JFN 6402`
**Confirm it:** shipped (Linden has 20 moves) both cars reach Linden Glazier in session 1 either way. The setting differs only when the destination stop is short of moves: with the Linden stop at 1 move and `service_all` false neither car moves; true sends JFN 6402 to Ferris Yard and JFN 6401 to Carrow Yard, from where they reach Linden Glazier over two trains. `ops_explain_build` shows it (gate G6). `ops_why_not` cannot know how the moves run out, so D3 stays open, and its `notes` say what each setting then does.
**Try this:** the case itself: set the Linden stop `max_moves` 1 on a copy and flip `service_all`.

### R15. Directions

**Find it:** `Linden Westside`, `Carrow West Lead`, `EAST FREIGHT`, `HOP OUT`, `WSTX 1`
**Confirm it:** `ops_why_not` WSTX 1 to Carrow with `EAST FREIGHT`: first failure C9, "12r3 East, Linden Westside West"; with `HOP OUT` no failure. Session 1 `HOP OUT` sets it on Carrow West Lead.
**Try this:** `update_track` Linden Westside directions East/West: C9 passes, but `EAST FREIGHT` takes the car to Hop (two trains through staging) and `HOP OUT` brings it to Carrow West Lead in session 2.

### R16. Hyphen-named locations

**Find it:** `Pell Creek-(yard)`, `Pell Creek-(industries)`, `Pell Yard`, `Pell Brickworks`, `PELL SWITCHER`, `PELC 1`, `PELC 2`
**Confirm it:** session 1 `PELL SWITCHER` moves PELC 1 and 2 to Pell Brickworks; the manifest reads "Scheduled work at Pell Creek, departure time 13:30" with neither "(yard)" nor "(industries)".
**Try this:** `rename_location` to `Pell Creek-industries`: `ops_plan` reports `hyphen-no-split` (warning). The cars still move; the visible change is the name on paperwork.

### R17. A rest-of-the-world interchange

**Find it:** `Brae Outside`, `Carrow Outside Lead`, `Outside World`, `LOCAL-B`, `OUTX 1`, `OUTX 2`
**Confirm it:** session 1: OUTX 1 on Brae Outside with load L, OUTX 2 on Carrow Outside Lead with E; session 2 they swap. `ops_why_not` OUTX 1 to Brae Outside: can_move true, E10 and F4 pass.
**Try this:** schedule removed from Brae Outside: only `schedule-unused` is reported, and a session gives the same loads (the plain spur flips E and L by itself).

### R18. A descriptive interchange

**Find it:** `Northern Connection`, `Turn A`, `EAST FREIGHT`, `TURN`, `CNXX 1`
**Confirm it:** session 1 `EAST FREIGHT` sets CNXX 1 on Northern Connection (set out by it only); session 2 `TURN` pulls it to Turn A (session 3 Turn B). `ops_why_not` CNXX 1 to Northern Connection: can_move true.
**Try this:** none: the interchange has no physical track, so there is nothing to break.

### R19. Staging to staging

**Find it:** `Turn A`, `Turn B`, `Linden Team`, `TURN`, `TRNX 1`, `TRNX 2`, `TRNX 3`
**Confirm it:** session 1 `TURN` departs Turn A, TRNX 1 and 2 go to Linden Team, TRNX 3 is picked up at Linden and ends on Turn B. Session 2 departs Turn B, TRNX 1 and 2 end on Turn A and TRNX 3 returns to Linden Team.
**Try this:** allow_return false alone changes nothing. Then `ops_session update_car` HZMX 9 passenger false is refused with the `staging-departure-blocked` text, unless the call gives `accept_new_errors`. With both changes `TURN` fails B20.

---

## Known limits

Left out of the cases, or open in the plugin:

- A permanent custom load lost on arrival in staging is an open failure in the research, so no case builds it.
- `ops_why_not` reads the files as they stand, so what a build uses up as it goes stays open: moves (D3), train length (D9, G10) and room taken by cars bound for the same track (E9). Its `notes` say what follows (R09, R14).
- A stand-alone `wait_for_train_to_terminate` for a train the same automation terminated never finishes in JMRI 5.16; a second automation is the way round (U15).
- The on-time abort in JMRI 5.16 writes no build report, so `ops_explain_build` has nothing to read; a dry run gives `refused_before_build` (U20).
- Actions that do not exist: a car's final destination, adding a car to a built train, train build and terminate scripts and track type change. The showcase uses `ops_deliver_car` for final destinations, and names tracks instead of tagging them, though `update_track` can now set a comment.
- `ops_why_not` does not follow a load generated for a staging-to-staging move, so it can miss why such a car stays.
- Two cases show `not_checked` and are left to a real build: a locomotive with no track at the terminal, which fails that build, and overlapping dates in a staging pool.
- Tools return long text by default. `ops_why_not` takes `failing_only`, and `ops_list` takes `filter`.
- Interactions kept on purpose: the Fiddle yard, `Carrow Box Factory` and `Carrow Glass Works` take default-E JFN boxcars from other cases after session 1, `Carrow Salt Works` takes empty JFN covered hoppers, and the `West Staging` trains run out of cars after session 1.
