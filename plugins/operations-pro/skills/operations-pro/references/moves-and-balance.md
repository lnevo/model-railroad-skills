# Move counts, priority and balance

## Move counts steer the builder

- Each track has a move count, an integer of either sign. The column is off by default: Tools, Show Track Moves, on the location edit window. It is hand-editable.
- At a location, tracks with schedules sort first whatever their count, alternates are removed, and the rest sort by lowest count. The first accepting track ends the search at that location. So a large negative count on a yard track makes it fill first among unscheduled tracks, but never ahead of a scheduled spur.
- Between locations the lowest ratio of moves used to moves allowed wins, squared for the terminal and for a track with a schedule. The terminal is favoured, not starved.
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
- Planned pick ups, the ignore-used-length percentage, let the builder discount part of the used length. Use it only on a track where only locos go, because cars will fill the freed room.
- A pool shares length between tracks, with a minimum per track. It does not make the builder search those tracks as one; model drawers as a location with rows as tracks instead. Pool requests change track lengths at build time, so a pooled track's length is not a stable input.
- Set a track's length to zero to retire it: nothing new is sent and the cars there are pulled. Delete it once the drop count reaches zero.
- A yard track entered shorter than real gives operators spare room.

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

Per type, the figure is space used by all cars of that type as a percentage of all track that accepts the type, as if they all sat on it. Layout fullness comes from Print Locations. Half full is a working start.

Checked against JMRI 5.16 source, tag v5.16.
