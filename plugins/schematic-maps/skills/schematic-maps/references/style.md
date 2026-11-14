# Drafting style

What the sheet looks like and why. The rules come from published track diagrams: prototype interlocking sheets, track charts and model railroad crew charts. Each rule names the examples it comes from, so you can look at them. Nothing here is copied from them; look at the originals for the drawing.

Read this when a reader asks "why is it drawn that way", wants to change the look, or asks for something the sheet does not show yet. The command applies the rules marked **drawn**. The rules marked **not yet** are the style's, but the command does not draw them: say so, and offer to add the item by hand to the SVG or as a note beside it.

## At a glance

| Rule | Status |
|------|--------|
| One straight main per level, one band per level | drawn |
| Diverging legs at 45 degrees, ladders parallel | drawn |
| Two line weights: heavy main, light everything else | drawn |
| Hidden track dashed | drawn |
| Lettered connectors between bands, helix marks | drawn (helix elevation not yet) |
| Station bars under the track | drawn |
| Open ends with "To X" | partly: arrow and name; no terminal dot |
| Direction legend | drawn, once per page, or one per band (`band_legend`), plus an arrow on each main run where a level runs east to the left |
| Direction of each track | drawn where given (`track_directions`): one head for one way, two for both ways |
| Title block | drawn: name lines, and date, revision and sheet number when set; no revision history block |
| Labels in capitals, black on white | drawn |
| Signal masts | drawn |
| Capacity of yard tracks | drawn with `capacity`: cars after each yard or stub track name, totals under the station bars |
| Interlocking limits, yard limits, mileposts, dimension lines | not yet |
| Road crossings, bridges, industries | not yet |
| Long band folded into rows across the page | not yet |
| Detail sheet per town | not yet |

Example names used below are listed at the end, with links.

## The main and the bands

1. **One straight line for the main, one band for each level.** Several levels stack as horizontal bands, each with its main drawn dead level, and a name on the band. Drawn: the main-level rule (R5) keeps the main level through every switch, and `levels` in the overrides cuts the plan into bands. From: NYAMR orthogonal schematic, NEK schematic, St Charles chart, Willow Creek, the SAT paper's rule A.
2. **Branches and sidings leave at 45 degrees and run parallel.** Every diverging leg is one 45-degree step; a passing siding is a parallel line with a switch at each end; a yard is a ladder of parallel tracks, each stepping off the one before. No curves, except a loop drawn as a loop. Drawn: rows are whole grid steps and legs are diagonal (R6 keeps a yard track level along the ladder). From: NEK, St Charles fascia diagram, PRR 1958 diagram, PRR Floreffe plan, Conemaugh yard map, Harold interlocking schematic. Real angles are the prototype sheets' habit (Walbridge, the 1951 rebuild plan); an operator's schematic gives that up to stay readable.
3. **A switch's left and right legs stay left and right.** The hand of each switch comes from the overrides; the tool never guesses one. From the SAT paper's rule C.

## Line weights

4. **Two weights.** The main is heavy; sidings, yard tracks, spurs and crossings are about half. Drawn: `main_w` 3.2 and `side_w` 1.4 (drawing units, 96 to the inch), set in the preferences. From: St Charles fascia diagram, Willow Creek, Floreffe plan. Several prototype sheets use one weight for everything (the 1951 rebuild plan, the 1958 diagram, Walbridge), so two weights is a choice for readers, not a standard; no source gives weights in points.
5. **Hidden or staging track is dashed.** Drawn, for any track the plan marks hidden (`7 5` dash). From: NEK, St Charles chart, Willow Creek. The 1958 diagram uses dashes for something else (stages of a rebuild), so dashes are common, not universal.
6. **Black on white first.** Colour only as a second cue, never the only one, so the sheet still reads photocopied. Drawn: the tool uses black only. From: the territory colour code on the chicagorailfan page, the club plan with colour-only use (VMRR), and the St Charles chart, which is black and white by design. Not yet: red for rule limits or tinted staging, which the NYAMR sheet and the museum plan use.

## Levels, helixes and connectors

7. **A connector joins one band to the next.** A run that joins two levels is cut; each end is a circle holding a letter, with "TO X" beside it, and the same letter at the other end. Drawn. From: NEK (circled letter and arrowhead), St Charles chart and blocking sheet (boxed letters), the museum plan (numbered "To X (n)" matched at the far end), the NYAMR schematic (helix letters).
8. **A helix is a labelled mark, never drawn to look like one.** No source has one standard glyph; each writes the word. Drawn in four styles, chosen by `helix_style`: a box reading HELIX TO X where the tracks end (the default), a coil of three turns, a lettered circle, or an arrow with words. Each helix track keeps the same tag (H1, H2, ...) on every level. From: the Ridgely and museum plans (rings and the word "Helix", up and down arrows), NYAMR schematic, VMRR plan ("Up to 2nd level"). Not yet: the height of each level in a box on the track (museum and Ridgely plans).
9. **Staging is a box that names the places it stands for.** From NEK ("Staging: Newport VT, Montreal QC"). Not yet: the helix box names only where it leads.

