# Sessions: build, move, terminate, reset

## Build

- Build assigns a train, a destination and route positions to each car it takes, and leaves per-stop counters in memory. It also writes the build report, manifest and switch lists.
- Build on a built train resets it first and ignores a refused reset. The plugin's `ops_train` refuses to build a built train unless `rebuild` is set, and refuses a train en route.
- A failed build, and a good build with warnings, open a dialog on the JMRI computer and wait. So do the staging prompts. `ops_train` turns build messages and the prompts off for the build and puts them back; JMRI then chooses the staging track. A train's own build script, and a Message step in an automation, can still open a window.
- The Build box is honoured by Build All and automations, not by the train's own Build button.
- Status codes separate Build Failed from Partial. The Report button shows only for Build Failed. A report's date tells you if it is stale.
- In on-time build order a train may not depart earlier than the last built train, and the builder waits up to two minutes for another build to finish.
- Build order among trains: `ops_train` with `all` builds enabled, unbuilt trains in departure time order.

## Move and terminate

- Move takes a location name and walks the train through each stop to it. The JSON server does the same, and answers 428 for an unbuilt train. Cars arriving at their destination lose their train, so Move frees them for the next build before terminate.
- Terminate is a move through every remaining stop. Cars follow only if they were assigned at build; cars left where they started were never in the train. Terminating into staging fills the track.
- A car in a train en route is unavailable to other builds. Do not terminate a train until it truly reaches its terminus; use Move to keep its position true.
- Terminate and move run with no builder dialogs.

## Reset

- Reset returns the train and its cars to their pre-build state. A load generated from staging goes back to E; the previous final destination and schedule item are restored.
- A train en route cannot be reset. Nothing but a Restore rolls move counts back.

## Set Car and edits after build

- Set Car on a built train checks that the train can serve the car and carry its load, then adds the car anywhere on the train's route. It sets the train modified.
- Set Car runs a track's schedule only when the track changes and the user says yes. `ops_deliver_car` and `ops_live_car` do the same, on the lead car, by running `scheduleNext` then `loadNext` in that order.
- The Yardmaster and Conductor windows can add cars to a train at its location through the cars table. The web versions were not checked.
- Editing routes, tracks or trains while a train is built is unsafe because the build's counters live only in memory. The plugin refuses file changes while any train is built, apart from cars not on a train.
- The plugin's `place_car` sets a car's location without a schedule or a move count. `clear_final_destination` is the first step in freeing a stuck car; then set its track, then deliver it to re-apply the schedule.

## Train schedules, days and time

- A train schedule is a named day. Activate sets the active day; Apply sets each train's Build box for that day. They are two separate actions in automations. The report header shows the active schedule, and a wrong one is a common cause of nothing building.
- Schedule days never use the calendar. Schedule lines carry a set out day and a pick up day that are tested against the active day.
- Manifest and report dates come from the JMRI timebase, which may be a fast clock.
- On-time mode uses departure times and a dwell time, default 60. Otherwise departure time only feeds expected times on paperwork and the timing check against other trains' pulls.
- The plugin's `set_active_day` sets the active day in the files. Days themselves are not written yet.

## Automations

- Automations live in the train roster file. Actions include build, move, terminate, reset, activate and apply train schedules, go to a step on success, wait for a train to terminate, print, and generate or update CSV switch lists. "Generate CSV Switch Lists Changes" writes only locations touched by a new build; Update writes them all.
- A Message step opens a window on the JMRI computer.
- In 5.16 a LogixNG action can start an automation, and starting one loads the Operations data first.
- Operations startup scripts run when the train roster loads, not at JMRI start. The automation manager loads it when it initialises, and a JSON request for trains loads it too, which is how the live tools wake the agent.
- `ops_live_automation` runs a named automation with build dialogs off and waits up to two minutes. The plugin can run automations but not create them.

## Session patterns

- Build, print, terminate in groups so a later group can draw on cars freed by an earlier one. An automation with wait-for-terminate steps does this.
- A dry run before a session: `ops_dry_run` builds and terminates every enabled train on a copy and reports, changing nothing. A manual backup, build and terminate all days, then Restore does the same by hand.
- Only one running JMRI may own the files. Any builder dialog opens on the computer running JMRI.

## Live lane

| Need | Tool |
|---|---|
| Train states, agent running | `ops_live_status` |
| Build, move, terminate, reset | `ops_train` |
| Set a car and run the schedule | `ops_live_car` |
| Save now so the file tools see the latest | `ops_live_save` |
| End of a build report or manifest | `ops_live_report` |
| Run an automation | `ops_live_automation` |

Move and terminate work on stock JMRI with the web server on. Build, reset, set car, save, report and automation need the agent, installed once with `ops_install_agent` and `ops_apply` with JMRI exited. The agent takes commands through a Memory and answers in another; it runs only the listed commands.

## Paperwork facts

The build report has levels; Very Detailed is the default and is what every diagnosis needs, with the router level at Normal. Manifests, switch lists and CSV versions are written at build into their folders. Format options are outside what this skill checked.

Checked against JMRI 5.16 source, tag v5.16.
