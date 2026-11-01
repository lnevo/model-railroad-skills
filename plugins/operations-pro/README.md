# Operations Pro for Claude Code

Tools for setting up, checking and running JMRI OperationsPro with Claude. The aim is full management of an Operations railroad by an AI agent, with a change plan you can see first.

**Status: in development.** The first stage works and only reads: it never changes your files. This page describes the plan as well as what exists today. Rules are written for JMRI 5.16.

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
| MCP server | Exposes these tools to Claude as `ops_why_not`, `ops_audit` and `ops_list` | Done, read-only |
| Write actions | Make a multi-screen change in one step | Planned |
| Build check | Runs JMRI's own builder on a copy and compares the reports before and after | Planned |
| Session control | Build, move and terminate trains in a running JMRI | Planned |
| Skill | Verified rules for setup, routing, staging, schedules and sessions | Planned |
| Diagnosis agent | Reads long build reports without changing anything | Planned |

## Changing data safely

Unlike the read-only tools in `model-railroad-skills`, this plugin will change your data, which is why it's a separate install. The planned rules are:

- **File changes need JMRI fully exited.** JMRI holds Operations data in memory and writes whole files on save, so an edit made while it's running can be overwritten.
- **Every file change is a transaction:** back up, show the diff, apply, audit, and restore the backup if the audit fails.
- **Move counts are preserved.** They steer the builder, so resetting them quietly changes your traffic.
- **Derived fields are left alone.** A car's destination, for example, depends on where it sits in a train's route. Those changes go through JMRI.

## Limits

- It only ever works on the Operations folder you point it at.
- JMRI's JSON server has no train build action and doesn't cover schedules, Operations routes, loads or divisions, so those need another route.
- Rules come from the JMRI 5.16 source. Other versions may differ.

## Use and test

Set `OPS_DIR` to your Operations folder, or pass `ops_dir` on each call. Tools read the files on disk, which can lag a running JMRI by a minute or two. A gate that depends on the build itself, such as a random draw or timing against another train, reports `not_checked`.

```
python3 -m unittest discover -s plugins/operations-pro/tests
```

The tests hold the gates to `tests/fixtures/demo/jmri_oracle.json`, which is what real JMRI 5.16 said about the demo railroad. `tests/jmri_oracle.py` regenerates it.

## License

MIT, as for the rest of this repository.
