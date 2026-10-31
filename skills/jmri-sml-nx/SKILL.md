---
name: jmri-sml-nx
description: Explains and fixes JMRI Signal Mast Logic, automatic discovery, and Entry/Exit (NX), including how facing and protected blocks are resolved from mast slots at block boundaries and end bumpers. Use when placing masts or NX sensors on a Layout Editor panel, by GUI or by script, when choosing east or west bound slots, when discovery misses a mast or pair, when errors such as "No facing block found for destination mast" or "routing not stabilised" appear, when a mast at a buffer stop will not work, when editing signalmastlogics or entryexitpairs XML, or when choosing an NX type. For general XML edit safety and Store behaviour, use jmri-panel-xml.
---

# Signal Mast Logic and Entry/Exit in JMRI

## Terms

- Signal Mast Logic (SML): the rules between one source mast and one destination mast.
- Facing block: the block the train is in when it reads the mast.
- Protected block: the block the mast guards, next along the route.
- Slot: the place a mast binds on a track object.

Every lookup below starts from the slot. The mast icon plays no part.

## Before discovery can run

- Turn on Layout Block routing (`blockrouting="yes"` in `layoutblocks`).
- Wait for routing to settle after load. It needs a quiet period, two seconds by default.
- Give every block a user name. Facing lookup fails on a block without one.
- Assign blocks to track. Boundaries only exist between two assigned, different blocks.

Discovery for all masts defers itself and reruns if routing has not settled. Discovery for one mast throws "routing not stabilised" instead.

## Where masts can go

Place a mast only at a block boundary, or at an end bumper.

- Anchor: a boundary only if its two segments are in different blocks.
- Turnout leg: a boundary only if the attached segment's block differs from the turnout's block.
- Level crossing leg.
- End bumper.

A mast on an anchor with the same block on both sides is invisible to discovery. Why: discovery walks pairs of neighbouring blocks and asks for the mast between them. To use that spot, split the block there.

## Anchors: which slot

- `eastboundsignalmast` faces the block on the west side and protects the block on the east side.
- `westboundsignalmast` faces the east side and protects the west side.

East and west come from panel coordinates, not railroad compass. JMRI compares the far ends of the two attached segments:

- If the x gap is more than twice the y gap, the track is horizontal. West is left.
- If the y gap is more than twice the x gap, the track is vertical. West means north, which is up the panel. So the east slot is southbound.
- Otherwise, JMRI treats it as horizontal.

Traps:

- The far ends decide, not the track's angle at the anchor. A long curve can classify differently from how it looks locally.
- Moving, rotating or mirroring track can change the answer. Recheck slots after any geometry edit.
- To check by eye, open Set Signal Masts on the anchor. Each slot shows its Protecting Block.
- At an edge connector, ignore the East and West labels. Use only the Protecting Block.

## End bumpers: which slot

Use the slot for the direction a train travels into the bumper:

| Track runs from bumper | Bumper is at | Slot |
|---|---|---|
| Left | Right end of track | `eastboundsignalmast` |
| Right | Left end of track | `westboundsignalmast` |
| Up | Bottom end of track | `eastboundsignalmast` |
| Down | Top end of track | `westboundsignalmast` |

The same applies to `eastboundsensor` and `westboundsensor`. The rule uses the bumper position and the far end of its one segment, with the same horizontal and vertical test as anchors.

Prefer the Set Signal Masts dialog when you can. At a bumper, it offers only the correct slot.

Why the slot matters: an end bumper has only `connect1`. The east slot resolves to `connect1` only when that segment is on the west side; otherwise lookup takes `connect2`, which is empty, and returns no block. The west slot is the mirror image.

The trap: discovery's bumper search accepts either slot, but building the pair does not. A mast in the wrong slot is listed as a destination, then fails with "No facing block found for destination mast".

Other bumper rules:

- A bumper mast is a destination only, never a source. It has no protected block, so nothing can be discovered from it.
- To let a train leave a stub, put a mast at the stub's block boundary facing out.
- Discovery searches for a bumper mast only if the block has exactly one neighbouring block. If the stub block has more, the mast is not found. Split the block with an anchor so the last block has one neighbour.
- A virtual mast works as the destination at a buffer stop or dark area. It only needs to show Danger.

## Turnouts and crossings

- A turnout mast faces the track at that leg: slot A faces the segment on A, and so on.
- The mast protects the turnout's own block. You can only signal into a turnout, not out of it. For the block leaving a turnout, use an anchor on the next boundary.
- On a linked turnout, slot A counts only for an unlinked turnout or the first of a three-way.
- Crossings follow the same rule: masts cover the boundary into the crossing.
- When both crossing blocks are set and differ, SML adds the crossing's other block as a required-clear block automatically.
- Thrown routes through a double crossover add its conflicting blocks to the auto list too.

## What discovery does

There are two ways to run it:

