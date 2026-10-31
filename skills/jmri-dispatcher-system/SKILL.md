---
name: jmri-dispatcher-system
description: Sets up, runs and troubleshoots the stock JMRI Dispatcher System jython package (jython/DispatcherSystem), covering Stage 1 and Stage 2, station blocks marked by block comments, signal mast placement, transit creation, modal dialogs and the Set Train Facing Direction dialog. Use when someone marks stations, runs Stage 1, sees a Dispatcher System error or a stalled run, finds transits or MoveTo sensors missing, or a dispatched train moves the wrong way. Failures are fixed in the panel and tables data, never by patching the package. Not for the plain JMRI Dispatcher window without this package.
---

# JMRI Dispatcher System

Dispatcher System reads a Layout Editor panel, then builds signal mast logic, sections, transits, train info files, station sensors and panel icons. Fix inputs and run it again. Leave the package files alone.

## Before Stage 1

Have all of this in place:

- Track, blocks and signal masts on a Layout Editor panel.
- A length on every block. The check warns if one is missing, and lengths weight the route search.
- An occupancy sensor on every block. The check warns if one is missing.
- At least one roster entry with a speed profile. Without one, Stage 1 stops with "No roster entries".
- At least two station blocks.

Start it from `jython/DispatcherSystem.py` or `jython/DispatcherSystem/DispatcherSystem.py`, with the tables and panels loaded. The window has two buttons, Stage1 and Stage2.

Do not name your own panel "Dispatcher System". The package skips a Layout Editor panel with that name when it looks for masts.

## Station blocks

- Put the word `stop` in the block's Comment field to make it a station.
- Treat any comment containing those four letters, in any case, as a station. The test is `"stop" in comment.lower()`.
- Write "not a station" on a block that must not be one. "not a stop", "non-stop" and "stopper" all match and make it a station.
- Expect every turntable and traverser block to become a station. No comment is needed.
- Put every station block on a Layout Editor panel. A `stop` comment on a block with no layout block shows "Probably trying to set a station for non-existant block", then the script dies with a deliberate NameError on `xxxxstopxxxxx`.
- Avoid `MoveTo` and `MoveInProgress` in your own sensor user names. Stage 1 deletes every sensor whose user name contains either string.

Each station gets the sensors `MoveTo<block>_stored` and `MoveInProgress<block>`, with spaces in the block name changed to underscores.

## Signal masts

- Give every mast a user name with no colon in it. Sections are named `MastA:MastB`, and the package splits that name on `:` and compares each part with the mast's user name. A mast with no user name fails this, and virtual mast system names contain colons.
- Put a mast on the far side of every station block, including the buffer end of a stub. The destination end looks up the section that holds the mast before the block, then takes the other mast in that section name.
- Treat the mast behind a starting block as optional. For stubs the package starts from the second mast.
- Put a mast between each pair of stations. An edge with no mast in its path is dropped from the graph with no dialog.
- Use a virtual mast where there is no real signal. The package only asks for SignalMast beans on the panel.
- Bind masts at real block boundaries. The lookup between two blocks starts from the connection between them, so a mast on an anchor with the same block on both sides is not found. Split the block, and reuse the occupancy sensor if the track is one electrical section.
- Answer Yes to the "have the same sensor" check if the sharing is deliberate. It is a warning and the run continues.
- On an end bumper, use the slot for the direction of travel toward the bumper. That is the eastbound slot on a right-end bumper and the westbound slot on a left-end one. On vertical track, use westbound at the top of the panel and eastbound at the bottom. A bumper has only one connection, and the other slot resolves to no block, giving "No facing block found for destination mast".
- Leave generated section names alone. A hand-renamed section breaks the mast lookup.

## Stage 1: what it does

Stage 1 runs in this order:

1. Stores a backup as `<panel>_backup.xml` next to the loaded panel file, numbered if one exists.
2. Runs the checks for sensors, shared sensors, stations, lengths and speed profiles.
3. Deletes icons, the `Run Dispatcher` Logix, all transits, all signal mast logic and all sections.
4. Deletes its control sensors and every MoveTo sensor. Forward stopping sensors are saved first and restored later.
5. Enables advanced routing and runs Discover for signal mast pairs.
6. Generates sections, adds the `Run Dispatcher` Logix and adds icons.
7. Deletes every file in `preference:dispatcher/traininfo/`, then builds transits and two train info files per route: `_fwd.xml` and `_rvs.xml`.

Plan around these effects:

- Do not rely on anything hand-made in those tables. Manual signal mast logic pairs, transits and sections are gone after Stage 1, so make the panel good enough for Discover to find them.
- Move any train info file you want to keep out of the traininfo folder first.
- Store after Stage 1 finishes, then restart. Only the backup is written automatically. The final dialog says "A store and restart is recommended."
- Run Stage 1 again after any change to blocks, masts or station comments. "Route graph out of date. Regenerate Dispatcher System" means a train info file is missing.

