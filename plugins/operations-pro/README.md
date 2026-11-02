# Operations Pro for Claude Code

Build, change, run and understand a JMRI OperationsPro railroad with Claude, without teaching it OperationsPro first. The skill carries the rules the program applies, and the tools do the work at the level of the railroad rather than one field at a time, with a change plan you see before anything is written.

**Status: in development.** 85 actions and 21 tools. It can set up a railroad from nothing, audit one, change the files with JMRI exited, run trains in a running JMRI, and explain what the builder did and why. Rules are written for JMRI 5.16.

## What it helps with

OperationsPro is powerful, and much of how it behaves isn't obvious from its screens. This plugin works across the whole job:

- **Building a railroad:** locations, tracks, industries with their schedules, routes, trains, loads, cars, locomotives and consists, divisions, train schedule days, and manifest and switch list formats, in the order the program needs, with a change that spans many screens made in one step. Start from an empty Operations folder or from one you already have.
- **Generating traffic:** custom loads, schedules, staging (including load conversion on arrival, planned pick ups for a swap, and the home division rule), interchanges and multi-train routing that send cars where you intend.
- **Running sessions:** building and terminating trains, Set Car, manual corrections, and resetting between sessions.
- **Finding out why:** explaining a failed build, a stuck car, a held car, drained spurs or full yards from the build report and the data, with the setting that changes it.
- **Yards and special moves:** classification, arrival and departure tracks (including the A/D track recipe), switchers, cabooses and the two traps that hide them, kernels, passenger blocking and buffer cars. Locomotive changes, helpers and caboose changes en route are written with `set_train_leg` (leg 2 and leg 3 of Edit Train), and `set_engine_moves` rests or promotes a locomotive. Unit trains are a modelling choice, not a builder setting.
- **Looking after the data:** auditing it, backing it up on demand (`ops_backup_now`), and recovering it: `ops_backups` and `ops_restore` work on a folder with a missing or corrupt file, and `ops_restore` with `file` puts back just that one file. A folder with no Operations files starts as an empty railroad. Cars are loaded by turning each CSV row into an `add_car` action; there is no import action, and JMRI's own importer errors are not diagnosed. Moving between JMRI versions is outside what was checked.
- **Paperwork settings:** page, font, colours, tabs, which fields print, phrase text, per-train railroad name and logo path, and CSV files at build. It does not print, and it cannot set a logo's image type or size, bold text, or two fonts.

## Parts

| Part | What it does | State |
|---|---|---|
| Skill | Verified rules for setup, routing, staging, schedules, sessions and diagnosis | Done |
| Write actions | Make a multi-screen change in one step, with JMRI exited. `ops_actions` lists them | Done |
| Data parser | Reads the six Operations XML files | Done |
| `why_not` | Walks each requirement in the builder's order and names the setting that blocks a car | Done |
| `audit` | Finds problems across the railroad, such as a car type no train can carry, a locomotive no train takes, or a schedule with only one destination | Done |
| `explain_build` | Reads a build report and names the gate behind each refusal | Done |
| Diagnosis agent | `ops-diagnoser`: reads reports and files with reading tools only | Done |
| Build check | Runs JMRI's own builder on copies, several times each side, and compares the results | Done |
| Dry run | Builds and terminates every enabled train on a copy and reports | Done |
| Session control | Build, move, terminate and reset trains in a running JMRI | Done |
| Demo railroad | An invented railroad with deliberate faults, for tests | Done, builds in real JMRI 5.16 |
| MCP server | Exposes the tools below to Claude | Done |



## Skill

`skills/operations-pro/` is the guidance. The entry file says how to work, which tool to reach for and the dozen facts that trip most people. Nine reference files hold the detail, one per question: the builder's gate order (the ids `ops_why_not` and `ops_explain_build` print), loads and schedules, staging, routing, move counts and balance, special cars, sessions, data and files, and diagnosis with the audit finding names. Each rule was checked against the JMRI 5.16 source or tested in JMRI 5.16, except where a file says a point was not checked; modelling choices are labelled as such.

## Tools

