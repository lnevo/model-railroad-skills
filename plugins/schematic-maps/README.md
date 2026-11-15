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
schematic cats panel.xml --data DIR graph.json:NAME [--band "Main"] [--bindings b.json] [--templates-from desk.xml]
                        [--cells-per-unit 1] [--fit 63x36]                a CATS Designer panel from the same grid
schematic le panel.xml --data DIR graph.json:NAME [--names names.json] [--panel NAME]   a JMRI Layout Editor panel
schematic check sheet.svg --list
```

Interlocking limits are optional: `control_points` in the plan overrides names each control point, an optional short code and the switches it covers. Detail sheets (not the overall sheet) draw square brackets across the tracks at its outer ends and the quoted name (see style rule 10), for each control point whose switches are all on the sheet.

Layer files in `DIR`: `NAME.plan_overrides.json` (facts about the railroad), `NAME.signals.json` (generated), `NAME.preferences.json` (the look, optional). Page folding is a preference (`fold: true` or `fold_min_scale` in the preferences file): a band too long to read at Letter size is cut into rows with CONTINUES arrows. The skill, [`skills/schematic-maps/SKILL.md`](skills/schematic-maps/SKILL.md), walks through the overrides and the checks.

Mileposts are a preference (`mileposts: true`, or `{"step": 0.25}` in miles) and need layer 1 facts: `milepost_origin` (`{"switch": "1", "milepost": 0.0}`), `scale_ratio` (87.1 for HO), `helix_length_in` to carry the count through a helix, and optionally `milepost_route`. The count runs in scale miles along the main route from the origin using the same lengths as capacity; ticks sit where it crosses a multiple of the step. With the preference off the drawing is unchanged. See rule 19 in `skills/schematic-maps/references/style.md`.

## Detail sheets

`schematic detail` draws one station, or a named group of switches, as its own larger sheet, cut from the same solved drawing as the overall sheet so the two agree: same order of tracks, same lengths, same capacity counts and masts. Tracks that leave the cut end in an arrow reading `TO <station>` or `TO SW <number>`. Sheets come from the `detail_sheets` preference (name to switch numbers, which may overlap stations) when present, else the `stations` preference, all of them by default. Stations may overlap; `station_tracks` (plan overrides) limits a station's car total to listed tracks and `station_side` (preferences) puts its bar above or below the band; the object form (`switches`, `tracks`, `side`) also reads. A sheet shows a bar and car total for each station that lies wholly inside it; `detail_max_scale` (default 2) sets how far a sheet is enlarged. One selection writes a file, several write a folder of `<station>.svg`.

## CATS panel

`schematic cats` writes a CATS Designer panel (XML) from the solved bands, so a dispatcher panel starts from the same track as the drawing. Each schematic grid unit is two CATS cells, so every 45 degree leg lands on whole cells and each track has a free row below it for its name. Bands stack top to bottom; `--band` keeps the bands whose title starts with the text. It writes the track, switch points with two routes (normal is leg B), a double crossover as its X with a crossing edge, turnbacks as a vertical run, one block per track and one OS block per switch, switch numbers and track names as labels, and logical joins for connector letters and helix tracks that appear on two drawn bands. A turnback joining two differently named tracks is two blocks, parted in the middle of its run (before 0.1.13 it was one block under the first name, and the second name was lost). Every block boundary edge names its block in full. Compress Screen and Automatic Wrapping are turned off in the file.

CATS draws every cell at a fixed 30 pixels and has no zoom, so a panel two cells per unit is often wider than the dispatcher's screen. `--cells-per-unit 1` draws one cell per grid unit, half the size each way, with one empty column on the left: names go on the track (over or under it in its own cells; a yard's parallel tracks are named in one column), each label is placed where it covers no track line, signal or other label at the 30 pixel grid, and a connector or helix label sits beside its end on its own row (else over a connector's or under a helix track's last level cells), without "(JOINED)". OS blocks end a whole step past the points where the track allows, else one cell (mid-slope). Bound masts' gaps slide along their own tracks, between the same two blocks, so a control point's masts stand in one column per direction (a gantry) and out of switch cells. Each mast is then drawn at its clearest spot: lamps pointing the way of the move, on its right-hand side, clear of track, points and other masts. The rules and the renders behind them are in [`skills/schematic-maps/references/cats-signals.md`](skills/schematic-maps/references/cats-signals.md). To keep the OS blocks of switches joined by a one-unit level track apart, that grid column gets a second cell (a slope across it takes the extra cell as level track at a bend); a column that cannot widen (a one-row slope from points to points crosses it) is logged and its switches share an OS block. `--fit COLSxROWS` stops the run when the panel shows more cells than that: 63x36 for a 1900 x 1200 screen, allowing about 100 pixels for the menu and title bars.

Without `--bindings` the panel has no sensor or turnout bindings and no signals; open it in the Designer to add them. `--bindings FILE.json` ties it to the layout's devices:

```json
{"switches": {"3":   {"block": "OS Switch 3", "normal": "B",
                      "routes": {"B": {"ROUTECOMMAND":   {"DECADDR": "12", "JMRIPREFIX": "IT", "USER_NAME": "Switch 3", "command": "close"},
                                       "SELECTEDREPORT": {"DECADDR": "12", "JMRIPREFIX": "IT", "USER_NAME": "Switch 3", "command": "close"}},
                                 "C": {"ROUTECOMMAND":   {"DECADDR": "12", "JMRIPREFIX": "IT", "command": "throw"}}}},
              "7/7b": {"block": "OS Switch 7b"}},
 "blocks":   {"Main": {"name": "Track Main", "station": "Main", "discipline": "CTC",
                       "occupied":   {"DECADDR": "40", "JMRIPREFIX": "IS", "USER_NAME": "Main occupied", "command": "close"},
                       "unoccupied": {"DECADDR": "40", "JMRIPREFIX": "IS", "command": "throw"}},
              "3-5":  {"name": "OS Switch 3"}},
 "masts":    {"12C":  {"name": "Mast 12C", "template": "double", "pantype": "LAMP2"}}}
