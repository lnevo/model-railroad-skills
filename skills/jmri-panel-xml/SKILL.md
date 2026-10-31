---
name: jmri-panel-xml
description: Edits JMRI Layout Editor panel and tables XML safely by script. Covers what a panel or tables file holds, the names and connections that must agree across it, what JMRI rewrites on Store, why edits must happen with JMRI closed, and how geometry attributes behave. Use when a task reads, generates, or changes a JMRI panel or tables .xml file, when adding or renaming tracks, anchors, end bumpers, turnouts, blocks or masts outside the JMRI GUI, when moving or scaling panel geometry by script, or when a panel loads with missing connections, lost blocks, or vanished edits. Not for signal logic semantics; use jmri-sml-nx for facing blocks, Signal Mast Logic discovery, and Entry/Exit.
---

# Editing JMRI panel and tables XML

## The safe sequence

1. Close JMRI.
2. Copy the file somewhere safe.
3. Parse and edit with a real XML library. Do not patch text with regex.
4. Check your edits against the key rules below.
5. Run JMRI's Validate XML File tool.
6. Open the file in JMRI and read the log for errors.
7. Run the Layout Editor Check menu: Un-Connected Tracks, Un-Blocked Tracks, Non-Contiguous Blocks.
8. Store from JMRI once, then diff against your edit to see what JMRI normalised.

## What is in the file

The root is `layout-config`. The sections you will touch most:

- `turnouts`, `sensors`, `memories`, `blocks`: named beans.
- `signalmasts`: the masts themselves.
- `layoutblocks`: Layout Blocks, plus the `blockrouting` and `routingStablisedSensor` attributes.
- `signalmastlogics`: stored Signal Mast Logic.
- `entryexitpairs`: stored NX pairs.
- `LayoutEditor`: one element per panel, named by its `name` attribute.

Inside `LayoutEditor`:

- Icons and labels, such as `signalmasticon` and `sensoricon`.
- `layoutturnout`, `layoutSlip`, `levelxing`, `layoutturntable`, `layouttraverser`.
- `tracksegment`.
- `positionablepoint`: anchors, end bumpers, and edge connectors, by `type`.
- `layoutShape`.

Not stored at all, so never add them:

- Block connectivity. JMRI rebuilds it from the track objects after load.
- Block routing tables.
- Automatic SML blocks and turnouts.

## Every element needs a class

- Give every direct child of `LayoutEditor` a `class` attribute. Copy it from a sibling of the same kind.
- Do not modernise class values. JMRI deliberately stores old names such as `...configurexml.TrackSegmentXml` and maps them on load.

Why: the panel loader reads `class` on each child, with no null check, to pick the adapter.

## Track names must match their type

JMRI finds a connected object by the prefix of its name. Use these prefixes for new `ident` values:

| Object | Prefix | Example |
|---|---|---|
| Turnout | `TO` | `TO12` |
| Anchor | `A` | `A40` |
| End bumper | `EB` | `EB3` |
| Edge connector | `EC` | `EC1` |
| Level crossing | `X` | `X2` |
| Slip | `SL` | `SL1` |
| Turntable | `TUR` | `TUR1` |
| Traverser | `TRV` | `TRV1` |
| Track segment | `T` | `T77` |

- Keep each `ident` unique in the panel.
- Do not start a track segment name with `TO`, `TUR` or `TRV`. Those prefixes are tested first, so the lookup goes to the wrong object type and returns nothing.
- A prefix outside this table generally logs "unknown type name prefix" and leaves the connection empty.

## Connections must agree at both ends

A `tracksegment` names both ends:

```xml
<tracksegment ident="T77" blockname="Block A"
  connect1name="TO12" type1="TURNOUT_B"
  connect2name="A40" type2="POS_POINT"
  dashed="no" mainline="yes" hidden="no" class="..."/>
```

- `type1` and `type2` say which part of the object connects: `POS_POINT` for anchors and bumpers, `TURNOUT_A` to `TURNOUT_D` for turnout legs.
- The far object must point back:
  - A turnout leg uses `connectaname` to `connectdname`.
  - A `positionablepoint` uses `connect1name` and `connect2name`.
- An end bumper uses `connect1name` only.
- Update both sides on every rewire. Load does not reconcile them. It looks up each stored name, and a name that finds nothing just stays unconnected.
- Edge connectors also need `linkedpanel` and `linkpointid`, and the partner must name this point back.

## Attribute defaults on load

If you omit these on a `tracksegment`, JMRI assumes:

- `dashed`: yes.
- `mainline`: yes.
- `hidden`: no.

Write all three, so a new segment does not load dashed by accident.