| Tool | Changes files? | What it does |
|---|---|---|
| `ops_actions` | No | Lists the change actions and their fields |
| `ops_plan` | No | Works out a change and shows the diff and any new audit findings |
| `ops_apply` | Yes | Applies a plan |
| `ops_session` | Yes | Applies a car correction without a separate plan step |
| `ops_deliver_car` | Yes | Sets a car on a track and runs that track's schedule, as Set Car does. Refuses a car already on that track, as Set Car runs a schedule only when the track changes |
| `ops_why_not`, `ops_audit`, `ops_list` | No | Explain a stuck car from the files, check the railroad, list records |
| `ops_explain_build` | No | Reads a train's build report: outcome, each stop's moves, excluded cars and each car's story with gate ids |
| `ops_build_check` | No | Compares real builds before and after a plan, on copies |
| `ops_dry_run` | No | Runs a whole session on a copy; each train comes back with its build report read as `ops_explain_build` reads it (`detail`: summary, normal, full) |
| `ops_backups`, `ops_restore` | Restore only | Lists backup sets and puts one back, or with `file` only one lost or unreadable file; both work on a broken folder |
| `ops_backup_now` | Adds a backup set | Takes a backup set now, in JMRI's own `backups` folder, as `ops_apply` does before a change |

These work on a running JMRI, and don't need it exited:

| Tool | Needs the agent? | What it does |
|---|---|---|
| `ops_live_status` | No | Shows each train's state and whether the agent is running |
| `ops_train` | Build and reset only | Builds, moves, terminates or resets one train or all of them; a build answers with the report read as `ops_explain_build` reads it (`detail`: summary, normal, full) |
| `ops_live_car` | Yes | Sets a car on a track and runs the track's schedule on the named car, without Set Car's track-change test or any prompt |
| `ops_live_save` | Yes | Saves the Operations files now, so the reading tools see the latest state |
| `ops_live_report` | Yes | Reads the end of a build report or manifest |
| `ops_live_automation` | Yes | Runs a named automation |
| `ops_install_agent` | | Copies the agent beside the Operations files and plans its startup entry |

## Diagnosis

`ops_explain_build` reads the file JMRI writes in `buildstatus` when a train is built. Every line is matched against the messages JMRI 5.16 prints, so the result says what the builder did rather than what the files suggest: the failure cause with its gate, each stop's moves, the cars excluded before the search and why, and for each car the tracks tried, the refusal and the screen that changes it. Pass a car to follow one car, or paste report text from another computer. JMRI writes every detail level to the file whatever the Build Report setting shows; only the router lines depend on the router level.

The `ops-diagnoser` agent does this with reading tools only. Hand it a failed build or a long report and it returns the cause, the report lines, and the setting that fixes it, without changing anything.

## Running trains in a live JMRI

JMRI's JSON server can move and terminate a train, but can't build or reset one. So this plugin adds a small agent: a script that JMRI runs from its Operations startup scripts. It takes commands through a Memory that the JSON server can set.

To set it up:

1. In JMRI's Preferences, add a Startup item to start the web server.
2. Exit JMRI, run `ops_install_agent`, and apply its plan with `ops_apply`.
3. Start JMRI. The first live tool call loads Operations if it isn't already open, and that starts the agent.

Set `JMRI_URL` if JMRI isn't at `http://localhost:12080`. It can be another computer.

- **Builds don't stop on a dialog.** A failed build, or a good build with warnings, normally opens a window on the JMRI computer and waits for someone to click it. The agent turns those windows off for the build, along with the staging track prompts, then puts the settings back. With prompts off, JMRI chooses the staging track itself.
- **A built train isn't rebuilt by accident.** Building again resets the train, so it needs `rebuild`. A train en route can't be built or reset.
- **A refused Set Car puts the car back.**
- **Only the listed commands run.** The agent doesn't evaluate text it's sent. Anyone who can reach JMRI's web server can send commands, as they already can for turnouts and sensors.
- **A Store of tables in JMRI** can save the agent's three `IMOPSPRO_` Memories. They're harmless: they hold the agent version, the last command and the last reply (which can be a whole build report).

## Changing data safely

