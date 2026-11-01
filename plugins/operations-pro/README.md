# Operations Pro for Claude Code

Tools for setting up, checking and running JMRI OperationsPro with Claude. The aim is full management of an Operations railroad by an AI agent, with a change plan you can see first.

**Status: in development, not ready to use.** It isn't listed in the marketplace yet, and this page describes the plan as well as what exists today. Rules are written for JMRI 5.16.

## The problem

One idea in OperationsPro often means changes across many screens. Before a new car type can move, the location, tracks, route and each train all have to allow it. When one setting is missed, the car stays put, and the reason is somewhere in the build report.

This plugin works at the level of the railroad, not single fields. You ask why a car won't move, or ask for a new flow of traffic, and it deals with the screens involved.

## Planned

| Part | What it does | State |
|---|---|---|
| Data parser | Reads the six Operations XML files | Written, not yet tested |
| Demo railroad | An invented railroad with deliberate faults, for tests | Written, not yet tested |
| `why_not` | Walks each requirement in the builder's order and names the setting that blocks a car | In progress |
| `audit` | Finds problems across the railroad, such as a car type no train can carry or a schedule with only one destination | In progress |
| MCP server | Exposes these tools to Claude | In progress |
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

## License

MIT, as for the rest of this repository.
