# Seeding a CATS panel from the grid

`schematic cats OUT.xml --data DIR GRAPH.json:NAME ... [--band TITLE]` seeds a CATS Designer panel from the solved grid. It writes track, switch points, blocks, labels and logical joins; with `--bindings` (see the README) it also binds switch routes and block sensors, renames blocks to the layout's names and places masts. Without it there are no bindings and no signals; those are added in the Designer. The panel has not been checked by loading it in CATS for every kind of railroad, so offer it as a starting panel, not a finished one. What it does is under "How the command builds it" at the end.

The rules below come from the CATS Designer User Guide (pages 10 to 13, 52 to 64, 81 and 87) and were checked against the open CATS source, `cats/layout/items/Track.java` in the [CATS repository](https://bitbucket.org/Kb0oys/cats/src/master/). The guide is [here](https://cats4ctc.wdfiles.com/local--files/main:userguides/DesignerManual.pdf). Not found in either: a maximum grid size, any way to draw a curve, a vertical or non-45-degree diagonal, or rotated text.

## What a cell holds

- The panel is a rectangle of square cells, in columns and rows, that can be inserted, deleted, copied and pasted.
- A cell holds track, a label, a picture, a button, a station icon, or a mix, except that a picture excludes track and label.
- Track in a cell is any of six segments, each running from the middle of one edge to the middle of another: vertical, horizontal, and four diagonal corners (left to top, right to bottom, right to top, left to bottom). Several can share a cell.

## What that means for the schematic

- **A diagonal is two quarter-cell pieces.** A 45-degree step of one row uses one column and the neighbouring cells in two rows. Two parallel tracks one row apart join by a one-column diagonal; there is no half-row offset. The schematic's steps already fit this.
- **Connection is by shared cell edge.** Segments that end on the same edge are joined. Two or three tracks meeting on one edge are read as switch points. Exactly two complementary tracks meeting on an edge may be a crossing or a double slip, and the Designer asks which.
- **Crossings** are recognised only when both touching cells hold just two tracks and the segments are complements: the two diagonals of a cell, or two horizontals, or two verticals. Nothing signals at a crossing.
- **Blocks** come from tracks that share edges with no block boundary between them. A boundary lies on a cell edge, and signals attach only to boundary edges.
- **Signals** go in the cell by a placement code (left, low and so on) with a facing direction; a signal faces out of the block it guards. Draw names and signals below the track, because train labels show above it.
- **Labels** are one name per cell by a position code; text may spill into neighbouring cells.
- **Stations** are a solid box icon in a cell, in a chosen colour, with no effect on operation.
- **Two track ends that do not touch can be declared logically adjacent.** A helix or a level jump can be a logical join between two bands instead of a drawn line.

## Display settings to turn off when seeding

CATS compresses columns that hold no diagonals or labels to half width (Compress Screen) and wraps a wide panel into bands (Automatic Wrapping). Author the panel as one linear layout, or turn both off, so the screen matches the grid.

## How the command builds it

- **Scale.** One schematic grid unit is two cells. A schematic point (c, r) is the middle of the left edge of cell (2c, 2r) plus a margin. A level step fills one HORIZONTAL; a step up fills UPPERSLASH in its cell and LOWERSLASH in the cell above; a step down fills LOWERBACKSLASH and UPPERBACKSLASH below. Every leg is whole cells at 45 degrees, and the odd rows between tracks hold the names.
- **Switches.** A switch's legs B and C leave from one cell edge, its points. The points carry SWITCHPOINTS with two ROUTEINFO (the far edge of each leg's piece); leg B, the straight leg as the band records it, is NORMAL. A double crossover is its X across both through tracks: four points and a CROSSINGEDGE where the diagonals meet.
- **Turnbacks** are a vertical run in one column, ending in a corner piece at each track.
- **Blocks.** One per track (its name, or the two switch numbers it joins), one OS block per switch (switches of one number joined by a track share it, unless bindings give them different blocks). An OS block reaches one step past the points on each leg (past the X for a crossover), so no boundary lands on points or a crossing; the CATS edge builder ignores points on an edge that also has a block. A turnback joining two differently named tracks is cut in the middle of its vertical run. Every boundary edge names its block in full (CATS keeps one Block per name, `Block.findBlock`); discipline is CTC unless `--discipline` or a binding says otherwise.
- **Signals** (bound masts only). A mast stands on the block boundary nearest its place on its run. Its SECSIGNAL is on the edge of the block it protects, the block its move enters, with `SIGORIENT` the move's direction (the opposite of that edge) and `SIGLOCATION` on the right-hand side of the move: `UPRIGHT` on a right edge, `LOWLEFT` on a left edge, `LEFTUP` on a top edge, `RIGHTLOW` on a bottom edge.
- **Ends.** Connector letters and helix tracks that appear on two drawn bands are joined with SHARED (a block boundary on each side); others get a label, `A: TO <level>` or `HELIX TO <level>`.
- **Labels.** Band title with the left and right words, switch numbers next to the points, track names in a free cell under the longest level run, one label per cell.
- **Display.** `COMPRESSIONTAG` and `ROWWRAPTAG` are present, which turns Compress Screen and Automatic Wrapping off.

Keep the schematic as the master; regenerate the panel from it rather than editing the two by hand.
