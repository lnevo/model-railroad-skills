---
name: schematic-maps
description: Draws a model railroad's track as a clean schematic diagram with the schematic command, from the track plan's AnyRail JMRI export and, for signals, a JMRI Layout Editor panel. It makes one band per level, joins levels with lettered connectors, keeps the main line level through every switch, steps yard ladders diagonally, draws loops and helix tracks, places switch numbers, track names and signal masts so nothing overlaps, and checks the result. Use when someone wants a schematic, track diagram or system map of their layout, asks to turn a plan into a diagram, to add signals from a panel, to fix a crossing or overlapping label, or to compare a drawing against a saved one. Not for editing the Layout Editor panel itself.
---

# Schematic maps from a track plan

The reader gets one sheet: a band for each level of the railroad, the main line straight through every switch, yard ladders stepping down in a diagonal with their tracks level, loops, helix tracks, lettered connectors where a track climbs between levels, and signal masts drawn the way a physical characteristics book shows them. Nothing crosses and no label sits on track. They keep the plan and one small file of facts about the railroad; the command does the layout.

## What goes in

| Input | What it holds | Who writes it |
|-------|---------------|---------------|
| Plan graph | Switches, track ends and runs with lengths, read from the plan's JMRI export (`plan` command) | The command |
| Plan overrides, `NAME.plan_overrides.json` | Facts the plan does not hold: switch numbers, switches that were not built or were added, track names, which tracks are main, helix tracks, level heights | The reader and the agent together |
| Signals, `NAME.signals.json` | Masts, found on a Layout Editor panel (`signals` command) | The command, never by hand |
| Preferences, `NAME.preferences.json` | The reader's look for one sheet: titles, band order, lengths chosen for looks | The reader (optional) |

With no preferences file the sheet is still correct. Preferences only move, stretch or mirror what the rules placed.

## Run it

Put the layer files in one folder (`--data`). `<plugin>` is the folder two above this file; `<plugin>/bin/schematic` runs `python3 -m schematic`.

1. **Read the plan.** `schematic plan export.xml graph.json` (add `--parts parts.json` for plan part numbers and heights, `--section +Name` to keep one group of sections). Read the notes it prints: how many junctions matched, how many pairs of track ends were joined.
2. **Write the overrides.** Start with `relabel` (plan part numbers to the railroad's switch numbers), then `remove`, `switch`, `crossover`, `move`, `name`, `end`, in that order of need. Every switch you add or move needs `hand` ("R" or "L") and `source` (`le_panel`, `owner` or `plan`). The command stops with the switch's number if either is missing; it never tries both hands. Add `main_route`, `levels` and `helix` once the track is right.
3. **Draw.** `schematic draw out.svg --data folder graph.json:NAME`. List several `graph.json:NAME` pairs for several plans on one sheet. It prints the drawing faults and the label faults.
4. **Check.** `schematic report --data folder graph.json:NAME` lists crossings, every switch where the main-level or ladder rule gave way for a tighter drawing, and anything not drawn. `schematic check out.svg --list` judges the finished SVG's labels. Fix faults by correcting the overrides, not by nudging the drawing.
5. **Add signals.** `schematic signals tables.xml graph.json NAME NAME.signals.json --data folder --numbers numbers.csv --lengths lengths.csv`, then draw again. `numbers.csv` has the columns `le_ident,switch`, `lengths.csv` has `user_name,inches` (block lengths: the panel is not to scale). Read what it could not place.
6. **Keep a golden.** `schematic fingerprint golden.json --data folder graph.json:NAME` writes each switch's column, row, facing and level leg, each track's row and span, and each connector's letter. A later run compared with it prints every difference switch by switch, so a change of look never breaks it.

## What the rules do

- **Levels.** One band per level; a run joining two levels is cut and drawn as a pair of lettered connectors.
- **Main level.** Where the main enters a switch at its points and leaves by one leg, that leg is level. A loop's return is drawn as a fold and is not counted.
- **Ladders.** A switch with a short link (under 40 cm by default) to the next switch and a yard track on its other leg keeps the yard track level; the link slopes.
- **Rows.** Two tracks are kept on separate rows only where they run side by side.
- **Hands.** Come from the overrides. A missing hand is an error naming the switch.
- **Labels.** Each label has a measured box and a list of allowed positions; the hardest are placed first. Helix boxes and station brackets are drawn before labels are placed. A label that finds no free position claims a cell on its own track, and the band is laid out again (up to three rounds), so a short track grows to fit its name or its masts without a length preference.
- **Masts.** Drawn on the right-hand side of the track for the way they govern, east to the right on every band; virtual masts (Dispatcher only) are not drawn; masts named in `signals_planned` are dashed.

Run hints (layer 3): `min_cells` `[a, b, cells]` and `shorten` `[a, b]` name a run by its two end switches; list the tracks the hint is for after them (`[a, b, cells, "S-3", "S-4"]`) when more than one track joins the two. A track with a joined name ("A / B") may be listed by either part. The run stops, naming the hint, when a hint reaches no track (a renamed or removed switch), when one without track names reaches two tracks, or when a listed track is not reached; the check runs once per input across all its bands.

Facing letters (layer 3): `facing_letters: true` prints R or L after each switch number, from the main route's direction (`main_route` is listed west to east, in timetable order); a switch the route does not reach takes the direction it is drawn with. `direction_arrows: true` puts an EAST arrow on each main run of a band whose main runs east to the left anywhere (not on a band turned with `rotate_bands`). Where the main route itself turns back (a reversing loop at its end) the run log names the switches to check.

Title block fields (layer 3): `date` as YYYY-MM-DD, `revision` and `sheet` ("1 of 1") print in a ruled column beside the title; set them in `sheet.preferences.json`, or in the last input's preferences, which also set the page; the same keys in an earlier input are not read. They are left out when not set, and a date that is not a real YYYY-MM-DD date stops the run with an error naming it. The box and column grow to fit long values.

Preferences that pin a choice (layer 3, never needed for a correct sheet): `level_leg` names the leg a switch keeps level, as `{"31": "B"}`, where the rules chose the other valid one. It overrides R5 and R6, so use it only for the reader's own look, such as a ladder the reader wants drawn the other way. R5 and R6 are strong preferences, not pins: where breaking one draws the sheet in clearly fewer rows (a short loop, a ladder with a level link), the search breaks it and the report lists it; `rule_weight` (default 2.0) sets how much tighter the sheet must get. A preference may only move, stretch or mirror what the rules placed; if it causes a fault, the report shows it.

Declared ends are layer 1 facts that outrank the fault count: `left_end` is the track whose end must be the leftmost on its band and run leftward from its switch, and `helix_side` is the side a level's helix ends on.

Settings that are tuning, not per-switch hints: `ladder_link_max_cm` (40) and `long_track_cm` (100), in the overrides.

## References

`references/style.md` has the drafting style, one rule at a time, with the examples it comes from and which rules the command draws and which it does not yet (capacity, mileposts, interlocking limits, date and revision, folding a long band). Read it when asked why the sheet looks as it does or for something it does not show. `references/cats-grid.md` is the CATS Designer's cell rules, for a later step that seeds a CATS panel from the grid; the command does not do that.

## Pitfalls

- A hop in `main_route` written `[from, to, "direct"]` marks every track between the two; one written `[from, to]` takes the shortest. Through a double crossover use the shortest form unless both tracks are main.
- Two track ends on the same spot in the plan are one track; the reader joins them. A loop that returns to its own switch arrives this way.
- Heights are read from the parts file, matched by position. Check the "matched n of m" line.
- Text is measured with a bundled table for a Helvetica-style face, so results do not change with the fonts installed.
