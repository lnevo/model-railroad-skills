---
name: operations-pro
description: Sets up, checks, changes and runs a JMRI OperationsPro railroad with the operations-pro tools, and explains what the train builder did and why. Covers default and custom loads, schedules, staging, interchanges and routing, move counts and traffic balance, locomotives, cabooses, kernels and passenger cars, sessions, train schedules and automations, and the six Operations XML files. Use when someone asks why a car will not move or sits on hold, why a build failed, how to set up loads, schedules, staging, interchanges or routes, how to add or change locations, tracks, trains or cars safely, how to build, move, terminate or reset trains, or how to back up, restore, import or move Operations data. Rules come from the JMRI 5.16 source. Not for Layout Editor panels, signals or Dispatcher.
---

# OperationsPro

OperationsPro moves cars by building trains. Almost every surprise is a gate in the builder that the screens do not show. This skill says how to build a railroad in the order the program needs, how the builder decides, which tool to use, and what to read before changing anything.

## Start a railroad from nothing

Ask first: staging or a loop, default loads only or custom loads, and which trains should run in what order. Then build in this order. Each step is an `ops_plan` the user sees, then `ops_apply`, with JMRI exited. Point `ops_dir` at an empty Operations folder or at one JMRI has already made.

1. **Car types and custom loads:** `add_car_type`, `add_load`. The default E and L loads already exist.
2. **Locations and tracks:** `add_location`, then `add_track` for yards, interchanges and staging. An industry is `add_industry`, which makes the spur and its schedule in one step. Staging that should send custom loads is `setup_custom_staging`. An interchange between two trains is `setup_interchange`.
3. **Routes:** `add_route`, one per train pattern, with each stop's direction, moves and train length.
4. **Trains:** `add_train`, which also puts the train on the pick up and set out lists of the tracks along its route.
5. **Cars:** `add_car`, then `place_car` on the starting track. Kernels with `set_kernel`.
6. **Check:** `ops_audit`, then `ops_dry_run`, which builds and terminates every train on a copy. Read its reports with `ops_explain_build` and fix what they say before the first real session.

A minimal working railroad is two locations with a yard each, one route between them, one train and a few cars of one type. Everything else is added to that, one plan at a time.

## How to work

- **Read before you change.** Run `ops_audit` on a railroad you have not seen, and `ops_why_not` for a car that will not move. Both read the files, so with JMRI running call `ops_live_save` first or the files lag by a minute or two.
- **Two lanes.** The file lane changes the six XML files and needs JMRI fully exited, not just the windows closed. The live lane talks to a running JMRI through its web server and the plugin's agent. Choose by what the user has open.
- **Setup changes show a plan first.** Call `ops_plan`, show the user the diff and any new audit findings, then `ops_apply`. Session corrections to a car use `ops_session` without the plan step.
- **Do not hand-edit XML with JMRI running,** and do not edit the XML at all when an action exists. JMRI rewrites whole files from memory on save and exit, and drops anything it does not store.
- **Leave move counts alone** unless asked. They steer traffic. Only `set_track_moves` and `reset_moves` change them.
- **Judge by the build report.** `ops_explain_build` reads the file JMRI wrote and names the gate behind each refusal; it beats anything worked out from the files. For a failed build or a long report, hand the job to the `ops-diagnoser` agent, which can only read. Two identical builds can differ, so compare sets of outcomes, not one run.
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

Read: `ops_explain_build`, `ops_why_not`, `ops_audit`, `ops_list`, `ops_actions`, `ops_plan`, `ops_build_check`, `ops_dry_run`, `ops_backups`.
Write with JMRI exited: `ops_apply`, `ops_session`, `ops_deliver_car`, `ops_restore`, `ops_install_agent`.
Live JMRI: `ops_live_status`, `ops_train`, `ops_live_car`, `ops_live_save`, `ops_live_report`, `ops_live_automation`.

`ops_actions` lists the change actions with their fields. The plugin README has the full table.

## Facts that trip everyone

- A spur with a schedule refuses any car with no matching line. A spur with no schedule refuses every custom load.
- Default E and L cars are never routed. They take the first accepting track on the building train's own route, scheduled tracks first. A car with a final destination is always routed, whatever its load.
- A schedule acts three times: as a gate on entry, at build when the line is assigned, and on delivery when the load changes. Set Car applies it only when the track changes and the user says yes.
- Staging can send a default empty. What blocks it is a Ship Load Option that excludes E, a train that does not carry E, or no track ahead that takes E.
- Every car on a departure staging track must leave or the build fails, except in on-time mode.
- Yards ignore pick up and set out lists and the Destinations filter. Interchanges, spurs and staging filter trains; only interchanges and staging filter destinations.
- The Destinations filter holds locations, not tracks, and tests the car's final destination. With no final destination it tests the next location the train would use.
- A car set out on an interchange with Pick ups set to Any cannot be pulled by a train on the same route.
- Adding a track resets that location's move counts. Assigning a different schedule from the schedule window resets every location.
- The built year test excludes both ends. Hyphen names split only on `-(` or `-<number>`.
- Changing a car's location through JSON does not run a schedule, and a car POST without `weightTons` blanks it. JSON cannot build a train.
- Autosave writes one to two minutes after a change, and exit always writes. Edits made outside JMRI while it runs are lost.

## Out of scope

Manifest and switch list formats, printing and third-party paperwork tools, RFID and reporters, train icons on panels, locale and scale settings, migration from other programs, and version-specific bugs. Give the confirmed facts in `sessions.md` and `data-and-files.md` where they touch these, and say the rest is outside what this skill checked.

Checked against JMRI 5.16 source, tag v5.16.
