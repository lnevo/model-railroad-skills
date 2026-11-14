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
schematic check sheet.svg --list
```

Interlocking limits are optional: `control_points` in the plan overrides names each control point, an optional short code and the switches it covers; the sheet draws square brackets across the tracks at its outer ends and the quoted name (see style rule 10).

Layer files in `DIR`: `NAME.plan_overrides.json` (facts about the railroad), `NAME.signals.json` (generated), `NAME.preferences.json` (the look, optional). The skill, [`skills/schematic-maps/SKILL.md`](skills/schematic-maps/SKILL.md), walks through the overrides and the checks.

## The example

`tests/example.py` writes a made-up railroad, the Pine Hollow & Eastern, as every file the tool reads: a plan export, plan parts, a Layout Editor panel, switch numbers, block lengths and layer files. It has a yard ladder, a double crossover, a loop, two levels joined by a rise and a helix track, a switch added by the overrides, a switch in the plan that was never built, and masts on a turnout leg, an anchor and a ladder link. It is track only and invented for the tests. `tests/golden/` holds the fingerprints of its drawings.

## Tests

```
python3 -m unittest discover -s tests
```

`UPDATE_GOLDEN=1` rewrites the fingerprints after a change you meant; a mismatch otherwise prints each difference switch by switch.

## Where it came from

The layout engine, readers and label placer were proved as a spike on one real railroad, then rebuilt here as tested modules. The generation rules replace the hand hints the spike needed: the main level (R5), ladders (R6), rows for tracks that run side by side (R7), hands from the overrides (R10) and labels that claim grid room on their own track (R12).
