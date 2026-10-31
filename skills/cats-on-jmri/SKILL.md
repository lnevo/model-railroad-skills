---
name: cats-on-jmri
description: Guides running CATS (Crandic Automated Traffic System) on top of JMRI, covering version checks, installation beside JMRI, the relationship between Designer and CATS, panel XML structure, how panel entries bind to JMRI sensors, turnouts, signal heads and masts, and what must not be done with JMRI tables during a CATS session. Use this skill when installing or launching CATS, when reading or debugging a CATS panel XML file, when track is missing from the dispatcher panel, when a device will not bind, or when deciding where JMRI tables may be edited and stored.
---

# CATS on JMRI

CATS is a CTC dispatcher panel that runs inside the JMRI application framework. Its main class, `cats.apps.Crandic`, extends JMRI's `apps.Apps`. It draws from a panel XML file and reaches hardware through JMRI's device managers.

## Check versions

- Read the versions in `cats/common/VersionList.java`: `CATS_VERSION`, `DESIGNER_VERSION` and `STATUS_VERSION`.
- Do not assume a supported JMRI range from the source. It declares none, and CATS makes no JMRI version check at startup.
- Get the range from the notes for your CATS release, and retest after every JMRI upgrade. The startup splash names the JMRI version and the log names the CATS version.
- Use Java 11 or later. The launcher `Cats.sh` runs JMRI's Java version check before it starts CATS. On macOS it searches for Java 11 to 17.
- Expect only a warning for a panel whose `VERSION` attribute falls outside 0.07 to `DESIGNER_VERSION`. Treat that warning as a real format question: CATS still tries to load the file.

## Install and launch

- Put `cats.jar` and the launcher in the JMRI program folder, next to `jmri.jar`. `Cats.sh` changes to `JMRI_HOME`, which defaults to the script's own folder, then builds its classpath from `jmri.jar`, `cats.jar` and `lib/*.jar`.
- Start CATS with the launcher, passing a profile and the panel file:

  ```bash
  ./Cats.sh --profile=MyProfile /full/path/to/panel.xml
  ```

- Use a full panel path, because the working directory is `JMRI_HOME`.
- Pass only one panel. With several, CATS warns and uses the last.
- Open a panel later with File > Open if none was given at launch.
- Never unpack or decompile `cats.jar`. The project is open source: read the Java source instead.

## Designer

- Treat Designer as a separate program. Its source is not part of the CATS source tree, so this skill covers only what CATS requires of the file it writes.
- CATS reads panel XML with root element `DOCUMENT`. It does not read a JMRI Layout Editor panel as a track plan.
- Do not rely on Designer to catch the edge rules below. A source comment states that it does not enforce a track edge at the end of track, so check a hand-edited or generated panel yourself.

## Panel XML structure

```xml
<DOCUMENT VERSION="3.1" WIDTH="800" HEIGHT="400" X="0" Y="0">
  <!-- fonts, counters, signal templates, colours, stores -->
  <JMRINAME JMRIPREFIX="IS" XMLTYPE="Sensor">...</JMRINAME>
  <TRACKPLAN ROWS="10" COLUMNS="40">
    <SECTION X="1" Y="2">
      <TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
      <SEC_EDGE EDGE="LEFT"/>
      <SEC_EDGE EDGE="RIGHT"/>
    </SECTION>
  </TRACKPLAN>
</DOCUMENT>
```

Each `SECTION` is one grid cell. Each `TRACK` joins two edges of the cell:

| TRACK | Joins |
|-------|-------|
| `HORIZONTAL` | LEFT, RIGHT |
| `VERTICAL` | TOP, BOTTOM |
| `UPPERSLASH` | LEFT, TOP |
| `LOWERSLASH` | RIGHT, BOTTOM |
| `UPPERBACKSLASH` | RIGHT, TOP |
| `LOWERBACKSLASH` | LEFT, BOTTOM |

### Turnouts

Give a turnout cell two tracks that share one edge. Put `SWITCHPOINTS` on the shared edge. In each `ROUTEINFO`, `ROUTEID` names a leg's far edge, and `NORMAL="true"` marks the normal leg:

```xml
<SECTION X="7" Y="2">
  <TRACKGROUP>
    <TRACK>HORIZONTAL</TRACK>
    <TRACK>LOWERBACKSLASH</TRACK>
  </TRACKGROUP>
  <SEC_EDGE EDGE="RIGHT"/>
  <SEC_EDGE EDGE="BOTTOM"/>
  <SEC_EDGE EDGE="LEFT">
    <SWITCHPOINTS>
      <ROUTEINFO ROUTEID="RIGHT" NORMAL="true"/>
      <ROUTEINFO ROUTEID="BOTTOM"/>
    </SWITCHPOINTS>
  </SEC_EDGE>
</SECTION>
```

Set `SPUR="true"` on `SWITCHPOINTS` for a spur turnout. Without it the points are built as an OS edge.

