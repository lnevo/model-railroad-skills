---
name: operations-pro
description: Sets up, checks, changes and runs a JMRI OperationsPro railroad with the operations-pro tools, and explains what the train builder did and why. Covers default and custom loads, schedules, staging, interchanges and routing, move counts and traffic balance, locomotives, cabooses, kernels and passenger cars, sessions, train schedules and automations, and the six Operations XML files. Use when someone asks why a car will not move or sits on hold, why a build failed, how to set up loads, schedules, staging, interchanges or routes, how to add or change locations, tracks, trains or cars safely, how to build, move, terminate or reset trains, or how to back up, restore, import or move Operations data. Rules come from the JMRI 5.16 source. Not for Layout Editor panels, signals or Dispatcher.
---

# OperationsPro

OperationsPro moves cars by building trains. Almost every surprise is a gate in the builder that the screens do not show. This skill says how to build a railroad in the order the program needs, how the builder decides, which tool to use, and what to read before changing anything.

## Start a railroad from nothing

Ask first: staging or a loop, default loads only or custom loads, and which trains should run in what order. Then build in this order. Each step is an `ops_plan` the user sees, then `ops_apply`, with JMRI exited. Point `ops_dir` at an empty Operations folder or at one JMRI has already made.

1. **Car types and custom loads:** `add_car_type`, `add_load`. The default E and L loads already exist. On an empty railroad a load has nothing to carry or take it yet, so this plan and early staging trains are blocked by audit errors that later steps clear: tell the user, and pass `accept_new_errors` to `ops_apply`. Use it only for errors a later step of this order clears.
2. **Locations and tracks:** `add_location`, then `add_track` for yards, interchanges and staging. An industry is `add_industry`, which makes the spur and its schedule in one step. Staging that should send custom loads is `setup_custom_staging`. An interchange between two trains is `setup_interchange`. Converting an existing default-load spur to custom loads has no single action: put `add_schedule` and then `update_track` (`schedule`, `schedule_mode`) in one plan; the worked example is in `references/loads-and-schedules.md`.
3. **Routes:** `add_route`, one per train pattern, with each stop's direction, moves and train length.
4. **Trains:** `add_train`, which also puts the train on the pick up and set out lists of the tracks along its route.
5. **Cars:** `add_car`, then `place_car` on the starting track. Kernels with `set_kernel`.
6. **Locomotives:** `add_engine_type` if the defaults do not fit, `add_engine` on its starting track, consists with `set_consist`, locomotive changes or helpers en route with `set_train_leg`, and a resting locomotive with `set_engine_moves`. A model's type, length and horsepower are shared by all its engines. Divisions, if used, with `add_division`, `set_location_division` and `set_car_division` (locomotives: `set_engine_division`). Cars a train must take first: `set_manual_build`. A session to run unattended: `add_automation` with steps that open no window (`references/sessions.md`).
7. **Check:** `ops_audit`, then `ops_dry_run`, which builds and terminates every train on a copy. Each train comes back with its report already read (outcome and findings; `detail` normal or full for more, or `ops_explain_build` with a car); fix what they say before the first real session.

A minimal working railroad is two locations with a yard each, one route between them, one train and a few cars of one type. Everything else is added to that, one plan at a time.

## How to work

- **Read before you change.** Run `ops_audit` on a railroad you have not seen, and `ops_why_not` for a car that will not move. Both read the files, so with JMRI running call `ops_live_save` first or the files lag by a minute or two.
- **Two lanes.** The file lane changes the six XML files and needs JMRI fully exited, not just the windows closed. The live lane talks to a running JMRI through its web server and the plugin's agent. Choose by what the user has open.
- **Setup changes show a plan first.** Call `ops_plan`, show the user the diff and any new audit findings, then `ops_apply`. Session corrections to a car use `ops_session` without the plan step.
- **Do not hand-edit XML with JMRI running,** and do not edit the XML at all when an action exists. JMRI rewrites whole files from memory on save and exit, and drops anything it does not store.
- **Leave move counts alone** unless asked. They steer traffic. Only `set_track_moves` and `reset_moves` change them.
- **Judge by the build report.** `ops_explain_build` reads the file JMRI wrote and names the gate behind each refusal; it beats anything worked out from the files. Two identical builds can differ, so compare sets of outcomes, not one run.
- **A failed build or a long report goes to the `ops-diagnoser` agent.** When the user asks why a build failed, why cars were left behind across a train, or what a long report says, start that agent first rather than reading the report here. It can only read, and returns the cause with the setting that fixes it. A single car's question with a named train stays here with `ops_why_not`.
- **No changes while a train is built,** apart from cars not on a train. A build keeps per-stop counters in memory only.
- **Say what you did not run.** A dry run on a copy is not a session on the railroad.

## Read the reference for the question