```

- **switches**, by label, or `label/alias` for one of several switches with that number (a key that is not a whole label splits at its last `/`; labels compare as text): `block` names its OS block (switches of one number given different blocks keep apart; switches given one block name share one block, and that name is never suffixed or shared with another block), `normal` picks the CATS normal leg (default B), `label` replaces the number shown at its points (such as 23A and 23B for the two halves of a crossover), and `routes` gives each leg's IOSPECs (`ROUTECOMMAND`, `SELECTEDREPORT`, `NOTSELECTEDREPORT`). Double crossovers take a `block` only.
- **blocks**, by the panel's block name (after the switches' `block`s): `name` renames it, so a short track between two switches can join one of their OS blocks. Blocks end up as one only when the bindings name them all (a block keyed in `blocks` or named by a switch `block` keeps its own name); renaming onto a block the bindings do not mention stops the run, and each merge is reported; `station`, `discipline`, and the `occupied` and `unoccupied` IOSPECs.
- **masts**, by the name in the signals layer, field or planned (virtual masts are not drawn): `name` is the SECSIGNAL text (the layout's mast name), `template` the physical signal template, `pantype` the panel lamp (default `LAMP` and the head count). Each mast goes on the block boundary nearest where it stands on its run, on the edge of the block it protects (the side its move is heading for), facing out of that block, on the right-hand side of the move.
- An IOSPEC holds `DECADDR`, `JMRIPREFIX`, `USER_NAME` (also `JMRIDEVICE`, `EXIT_CMD`, `DELAY`) and its `command`, `close` or `throw`. Keys starting with `_` are notes. A name the panel does not have, or an unknown field, stops the run.

`--templates-from DESK.xml` copies the `SIGNALTEMPLATE`, `JMRINAME` and `COLORDEFINITION` elements of an existing CATS panel, so the masts' templates and the IOSPECs' device prefixes resolve and the colours match (CATS paints a block with no occupancy sensors in its DARK colour, grey by default); a mast naming a template the panel has no `SIGNALTEMPLATE` for stops the run. The cell rules are in [`skills/schematic-maps/references/cats-grid.md`](skills/schematic-maps/references/cats-grid.md).

## Layout Editor panel

`schematic le` writes a JMRI Layout Editor panel (one `<LayoutEditor>` element) that looks like the sheet: every band stacked on one panel, straight rows, yards leaving at the drawn slopes and running level, every corner rounded by a circular arc, each turnback a half circle, helix ends marked by a circle and connector letters in a circle, with switch numbers, track names, station names and band titles as labels. One grid unit is 36 pixels (`--cell`, `--row`); with the `equal_width` preference a narrower band is stretched along its length as on the sheet. It writes turnouts (right or left hand as drawn, the drawn straight leg as leg B and `continuing` set so the normal route stays on the band's leg B), a double crossover as a DOUBLE_XOVER, two switches of one number joined C to C as one single crossover, track segments with `mainline` set from the main route (Layout Editor draws main track wider), anchors, end bumpers, and a hidden track segment joining each connector letter and helix track that appears on two drawn bands, so the panel is one connected railroad. `--names` binds it to existing JMRI objects: by band key, turnout names, OS blocks, the normal leg, and each track's blocks in order (a track with several blocks is cut into equal lengths); without it, blocks are named after the tracks and turnouts are left unnamed. It writes no masts, sensors or block beans: add the turnouts and blocks to the tables file the panel goes into, close JMRI first, and check the panel with Layout Editor's Check menu once it loads. The mapping is in [`skills/schematic-maps/references/le-panel.md`](skills/schematic-maps/references/le-panel.md).

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
