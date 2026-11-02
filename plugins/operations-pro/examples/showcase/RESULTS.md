# Showcase results

What was built, what each case does in real headless JMRI 5.16, which test holds it and which tool confirmed it. The railroad is the Juniper Falls & Northern; the guide is [`GUIDE.md`](GUIDE.md), the plan [`PLAN.md`](PLAN.md).

## How it was built and checked

- Build files `build/00` to `build/76` are replayed by `build.py`. In stage 4 every step of every file was also applied through the native tools (`ops_plan` then `ops_apply`, and `ops_deliver_car`; `ops_dir` always explicit) on a fresh copy of `servers/blank`, by sub-agents that were forbidden scripts. The six Operations XML files of that native copy are **byte-identical** to the `build.py` replay before the JMRI merge, and the `ops_data.load` records are equal (0 differences). No native refusal occurred that `build.py` did not also hit.
- The shipped folder is `build.py --ship`: the replay, one real JMRI load-and-save, and a real build of every train for `buildstatus/`. JMRI's save re-orders some lists (car types, loads), so the shipped files differ from the native copy in order only.
- `backups/` was cleared after the merge and one set taken with the native `ops_backup_now`.
- Shipped state: no audit errors, three intended findings (see REFERENCE.md). All 18 trains build in session 1. Active day Tuesday. Nothing is built or terminated in the shipped files.
- Tests: `tests/test_showcase.py` (97 tests). Cases assert in three chains of three real JMRI sessions; experiments run on scratch copies.
- Honest note on path: the build was native throughout. The confirmations in the table below were run by the tests (server functions, "script") except the rows listed under "Native confirmation record", which were run with the plugin's own tools. Batches A to F were built in stage 3 through `build.py` and the server functions in places; stage 4 repeated every step natively.

## Independent review

A fresh review checked 201 claims in the guide, now `REFERENCE.md`, against JMRI 5.16 source and real runs, seeing only the guide and the database: 181 passed, 17 failed, 3 unverified. The guide was corrected from those findings. Where a row below differs from the guide, the guide is right. These cases changed: U03 (named train needed), U06 (Try this: no generator-no-target; goes to East Mixed), U08 (line id 9c1), U10 (line id 13c1), U12 (loco change uses no moves), U14 (line id 15c1), U17 (FIDDLE JOB prints the JMRI default name), U19 (ops_list shows pool name only), R02 (Try this: car stays at Carrow Packing), R05 (Try this: LOCAL-B takes it to Dunmere Yard), R07 (Try this: only XFRX 1 left behind), R10 (ops_list shows pool name only), R11 (D19 on session 1 state only), R19 (Try this order refused by ops_session), U20 (A2 text not reproducible through tools). The review also said the audit false-positive explanation was wrong; running the audit's own reachability check showed the sample-car cause is right (the case's own road finds a chain, the sample does not), but the road list need not be on the destination spur, so the wording was corrected rather than dropped.

## Plugin behaviour check

Five fresh `claude -p --plugin-dir` sessions from an unrelated folder, one plain question each, naming no tool or skill. The operations-pro skill triggered in all five. `ops-diagnoser` was used in none, including the long build report question. Tools chosen were `ops_why_not`, `ops_explain_build`, `ops_audit`, `ops_list`, `ops_dry_run` and `ops_actions`, plus file reading. Four answers were right. The MODE answer was right about the cause but stated it as likely. Two sessions could not run a second session, because the test setup did not permit shell copies.

After the plugin fixes, the same check with five new plain questions: `ops-diagnoser` ran in three of five, on the failed build, the long report and the cars left behind. The two it missed were a single car's question, which stays in the main session by design, and a question about adding a track comment. The skill loaded in three of five; the two sessions that started the agent directly did not load it. Five sessions are still a small sample.

## Hand edits

None. No `hand_edit` step is used in any build file.

## Edits to build files made while integrating (not hand edits to Operations files)

| Where | Change | Reason |
|---|---|---|
| `build/40_d.json` | `Northwood Steel` track moved from step 1 to step 2, after `Ferris Relay` | the plan was blocked ("No chain of trains takes Coil ...") until the relay existed |
| `build/60_f.json` | `set_line_days` Tuesday Dock line 1 setout_day Tuesday after `add_default_days` | the day half of U14; days belong to batch F |
| `build/70_audit.json` (new) | 27 `update_track` actions turning every `trains` pick up and set out list into an `excludeTrains` list | batch B had cut 126 `train-not-on-list` infos this way; the other batches left 202. Only `Ferris Transfer` (a route list, R07) keeps two |
| `build/75_fix.json` (new) | adds `Brae Depot` and `Dunmere Depot` (receive Machinery, road JFN); road JFN only on `Carrow Box Factory`, `Carrow Glass Works` and `Carrow Salt Works` | the depots were in the plan for batch B but never built (U06 needs them); the three Carrow spurs took default-E boxcars of other roads (DAYX 1, FRHX 1, LCLX 1) in session 1 |
| `build/76_tags.json` (new) | tag `[U20]` on `LOCAL-B` and `LOCAL-H` | U20 had no tagged object |