| Question | File |
|---|---|
| Why did a car fail, which gate, in what order | `references/build-order.md` |
| Default and custom loads, schedules, RWE and RWL, load type | `references/loads-and-schedules.md` |
| Staging departures, generated loads, ship options, returns | `references/staging.md` |
| Interchanges, routed cars, alternates, filters, directions, divisions | `references/routing.md` |
| Move counts, priority, aggressive mode, length, pools, spurs drain | `references/moves-and-balance.md` |
| Locomotives, cabooses, kernels, passenger, hazmat, LCL, TOFC, RIP | `references/special-cars.md` |
| Build, move, terminate, reset, Set Car, days, automations, live JMRI | `references/sessions.md` |
| The six files, backups, autosave, derived fields, JSON, import | `references/data-and-files.md` |
| Symptoms, build report lines, audit finding names | `references/diagnosis.md` |

Read one file, not all of them. The gate ids in `build-order.md` are the ids `ops_why_not` prints.

## Tools

Read: `ops_explain_build`, `ops_why_not`, `ops_audit`, `ops_list`, `ops_actions`, `ops_plan`, `ops_build_check`, `ops_dry_run`, `ops_backups`, `ops_backup_now` (takes a set; JMRI may stay running).
Write with JMRI exited: `ops_apply`, `ops_session`, `ops_deliver_car`, `ops_restore`, `ops_install_agent`.
Live JMRI: `ops_live_status`, `ops_train`, `ops_live_car`, `ops_live_save`, `ops_live_report`, `ops_live_automation`.

`ops_actions` lists the change actions with each field, whether it is required and what it takes; give `action` for one. Track list options start lower case (`trains`, `routes`, `excludeTrains`). A new engine model needs type and length.

Reading `ops_why_not`: `first_failure` is set only when the car cannot move. When the router chains other trains, `direct_failure` says why this train cannot do it alone, and `router_path` gives the chain. `notes` holds what the gates cannot say, such as a car that stays in staging, and which train was picked when none was named; give `failing_only` for a short answer. `ops_list` takes `filter`. `ops_explain_build` sets `stale` when the files have changed since the report; a dry run writes no report there, so use the reports in its own result.

## Facts that trip everyone

- A spur with a schedule refuses any car with no matching line. A spur with no schedule refuses every custom load, unless the spur is already the car's assigned destination track (Track:2062, so a routed car can still arrive), and flips a default E to L (or L to E) on delivery.
- `can_move: true` from `ops_why_not` means the gates pass, not that the builder will choose that track: ties go to the later stop, and at a location schedule tracks come first, then the lowest move count.
- Default E and L cars are never routed. They take the first accepting track on the building train's own route, scheduled tracks first. A car with a final destination is always routed, whatever its load.
- A schedule acts three times: as a gate on entry, at build when the line is assigned, and on delivery when the load changes. Set Car applies it only when the track changes and the user says yes.
- Staging can send a default empty. What blocks it is a Ship Load Option that excludes E, a train that does not carry E, or no track ahead that takes E. A car with a home division also needs a reachable location in its division; a generated load does not get round that.
- Every car on a departure staging track must leave or the build fails; on-time mode only drops the check that every car on the track is available to the train.
- Yards ignore pick up and set out lists and the Destinations filter. Interchanges, spurs and staging filter trains; only interchanges and staging filter destinations.
- The Destinations filter holds locations, not tracks, and tests the car's final destination. With no final destination it tests the next location the train would use.
- A car set out on an interchange with Pick ups set to Any cannot be pulled by a train on the same route.
- Adding a track resets that location's move counts. Assigning a different schedule from the schedule window resets every location.
- The built year test excludes both ends. Hyphen names split only on `-(` or `-<number>`.
- Changing a car's location through JSON does not run a schedule, and a car POST without `weightTons` blanks it. JSON cannot build a train.
- Autosave usually writes within two minutes of a change, a running build delays it, and exit always writes. Edits made outside JMRI while it runs are lost.

## Out of scope

**The plugin does not write:**

- A train's build or terminate script (a security risk, and a script can hang on a dialog). An automation with build, wait and terminate steps is the alternative (`sessions.md`).
- A track's type. Empty the track, `delete_track`, then `add_track` with the new type.
- A car's final destination: it is derived. It comes from a schedule line's ship destination, a return-when-empty or loaded setting, a manual build line with a destination, or the home division search; `ops_deliver_car` runs the schedule as Set Car does.
- A car added to a train that is already built. Write a manual build line before the build (`set_manual_build`); a line cannot name one car, only type, road and load.
- Track Analysis windows, and any third-party formatter or spreadsheet tool.
- A CSV import (`add_car` for each row does the job; `data-and-files.md`).

**Paperwork.** The plugin sets what JMRI writes for manifests and switch lists: page, font, colours, tabs, which lines and fields print, header and phrase text, a train's own railroad name, logo path and times, and the CSV files written at build (they appear only on the next build; see `sessions.md`). Out of scope are printing itself (printers, drivers, PDF output), CSV column content, bold text or comment colours, two fonts, the logo's image type and size, and web and tablet manifests.

**Also outside what this skill checked:** RFID and reporters, train icons on panels, locale and scale settings, migration from other programs, and version-specific bugs. Give the confirmed facts in `sessions.md` and `data-and-files.md` where they touch these, and say the rest is outside what this skill checked.

Checked against JMRI 5.16 source, tag v5.16, or tested in JMRI 5.16, except where this file says a point was not checked.
