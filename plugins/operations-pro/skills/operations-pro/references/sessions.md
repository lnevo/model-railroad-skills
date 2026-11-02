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
- A route stop's `depart_time` (HH:MM) fixes the manifest time at that stop, and later stops follow from it; `wait` adds minutes there to the travel time. Both are stop fields of `add_route` and `update_stop`, and `ops_list routes` shows them.
- A train schedule holds an id, a name, a comment and a list of trains. The builder never reads the list: it reads only the active id, against a car's pick up day and a schedule line's set out day. The list matters when Apply sets each train's Build box from it.
- A car's pick up day naming a schedule that no longer exists lets the car go any day. A schedule line's set out day naming one is never used to pick a custom load, yet the line still accepts cars any day, so delete days with their lines in mind.
- With no train schedules at all, JMRI makes Sunday to Saturday on its next save. Its Restore button adds them by name.
- The active id lives at the root of the train file. Older files also hold one under options; JMRI reads that first and the root one last, so the root one wins.
- Write actions: `add_day`, `add_default_days`, `update_day` (rename or comment; everything else holds the id), `delete_day` (refused for the last day or one an automation or manual build names; schedule lines that name it are refused unless `clear_lines`, which sets them to any day; cars waiting for it are freed; if it was active, none is), `set_day_trains` (replace, add, remove, or copy the Build boxes), `apply_day` (Apply: sets every Build box from the day, the active one by default), `set_line_days` (a schedule line's set out and pick up days), and `set_active_day` (a day, Any, or none). A schedule line naming an unknown day is refused. `ops_list` type `days` lists them. Gate A1 says when the active day's list disagrees with a train's Build box.

## Automations

- Automations live in the train roster file. Actions include build, move, terminate, reset, activate and apply train schedules, go to a step on success, wait for a train to terminate, print, and generate or update CSV switch lists. "Generate CSV Switch Lists Changes" writes only locations touched by a new build; Update writes them all.
- A step with a message, a Message Yes or No step, and the print and preview steps open a modal window on the JMRI computer, and the automation waits until someone answers it. A headless JMRI, or one with no one at it, stops there. A train's own scripts, run by a build or move step, can do the same.
- The startup automation runs every time JMRI loads the train file, on every computer that opens the folder.
- In 5.16 a LogixNG action can start an automation, and starting one loads the Operations data first.
- Operations startup scripts run when the train roster loads, not at JMRI start. The automation manager loads it when it initialises, and a JSON request for trains loads it too, which is how the live tools wake the agent.
- `ops_live_automation` runs a named automation with build dialogs off and waits up to two minutes.

## Writing automations and manual builds

With JMRI exited, through `ops_plan` and `ops_apply`. `ops_list` with type `automations` or `manual_builds` shows what is there, including the step names.

- `add_automation` and `update_automation` take steps in order. Each step names `do` (the JMRI action, such as `build_train`, `move_train`, `terminate_train`, `activate_train_schedule`, `run_automation`, `goto_if_failure`, `halt`) and only the fields that action keeps: a train for train steps, a stop on that train's route for move, wait and en-route steps, an automation for run, stop, resume and wait steps, a step number for GOTO, a day for Activate. JMRI drops any other field on its next save, so the plugin refuses it.
- A step that opens a window is refused unless `allow_dialogs` is set, because it stops an unattended run. Messages are MessageFormat text: `{1}` is the train, `{2}` the stop, and a lone `'` must be written `''`.
- `update_automation` with steps replaces them all; the new steps start not yet run. `delete_automation` is refused while another automation's step names it, and clears the startup choice if it was the startup automation. `set_startup_automation` picks the one JMRI runs on load; the build check and dry run copies run it too.
- `set_manual_build` sets a train's manual build lines (gate B19): type, road, load, the stop and pick up track, a destination and destination track, a day, a count, and warn, fail or remove. Lines are checked as the Edit Train manual build window offers them: car types the train takes, a road only with a type and only one a car of that type has, the type's loads, stops on the train's route, no staging tracks, tracks that take the type, road and load. `delete_manual_build` removes them.
- Deleting a train removes its manual build. A track, location or train that a line or step still names cannot be deleted, and a train whose lines or steps name a stop cannot change route, until those are changed. Renaming a car type, road or load follows into the lines.

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

The build report has levels; Very Detailed is the default and is what every diagnosis needs, with the router level at Normal. Manifests, switch lists and CSV versions are written at build into their folders.

Manifest and switch list formats live in `Operations.xml`; the Trains window's print options live in the train file.

- Each line (loco pick up and set out, car pick up, set out and move, missing car, and the three switch list car lines) is a prefix and a list of fields. The fields are English words in the file, whatever the language, and a word JMRI does not know prints an error on the manifest. Tab, Tab2 and Tab3 are offered only with tabs on. The missing car line has no prefix.
- With "same as manifest" on, which is the default, a save writes the switch list lines, prefixes and orientation from the manifest ones, so a switch list setting of its own is lost until it is turned off.
- Printed phrases (manifest, switch list and column headers) are stored only when they differ from JMRI's wording. Most go through Java's message format: `{0}` and the like are filled in, a single apostrophe starts quoted text, so `''` prints one, and an unmatched brace prints an error on the manifest instead of the text.
- Colours are names (black, darkGray, gray, lightGray, white, red, pink, orange, yellow, green, blue, magenta, cyan, brown) or `#RRGGBB`; a hex value equal to a name is saved as the name. The logo is stored only when set. Orientation is stored in the words JMRI shows in its own language (Portrait, Landscape, 4.25 x 11, 3.25 x 11 in English); the plugin writes the English ones.
- A train can carry its own railroad name and logo for its manifest, and can leave out times.
- Write actions: `set_manifest_options` (page, font, colours, tabs, what prints, switch list options, CSV files, print preview and build report printing), `set_manifest_format` (one line's prefix and fields), `set_manifest_text` (one phrase, or back to JMRI's), `set_train_manifest` (a train's railroad name, logo and times). `ops_list` type `manifest` shows every setting, with JMRI's default where the file has none. The control limits (field lengths) and the day name mapping are not written.

Checked against JMRI 5.16 source, tag v5.16.