## Cases

For every case: state, whether it worked first time (No means a plugin fault, a changed expectation or a rework), the test, the tool that confirmed it and who ran it ("native" is the plugin's MCP tool, "script" is the same server function called from a test), what it said, and the experiment ("Try this") with its outcome. Every experiment was run once on a scratch copy.

| Case | State | First time | Test (`tests/test_showcase.py`) | Confirmed by | What it said | Experiment outcome | Note |
|---|---|---|---|---|---|---|---|
| U01 | Reworded | No | BraeDunmereSessions.test_u01_*; BraeDunmereWhyNot.test_u01_* | native | ops_why_not JFN 101 to Brae Feed Mill, LOCAL-B: can_move true, E8 pass, E10 pass | loads Include Feed on the mill: D16 fails, E8 "Brae Feed Mill Include: Covered Hopper E" | Seeded by one delivered car; merged railroad puts the empty hopper on the mill in session 1 (built alone it went to Dunmere Yard) |
| U02 | Reworded | No | BraeDunmereSessions.test_u02_* | script | ops_list cars JFN 201 (Canned, fd Grocery Dock); manifest line | place_car without delivery: audit schedule-not-applied | JFN 202 dropped; default empties compete for every spur |
| U03 | Reworded | No | BraeDunmereSessions.test_u03_* | script | ops_why_not WNDR 1 to Brae Lumber: D7 then E2,E3,E4,E10,F2 | schedule removed from Lumber Dealer: only schedule-unused; cars still arrive | Cars start loaded through ops_deliver_car; plan claimed load-no-receiver, JMRI says schedule-unused |
| U04 | Reworded | No | HopKessockSawyerCases.test_U04_* | script | ops_why_not JFN 401 to Sawyer Pasta Plant: can_move true | pickups false + local_moves false: C2 fails, 0 cars; local_moves alone does not stop JMRI | Second route stop does not break it; why_not agrees: G3 passes, as the car falls to the train's own route |
| U05 | Proved | Yes | HollisOakhavenCases.test_u05_* | native | ops_why_not GNDX 501 to Hollis Mill, LOCAL-H: track_order Hollis Track 2 before Hollis Track 1 | set_track_moves Hollis Track 2 200: order reverses, cars go to Track 1 |  |
| U06 | Reworded | No | StagingCases.test_u06_*; MergedCases.test_u06_* | native | ops_explain_build CUSTOM JFN 601: generate load, C10 refusals, route West Custom > Carrow Yard > Brae Depot | depot schedules removed: generator-no-target info; CUSTOM still builds, load diverted toward staging | Depots were in the plan for batch B but not built; added in 75_fix.json. Try-this reworded (no C10 failure) |
| U07 | Proved | Yes | StagingCases.test_u07_* | script | ops_dry_run both trains built; ops_why_not SWPX 1 to East Swap SWAP-E: A7 pass | East Swap ignore_used_percent 0: staging-departure-blocked; SWAP-E fails A7 | Try-this reworded: only the first train fails |
| U08 | Reworded | No | BraeDunmereSessions.test_u08_* | script | ops_why_not JFN 801 to Fiddle South: F5 not_checked random 25% | drop the random line: both lines fire like Fiddle North | Statistical over 3 chains |
| U09 | Proved | Yes | BraeDunmereShipped.test_u09_*; BraeDunmereSessions.test_u09_* | script | ops_list tracks: same schedule id on both elevators | copy schedule onto Elevator B: clean, no finding |  |
| U10 | Reworded | No | BraeDunmereSessions.test_u10_*; BraeDunmereWhyNot.test_u10_* | script | ops_why_not FRHX 1 to Freight House-(2): E10, F4, D16 fail | rename_track to Freight House-2: clean (field is new) |  |
| U11 | Reworded | Yes | HollisOakhavenCases.test_u11_* | script | ops_why_not MILX 1101 to Mill Spur; ops_explain_build LOCAL-H E9 | Mill Spur ignore_used_percent 0: D16 fails E9; Mill Spur ends empty | Cars return to Carrow Mill Lead, not Carrow Yard |
| U12 | Reworded | No | StagingCases.test_u12_* | script | ops_build_check aggressive true: now_fail [] changed {} | MODE stop max_length 100 with aggressive: D9, B20 | Counts 1 and 4, not 3 and 2 |
| U13 | Proved | Yes | StagingCases.test_u13_*; HollisOakhavenCases.test_u13_*; BraeDunmereSessions.test_u13_* | script | ops_explain_build MODE engines JFN 56 JFN 55; manifests | caboose pick ups Any: caboose-interchange-same-route, B6; Brae Engine Track ignore_used 0: A8; place_car on kernel member refused | Loco change costs two of the stop moves |
| U14 | Reworded | No | DaysCases.*; MergedCases.test_u14_*; BraeDunmereSessions.test_u14_* | script | ops_list days; ops_why_not DAYX 1 to Tuesday Dock LOCAL-B: A1, F1 pass | Saturday active + applied: A1 and F1 fail; JMRI builds six trains | set_line_days for Tuesday Dock added to 60_f (it had no home) |
| U15 | Reworded | No | AutomationCases.* | script | ops_list automations five steps; JMRI ran all five | message_yes_no step refused; own-terminate wait never finishes | Close Out helper added; wait needs another actor |
| U16 | Proved | Yes | HollisOakhavenCases.test_u16_* | native | ops_explain_build LOCAL-H TEMX 1: assigned to Oakhaven Team, and manual_build gives the line | delete_manual_build + 1 move: TEMX 1 stays |  |
| U17 | Reworded | No | PaperworkCases.* | script | ops_list manifest; LOCAL-B manifest text | unmatched brace refused by the plugin |  |
| U18 | Reworded | No | HopKessockSawyerCases.test_U18_* | script | LOCAL VALLEY FLYER manifest order | FLYX 5 blocking -9: picked up first | Station spurs fenced to VALLEY FLYER |
| U19 | Reworded | No | HollisOakhavenCases.test_u19_* | native | ops_why_not POOX 1901 to Hollis Pool 1: can_move true; saved lengths 132 and 268 | min_length 350 refused; pool removed 2 and 4 | Three cars per track, not all six on Pool 1 |
| U20 | Reworded | No | OnTimeCases.* | script | ops_why_not DAYX 1 to Tuesday Dock LOCAL-B: A2 fail "departs at minute 540; last built train LOCAL-H departs at minute 600" | depart_hour 11: A2 passes | JMRI gives status Error with no report, not Build Failed |
| U21 | Proved | Yes | FerrisNorthwoodCases.test_u21_* | script | ops_why_not NWRX 1 to Northwood Yard EAST FREIGHT: router two trains through yard Ferris Yard; C12 fails | set_car_division none: C12 passes; car still arrives | Experiment reworded |
| U22 | Reworded | No | StagingCases.test_u22_*; BraeDunmereSessions.test_u22_* | native | ops_explain_build TURN: departs Turn A, terminates Turn B | HZMX 9 passenger false: car does not ride; LCLX 1 passenger false: D4 | LCL dock moved to Carrow; Try-this reworded |
| U23 | Proved | Yes | BackupCases.* | native | ops_backup_now then ops_backups: one set, six files, complete | delete_car then ops_restore, audit unchanged | Shipped set taken with the native tool |
| U24 | Proved | Yes | HollisOakhavenCases.test_u24_* | script | ops_list cars RIPX 1 load L; track load_options | load_options [] : RIPX 1 turns E |  |
| R01 | Proved | Yes | HollisOakhavenCases.test_r01_* | native | ops_why_not JFN 5101 to Oakhaven Cannery LOCAL-H: single train, E7 E8 E9 D16 G12 pass | LOCAL-H drops false: D1, G6 fail |  |
| R02 | Reworded | No | FerrisNorthwoodCases.test_r02_* | native | ops_why_not JFN 5201 to Cold Store EAST FREIGHT: two trains through interchange Ferris Exchange; direct_failure D1, can_move true | destinations Include Linden: interchange-no-exit, G12 fails | Car goes to Hop instead of waiting |
| R03 | Proved | No | HollisOakhavenCases.test_r03_*; MergedCases.test_r03_* | native | ops_why_not JFN 5301 to Linden Pipe Yard LOCAL-H: two trains through yard Carrow Transfer | carRoutingViaYards false: could not route, G12; build still delivers | Destination lines added in 55_c after Linden Pipe Yard exists |
| R04 | Proved | No | HollisOakhavenCases.test_r04_*; FerrisNorthwoodCases.test_r04_* | native | ops_why_not JFN 5401 to Northwood Steel LOCAL-H: 3 trains | Ferris Relay destinations Include Linden: interchange-no-exit, G12 | Northwood Steel track moved after Ferris Relay in 40_d to clear a blocked plan |
| R05 | Reworded | No | HopKessockSawyerCases.test_R05_* | native | ops_why_not JFN 5501 to Linden Pier: two trains through staging Hop; direct_failure D14, can_move true, as JMRI delivers it | carRoutingViaStaging false: could not route car, G12 | JFN 5502 made a Hopper |
| R06 | Reworded | No | FerrisNorthwoodCases.test_r06_* | script | ops_why_not GTEX 1 to Gate Yard NORTH JOB: D6 fails | destinations all: D6 passes; car on Gate Yard | Filter reversed from the plan |
| R07 | Reworded | No | FerrisNorthwoodCases.test_r07_* | script | ops_why_not XFRX 1 to Northwood Shed NORTH JOB: B6 pass | pickup Any: B6 fails |  |
| R08 | Proved | No | FerrisNorthwoodCases.test_r08_*; MergedCases.test_r08_* | native | ops_why_not BOXX 1 to Hop EAST FREIGHT: E7 fails (can_move false); JFN 5801 to Ferris Routed: router two trains, E7 pass | only_final_destination false: E7 passes |  |
| R09 | Proved | Yes | HollisOakhavenCases.test_r09_* | native | ops_explain_build LOCAL-H JFN 5901: E9 at plant and overflow, sends to yard; why_not leaves E9 not_checked before the build | forwardToYard false: car stays on Hollis Quarry |  |
| R10 | Reworded | No | FerrisNorthwoodCases.test_r10_* | script | ops_list tracks pool fields | pool removed: only four cars move | Pools 120 ft; three and two, not all on Pool 1 |
| R11 | Reworded | No | HopKessockSawyerCases.test_R11_* | script | ops_why_not KESX 1 to Class 1 KESSOCK SWITCHER: D19 pass | allowLocalInterchange false: D19 fails, switcher-local-off |  |
| R12 | Proved | Yes | HopKessockSawyerCases.test_R12_* | script | ops_why_not SWYX 1 to Sawyer Warehouse: can_move true | allowLocalSpur false: D19; yard to yard still moves |  |
| R13 | Proved | No | HopKessockSawyerCases.test_R13_* | script | ops_why_not OILX 1 to Ferris THRU: D10; OILX 2 to Dunmere: D11 | allow_through_cars true: D10 passes | Needed train-list fences |
| R14 | Reworded | No | HopKessockSawyerCases.test_R14_* | script | ops_explain_build EAST FREIGHT JFN 6402 with Linden stop at 1 move: G6 | the case itself on a copy | Setting matters only when the stop is short of moves |
| R15 | Proved | No | HopKessockSawyerCases.test_R15_* | script | ops_why_not WSTX 1 to Carrow EAST FREIGHT: C9 fail; HOP OUT no failure | Linden Westside East/West: C9 passes, car goes via Hop | Try-this prediction was wrong |
| R16 | Proved | Yes | FerrisNorthwoodCases.test_r16_* | script | ops_list locations; manifest text | rename to Pell Creek-industries: hyphen-no-split warning | Experiment reworded |
| R17 | Reworded | No | BraeDunmereSessions.test_r17_*; BraeDunmereWhyNot.test_r17_* | script | ops_why_not OUTX 1 to Brae Outside: can_move true | schedule removed: only schedule-unused | Session 2 load is L, not E |
| R18 | Proved | Yes | HopKessockSawyerCases.test_R18_*; MergedCases.test_r18_* | script | ops_why_not CNXX 1 to Northern Connection EAST FREIGHT: can_move true | none (modelling) | Second half with the real TURN tracks |
| R19 | Reworded | No | StagingCases.test_r19_* | native | ops_explain_build TURN: departure Turn A, terminates Turn B | allow_return false alone changes nothing | Try-this reworded |

Runs: every deterministic case held in all three chains (U08 is statistical, and which JFN 59xx lands where in R09 is build order).

## Dropped or reworded, with reasons

Nothing was dropped. Reworded: U01 (seeded by one delivered car), U02 (JFN 202 removed: a second default empty competes for every spur), U03 (loaded start; the plan's `load-no-receiver` finding is `schedule-unused`), U04 (a second route stop does not break it), U06 (no C10 failure: the staging generator falls back to any staging track), U11 (cars return to their own lead), U12 (one car to Brae, four to staging), U15 (a second automation, `Close Out`, because a wait for a train the same automation terminated never finishes), U18 (station spurs fenced to the train), U19 (three cars per track and the pool loan), U20 (JMRI reports status Error with no report), U22 (LCL dock at Carrow), R05 (JFN 5502 is a hopper), R06 (filter reversed), R10 (120 ft pools, three and two), R14 (differs only when the stop is short of moves), R17 (session 2 load is L), R19 (try-this).

## What changed when the cases met

- `Brae Depot` and `Dunmere Depot` were missing (see 75_fix).
- Default-E JFN boxcars of the Brae and Dunmere cases are drawn into `Carrow Box Factory`, `Carrow Glass Works`, `Carrow Salt Works`, the Fiddle yard and `Dunmere Yard` after session 1; cases assert session 1 except where stated.
- U01: in the merged railroad the empty hopper reaches `Brae Feed Mill` in session 1 (built alone it went to `Dunmere Yard`). The reason was not isolated.
- Sessions 2 and 3: `CUSTOM`, `MIXED` and `MODE` fail to build (their staging track is empty); `HOP OUT` joins them in session 3. By design.
- `FIDDLE JOB` (08:45) runs before `LOCAL-B` (09:00) and `LOCAL-H` (10:00); `LOCAL-H` carries its caboose in every session; Saturday active stops `LOCAL-B` building (A1).

## Native confirmation record (shipped folder, `ops_why_not` with the train named, real_build false)

| Row | can_move | Router and gates |
|---|---|---|
| R01 JFN 5101 to Oakhaven Cannery, LOCAL-H | true | "single train"; E7, E8, E9, D16, G12 pass |
| R02 JFN 5201 to Cold Store, EAST FREIGHT | true | "two trains through interchange Ferris Exchange"; direct_failure D1; E7, E8, E9, G12 pass |
| R03 JFN 5301 to Linden Pipe Yard, LOCAL-H | true | "two trains through yard Carrow Transfer"; direct_failure D1; G12 pass |
| R04 JFN 5401 to Northwood Steel, LOCAL-H | true | "3 trains": Carrow Relay, Ferris Relay, Northwood Steel; direct_failure D1 |
| R05 JFN 5501 to Linden Pier, EAST FREIGHT | true | "two trains through staging Hop"; direct_failure D14; JMRI delivers the car |
| R08 BOXX 1 to Hop, EAST FREIGHT | false | E7 fails "car has final destination none; only routed cars: True"; router not used |
| R08 JFN 5801 to Ferris Routed, EAST FREIGHT | true | "two trains through interchange Ferris Routed"; E7 pass |
| R09 JFN 5904 to Oakhaven Plant, LOCAL-H | true | "single train"; E9 pass (used 0, length 100); the real build refuses the plant at E9 (12 feet left) |
| U01 JFN 101 to Brae Feed Mill, LOCAL-B | true | E7, E8, E9, D16, G12 pass; router not used |
| U05 GNDX 501 to Hollis Mill, LOCAL-H | true | resolved to Hollis Track 2; track_order Hollis Quarry, Mill Spur, Hollis Coil Mill, Hollis Track 2, Hollis Team, Hollis Pool 1, Hollis Pool 2, Hollis Shop Lead, Hollis Yard, Hollis Track 1 (Track 1 also passes, last) |
| U19 POOX 1901 to Hollis Pool 1, LOCAL-H | true | E4 pass "Include: road POOX"; E8, E9 pass |

`ops_explain_build` (native): CUSTOM JFN 601 assigned to Carrow Yard, final destination Brae Depot, search "generate load", eleven C10 refusals, route West Custom, Carrow Yard, Brae Depot; LOCAL-H TEMX 1 assigned to Oakhaven Team, search "default", nothing about the manual build line; LOCAL-H JFN 5901 assigned to Oakhaven Yard, final Oakhaven Plant, search "router", E9 at the plant (12 feet) and at Plant Overflow (6 feet); TURN "Partial 10/55 cars", departs Turn A (West Custom, West Mixed, West Mode rejected at A8) and terminates on Turn B (A7 on the others). The native `ops_audit` listed the six intended findings. The other confirmations in the table ran as server functions from the tests ("script"); the native tools call the same functions.

## Disagreements between the plugin and real JMRI

Recorded in REFERENCE.md "Known limits": what a build uses up as it goes stays open in `ops_why_not` (moves, train length, room for cars bound for the same track), with `notes` saying what follows.
