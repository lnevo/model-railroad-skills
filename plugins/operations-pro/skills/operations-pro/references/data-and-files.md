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
- To move a railroad: copy the six files into the same folder of the other install with JMRI closed.
- `ops_backups` lists sets; `ops_restore` puts one back after backing up the current state. `ops_backup_now` takes a set on demand, as the plugin does before a write, for example right after a build and before printing; it copies the files on disk, so save JMRI first.

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
| Car `lastRouteId` | Drives the interchange same-route rule |
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

Set a track's length to zero first so nothing new is sent, wait for its drop count to reach zero, then delete. Deleting a track fires events that clear final destinations pointing at it. The plugin's `delete_track`, `delete_location`, `delete_route`, `delete_schedule` and `delete_train` refuse while anything still points at the record and list what does.

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

- Cars import from CSV with the car columns plus division, schedule id, RWE, RWL, destination, final destination and train.
- Routes import; an existing route is not overwritten. Trains and schedules export only.
- The RFID attribute on a car is the lower-case `rfid`, shown once RFID is enabled in Settings.

## Several computers

One running JMRI owns the data. Two running copies go out of sync because each holds its own memory and writes whole files. Builder dialogs open on the computer running JMRI, whatever started the build. The plugin's running-JMRI check sees this computer only, so close JMRI elsewhere too.

## Lost data

Nearly empty rosters after a start usually mean a bad file, recovered from `autoBackups`. Help, System Console shows the load errors. Restore from Settings, not by opening backup files by hand.

Checked against JMRI 5.16 source, tag v5.16.