## Stations, ends and direction

10. **A station is a bar under the track, with the name in bold capitals.** The bar spans the switches that belong to the station, with end ticks; stations that overlap stack in lanes. Drawn, from `stations` in the preferences. From: NYAMR schematic, St Charles chart (name with a short code), Santa Rosalia (names on the line). Not yet: the short code in brackets, and the quoted control-point name with a tower box and square brackets across the tracks for interlocking limits (the 1958 diagram and the 1951 rebuild plan).
11. **Every open end says where it goes.** Drawn: an arrowhead and "TO X" for a track that leaves the sheet; a short bar for a track that just ends. Not yet: a filled dot for a terminal (NEK). From: the 1958 diagram, the 1951 rebuild plan, Harold, NEK, Santa Rosalia ("To Ballard", "End of branch").
12. **Direction is printed once on the page, east to the right.** Drawn: two arrows with the direction names at the top, from `left` and `right` in the preferences, and no band is turned end for end unless you set `rotate_bands`. From: St Charles ("WEST | EAST"), the 1958 diagram. The prototype sheets were not consistent across a book and readers noticed, so the direction stays fixed on every sheet of a set. With `direction_arrows`, on a level whose main runs east to the left anywhere (a level reached by a helix, a loop that comes back along the other side), each level stretch of main track also carries a small EAST arrow, since one page legend would mislead there. Where the main runs east to the right throughout, the page legend alone says it. Where the levels differ (one drawn end for end, one whose tracks run both ways, a staging yard run one way), `band_legend` gives each band its own legend above its title instead: west to the left, west to the right, one arrow only, or none. A band with no single direction carries an arrow on each track, from `track_directions` in the overrides (a fact about the railroad, never guessed), with two heads where trains run both ways. No source sheet here draws per-track arrows; this is the tool's choice.

## Numbers and names on the sheet

13. **Capitals for tracks and signals, mixed case for towns, one sans-serif face.** Drawn: track names in spaced capitals along the track, switch numbers bold at the points, station names bold capitals, Helvetica-style faces. From: NEK, the 1958 diagram, the PRR Floreffe plan, St Charles. The prototype sheets turn text only along a vertical leg; the tool keeps all text level.
14. **A switch is numbered where its points are; a crossover prints one number.** Drawn: a double crossover is an X with its number above it. From: the 1951 rebuild plan, Walbridge, VMRR (switch numbers at the turnout), the model board description. With `facing_letters` in the preferences, a switch prints R or L after its number (23R, 101AL, a moved switch 223R*): R when its points meet an eastward train first, the sense of R and L in signal names. East follows the main route in timetable order, so it stays true through loops and on levels drawn east to the left; a level with no main route uses the direction it is drawn with. A crossover's shared number and a double crossover print no letter.
15. **No label sits on track, on another label or on a symbol.** Drawn (R12): each label has a list of allowed places and the hardest are placed first; a label with no place makes its own track longer. This is the one rule none of the sources gives, and the one where prototype sheets are weakest. The SAT paper calls general label placement a hard problem and uses rows of symbols above and below each track.
16. **Name every track on the line.** Drawn for tracks that have a name in the overrides. From: the 1958 diagram ("NO. 1 EWD MAIN TRK."), NEK (line names), Santa Rosalia. Not yet: a track number counted outward from the main (Whitcomb article); the reader gives names instead.

## Signal masts

17. **A mast is a stem across its foot, a short arm and one open circle for each head, with its name beyond the stem.** It stands on the right-hand side of the track for the direction it governs, so with east to the right a westward mast is above the track and an eastward one below. Drawn: this follows how the NYAMR Physical Characteristics Book draws masts. A mast on a sloping ladder link is drawn along the slope. A mast listed as planned is dashed; a virtual mast, used only by Dispatcher, is not drawn. From: the NYAMR book, the 1951 plan and the 1958 diagram (flag or arrow glyphs and a number beside them). Not yet: lever numbers, or the mast's aspects.

## Capacity, mileage and what to leave out

