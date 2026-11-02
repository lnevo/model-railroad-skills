# Move counts, priority and balance

## Move counts steer the builder

- Each track has a move count, an integer of either sign. The column is off by default: Tools, Show Track Moves, on the location edit window. It is hand-editable.
- **Track order at a location:** alternates are removed, tracks with schedules sort first whatever their count, and the rest sort by lowest count (ties keep track id order as text). The first accepting track ends the search at that location. `ops_why_not` with no track named lists this order as `track_order` and shows the first track that passes. A track named in the call is tested alone.
- Negative counts are legal: the count is an integer of either sign, and `set_track_moves` accepts any whole number. A large negative count on a yard track makes it fill first among unscheduled tracks, but never ahead of a scheduled spur. To send cars to the second of two equal tracks, give the other a large positive count (tested: all four cars went to the second track). **Priority does not do this.**
- Between locations the lowest ratio of moves used to moves allowed wins, squared for the terminal and for a track with a schedule. The terminal is favoured, not starved.
- **Ties go to the later stop** (TrainBuilderCars:1885 compares with a strict less-than). So when two stops are equally good, the later one, usually the terminal, wins. `ops_why_not` `can_move: true` means the car can go there, not that the builder will choose it; do not promise delivery to an earlier stop on that basis, and expect `ops_build_check` to show "no change" when a fix removes a refusal but the car still goes to the later stop.
- The custom-load spur search is global by move count across all locations.
- Departure staging track choice is by lowest move count.
- The saved count is moves minus pending set outs; JMRI adds them back on load. The plugin preserves counts on every action except `set_track_moves` and `reset_moves`.

## Resets

| Change | Effect on counts |
|---|---|
| Adding a track in JMRI's window | Resets every track at that location |
| Assigning a different schedule from the schedule edit window | Resets every track at every location |
| Creating a schedule, deleting a track, setting a schedule by script | No reset |
| Add then delete a track | Resets that location |
| The plugin's `add_track` | No reset |

Hand-placed biases are lost by the first two. Re-apply them with `set_track_moves`.

## Priority

Track priority and load priority decide which cars are **analysed first**: track priority, then load priority, then car move count, with route order and FIFO or LIFO on top. Priority never decides where a car goes and never guarantees a move. To prefer a destination track, change its move count.

## Route moves against train length

- Each stop asks for its Moves count. In aggressive mode the first pass asks for half at non-departure stops; a Random percentage reduces moves by up to that much.
- Pick ups count toward the stop's moves; a kernel is one move.
- A train length failure on a leg ends the destination search for that car. A train that reaches its maximum length early never gets to the spurs beyond, so cars pile into the first accepting yards.
- Raising location moves does not help when length is the limit. Author's rule of thumb, not a gate: keep moves low enough that the train never hits its length, about two or three per stop for a ten-car train. Listing a location twice for direction reasons is fine if each line carries a small count.
- A ten-foot spur from a typo rejects every car on capacity. The audit reports `type-no-track` and `car-on-refusing-track` for related traps.

## Normal and aggressive

- Normal makes one pass. Aggressive makes two to four, and later passes revisit cars skipped earlier, which makes swaps possible on full spurs.
- A train's own "normal mode" build option overrides the global aggressive setting.
- A schedule line's random is scaled by the number of passes.
- Build from staging in normal mode is on by default.

## Room on a track

- Room is used length plus reserved length plus this car's length within the track length. A car's length includes a coupler allowance of four feet, or one metre.
- Reserved length counts cars en route. The spur's "% from staging" factor scales it for load generation.
- Planned pick ups, the ignore-used-length percentage (`update_track` `ignore_used_percent`: 0, 25, 50, 75 or 100), let the builder discount part of the used length. Cars will fill the freed room, so use it where that is wanted. Observed outcomes, not asserted by a test:

| Case | What fixed it |
|---|---|
| A turn must swap seven cars at a full seven-spot industry and yard | `ignore_used_percent` 100 on both tracks **and** route moves at each stop covering set outs plus pick ups (7 / 14 / 7). Aggressive mode alone, or moves alone, built nothing; planned pick ups with moves left at 5 built 5 of 7 |
| A spur should take the parked cars' room for new set outs while the same turn pulls them | Aggressive mode, or planned pick ups 100: all four set outs placed |
| Two full staging tracks swapped by two trains | Planned pick ups 100 on both (`staging.md`) |
| A locomotive-only track used for a loco change | Planned pick ups (`special-cars.md`) |

The report line "ignored because the stop's moves were used up" means moves ran out, not that no track would take the car; raise the stop's Moves. `ops_why_not` marks D3 (moves) `not_checked`, so only the build report explains move exhaustion.
- A pool shares length between tracks, with a minimum per track. It does not make the builder search those tracks as one. Pool requests change track lengths at build time, so a pooled track's length is not a stable input. Modelling drawers as a location with rows as tracks is a modelling choice.
- A pool's minimums must not add up to more than its tracks' lengths: the sum of the minimum lengths against the sum of the lengths. JMRI's pool window shows "ERROR: Minimum > Length" then (PoolTrackFrame:270), but loads such a pool without complaint, and a track lends length only down to its minimum (Pool.requestTrackLength). A pool is how one length limit is shared across two tracks; the short track can end up holding more than its own length. The pool actions refuse it, and audit `pool-minimum-over-length` finds an existing one. Lower the minimums or lengthen the tracks.
- Set a track's length to zero to retire it: nothing new is sent and the cars there are pulled. Delete it once the drop count reaches zero.
- Entering a yard track shorter than real to give operators spare room is a modelling choice.

## Hold

- Hold is a spur option under Schedule Options. With it on, a spur that is routable but full holds the car rather than letting it fall to staging. The hold also applies when the router says another train could deliver.
- A car departing staging is never held.

## Spurs drain and yards fill

The mechanics behind the complaint:

1. The first accepting track at a location ends the search, so a yard track with a low count takes the car before any unscheduled spur.
2. A length failure ends the car's search, so long trains never reach distant spurs.
3. Default-load cars take any accepting track; only a schedule line, a final destination or a division points them anywhere.
4. Custom loads do not by themselves raise movement, and divisions used badly limit it.

Fixes: give spurs schedules, which sort first; set yard counts high and spur counts low with `set_track_moves`; cut route moves below the length limit; restrict interchanges to the trains meant to use them, since any train may work a yard. Do not clear car histories or counts to fix it.

## Track Analysis

The forum reads the per-type figure as space used by all cars of that type as a percentage of all track that accepts the type, as if they all sat on it; that reading was not checked against the source. Layout fullness comes from Print Locations. Half full as a starting point is a modelling choice.

Checked against JMRI 5.16 source, tag v5.16, or tested in JMRI 5.16, except where this file says a point was not checked.