### What one edge can be

Each `SEC_EDGE` becomes exactly one kind of edge, checked in this order:

1. `BLOCK`, with or without a signal: a block edge.
2. `SECSIGNAL` with no block: a signal edge, which is also a block edge.
3. `SWITCHPOINTS`: points.
4. A crossing edge.
5. Nothing: a plain edge.

Do not put `BLOCK` or `SECSIGNAL` on the same edge as `SWITCHPOINTS`. The points are dropped with no error.

### Block rules

- Give every block edge a matching block edge in the neighbouring cell. Pair a named `BLOCK` with a bare `<BLOCK />`, or with a `SECSIGNAL`. `BlkEdge` casts its neighbour to `BlkEdge` when it searches for trains, so a plain edge or points opposite throws `ClassCastException` at run time, during occupancy, and not at load.
- Leave the joint plain on both sides when the far side is `SWITCHPOINTS`.
- A block edge with no neighbour is fine, such as end of track or the panel rim.
- `BLOCK` on a turnout cell's non-points edges is legal.
- Expect blocks to flow through turnouts. Points pass their block on to the next edge, so a block region is every cell not separated by a `BLOCK` edge.
- Name each region once. A bare `<BLOCK />` adopts the block that reaches it. Two different named blocks in a region log `has a second definition for its Block`.
- Set `DISCIPLINE` to exactly one of `CTC`, `ABS`, `APB-2`, `APB-3`, `DTC` or `Unknown`. Anything else, including plain `APB` or `UNDEFINED`, is rejected on load.

### Blank cells

A cell paints only if its track is in a block with `VISIBLE="true"`, which is the default. Search standard output for this message before trusting the screen:

```text
Found a track in Section (x,y) that is not in a Block.
```

### Screen layout

- Screen compression defaults to on, so columns can look squeezed. A bare `<COMPRESSIONTAG />` turns it off.
- Change cell size in CATS under Appearance > Grid Size. The default is 30 by 30.

## How devices bind

An `IOSPEC` names a JMRI device and a state:

```xml
<OCCUPIEDSPEC>
  <IOSPEC JMRIPREFIX="LS" DECADDR="101" USER_NAME="Block A1 Occ">close</IOSPEC>
</OCCUPIEDSPEC>
<UNOCCUPIEDSPEC>
  <IOSPEC JMRIPREFIX="LS" DECADDR="101">throw</IOSPEC>
</UNOCCUPIEDSPEC>
```

- Identify a device by any of: prefix plus address, prefix plus `USER_NAME`, or `JMRIDEVICE` plus `USER_NAME`. `JMRIDEVICE` is the type spelled out, such as `Sensor` or `Turnout`.
- End a prefix in the type letter: `C` chain, `L` light, `M` memory, `R` reporter, `O` route, `S` sensor, `T` turnout.
- Read the state words by device type:

| Device | `throw` | `close` |
|--------|---------|---------|
| Sensor | INACTIVE | ACTIVE |
| Turnout | THROWN | CLOSED |
| Light | OFF | ON |

  So occupancy from an active-when-occupied sensor is `close`.
- Prefer user names when the device already exists in JMRI. A user name that JMRI lacks reports `not found` and leaves the entry unresolved.
- Check system names carefully. CATS calls JMRI's `provide`, so a mistyped address silently creates a new device in the JMRI table.
- Expect CATS to write user names into JMRI when an existing device lacks one.
- Load the JMRI tables first. Use the profile's startup, or set `INCLUDEFILE` on `DOCUMENT`. That attribute loads the named JMRI file through JMRI's configure manager, activates Logix and initializes layout block paths. Use a full path that is valid on that computer.

### Signals

- CATS looks up a signal head by name in JMRI's signal head table and uses it if found.
- If there is none, CATS creates its own head and registers it in JMRI's signal head table.
- CATS likewise looks up a mast by the signal's name. If there is none, it creates a virtual or head-based mast and registers it. Unnamed signals get names starting with `Cats`.
- Define heads and masts in JMRI first if you want CATS to use yours.

## JMRI tables during a CATS session

Do this:

- Edit and Store JMRI tables in PanelPro, with no CATS panel loaded.
- Never use a JMRI Store action in a session with a CATS layout open.

Why:

- CATS registers heads and masts it created, and user names it applied, in JMRI's live managers.
- JMRI's store writes every head in the signal head manager, not only those you defined.
- CATS's `HWSignalHead` and `SWSignalHead` store with class names under `cats.jmri.configurexml`, which exist only in `cats.jar`. The saved table file then depends on CATS.

Checked against: CATS source (bitbucket.org/Kb0oys/cats) commit d63e7207a543928a2b38abce218b6103432f633f (CATS_VERSION 3.1.1, DESIGNER_VERSION 3.1), and JMRI source commit bd71f7f25b38e55107cc049b957385de97ad6951 (5.17.4-SNAPSHOT, partial checkout).
