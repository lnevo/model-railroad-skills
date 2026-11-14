# Schematic maps (separate plugin)

`schematic-maps` draws a model railroad's track as one clean schematic sheet: a band for each level, the main line level through every switch, yard ladders stepped diagonally, loops, helix tracks, lettered connectors between levels, and signal masts. It reads the track plan's AnyRail "export to JMRI" file and, for masts, a JMRI Layout Editor panel; it writes an SVG and checks it for crossing lines and overlapping labels.

It runs a Python command and writes files you choose, so it is a separate install.

```
claude plugin install schematic-maps@model-railroad-skills
```

The command uses only the Python 3.11+ standard library. No fonts are read: text is measured with a bundled table, so the same input draws the same sheet on every machine.

## Use

`<plugin>/bin/schematic` runs `python3 -m schematic` with the plugin folder on the module path.

```
schematic plan plan.xml graph.json --parts parts.json
schematic signals tables.xml graph.json NAME NAME.signals.json --data DIR --numbers numbers.csv --lengths lengths.csv
schematic draw sheet.svg --data DIR graph.json:NAME
schematic report --data DIR graph.json:NAME
schematic fingerprint golden.json --data DIR graph.json:NAME
schematic detail details/ --data DIR graph.json:NAME                      one sheet per station of the `stations` preference
schematic detail yard.svg --data DIR graph.json:NAME --station "Yard"      one station
schematic detail pair.svg --data DIR graph.json:NAME --switches 11 12 --name "Pair"   any group of switches
schematic check sheet.svg --list
```

Layer files in `DIR`: `NAME.plan_overrides.json` (facts about the railroad), `NAME.signals.json` (generated), `NAME.preferences.json` (the look, optional). Page folding is a preference (`fold: true` or `fold_min_scale` in the preferences file): a band too long to read at Letter size is cut into rows with CONTINUES arrows. The skill, [`skills/schematic-maps/SKILL.md`](skills/schematic-maps/SKILL.md), walks through the overrides and the checks.

## Detail sheets

`schematic detail` draws one station, or a named group of switches, as its own larger sheet, cut from the same solved drawing as the overall sheet so the two agree: same order of tracks, same lengths, same capacity counts and masts. Tracks that leave the cut end in an arrow reading `TO <station>` or `TO SW <number>`. Sheets come from the `detail_sheets` preference (name to switch numbers, which may overlap stations) when present, else the `stations` preference, all of them by default. A sheet shows a bar and car total for each station that lies wholly inside it; `detail_max_scale` (default 2) sets how far a sheet is enlarged. One selection writes a file, several write a folder of `<station>.svg`.

## The example

`tests/example.py` writes a made-up railroad, the Pine Hollow & Eastern, as every file the tool reads: a plan export, plan parts, a Layout Editor panel, switch numbers, block lengths and layer files. It has a yard ladder, a double crossover, a loop, two levels joined by a rise and a helix track, a switch added by the overrides, a switch in the plan that was never built, and masts on a turnout leg, an anchor and a ladder link. It is track only and invented for the tests. `tests/golden/` holds the fingerprints of its drawings.

Where two tracks join the same two switches, an override edit that names the pair stops and asks for the leg instead of taking the longer track: `"port": "C"` beside `on`, a third item in `onto` (`["3", "4", "C"]`), a fourth in a `name` entry, and the leg in `track_directions`.

## Tests

```
python3 -m unittest discover -s tests
```

`UPDATE_GOLDEN=1` rewrites the fingerprints after a change you meant; a mismatch otherwise prints each difference switch by switch.

## Where it came from

The layout engine, readers and label placer were proved as a spike on one real railroad, then rebuilt here as tested modules. The generation rules replace the hand hints the spike needed: the main level (R5), ladders (R6), rows for tracks that run side by side (R7), hands from the overrides (R10) and labels that claim grid room on their own track (R12).
