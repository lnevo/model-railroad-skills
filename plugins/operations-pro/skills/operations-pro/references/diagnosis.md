# Diagnosis

## Gather first

- The build report, from `operations/buildstatus`. `ops_explain_build` reads it with the train name, or with `path` or pasted `text`. JMRI writes every detail level to that file whatever the Build Report setting shows; only the router lines depend on the router level, so set it to Detailed when routing is the question. `ops_dry_run` and `ops_train` build return the same reading for each train they build (the end of the file only if there is none). `ops_live_report` reads the end of the file from a running JMRI.
- The six XML files, after `ops_live_save` if JMRI is running.
- The JMRI version and the active train schedule, both in the report header.
- What the user expected to happen, in words.

Then run `ops_audit` for the railroad and `ops_why_not` for the car, with the train and track named when known. The `ops-diagnoser` agent does all of this with reading tools only; use it for a failed build or a report too long to read by hand.

## What ops_explain_build returns

- `outcome`: built or failed, the failure lines with their gate, the warning count.
- `route.passes`: each stop with the moves requested, used and the result, plus notes such as a skipped stop or a direction the location cannot serve.
- `excluded_cars`: cars removed before any search, each with its B gate and the screen that fixes it.
- `cars`: one story per car with its attempts: the search kind (default, custom load, router, generate load), the tracks refused with the gate, the accepted candidate, and the outcome (assigned, no destination, held, pick up refused, returned to or left in staging).
- `ignored_moves_done`: cars never tried because the stop's moves were used up.
- `not_routable`: the warning list of cars whose final destination could not be reached.
- `summary`: the same in sentences. `unparsed` lists any line that matched no JMRI 5.16 message; a non-empty list on another version means the wording changed there.

Line numbers refer to the file, so a claim can be checked against it.

## Reading the report

Wording follows the message keys and may differ a little between versions.

| Report text | Meaning |
|---|---|
| "Find destinations" | The default search along the route: a default load or no final destination |
| "Find spur" | The custom load search |
| "Did not assign a destination for car" | A stuck car; search for it |
| "{n}/{m} cars at location" | Not a fault; the stop's moves were used. Raise Moves on the route |
| "Can't send to spur due to Load" | The spur's load option excludes the load (E8) |
| "isn't serviced by departure track" | The car's own track's Destinations filter excludes the destination (D6, B8) |
| "location is equal to destination" | Same split location without a switcher or exemption (D4) |
| "Can't send directly to alternate" | Alternate tracks are never direct destinations |
| "Could not find a first hop" or "last hop" | Router gap or no room at the hop (G12) |
| A schedule message rather than a load message | The spur has a schedule and no line matched (E10, F) |
| An interchange line naming the car's last route | The same-route rule on an interchange (B6) |
| Stuck cars in staging after the car list | Every car on the departure track must leave (B20) |
| "called before trains completely loaded" in the log | Files loaded in the wrong order; a hand edit or a bad file |

A build in aggressive mode shows half the moves on the first pass. Two identical builds can differ because staging and load picks are random, so compare several runs; `ops_build_check` does that.

## Symptoms

| Symptom | Likely causes | Check |
|---|---|---|
| Car on hold or never moves | No accepting track on the route; default load with nothing pointing it; custom load with no receiving schedule; wait count; interchange same-route rule; direction | `ops_why_not` to each candidate destination |
| Build fails from staging | One car on the track cannot leave: ship option excludes E, train does not carry the load, out of service, no room ahead, divisional empty | `ops_why_not` for each car on that track; audit `staging-departure-blocked` |
| Cars scatter across a yard despite a schedule | Destinations filter leaves out the schedule's location; spur full; length failure before the spur | Audit `interchange-no-exit`; `ops_why_not` to the spur |
| Car stuck on an interchange | Custom search fallback left it there with no final destination; Pick ups Any on the same route; Destinations filter with no exit | Audit; `ops_why_not` with the pulling train |
| Same train cannot pull from an interchange it served | Pick ups Any and the car's last route is this route | Name the train or route in Pick ups |
| Spurs drain, yards fill | Length limit reached early; no schedules; yard counts low | `moves-and-balance.md`; route Moves and Max Length |
| Schedule never fires | Car was already parked when the schedule was added; wait count; set out day against the active day; random | Deliver the car with `ops_deliver_car` |
| Nothing builds | Build boxes cleared by Apply on the wrong day; wrong active schedule | Report header; `set_active_day`, then `apply_day` |
| New train takes nothing | Train missing from the tracks' Pick ups and Set outs lists; a copy named with a hyphen difference | Audit `train-not-on-list`; `add_train` adds the lists |
| Caboose not found | Not flagged caboose; caboose road list; track direction or pick up list | Audit `caboose-road-mismatch` |
| Build fails on a kernel | Members on different tracks | Audit `kernel-split` |
| Build finds no locomotive | Model or road the train asks for; type, loco road, owner or built dates refuse every engine; consist size not exactly the count; out of service | Audit `engine-no-train`, `model-type-no-train`, `model-type-no-track` |
| Every car refused at a spur | Length typo; type not on the track; load option | Audit `type-no-track`, `car-on-refusing-track` |
| Car goes to staging instead of the spur | Spur full or not routable; no Hold; Destinations filter | `ops_why_not` to the spur |
| Custom-load car became a default load | RWE to an unscheduled spur; blank ship with the wrong load type; arrived in staging with the convert option | Audit `rwe-to-unscheduled-spur`, `custom-empty-flagged-load` |
| Report may show E twice with different names | A renamed default beside a custom one | Audit `renamed-default-collision` |
| Train works a location but never a track there | Track direction, or Pick ups and Set outs lists | Audit `track-direction-unserved` |
| Edits vanished | Made while JMRI ran; overwritten by autosave or exit | Restore; redo with JMRI exited |
| Cars gone after a start | Bad file | `ops_restore` from `autoBackups` |
| Remote build never finishes | A dialog open on the JMRI computer | Use `ops_train`, which turns dialogs off |