18. **Capacity belongs next to the track name.** A yard track is labelled with how many cars it holds, in 50-foot cars, and a ladder carries a total. Drawn with the preference `capacity` (`car_in`, default 7.4 in for a 50 ft HO car): every track that is not main, not a ladder link and not a connector shows its count after its name, or alone where it has none. The length is layer 1's `track_lengths_in` for a named track when given, else the plan's; an unnamed track that switches cut into pieces along one row counts once from the pieces' sum. Each station bar adds the total of the tracks whose west end is one of its switches. From: Conemaugh yard map (boxed bracket with a total), the NYAMR book, employee timetables (capacity columns). The model railroad examples left it out, so test whether the reader wants it on the map or in a table beside it.
19. **Mileposts and distances are ticks, not a scale.** Drawn for mileposts: with the preference `mileposts` (true, or `{"step": 0.25}`) each main-route track carries a small diamond on a stalk with its count beside it, above the track if there is room, else below, placed by the label placer. The count is in scale miles from layer 1's `milepost_origin` (a switch and its number) with `scale_ratio` (87.1 for HO), along `milepost_route` (default `main_route`, listed in timetable order), using measured lengths where `track_lengths_in` has them and the plan's elsewhere; a `helix_length_in` carries it through a helix to the next level. Ticks follow real length, so on a stretched drawing they are not evenly spaced on paper. Without a step, the smallest of 0.05 to 10 miles that leaves each band at most 8 ticks (fewer on a short band) is used for the whole sheet. Not yet: the feet between interlockings on a dimension line along the top. From: the 1958 diagram, the Floreffe plan, the PRR track chart legend, the 1951 plan.
20. **Leave out what does not operate.** NEK's author says it shows the passing sidings and the main yards, not every track. The tool follows what the plan and the overrides hold; a track the reader removes in the overrides is gone from the sheet.
21. **Road crossings, bridges and industries.** Paired verticals for a street with its name, a dashed vertical with its number for a bridge, outlined boxes touching the track an industry serves. Not yet. From: the 1951 plan, Floreffe plan, Santa Rosalia.

## Page, title and fold

22. **One page, US Letter landscape, drawn to fit.** Drawn: the page is 11 by 8.5 inches with a border, the bands are centred and the whole drawing is scaled down until it fits, never up. Several plans on one page share the same style. `equal_width` stretches narrower bands to match the widest.
23. **The title block names the railroad, the sheet and the date, and says what changed.** Drawn: a ruled box at the bottom left with the lines of `title`, the first bold, and, when the preferences set any of `date` (YYYY-MM-DD, printed NOV 14, 2026), `revision` (printed REV 1) and `sheet` ("1 of 1", printed SHEET 1 OF 1), a ruled column at its right with those fields stacked (Willow Creek's date stamp, the 1958 diagram's order number). Not yet: a revision block listing past changes (Walbridge); the history lives where the sheet is kept. The sources put the block at the bottom right; the tool puts it bottom left, clear of the direction legend and the long bands.
24. **A band that is too long folds into rows across the page.** The NWV schematic does this with a large arrow showing the way on. Drawn, when asked: with `fold: true` (or `fold_min_scale`, the smallest scale allowed, default 0.65) a sheet that would be drawn below that scale has its long bands cut into rows stacked down the page, as many as give the largest drawing (two to eight). Each row is a window onto the band's own drawing, so nothing in it changes. The cut is a rule, not a hint: never through a ladder, a crossover, a loop's bend, a label or a symbol, not under a station bracket if any other place will do, where the fewest tracks run on past it, and so the rows come out about equally full. The main line leaves a row in a large arrow marked CONTINUES and arrives at the next in one marked CONTINUED; every other track that runs on gets a small arrow; a row after the first repeats the band's title with (CONTINUED). Folding is left alone when it would not raise the scale. Off by default: with neither setting, or a sheet already above the floor, the page is byte for byte as it was. Not yet: a band turned end for end (`rotate_bands`) is never folded; a fold has no lettered connector, the arrows carry the way on.
25. **One overall sheet, plus a detail sheet for each town or group.** From: NMRA beginner's guide, Gateway NMRA, Santa Rosalia, the Physical Characteristics Book. Not yet: the tool draws the overall sheet only.

## What the style leaves open

The sources disagree on these, so the tool picks one and says so:

- **Orientation.** The prototype books vary; the Yosemite deck plans fix north; schematics use timetable east to the right. The tool uses east to the right on every band.
- **Track numbers or names.** Numbered from the main outward (Whitcomb), written on the line (Santa Rosalia), or none (Willow Creek). The tool prints names.
- **Hidden track.** A dashed line, or a lettered box at each end (St Charles). The tool dashes the line.
- **Levels.** Separate sheets (Yosemite), a dashed lower level on one plan (A&LS) or bands on one straightened sheet (NEK, NYAMR). The tool stacks bands.
- **Geometry.** Prototype interlocking sheets keep real angles; crew charts use 45 degrees. The tool uses 45 degrees; ask the reader to check a newcomer can still map it to the room.