Unlike the read-only tools in `model-railroad-skills`, this plugin changes your data, which is why it's a separate install.

- **File changes need JMRI fully exited.** JMRI holds Operations data in memory and writes whole files on save, so an edit made while it's running can be overwritten. The tools check this computer for a running JMRI. They can't see another computer that has the same folder open, so close it there too.
- **Every file change is a transaction:** plan and show the diff, then back up, apply, audit, and restore the backup if anything fails. Backups go in JMRI's own `backups` folder, so its Restore window lists them too.
- **A plan is tied to the files it saw.** If the files change afterwards, the plan is refused.
- **No changes while a train is built,** apart from cars that aren't on a train.
- **Move counts are preserved.** They steer the builder, so resetting them quietly changes your traffic. Only `set_track_moves` and `reset_moves` change them, and a final check refuses anything else that would.
- **Derived fields are left alone.** A car's destination, for example, depends on where it sits in a train's route. Those changes go through JMRI.
- **Settings JMRI ignores or drops are refused,** such as a pickup list on a yard or a schedule on a non-spur.
- **A locomotive model holds one set of values.** JMRI keeps type, length, horsepower, weight and B unit on the model, not on the engine, so an engine that differs from the rest of its model is refused, and `update_engine_model` changes them on every engine of it. A railroad with no engine file gets the one JMRI would write, with its default models, types and lengths. A train's locomotive model and road take only what JMRI's Edit Train window offers: a model in the roster, a road of an engine of that model, or blank for any.
- **New audit errors block a plan** until you accept them. Renaming something that already had a fault reports that fault under its new name, so a block isn't always a new problem.

The builder makes random choices, so two identical builds can differ. The build check counts a train as changed only when none of its results after the plan appeared before it, and shows partial overlaps separately. A rare outcome can still be missed.

## Limits

- It only ever works on the Operations folder you point it at, and JMRI's checks run on temporary copies.
- `ops_build_check`, `ops_dry_run` and `ops_deliver_car` need JMRI installed. Set `JMRI_HOME` if it isn't found.
- It does not write a train's build or terminate script, a track's type (empty it, delete it and add the new type), a car's final destination (it is derived), a car added to a built train (use a manual build line before the build), or Track Analysis. Printing itself, CSV column content and web or tablet manifests are outside it.
- JMRI's JSON server doesn't cover schedules, Operations routes, loads or divisions, so those are changed through the files.
- A train's own build or terminate script runs as usual, and can still open a window or hang. So can an automation step with a message, a Message Yes or No step or a print step: JMRI shows a modal window and the run waits there. `add_automation` and `update_automation` refuse those unless `allow_dialogs` is set, and warn about train scripts, wait steps and steps that start an outside program.
- `ops_explain_build` reads a file, so for a JMRI on another computer copy the report or paste its text. `ops_live_report` fetches only the end of it.
- Rules and report wording come from the JMRI 5.16 source. Other versions may differ; a line the reader does not recognise is listed as unparsed rather than guessed at.

## Use and test

Set `OPS_DIR` to your Operations folder, or pass `ops_dir` on each call. Tools read the files on disk, which can lag a running JMRI by a minute or two. A gate that depends on the build itself, such as a random draw or timing against another train, reports `not_checked`.

```
python3 -m unittest discover -s plugins/operations-pro/tests
```

The tests hold the gates to `tests/fixtures/demo/jmri_oracle.json`, which is what real JMRI 5.16 said about the demo railroad; `tests/jmri_oracle.py` regenerates it. Three variants of the demo (`build`, `space`, `aggressive`) reach the gates the demo does not, such as on-time order, pools and manual build lines, each with its own answer from JMRI; `tests/variant_fixtures.py` rebuilds them. The report reader is held to `tests/fixtures/demo/buildstatus`, the reports real JMRI 5.16 wrote for the same railroad together with what the builder returned; `tests/report_fixtures.py` regenerates those. Where JMRI is installed, the write tests also make it load and save what was written, and `tests/test_live.py` starts a real JMRI for each live test. Both skip that otherwise.

## License

MIT, as for the rest of this repository.
