# Data and files

## The six files

All in `operations/` under the profile's user files unless the Settings say otherwise.

| File | Holds |
|---|---|
| `Operations.xml` | Settings, manifest and switch list formats, control values |
| `OperationsLocationRoster.xml` | Divisions, locations and tracks, schedules |
| `OperationsRouteRoster.xml` | Routes |
| `OperationsTrainRoster.xml` | Trains, manual builds, train schedules, automations |
| `OperationsCarRoster.xml` | Roads, types, colours, lengths, owners, loads, kernels, cars |
| `OperationsEngineRoster.xml` | Models, types, lengths, consists, engines |

There is no seventh file. Generated folders beside them: `buildstatus`, `manifests`, `switchLists`, `csvManifests`, `csvSwitchLists`, `jsonManifests`, `carRouterReports`, `backups`, `autoBackups`, plus backup copies of switch lists and build status.

## How JMRI reads and writes

- Each file is read once, when Operations loads. There is no file watcher. An edit made outside JMRI while it runs is ignored until restart and overwritten by the next save of that file.
- A file is written only when its dirty flag is set, and then the whole file is regenerated from the objects. Attributes JMRI does not store are gone. Formatting and order change, so compare parsed content, not text.
- Autosave is on by default: check every minute, wait another minute if dirty, skip while a train builds, then save. So a change reaches disk after one to two minutes.
- Exit always saves dirty files through a shutdown task. Autosave off does not protect an outside edit.
- Restore is not a reload. JMRI must be fully exited before any file change, and started again afterwards.
- Writing a file makes a `.bak` of the previous one first.

## Backups

- An automatic backup set is taken when Operations initialises, default on, under `autoBackups/<date>_<nn>`.
- `backups` fills only from the Backup button, or from the plugin, which backs up before every write so JMRI's Restore window lists those sets too.
- JMRI has two restore entry points, the Restore dialog and the restore files action. Which folders each can reach was not checked.
- To move a railroad: copy all six files into the same folder of the other install with JMRI closed. Copy them as one set. The files refer to each other by id, and ids are reused: tracks are `<location>s<n>`, and a deleted track's id is given to the next track added. Copying only the location and route files from a test copy into the real railroad can leave a car's track id pointing at a different track, and the car then sits on it with no warning from the audit. A car whose track no longer exists is caught (`car-unplaced`; `ops_why_not` B1). Compare the cars' tracks after a partial copy.
- A lost or damaged file is recoverable, and the recovery tools work on the broken folder:

| Step | Tool |
|---|---|
| Take a set now (after a build, before printing; JMRI may stay running, but save first so the files are current) | `ops_backup_now` |
| List sets: JMRI's `backups`, `autoBackups` (taken each time Operations starts), the plugin's own | `ops_backups` |
| Put a whole set back; the current state is backed up first | `ops_restore` with `set` and `folder` |
| Put back one lost or unreadable file; the others keep the newer state, so run `ops_audit` after | `ops_restore` with `file` |
| See what is wrong | `ops_audit` reads a missing or corrupt file as empty and reports `file-missing` or `file-unreadable` |

- JMRI itself, started on a corrupt location file, loads no locations and may save the empty roster over it. Do not start it before the file is back.
- The automatic set predates any builds since it was taken, so restoring it after an accidental Terminate returns the cars to their pre-build tracks; build again, and since the builder is random the trains may differ from the ones printed. A set taken with `ops_backup_now` right after the build keeps the built state.
- A folder that has none of the four roster files is an empty railroad: the first `ops_apply` writes all six. A folder missing only some of them is refused for changes (writing would lose what they held) until they are restored.

## Fields that depend on others

Do not treat these as independent when editing. The plugin refuses or derives them.

| Field | Depends on |
|---|---|
| Track `moves` | Saved as moves minus pending set outs; load adds them back |
| Track used length, car count, reserved, drop and pick up counts | Not stored; rebuilt on load from the car and engine files |
| Car route location and destination ids, `<routeId>r<n>` | Read only if the car's train resolves and the id is on that train's route |
| Car destination | Forced on load; meaningful only with a matching train and route ids |
| Car schedule item id, `<scheduleId>c<n>` | A pending load effect on delivery |
| Car previous destination and schedule | Restored on reset |
| Car `lastRouteId` | Drives the interchange same-route rule. `place_car`, `ops_deliver_car` and `delete_route` clear it, as Set Car does |
| Car `loadFromStaging` | Reset returns the load to E |
| Car wait and pick up day | A pending schedule outcome |
| Track schedule pointer | Resets when the schedule changes |
| Track alternate, pool, destinations, pick up and set out ids | Cross references; changing the pick up or set out option clears its list |
| Train status, current stop, built, lead engine, staging tracks | Build state |
| Load, type, road, owner, colour and length names | Registered in lists in the car file; "type & load" entries join with ` & ` |
| Track length in a pool | Changed at build time by pool requests |