## Examples

Links were opened for the research behind this file; some prototype sheets were scans and some PDFs could not be opened (marked in the plan). They are other people's work: look, do not copy.

| Short name | What it is |
|------------|------------|
| NYAMR orthogonal schematic | [bands per level, helix letters, station bars](https://davebarraza.wordpress.com/wp-content/uploads/2021/02/nyamr-orthagonal-schematic-210210-1.pdf) |
| NYAMR Physical Characteristics Book | [station pages, capacities, signals](https://davebarraza.wordpress.com/wp-content/uploads/2026/04/nyamr-physical-characteristics-book-260415.pdf) |
| NWV schematic | North Western Vermont system schematic, NER Coupler 303, pages 22 and 23 (no public link) |
| NEK schematic | [Northeast Kingdom track schematic](https://mainecentral.blogspot.com/2017/03/nek-track-schematic.html) |
| St Charles chart | [crew training track chart](https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796) and [blocking sheet](https://appalachianrailroadmodeling.com/stcharlesbranch/wp-content/uploads/2022/01/Clearance-Train-Order-and-Blocking-Sheet.jpg) |
| Willow Creek | [unfolded schematic](https://sites.google.com/site/willowcreekrr/track-plan) |
| Santa Rosalia | [town schematic in an op session briefing](https://modelingthesp.blogspot.com/2025/10/an-op-session-briefing.html) |
| Whitcomb article | [setting up a layout for operations](https://rrmodelcraftsman.com/set-up-your-layout-for-realistic-operations/) |
| Museum plan, Ridgely plan | helix and staging drawn on plans: [museum layout, Model Railroader 2023](https://www.trains.com/wp-content/uploads/2023/11/MRR-western-pennsylvania-model-railroad-museum-layout-1223.pdf) and [B&O Ridgely Division, 2026](https://www.trains.com/wp-content/uploads/2026/01/MRR-baltimore-ohio-ridgely-division-track-plan-0226.pdf) (trains.com blocks some downloads; the Wayback Machine had them) |
| VMRR plan | [club all-track plan with a legend](https://vmrr.org/wp-content/uploads/2020/07/CurrentDesign2.pdf) |
| Yosemite deck plans | [a plan per deck, with heights](https://yosemitevalleyrr.com/modeling/layout-plans) |
| A&LS plan | [plan with dashed lower level](https://www.opsig.org/files/do_extras/ALSTrackPlan.pdf) |
| Walbridge | [PRR interlocking sheet, 1957](https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif) |
| 1958 diagram | [PRR general order 418 track layout](https://www.redoveryellow.com/position-light/PRR_Diagrams/map_ett_pgh_1958_418.gif) |
| Floreffe plan | [PRR plan, 1936](https://www.redoveryellow.com/position-light/PRR_Diagrams/floreffe.gif) |
| 1951 rebuild plan | [Railway Signaling and Communications, June 1951, page 377](https://jonroma.net/media/signaling/railway-signaling/1951/P%26LE%20Rebuilds%20Interlocking.pdf) |
| PRR track chart | [Pittsburgh Division, 1941, with its symbol legend](https://www.trainweb.us/centreg/docs/Pbgh_div_41_tc.pdf) |
| Conemaugh yard map | [1957 yard map with capacity brackets](https://www.trainweb.us/centreg/docs/conemaugh_yard_map.pdf) |
| Harold interlocking schematic | [simplified 45-degree schematic, page 9](https://www.irum.org/20190605_LGAX_Presentation.pdf) |
| Territory colour code | [chicagorailfan, methods of train operation](https://chicagorailfan.com/opermeth.html) |
| Model board | [a working model CTC board](https://friendstm.org/Signals/ModelBoardDescription.shtml) |
| SAT paper | Luteberget and Johansen, [Drawing with SAT](https://link.springer.com/content/pdf/10.1007/s00165-021-00566-z.pdf), Formal Aspects of Computing 33 (2021); the rules are read from [the thesis chapter](https://luteberget.github.io/preprints/luteberget-thesis-plain-b5-2019-09-17.pdf). Read for ideas only; this tool does not use its code |
| NMRA guide, Gateway NMRA | [NMRA beginner's guide part 9](https://www.nmra.com/node/4420), [Gateway NMRA](https://www.gatewaynmra.org/?p=257) |