- All masts: Tools > Auto generate Signaling Pairs in the SML table.
- One mast: the Discover button in the mast's Signal Mast Logic pane.

It pairs a source with each destination that:

- Is reachable from the source's facing block through its protected block.
- Runs in the same direction. A destination whose protected block lies on the path is rejected.
- Has no other same-direction mast between them.

Discovery rules to rely on:

- It only adds. It never removes a pair, and it skips pairs that already exist. Manual pairs survive, and stale pairs stay until you delete them.
- It works in memory. Store afterwards or the pairs are gone.
- On large layouts it can take some time.
- It logs and continues when one pair fails, and the failed destination stays in the list. Read the log.

## On panel load

- Automatic blocks and turnouts are rebuilt for pairs with `useLayoutEditor` set.
- Load does not add new pairs or remove invalid ones. It only refreshes existing pairs.
- A pair that fails here fails quietly. Its exception is treated as normal, so it simply has no automatic details. Check the pair in the SML table after any panel change.
- Changing the panel and saving does not rediscover in that session. Restart JMRI.

## Reading the errors

| Message | Means | Do this |
|---|---|---|
| advanced routing not enabled | Routing is off | Turn on Layout Block routing |
| routing not stabilised | Routing is still settling | Wait, then retry |
| No facing block found for source mast | Source slot does not resolve | Check the slot and boundary |
| No facing block found for destination mast | Often a bumper mast in the wrong slot | Use the table above |
| Path not valid, protecting block is null | No route through any protected block | Check connections and direction |
| Path not valid, destination check failed | Destination is unreachable or wrong way | Check slot direction |
| Signal X already exists between blocks | A same-direction mast is in the way | Pair with the nearer mast |
| Block X is not on a Layout Editor panel | No Layout Block for that name | Fix the block user name |

## SML XML

```xml
<signalmastlogic source="Mast 12">
  <sourceSignalMast>Mast 12</sourceSignalMast>
  <destinationMast destination="Mast 14">
    <destinationSignalMast>Mast 14</destinationSignalMast>
    <comment/>
    <enabled>yes</enabled>
    <allowAutoMaticSignalMastGeneration>no</allowAutoMaticSignalMastGeneration>
    <useLayoutEditor>yes</useLayoutEditor>
    <useLayoutEditorTurnouts>yes</useLayoutEditorTurnouts>
    <useLayoutEditorBlocks>yes</useLayoutEditorBlocks>
    <lockTurnouts>no</lockTurnouts>
  </destinationMast>
</signalmastlogic>
```

- Edit the child elements. The `source` and `destination` attributes are for human reading, and load ignores them.
- Do not write automatic blocks or turnouts. The `blocks`, `turnouts`, `sensors` and `masts` children hold user-set items only.
- Remember user-set items win over automatic ones.
- A missing source or destination mast logs an error and that logic is not loaded.
- Do not span a same-direction mast with one pair. Make two pairs instead.

## Entry/Exit (NX)

NX sets routes from a pair of sensors placed at block boundaries.

Sensor placement:

- Bind sensors in the same places as masts: `eastboundsensor` and `westboundsensor` on points, `sensorA` to `sensorD` on turnouts.
- Pick the sensor for the protected block. It is the entry for routes starting there and the exit for routes ending before it.
- At turnouts and crossings, sensors cover the boundary into the object only.
- At end bumpers, there is one choice. Use the slot table above.

Types, stored as `nxType` on each `destination`:

| Help name | `nxType` | Behaviour |
|---|---|---|
| Turnout Only | `turnoutsetting` | Sets turnouts |
| Turnout and SignalMast Logic | `signalmastlogic` | Also generates SML for the route |
| Full Interlocking | `fullinterlocking` | Also reserves the blocks |

For the SML types:

- Put masts at the same boundaries as the sensors, working in the same direction.
- If SML already exists for the pair, no temporary SML is made.
- Temporary SML lasts for the session and is not saved.
- Without Use ABS Signal Mode, the mast is held until a route is set.
- With all NX pairs of a source mast disabled, the hold is released.

Creating pairs:

- Auto Generate Entry-Exit Pairs finds all valid pairs. It is in Layout Editor Tools > Entry Exit.
- Manual pairs can be invalid, and invalid pairs are never used. Since 5.5.7 JMRI offers to delete one that fails validation.
- Both Way is not available if a boundary has a signal or the destination is at an end bumper.

Other limits:

- Removing an NX sensor also removes its pairs. It stops if a Logix or LogixNG uses one.
- A block referenced by a pair cannot be renamed or removed through Edit Track.

XML: `entryexitpairs` holds `layoutPanel` (with `name`), then `source` (with `type` and `item`), then `destination`. `type` is `signalMast`, `sensor` or `signalHead`. `uniqueid` is required on each `destination`.

Checked against JMRI source at commit bd71f7f (2026-10-31).