Ids: tracks are `<location>s<n>`, pools `<location>p<n>`, route stops `<route>r<n>`, schedule lines `<schedule>c<n>`. A car's id is its road and number. Clones from quick service carry `clone="true"`.

## What a hand edit can create that JMRI drops

A schedule or an alternate on a non-spur, and a Destinations filter on a yard or spur, are dropped on the next save. A pick up or set out list on a yard, and ship options or Routed on a spur, survive a save but are ignored. The plugin refuses to write any of them, and the audit reports the ignored ones.

## Deleting

Set a track's length to zero first so nothing new is sent, wait for its drop count to reach zero, then delete. Deleting a track fires events that clear final destinations pointing at it. The plugin's `delete_track`, `delete_location`, `delete_route`, `delete_schedule`, `delete_train` and `delete_load` refuse while anything still points at the record and list what does.

`delete_load` removes a custom load only once no car, schedule line, track or train load list or manual build line names it. `rename_load` onto a name the type already has is refused unless `merge` is set; the two loads then become one, keeping the existing one's settings. A track cannot change type: empty it, `delete_track`, then `add_track` the new type (once a delete and an add of a track in one plan was refused with "moves ... would change", because the new track took the deleted one's id; if that happens, use two plans).

## The JSON server

Types: car, cars, carType, engine, engines, kernel, location, locations, rollingStock, track, train, trains. No schedules, operations routes, divisions, loads, roads, owners, automations, train schedules, manifests or settings. The JSON `route` type is a panel route, not an operations route.

| Type | Read | Change | Create | Delete |
|---|---|---|---|---|
| car | one or list | yes | road and number; 409 if it exists | yes, no in-use check |
| engine | yes | yes | yes | yes |
| carType | yes | rename | add | 409 with conflicts unless forced |
| kernel | yes | rename | new | forced if not empty |
| location | yes | reporter, name, comment | needs a name | yes |
| track | one, with its location; no list | reporter, name, length, comment | needs name, type, location | yes |
| train | yes | move or terminate only | no | no |

- A car change can set location, location unknown, destination, train to null, road, number, colour, comment, owner, built, weight, RFID, length, out of service, type, caboose, hazardous, passenger, FRED and utility. It cannot set load, final destination, kernel, RWE, RWL, division, moves or wait.
- Any car POST without `weightTons` blanks the weight. The hazardous default is the combined car-or-load value, so a POST can make a load-hazardous car permanently hazardous.
- Location nodes use `name` for the id and `userName` for the display name, on locations, tracks and trains alike.
- A location change refuses a car on a train. A destination change bumps the track's schedule without route ids; a later build accepts it.
- A train POST with a location moves the train to it; with location null it terminates. There is no build.
- HTTP POST works with content type `application/json`. Any other content type reads only `state`, `location` or `value`, so a form-encoded POST changes nothing and returns the car unchanged. That is the "silently ignored" case; a websocket is not required.

## Import and export

- The plugin has no import action. To load a car list, turn each row into an `add_car` action (all rows in one `ops_plan`); fields such as built, weight, comment and the load carry over. Applied through the plan, 180 rows is a normal job.
- JMRI's own CSV import takes the car columns plus division, schedule id, RWE, RWL, destination, final destination and train. Its error "missing one or more of the first four required car attributes" says a line lacked the first four columns; the delimiter or a header row are the first things to look at (not checked against the source), and the plugin does not diagnose it.
- Routes import; an existing route is not overwritten. Trains and schedules export only.
- The RFID attribute on a car is the lower-case `rfid`, shown once RFID is enabled in Settings.

## Car history

JMRI's car logger is off by default. Turn it on with `set_option` group `logger`, name `carLogger`, value true (`engineLogger` and `trainLogger` are the same settings for engines and trains; `set_option` refuses a group or name the file lacks). After a build and terminate JMRI writes a CSV under `operations/logger/` with the car, type, load, location, track, final destination, train, moves and date. The plugin has no tool that reads that CSV; open it, or read it with `Read`.

## Several computers

One running JMRI owns the data. Two running copies go out of sync because each holds its own memory and writes whole files. Builder dialogs open on the computer running JMRI, whatever started the build. The plugin's running-JMRI check sees this computer only, so close JMRI elsewhere too.

## Lost data

Nearly empty rosters after a start usually mean a bad file, recovered from `autoBackups`. Help, System Console shows the load errors. Restore from Settings, not by opening backup files by hand.

Checked against JMRI 5.16 source, tag v5.16.