## Block names must line up in three places

A block exists as a Block bean, a Layout Block, and references from track objects.

- Set `blockname` on segments, and `blockname` to `blockdname` on turnouts, to the Layout Block user name.
- Do not use a system name there. If `blockname` is a Block system name, JMRI opens a dialog asking for a user name while the panel loads.
- Give the `layoutblock` the same user name as its Block. If no Block has that user name, JMRI creates a new one silently, with an `IB` system name.
- If `blockname` matches nothing, JMRI logs "does not return a block" and the track has no block.
- Rename a block everywhere at once: the Block, the `layoutblock`, every track and turnout reference, SML block lists, and any NX block references.

## Masts and sensors bind differently by object

| Object | Mast | Sensor |
|---|---|---|
| `positionablepoint` | `eastboundsignalmast`, `westboundsignalmast` attributes | `eastboundsensor`, `westboundsensor` attributes |
| `layoutturnout` | `signalAMast` to `signalDMast` child elements | `sensorA` to `sensorD` child elements |

- Use child elements on turnouts. An attribute with that name is ignored.
- Treat the slot as the binding. Facing-block lookup reads the slots and never reads `signalmasticon`.
- Bind each mast or sensor to one slot only. Lookup stops at the first match.
- Use names that resolve to an existing mast. A bad name logs "Unable to find Signal Mast".

## What JMRI owns

Store does not edit your file. JMRI builds a new document from the objects in memory.

Expect this after any Store:

- XML comments, unknown attributes, and unknown elements are gone.
- Attribute order and track ordering are JMRI's. In a panel, turnouts come first, then segments, points, crossings, slips, turntables, traversers.
- A `layoutblock` that no track uses is dropped. Only blocks with a use count above zero are written.
- `blockrouting` is written only when advanced routing is on. Turning it on by hand needs the attribute set to `yes`.
- A source mast with no destinations is dropped from `signalmastlogics` with a warning.

So keep your own metadata outside the file. Re-run generators from source data, not from a stored file you expect to keep your markup.

JMRI has two configuration stores:

- `storeConfig` writes layout configuration only, with no panels.
- `storeUser` writes user and configuration data, including panels.

Do not point a configuration-only store at a file that holds panels.

## Editing while JMRI is open

- Do not edit the file with JMRI running if that session might Store. Store writes memory over your edit.
- Do not Load an edited copy to pick up changes. Load creates objects; it does not refresh them. A panel whose name already exists triggers a duplicate-panel prompt, and answering Yes builds a second panel.
- Restart JMRI after every external edit.
- Remember Signal Mast Logic rediscovery runs when the panel loads, not when a panel changes and is stored.

## Occupancy sensors

- Note that sharing a sensor between blocks is not validated at load. The Layout Block edit dialog refuses a sensor already held by an in-use block, but a file can carry it.
- Do not rely on sensor-to-block lookup when two blocks share a sensor. It returns the first match.

## Geometry

Units are panel pixels. x grows right and y grows down.

- `positionablepoint`: `x`, `y`.
- `layoutturnout`: `xcen`, `ycen`, `xb`, `yb`, `xc`, `yc`, with `xa`, `ya`, `xd`, `yd` for crossovers.
- `tracksegment`: no coordinates. Its ends follow what it connects to.
- Arcs use `arc`, `flip`, `circle`, `angle`.
- Beziers use `bezier` and a `controlpoints` child with at least two `controlpoint` entries. Write them as `index`, `x`, `y`.

Rules:

- Move a turnout by shifting `xcen`, `ycen`, `xb`, `yb`, `xc`, `yc` by the same offset. B and C are absolute in the file, so moving the centre alone changes the turnout's shape.
- Do not edit `xa` and `ya` on a plain turnout. Point A is computed as the centre minus B's offset, so edits have no effect. On a wye it comes from the midpoint of B and C.
- Keep `ver` as written. `xa`, `ya`, `xd`, `yd` are read only when `ver="2"`.
- Do not change `xscale` or `yscale` to resize. They record scaling already applied; Layout Editor's scale operation moves the coordinates and updates them together.
- Update `panelwidth` and `panelheight` if you move track outside the canvas.
- Do not expect `x`, `y`, `windowwidth`, `windowheight` to win. Saved per-machine window preferences override them unless the old location and size preference is on.
- Expect two-decimal rounding if the shorten-writes store preference is on.
- Zoom is not in the panel element. It is a per-window preference.
- Treat coordinates as logic, not decoration. East and west mast slots are derived from them, and rotating or mirroring track can reverse which slot is correct. See jmri-sml-nx.

Checked against JMRI source at commit bd71f7f (2026-10-31).
