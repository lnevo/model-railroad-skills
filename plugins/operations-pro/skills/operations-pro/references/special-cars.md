# Locomotives, cabooses, kernels and special cars

## Locomotives

- A train has no track field for where its power goes. Staging keeps a departure and a termination track; otherwise locations and tracks decide. Control where power lands with a loco type accepted only on that track, plus the track's Pick ups and Set outs lists.
- Loco type is an available manifest attribute but absent from the default formats, so a fine-grained type costs nothing on paper.
- A train out of staging with a variable loco count should require zero engines: staging must clear, so the train takes what is there.
- A loco change at a track that the departing loco will free fails on room unless the track uses planned pick ups. Keep such a track for locos only.
- Changes en route are the train's leg 2 and leg 3 (Edit Train, build options). `set_train_leg` writes them, and is the answer to "change locomotives en route". A train moved to another route loses its legs. Most of its refusals are the window's own rules; the ones marked * are the plugin's, because the builder would misbehave:

| Leg setting | Rule |
|---|---|
| `leg` | 2 or 3 only; leg 1 is the departure, set with `update_train` |
| `locos` | `none`, `change`, `add`, `remove` or `helpers`; `none` with caboose `keep` clears the leg |
| `start` | Required: a stop after the departure, except that `add` and `helpers` may start at the departure (more power or a pusher out of the departure) when it is not staging. From staging the builder takes that leg's locomotives from the departure staging track too, so every arrangement failed the build* |
| `end` | Only for `add` and `helpers` (the builder ignores it otherwise); must come after `start`; `helpers` need it |
| `engines` | A count in the window's list, or `Auto HPT`; not `Auto`. 0 only for `change`: the departure power is set out at `start` and the train goes on with none (a real build did this); for `add`, `remove` and `helpers` 0 does nothing and is refused* |
| `engines` = `Auto HPT` on leg 3 | Refused*: the builder stops with an error when it finds no locomotives |
| Leg 3 start | Must come after leg 2's start* |
| `remove` | Not offered on a train that departs staging |
| `model`, `road` | Must be in the window's lists, and the train must service them |
| Caboose change | Not combinable with helpers; "remove" needs a caboose on the train |

- Keep the track where a locomotive is exchanged for locomotives only (a track-room caveat above); a boxcar set out on it fills the room.
- The builder takes the locomotive with the lowest move count first, so a new engine (0 moves) is picked before every older one, and takes every train until its count catches up. `ops_list engines` shows the counts and `set_engine_moves` sets them (by engine id or road and number); give the new engine a count near the others, or a high count to rest one.
- A train's engine count is `0`, a number up to Settings' maximum, `Auto`, or `Auto HPT`. `Auto HPT` is refused for a train that departs staging (the window does not offer it), and a staging track's locomotives all leave with the train: from staging give the number that is there, or 0, which takes whatever is there (in a test `Auto` also failed from a staging track of three locomotives, with the same "does not have the required number" message). The actions refuse values that JMRI cannot read, such as `AUTO HPT`, which crashed a JMRI build.
- Horsepower can be entered or derived from tractive effort. Auto horsepower per ton sizes consists.
- `OperationsEngineRoster.xml` does not exist until something writes it.
- JMRI keeps a locomotive's type, length, horsepower, weight and B unit on its model, not on the engine. Only model names are stored, so on load each engine sets its model and the last one read wins; the next save writes that value onto every engine of the model. Horsepower and weight need a model at all.
- A train's types, loco road list, owner list and built dates filter locomotives as they do cars, and an out of service engine is never used. Those exclusions are Very Detailed (level 7) lines in the build report.
- A consist is used through its lead. A train needing N engines takes a consist only of exactly N, and the lead takes the others with it from wherever they are.
- The audit checks locomotives against acceptance: `model-type-no-train` and `model-type-no-track` for a model whose type nothing takes, `engine-no-train` when every train refuses an engine by loco road, owner, built dates or the model and road it asks for, `engine-location-refuses-type` and `engine-on-refusing-track` for one sitting where its type is not taken, and `consist-split` for members on different tracks. A train asking for 0 locomotives takes none, except every one on its departure staging track.
- A train's `engine_model` and `engine_road` on `add_train` or `update_train` follow the Edit Train window: the model must be in the roster's model list (JMRI's defaults when there is no engine file) and of a type the train takes; the road must belong to an engine of that model, pass the train's loco road list, and have an engine of a type the train takes. Blank is the window's no-choice item and means any; the plugin reads `None` as blank unless a model or road has that name. Both must stay blank while the train needs 0 locomotives, because the window clears them then. A model with no engine yet is written with a warning that the train will not build.
- Write actions: `add_engine_type`, `rename_engine_type`, `delete_engine_type`; `add_engine` (a model that already has engines gives the new one its values, and a different value is refused), `update_engine` for the engine's own fields, `update_engine_model` for the values every engine of a model shares, `rename_engine_model` (follows the trains' model fields; renaming onto a JMRI default model such as GP30 gives the engines that model's built-in type, length, horsepower and weight, as the window's Replace does, and onto a new name keeps their values, where the window keeps type, length and horsepower but drops weight and B unit), `delete_engine_model`; `place_engine` (a session action; a consist moves by its lead), `delete_engine`; `set_consist`, `clear_consist`. A train's loco road list is `loco_roads` on `add_train` or `update_train`.
- A JMRI default model such as SW8 starts with JMRI's own values until an engine of it says otherwise. A railroad with no engine file gets the file JMRI writes for none, with its default models, types and lengths.