## Audit findings

Errors stop traffic; warnings are settings JMRI ignores or traps; info is worth knowing.

| Finding | Meaning |
|---|---|
| `type-no-train`, `type-no-track` | No train carries, or no track takes, a car type |
| `load-no-train`, `load-no-track` | A custom load no train carries, or no track takes with its type |
| `load-no-receiver`, `single-receiver-load`, `routing-gap` | A shipped load with no, one, or no reachable receiving schedule |
| `single-destination-schedule` | Every line names one ship destination, and nothing there takes the load or no train reaches it |
| `schedule-unused`, `schedule-on-non-spur` | A schedule no track uses, or one JMRI will drop |
| `yard-pickup-list`, `yard-drop-list`, `destinations-ignored`, `only-fd-ignored`, `ship-option-ignored` | Settings JMRI ignores on this track type |
| `alternate-ignored`, `interchange-as-alternate` | An alternate on a non-spur, or an interchange used as one |
| `interchange-no-exit` | The Destinations filter admits nowhere a pulling train goes |
| `blank-receive-on-staging-fed-spur` | Load generation cannot target this line |
| `custom-empty-flagged-load`, `load-flagged-empty`, `renamed-default-collision` | Load type and name traps |
| `generator-no-target`, `staging-ship-excludes-empty`, `staging-departure-blocked` | Staging traps |
| `caboose-road-mismatch` | A required caboose road no caboose on the route has |
| `route-direction-mismatch`, `route-stop-dead`, `track-direction-unserved` | A stop the location cannot serve, a stop with no moves possible, a track no stop serves |
| `list-stale-id` | A pick up or set out list naming a deleted train or route |
| `day-stale-id` | A schedule line or car naming a train schedule (day) that was deleted; JMRI treats it as any day, so clear it or set a real one |
| `train-not-on-list` | A train absent from a track's lists on its route |
| `built-boundary` | A car built exactly on a train's year limit, which the exclusive test refuses |
| `rwe-to-unscheduled-spur` | A return-when-empty that will drop the car out of routing |
| `kernel-split`, `car-unplaced`, `car-on-refusing-track` | Members on different tracks; no location or track; a track that does not take the car's type |
| `location-unserved`, `hyphen-no-split`, `switcher-local-off` | A location no route visits, a hyphen that does not split, a switcher with local moves off |
| `model-type-no-train`, `model-type-no-track` | A locomotive model whose type no train takes, or no track (with its location) takes, so its engines are never used or have nowhere to be set out |
| `engine-no-train` | A locomotive whose type some train takes, but every train refuses it by loco road list, owner, built dates, or the model and road it asks for (count 0 asks for none, except from departure staging); out of service engines are left out |
| `engine-location-refuses-type`, `engine-on-refusing-track` | A locomotive at a location, or on a track, that does not take its type: Set Locomotive refuses the spot without force, and no train sets it out there |
| `consist-split` | Consist members on different tracks; a train taking the lead adds the others at the lead's stop, wherever they sit |
| `pool-minimum-over-length` | A pool whose track minimums add up to more than its tracks' lengths, JMRI's "ERROR: Minimum > Length" |

## When the report and the tools disagree

The report wins. The tools read the files and report `not_checked` for gates that depend on the build itself: moves and train length once other cars are placed, a random draw that could take every move, quick service timing against a clone, which track a home division search picks, timing against other trains' pulls, room that pulls in aggressive mode or quick service may open, and a manual line that may or may not take the car. Say which gate was not checked.

Checked against JMRI 5.16 source, tag v5.16.
