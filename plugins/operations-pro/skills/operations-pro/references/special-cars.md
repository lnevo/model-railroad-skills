# Locomotives, cabooses, kernels and special cars

## Locomotives

- A train has no track field for where its power goes. Staging keeps a departure and a termination track; otherwise locations and tracks decide. Control where power lands with a loco type accepted only on that track, plus the track's Pick ups and Set outs lists.
- Loco type is an available manifest attribute but absent from the default formats, so a fine-grained type costs nothing on paper.
- A train out of staging with a variable loco count should require zero engines: staging must clear, so the train takes what is there.
- A loco change at a track that the departing loco will free fails on room unless the track uses planned pick ups. Keep such a track for locos only.
- Horsepower can be entered or derived from tractive effort. Auto horsepower per ton sizes consists.
- `OperationsEngineRoster.xml` does not exist until something writes it.
- JMRI keeps a locomotive's type, length, horsepower, weight and B unit on its model, not on the engine. Only model names are stored, so on load each engine sets its model and the last one read wins; the next save writes that value onto every engine of the model. Horsepower and weight need a model at all.
- A train's types, loco road list, owner list and built dates filter locomotives as they do cars, and an out of service engine is never used. Those exclusions are Very Detailed (level 7) lines in the build report.
- A consist is used through its lead. A train needing N engines takes a consist only of exactly N, and the lead takes the others with it from wherever they are.
- The audit checks locomotives against acceptance: `model-type-no-train` and `model-type-no-track` for a model whose type nothing takes, `engine-no-train` when every train refuses an engine by loco road, owner, built dates or the model and road it asks for, `engine-location-refuses-type` and `engine-on-refusing-track` for one sitting where its type is not taken, and `consist-split` for members on different tracks. A train asking for 0 locomotives takes none, except every one on its departure staging track.
- A train's `engine_model` and `engine_road` on `add_train` or `update_train` follow the Edit Train window: the model must be in the roster's model list (JMRI's defaults when there is no engine file) and of a type the train takes; the road must belong to an engine of that model, pass the train's loco road list, and have an engine of a type the train takes. Blank is the window's no-choice item and means any; the plugin reads `None` as blank unless a model or road has that name. Both must stay blank while the train needs 0 locomotives, because the window clears them then. A model with no engine yet is written with a warning that the train will not build.
- Write actions: `add_engine_type`, `rename_engine_type`, `delete_engine_type`; `add_engine` (a model that already has engines gives the new one its values, and a different value is refused), `update_engine` for the engine's own fields, `update_engine_model` for the values every engine of a model shares, `rename_engine_model` (follows the trains' model fields), `delete_engine_model`; `place_engine` (a session action; a consist moves by its lead), `delete_engine`; `set_consist`, `clear_consist`. A train's loco road list is `loco_roads` on `add_train` or `update_train`.
- A JMRI default model such as SW8 starts with JMRI's own values until an engine of it says otherwise. A railroad with no engine file gets the file JMRI writes for none, with its default models, types and lengths.

## Cabooses and FRED

- The caboose flag on the car is what counts, not the type name. An `(H)` marker beside a car is hazardous, not a caboose.
- The train's caboose road list is separate from its car road list. A caboose on a track whose direction does not serve the train, or on a track the train cannot pull from, is not found. The search runs in several passes. The audit reports `caboose-road-mismatch`.
- Requirement `0` means no caboose. A FRED car on a train that does not need FRED is dropped from the car list.
- Cabooses and FRED cars are placed first, may only be destined for the terminal, and share the passenger exemptions below for same-location, through-car and local rules. They are exempt from Routed.

## Kernels

- A kernel is switched as one unit and counts as one move. The members must be on one track; a split kernel fails the whole build. The audit reports `kernel-split`.
- A kernel may mix car types. For custom loads from staging, the lead car's load is evaluated; a non-lead member gets a valid load of its own if the lead's load is not valid for it, so two members can differ unless the arrival schedule pins one.
- To split a kernel on paper, break it up or make smaller ones. The `set_kernel` and `clear_kernel` actions do that.
- Sorting inside a kernel uses the blocking number, so blocking works for non-passenger cars there.

## Passenger cars and blocking

- The blocking number is an integer, default zero, not clamped. Manifests pad for plus or minus 99.
- Passenger cars with a negative number go to the front, most negative first; zero or positive go to the rear, before cabooses and FRED, ascending. Non-passenger cars sort by destination, hazardous, location and final destination.
- Track blocking order and route blocking order are two other numbers, used for the location's track order when every track has one, and for the route's blocking table.
- The passenger flag allows a return to the same location or track, skips the train load test, the later-pickup delay, the through-car rule and the local move rule, uses a weight default of 0.9 tons per foot, and keeps the car out of staging block counts and kernel grouping. It does **not** exempt the car from track type, road, load, length or a schedule. The train road test still applies.
- Passenger blocking order prints on manifests and switch lists.

## Hazardous and buffer cars

- Hazardous is a flag and a sort key. No placement rule exists, so a tank car can sit behind the loco. Use a buffer kernel of the right size, or reorder by hand.
- A car POST through JSON can turn a load-hazardous car into a car-hazardous one, because the default is the combined value.
- Buffer cars that must return to their starting track: flag them passenger.

## LCL, icing, RIP, TOFC and floats

- An LCL car that rides and returns: flag it caboose or passenger. A pick up message on the load and the print passenger load option carry the note. The builder never changes a load en route.
- A car moves once per train. For icing or servicing mid-run, terminate one train at the spur and start a second there, with a schedule setting the new load, or use a quick service track, which pulls through a clone in one build.
- RIP or shop moves: a schedule line with a low random percentage and the same receive and ship load, or Disable Load Change. The real frequency is lower than the percentage because every other gate runs first. Load changes happen on spurs only, so a yard-type RIP track keeps the custom load.
- TOFC: trailers as cars, kernelled to flatcars by the two sample scripts in JMRI's `jython/operations/`.
- Car floats: an automation builds the float train when another train terminates, but a build sees only cars already at the interchange, so pick ups run one train behind.

## Unit trains

The builder has no unit-train flag. A staging-to-staging train keeps its consist, so giving it a route from one staging to another and its own types or roads is the usual modelling choice.

Checked against JMRI 5.16 source, tag v5.16.
