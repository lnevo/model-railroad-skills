# Operations Pro for Claude Code

Tools for setting up, checking and running JMRI OperationsPro with Claude. The aim is full management of an Operations railroad by an AI agent, with a change plan you can see first.

**Status: in development.** It can read and audit a railroad, change its files with JMRI exited, and run trains in a running JMRI, and the skill tells Claude how the builder decides. The diagnosis agent is still to come. This page describes the plan as well as what exists today. Rules are written for JMRI 5.16.

## What it helps with

OperationsPro is powerful, and much of how it behaves isn't obvious from its screens. This plugin works at the level of the railroad, not single fields, across the whole job:

- **Setting up:** building locations, tracks, routes, trains and rolling stock in the right order, and making changes that span many screens in one step.
- **Generating traffic:** custom loads, schedules, staging, interchanges and multi-train routing that send cars where you intend.
- **Finding out why:** explaining a failed build, a stuck car, a held car, drained spurs or full yards from the data and the build report.
- **Yards and special moves:** classification, arrival and departure tracks, switchers, locomotive changes, cabooses, kernels, unit trains, passenger blocking and buffer cars.
- **Running sessions:** building and terminating trains, handling manual changes, and resetting between sessions.
- **Looking after the data:** auditing it, importing it, backing it up, recovering it, and moving between JMRI versions.

## Planned

| Part | What it does | State |
|---|---|---|
| Data parser | Reads the six Operations XML files | Done |
| Demo railroad | An invented railroad with deliberate faults, for tests | Done, builds in real JMRI 5.16 |
| `why_not` | Walks each requirement in the builder's order and names the setting that blocks a car | Done |
| `audit` | Finds problems across the railroad, such as a car type no train can carry or a schedule with only one destination | Done |
| MCP server | Exposes the tools below to Claude | Done |
| Write actions | Make a multi-screen change in one step, with JMRI exited. `ops_actions` lists them | Done |
| Build check | Runs JMRI's own builder on copies, several times each side, and compares the results | Done |
| Dry run | Builds and terminates every enabled train on a copy and reports | Done |
| Session control | Build, move, terminate and reset trains in a running JMRI | Done |
| Skill | Verified rules for setup, routing, staging, schedules and sessions | Done |
| Diagnosis agent | Reads long build reports without changing anything | Planned |

## Skill

`skills/operations-pro/` is the guidance. The entry file says how to work, which tool to reach for and the dozen facts that trip most people. Nine reference files hold the detail, one per question: the builder's gate order (the ids `ops_why_not` prints), loads and schedules, staging, routing, move counts and balance, special cars, sessions, data and files, and diagnosis with the audit finding names. Every rule in them was checked against the JMRI 5.16 source; modelling choices are labelled as such.

## Tools

| Tool | Changes files? | What it does |
|---|---|---|
| `ops_why_not`, `ops_audit`, `ops_list` | No | Explain a stuck car, check the railroad, list records |
| `ops_actions` | No | Lists the change actions and their fields |
| `ops_plan` | No | Works out a change and shows the diff and any new audit findings |
| `ops_build_check` | No | Compares real builds before and after a plan, on copies |
| `ops_dry_run` | No | Runs a whole session on a copy |
| `ops_apply` | Yes | Applies a plan |
| `ops_session` | Yes | Applies a car correction without a separate plan step |
| `ops_deliver_car` | Yes | Sets a car on a track and runs that track's schedule, as Set Car does |
| `ops_backups`, `ops_restore` | Restore only | Lists backup sets and puts one back |

These work on a running JMRI, and don't need it exited:

| Tool | Needs the agent? | What it does |
|---|---|---|
| `ops_live_status` | No | Shows each train's state and whether the agent is running |
| `ops_train` | Build and reset only | Builds, moves, terminates or resets one train or all of them |
| `ops_live_car` | Yes | Sets a car on a track and runs the track's schedule, as Set Car does |
| `ops_live_save` | Yes | Saves the Operations files now, so the reading tools see the latest state |
| `ops_live_report` | Yes | Reads the end of a build report or manifest |
| `ops_live_automation` | Yes | Runs a named automation |
| `ops_install_agent` | | Copies the agent beside the Operations files and plans its startup entry |

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
- **A Store of tables in JMRI** can save the agent's three `IMOPSPRO_` Memories. They're harmless: they hold only the agent version and the last command.

## Changing data safely

Unlike the read-only tools in `model-railroad-skills`, this plugin changes your data, which is why it's a separate install.

- **File changes need JMRI fully exited.** JMRI holds Operations data in memory and writes whole files on save, so an edit made while it's running can be overwritten. The tools check this computer for a running JMRI. They can't see another computer that has the same folder open, so close it there too.
- **Every file change is a transaction:** plan and show the diff, then back up, apply, audit, and restore the backup if anything fails. Backups go in JMRI's own `backups` folder, so its Restore window lists them too.
- **A plan is tied to the files it saw.** If the files change afterwards, the plan is refused.
- **No changes while a train is built,** apart from cars that aren't on a train.
- **Move counts are preserved.** They steer the builder, so resetting them quietly changes your traffic. Only `set_track_moves` and `reset_moves` change them, and a final check refuses anything else that would.
- **Derived fields are left alone.** A car's destination, for example, depends on where it sits in a train's route. Those changes go through JMRI.
- **Settings JMRI would drop are refused,** such as a pickup list on a yard or a schedule on a non-spur.
- **New audit errors block a plan** until you accept them. Renaming something that already had a fault reports that fault under its new name, so a block isn't always a new problem.

The builder makes random choices, so two identical builds can differ. The build check counts a train as changed only when none of its results after the plan appeared before it, and shows partial overlaps separately. A rare outcome can still be missed.

## Limits

- It only ever works on the Operations folder you point it at, and JMRI's checks run on temporary copies.
- `ops_build_check`, `ops_dry_run` and `ops_deliver_car` need JMRI installed. Set `JMRI_HOME` if it isn't found.
- Not written yet: engines, divisions, train schedule days, manual builds, automations and manifest formats. An automation can be run, but not created.
- JMRI's JSON server doesn't cover schedules, Operations routes, loads or divisions, so those are changed through the files.
- A train's own build or terminate script runs as usual, and can still open a window or hang. So can a Message step in an automation.
- Rules come from the JMRI 5.16 source. Other versions may differ.

## Use and test

Set `OPS_DIR` to your Operations folder, or pass `ops_dir` on each call. Tools read the files on disk, which can lag a running JMRI by a minute or two. A gate that depends on the build itself, such as a random draw or timing against another train, reports `not_checked`.

```
python3 -m unittest discover -s plugins/operations-pro/tests
```

The tests hold the gates to `tests/fixtures/demo/jmri_oracle.json`, which is what real JMRI 5.16 said about the demo railroad. `tests/jmri_oracle.py` regenerates it. Where JMRI is installed, the write tests also make it load and save what was written, and `tests/test_live.py` starts a real JMRI for each live test. Both skip that otherwise.

## License

MIT, as for the rest of this repository.
