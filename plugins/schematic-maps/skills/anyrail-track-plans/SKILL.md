---
name: anyrail-track-plans
description: Reads an AnyRail track plan through AnyRail's own exports and names every piece by its geometry, never by a maker's part number. Straights by length, curves by radius and angle, flex by length and tightest radius, turnouts by hand, shape (straight, curved, wye), route lengths, diverging angle and frog number, double crossovers by length and track spacing. Covers which AnyRail feature gives which fact (the JMRI export, the endpoint and connection tabs, track details, the lists of materials, sections and labels), the export's scale and coordinates, and the pieces command that lists every piece in the JMRI export. Use when someone asks what track a plan holds, how long a run or a yard track is, which turnouts or curves a plan uses, whether two plans or two libraries use the same parts, or how to get geometry out of AnyRail for another tool. Not for drawing a schematic (use schematic-maps) or for editing a Layout Editor panel.
---

# Reading AnyRail track plans by geometry

A plan's part names depend on the track library each piece came from, and two libraries can name the same shape differently or name different shapes alike. So tell every piece by what it is: where its ends are and which way they face. A turnout is a turnout because it has three ends, and its size, hand and angle come from those ends. A catalogue number is at most a hint, to check against the geometry.

## Where the geometry comes from

AnyRail's own features, from its manual (AnyRail 7, `anyrail.com/AR7Docs/en/`):

| Need | AnyRail feature | What it gives |
|------|-----------------|---------------|
| Every piece's shape, in a file | File, Export as, JMRI Layout file | A JMRI PanelPro XML file (a Layout Editor panel) and a background picture. Read it with `schematic pieces` (below) |
| One end of a piece | Click the end point: the Endpoint tab | Its height, x, y and direction in degrees |
| A joint between two pieces | Click the connection: the Connection tab | The same, for the joint |
| One piece, in full | Select it, Track tab, Details | Details and positions of the selected track |
| How much of each part | Home tab (or File, Info), List of materials | Every element used, the total track length and the length per element. Copy it into a spreadsheet |
| Sections and labels | Home tab (or File, Info), List of sections; File, Info, List of labels | The sections defined, and the labels given to items such as turnouts |
| A 2D trace | File, Export as, DXF | A 2D export of the trace |

The JMRI export is the only one that holds every piece's geometry in a documented format (JMRI's panel XML). The list of materials names parts by their library, so use it for counts and lengths, not to tell pieces apart.

AnyRail's coordinates: by default the origin is at the top left and y points down. The Settings tab can flip y and move the origin, and sets the measurement system (metric by default, or inches as fractions or decimals). Check those settings before comparing numbers from the Endpoint tab with anything else.

The `.any` plan file itself is an undocumented binary format. It can be read directly with a reader built for it; this plugin does not include one.

## What the JMRI export holds

Checked against JMRI's source (Layout Editor track segments and Bezier code, v5.16) and against AnyRail exports:

- **No part names, makers or heights.** Only shapes. Heights come from the Endpoint tab.
- **Scale.** A recent export was written at 12 px per inch of plan (the command's default), and checked end point for end point, its px divided by 12 per inch gave the plan file's own coordinates with no offset. Older exports came out smaller, so the size is not fixed: if lengths are all off by one factor, measure one piece in AnyRail and pass `--px-per-cm`.
- **Straight track** is a plain `<tracksegment>`.
- **A curve** is a segment with `arc="yes" circle="yes"` and `angle` in degrees. Radius = chord / (2 sin(angle / 2)), length = radius x angle in radians. On the plan checked, radii came out as round numbers (24 in, 28.5 in, 31 in), which is a quick check that the scale is right.
- **Flex** shaped freely is a segment with `bezier="yes"` and control points; JMRI draws a Bezier through end point, control points, end point (two control points: a cubic). Measure along the curve, not the chord.
- **A turnout part** is a short `<layoutturnout>` (`LH_TURNOUT` or `RH_TURNOUT`) with one track segment on each leg, out to an anchor point. Those three anchors are the part's own end points, exact to the plan. The short turnout drawn between them is a symbol, not to scale: never read the frog angle from it.
- **A three-way part** is exported as two turnouts joined by a short track. **A double crossover** is a `DOUBLE_XOVER` with four legs (tracks A to B and D to C).
- **Sections** become JMRI blocks; the section name follows the block name's second underscore. Track ends are `END_BUMPER` points.
- Track drawn dashed (`dashed="yes"`) is read as hidden track by the schematic plan reader.

## Telling pieces apart

| Piece | Ends | Told by |
|-------|------|---------|
| Straight | 2 | Length |
| Curve | 2 | Radius and angle |
| Flex | 2 | Length, change of heading end to end, tightest radius along it |
| Turnout | 3 | Hand, shape, straight route length, diverging chord, diverging angle |
| Three-way | 4 | One end facing the other three |
| Double crossover | 4 | Two parallel tracks: length and spacing |
| Crossing or slip | 4 | Two tracks crossing; the ends alone do not tell a diamond from a slip |

Turnouts, step by step:

1. **Points end**: the end the other two leave from.
2. **Hand**: with y pointing down, the diverging end lies clockwise (right) or counterclockwise (left) of the straight route, seen from the points.
3. **Shape**: read the heading where the straighter leg leaves the part, from the track joined beyond it. It runs on along its own chord on a straight turnout, bends toward the diverging leg on a curved turnout, and away from it on a wye.
4. **Diverging angle**: the change of heading between the two legs where they leave the part. The frog number of a straight turnout or wye is 1 / (2 tan(angle / 2)): an angle of 9.5 degrees is a number 6, 11.4 degrees a number 5.
5. **Size**: the straight route (points end to straight end) and the diverging chord (points end to diverging end). Two turnouts with the same hand, shape and sizes within a few millimetres are the same part, whatever their libraries call them.

Where nothing plain or flex joins beyond a leg (a buffer stop, a curve, another turnout butted on), that leg's heading cannot be read from the export. Say so, and read it in AnyRail's Endpoint tab instead of guessing.

## Run it

`<plugin>` is the folder two above this file; `<plugin>/bin/schematic` runs `python3 -m schematic`.

1. In AnyRail: File, Export as, JMRI Layout file.
2. `schematic pieces export.xml` prints the scale, then one line per kind of piece: count, measures in cm and inches, and the export idents. `--json pieces.json` writes every piece with its measures and end points; `--px-per-cm X` sets another scale.
3. Check the scale against one piece in AnyRail (two end points' x and y in the Endpoint tab).
4. Read the `note` and `skipped` lines. A note names turnouts whose shape could not be read. Skipped elements (level crossings, slips, turntables, elliptical arcs, other turnout types) are listed with the reason; nothing is dropped unseen.
5. Look at flex lines with a small tightest radius: a short flex piece with a kink in it shows up there.

## Pitfalls

- Never identify a part from its catalogue number alone. Libraries differ per file, and tags inside one file are not stable across files.
- The export's turnout type gives the hand but not the shape: a curved turnout is exported as `LH_TURNOUT` or `RH_TURNOUT` too.
- Two turnout halves of a three-way part read as two turnouts; one of them has a short straight route.
- Lengths from the list of materials and from the export are both plan lengths. They are not the length of the built track.
- Sharing: a plan's track geometry is the planner's own work, but its placed objects, buildings and the `.any` file may hold other people's copyright work. Share exports of track, not the plan file or its objects.