## Cabooses and FRED

- The caboose flag on the car is what counts, not the type name. An `(H)` marker beside a car is hazardous, not a caboose.
- The train's caboose road list is separate from its car road list. A caboose on a track whose direction does not serve the train, or on a track the train cannot pull from, is not found. The search runs in several passes. The audit reports `caboose-road-mismatch`.
- Requirement `0` means no caboose, `1` one; `requires` takes nothing else. A FRED car on a train that does not need FRED is dropped from the car list.
- Two traps stop a caboose that is plainly there. Both name the wrong screen in the failure line (it says Requires); the cause is in the excluded cars or the car story.

| Trap | Cause | Fix | Audit finding |
|---|---|---|---|
| B6, interchange same route | The caboose sits on an interchange with Pick ups Any and the turn's route set it out last time. After a few builds all the cabooses are barred | Name the train or route in the interchange's Pick ups (`update_track` `pickup` `{option: trains, names: [...]}`, lower case) | `caboose-interchange-same-route` |
| C9, track direction | The caboose's track serves other directions than the one the train departs in | Fix the track's Train direction | `caboose-track-direction` |
- Cabooses and FRED cars are placed first, may only be destined for the terminal, and share the passenger exemptions below for same-location, through-car and local rules. They are exempt from Routed.

## Kernels

- A kernel is switched as one unit and counts as one move. The members must be on one track; a split kernel fails the whole build. The audit reports `kernel-split`.
- A kernel may mix car types. For custom loads from staging, the lead car's load is evaluated; a non-lead member gets a valid load of its own if the lead's load is not valid for it, so two members can differ unless the arrival schedule pins one.
- At build the members take the lead's default load: a kernel of a buffer car (E) and loaded tank cars printed the tank cars as E on the manifest, although they were L in the file. `set_kernel` does not warn when the members' loads differ, so check them before grouping cars on purpose.
- To split a kernel on paper, break it up or make smaller ones. The `set_kernel` and `clear_kernel` actions do that.
- Sorting inside a kernel uses the blocking number, so blocking works for non-passenger cars there.

## Passenger cars and blocking

- The blocking number is an integer, default zero, not clamped. Manifests pad for plus or minus 99.
- Passenger cars with a negative number go to the front, most negative first; zero or positive go to the rear, before cabooses and FRED, ascending. Non-passenger cars sort by destination, hazardous, location and final destination.
- Track blocking order and route blocking order are two other numbers, used for the location's track order when every track has one, and for the route's blocking table.
- The passenger flag allows a return to the same location or track, skips the train load test, the later-pickup delay, the through-car rule and the local move rule, uses a weight default of 0.9 tons per foot, and keeps the car out of staging block counts and kernel grouping. It does **not** exempt the car from track type, road, load, length or a schedule. The train road test still applies.
- Passenger blocking order prints on manifests and switch lists.

## Hazardous and buffer cars

- Hazardous is a flag and a sort key. No placement rule exists, so a tank car can sit behind the loco. Either of these puts a buffer first:
  - A single buffer car flagged passenger with a negative blocking number (`update_car` `passenger`, `blocking`): it leads the train, and on the way back it is set out on its starting track.
  - A buffer kernel of the right size, but the members take the lead's load (see Kernels).
- A car POST through JSON can turn a load-hazardous car into a car-hazardous one, because the default is the combined value.
- Buffer cars that must return to their starting track: flag them passenger. Without the flag the car fails the same-location rule (D4, "switcher False") and stays home. The passenger flag is the exemption.

## LCL, icing, RIP, TOFC and floats

- An LCL car that rides and returns: flag it passenger. The caboose flag does not work in practice: a train that needs no caboose drops the car, and a train that needs one takes the LCL car as its caboose and leaves the real caboose behind (one caboose per requirement, B17). A pick up message on the load and the print passenger load option carry the note. The builder never changes a load en route.
- A car moves once per train. For icing or servicing mid-run, terminate one train at the spur and start a second there, with a schedule setting the new load, or use a quick service track, which pulls through a clone in one build. For icing within one train the route must reach the icing location a second, later time: the stop that set the car out cannot pull it (C11), so with one stop the car stays at the dock and only its clone moves on. Route Origin, Icer, Icer, Market works; Origin, Icer, Market does not.
- RIP or shop moves: a schedule line with a low random percentage and the same receive and ship load, or Disable Load Change. The real frequency is lower than the percentage because every other gate runs first. Load changes happen on spurs only, so a yard-type RIP track keeps the custom load.
- TOFC: trailers as cars, kernelled to flatcars by the two sample scripts in JMRI's `jython/operations/`.
- Car floats: an automation builds the float train when another train terminates, but a build sees only cars already at the interchange, so pick ups run one train behind.

## Unit trains

The builder has no unit-train flag. A staging-to-staging train keeps its consist, so giving it a route from one staging to another and its own types or roads is the usual modelling choice.

Checked against JMRI 5.16 source, tag v5.16.