## Stage 2

Click Stage2 and set these in the Dispatcher options, then save them from the Dispatcher frame:

- Use connectivity from Layout panels.
- Trains from Roster.
- Layout has block detection hardware.
- Automatically allocate Sections to Active Trains.
- Automatically set turnouts when a Section is allocated.
- Apply Connections Turnout Delay.
- SignalMasts/SML.
- The layout scale, and the scale in Preferences under Warrants so trains stop correctly.

Start running with the Run Dispatcher System control. It fires the `Run Dispatcher` Logix, which runs `program:jython/DispatcherSystem/Startup.py`.

## Modal dialogs

- If Stage 1 looks idle, look for a dialog first. The package uses `JOptionPane` with no parent window, and work stops until it is answered. It can sit behind other windows.
- In the sensor, shared sensor, station and length checks, Yes continues. No and Cancel stop the run.
- Do not close a check dialog with the window button. In most checks that takes no branch and the run carries on, as if you had said Yes.
- Treat "All Sections, Transits and TrainInfo Files produced." as the only sign of success.

## The facing dialog

"Set Train Facing Direction" asks: "What way is train facing towards highlighted block?"

- Look at the highlighted block on the panel and answer for that block, not for compass direction or the way the train will leave. It is a neighbour of the station.
- Answer `forward` if the front of the loco points at the highlighted block. Answer `reverse` if the front points away from it.
- Expect the stored value to be the opposite of your answer. `set_train_direction` stores `reverse` for `forward`, and the reverse for `reverse`. The setup and status tables convert it back for display.
- Do not treat that swap as a bug. The stored value is the direction of travel on the way in to the station from the highlighted block. When the next move goes back out through that block, `set_direction` changes direction again, so a train answered `forward` leaves on `_fwd.xml` running forward.
- Expect `_rvs.xml` for a train that continues out the other side after a `forward` answer. It faces the highlighted block and is moving away from it, so it backs out.
- Cancelling is not possible. The dialog repeats until answered.
- To correct a train that went the wrong way, use Modify Dispatcher System and tick Change Dir on its row. That swaps both the throttle direction and the stored direction.

## Diagnosing failures

Fix the panel or tables and rerun Stage 1. Do not patch, wrap or skip `CreateTransits`, `CreateIcons`, `Startup.py` or `TransitCreationTool`. The Logix and the scripts load the stock files from `program:` paths, so local edits belong to the JMRI install and not to your layout.

| Symptom | Cause | Fix |
|---|---|---|
| "Probably trying to set a station for non-existant block" | `stop` comment on a block not on a panel | Remove the comment or add the block to a panel |
| "You have not put signals between two stopping blocks, one being X" | No section contains block X | Add masts around X |
| "There is probably a missing signal mast in block X" | No section pairs the previous mast with X | Add the far-side mast for X. The script crashes after this dialog until you do |
| "there must be signal masts between and beyond each pair of stopping points" | Empty mast list for a station pair | Add a mast or remove a station |
| `WARNING: No signal masts could be found for path` in script output | Same, and the path is skipped | Same |
| `Signal Mast "B" is not reachable from "A"` | Mast list holds a pair Discover did not create | See below |
| `SignalMast Pair "A" to "B" does not have a Section associated with it` | Pair exists with no section | Check the mast bindings and the blocks between A and B |
| "No facing block found for destination mast X" | Mast in the wrong slot, or not at a boundary | Rebind the mast |
| "The routine at present requires section names to be the names of the signal masts" | Renamed section, or colon in a mast name | Fix the name and rerun |
| "No roster entries" | No roster entry has a speed profile | Add a speed profile |
| A station pair has no transit and no error | No path, or no mast on the path, so the edge was dropped | Check routing and masts between them |

The "not reachable" case kills the whole run:

- `create_transit` calls `TransitCreationTool.addNamedBean` outside its `try`, and that call throws `JmriException` when the signal mast logic has no such pair. Nothing catches it.
- Later failures in `createTransit` are caught, but the `transit.getUserName()` call after the `try` then fails on `None`.
- Expect leftovers after either failure: transits with `_temp` in their names, since the rename runs after the loop, and an incomplete traininfo folder.
- Find the pair in the JMRI log. The first mast comes from the first section that holds the start block and the next mast, so the two may face opposite ways. Fix the mast bindings or blocks so Discover builds the legal pair, then run Stage 1 again.

If Stage 1 fails after the delete steps, sections and transits are gone. Finish the fix and rerun, or reload `<panel>_backup.xml`.

Checked against JMRI source at commit bd71f7f (2026-10-31).
