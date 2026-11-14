# Seeding a CATS panel from the grid

Not yet implemented by the tool. This is what a later step needs to know: the schematic's layout is already whole grid cells, and the CATS Designer draws on a grid of cells too, so one layout could seed the other. Do not offer it as a feature; offer it as a possible next step.

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

## If it is built

Use integer rows and columns and 45-degree legs only, one row per offset, labels in a cell beside the track (below preferred), and a logical join for each connector or helix. Keep the schematic as the master; regenerate the panel from it rather than editing the two by hand.
