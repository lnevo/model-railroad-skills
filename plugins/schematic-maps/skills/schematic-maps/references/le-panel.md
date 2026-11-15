# Drawing a Layout Editor panel from the grid

`schematic le OUT.xml --data DIR GRAPH.json:NAME ... [--names NAMES.json] [--panel NAME] [--band TITLE]` writes one JMRI Layout Editor panel, a `<LayoutEditor>` element, drawn from the solved grid so it looks like the sheet. It holds track, turnouts, anchors, end bumpers, labels and circle shapes. It holds no masts, sensors or block beans. Offer it as a starting panel: it has not been loaded in JMRI for every kind of railroad. Put it into a tables file with JMRI closed, add the turnouts and blocks it names, then run Layout Editor's Check menu (un-connected tracks, un-blocked tracks, non-contiguous blocks) once it loads.

The rules below were checked against the JMRI source (`jmri/jmrit/display/layoutEditor/`, release 5.16): `LayoutTurnoutView`, `TrackSegmentView`, `LayoutShape` and their `configurexml` classes.

## What Layout Editor reads

- **Turnouts.** A right or left hand turnout stores its centre, B and C; A is always the centre minus B's offset, so A, the centre and B lie on one straight line. Leg C is free. A wye stores B and C, and A is the centre minus the middle of the two. Crossovers (`ver="2"`) store all four points: A to B is one track, D to C the other. A single crossover's diagonal runs from the middle of A-B to the middle of C-D: down to the right is RH_XOVER, down to the left LH_XOVER.
- **Normal route.** `continuing="2"` means closed sets the route to B; `continuing="4"` means closed sets it to C. So the geometrically straight leg can be B while the normal route is the diverging one.
- **Arcs.** A track segment with `arc="yes" circle="yes"` and `angle` (up to 180 degrees) is a circular arc between its two ends. It is drawn from end 2 counterclockwise on screen through `angle` to end 1, so it bows to the left of the way from end 1 to end 2 as seen on screen. `flip="yes"` swaps the ends, which bows it to the other side. Without `circle="yes"`, the arc is a quarter ellipse and `angle` is not stored.
- **Shapes.** A `layoutShape` of type Closed whose points are all Curve is drawn as quadratic curves through the middles of its sides. Eight points on a regular octagon draw a circle.
- **Widths.** Main and side track take their widths from the panel's options: `mainlinetrackwidth` and `sidetrackwidth`, and `mainBlockLineWidth` and `sideBlockLineWidth` in `layoutTrackDrawingOptions`. A segment is main when `mainline="yes"`.
- **Hidden track.** A segment with `hidden="yes"` keeps the track connected but is not drawn.

## How the command builds it

- **Scale.** A grid point (column c, row r) is the pixel point (36 c, 36 r) in its band, moved below the band before it and centred on the widest band. With `equal_width` a narrower band is stretched along its length, at most 2.5 times, with the `band_width` shares as on the sheet. A band in `rotate_bands` is turned end for end.
- **Switches.** A switch is a turnout centred on its points, with legs of up to 12 pixels along its tracks. The leg the drawing runs straight on from A is Layout Editor's leg B. When that is the band's leg C, the legs swap and `continuing="4"` keeps the normal route on the band's leg B, or on the leg the names give as normal. Hand is as drawn: C to the right of the way from A to B is right hand. A switch with neither leg straight is a wye.
- **Crossovers.** A double crossover is a DOUBLE_XOVER across its two through tracks, its legs in its four corners. Two switches of the same number joined C to C by one track, both drawn on level tracks, are one single crossover. The two switches' OS blocks go on A-B and on C-D, and the track between them is inside it.
- **Track.** Each track is a chain of segments from leg to leg along the drawn line. Every corner is rounded by an arc of up to 18 pixels radius, tangent to both sides. A turnback is two 90 degree arcs that meet at an anchor on its far point, a half circle as tall as the rows it joins. Hidden track (dashed on the sheet) is `dashed="yes"`.
- **Blocks.** One block per track; with names, a track may carry several, cut into equal lengths in order from its first end to its second. A cut never falls inside an arc. A turnout carries its OS block.
- **Ends.** A track end is an end bumper. A connector letter or helix track that appears on two drawn bands ends at an anchor, and a hidden segment joins the pair. A helix end gets a circle and `HELIX TO <level>`. A connector end gets its letter in a circle and `TO <level>` above it.
- **Labels.** Band titles, switch numbers on the side away from the diverging leg, track names over the longest level run, and station names (the `stations` preference) below the band or above it for a station on the top side.
- **Names.** `--names` is JSON by band key (the first word of the band title):
  `{"Main": {"turnouts": {node: turnout name}, "os": {node: OS block}, "normal": {node: "B" or "C"}, "blocks": {strand id: [block, ...]}}}`.
  Node and strand ids are the band's own. Without names, a track's block is its name, or the two switch numbers it joins, made unique. A turnback, and a connector or helix track drawn on two bands, keep one block. An OS block is `OS <number>`, and turnouts are not named.
- **Idents.** `TOG<n>` turnouts, `TG<n>` segments, `AG<n>` anchors, `EBG<n>` end bumpers and `SHG<n>` shapes. They are unique in the panel and never start a segment with `TO`.

Keep the schematic as the master. Regenerate the panel from it rather than editing the two by hand.
