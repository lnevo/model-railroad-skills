# Model railroad skills

Claude Code skills and read-only live tools for model railroad software: JMRI, stock JMRI MQTT, CATS and STS.

## Install

```
claude plugin marketplace add lnevo/model-railroad-skills
claude plugin install model-railroad-skills@model-railroad-skills
```

The live tools need `python3` and nothing else.

## Skills

Skills are guidance. They tell Claude how the software behaves, but they don't run anything or connect to a layout. Each skill says which source commit it was checked against, and a rule is included only if it was confirmed in the source or official documentation.

### `jmri-panel-xml`

- **Can do:** guide script edits to Layout Editor panel and tables XML, including adding or renaming track, turnouts, blocks and masts. It explains the name and connection rules, what JMRI rewrites on Store, and how geometry behaves, and helps diagnose missing connections, lost blocks and vanished edits.
- **Can't do:** explain signal logic, which `jmri-sml-nx` covers. Edits are only safe with JMRI closed.

### `jmri-sml-nx`

- **Can do:** explain where masts and NX sensors can go, how slots set facing and protected blocks, what discovery does, and what the common errors mean. It also covers editing the SML and Entry/Exit XML, and choosing an NX type.
- **Can't do:** run discovery, fix a pair that needs a block boundary the panel doesn't have, or cover general XML safety. The NX rules rest on JMRI's help and schema files, not its Java code.

### `jmri-dispatcher-system`

- **Can do:** walk through Stage 1 and Stage 2, marking station blocks, mast placement, modal dialogs and the facing dialog. An error table helps diagnose failed runs, and fixes go in panel or tables data.
- **Can't do:** patch or wrap the package, which it says never to do, or cover the plain JMRI Dispatcher window without this package. Hand-made SML pairs, transits and sections are gone after Stage 1.

### `jmri-mqtt-layout`

- **Can do:** explain stock connection settings, topics and payloads by device type, publish and subscribe direction, feedback modes, retained messages, signal masts, power, reporters and custom content parsers, plus traps confirmed in source.
- **Can't do:** cover custom bridges, gateways, device firmware or custom topic schemes. Mosquitto is covered only where it affects JMRI.

### `cats-on-jmri`

- **Can do:** cover version checks, installing beside JMRI, how Designer relates to CATS, panel XML structure, and how panels bind to JMRI devices. It helps debug missing track and devices that won't bind, and sets the rules for JMRI tables during a CATS session.
- **Can't do:** give a supported JMRI range, because the source declares none, or decompile `cats.jar`. It can't import a Layout Editor panel as a track plan, or drive Designer or the CATS window, though it can guide edits to panel XML.

### `sts-docker`

- **Can do:** cover compose services and profiles, environment settings, first-time database setup, web-app backups and restores, car photos and image upgrades, plus traps confirmed in source.
- **Can't do:** cover any railroad's seed scripts, session tooling or helpers, or day-to-day operations in STS. It's checked against one fork of the Docker project, and fork-only features were left out.

## Operations Pro (separate plugin)

`operations-pro` builds, changes, runs and explains a JMRI OperationsPro railroad. Unlike everything above it writes data, with a plan shown first and JMRI exited, which is why it is a separate install. See [`plugins/operations-pro/README.md`](plugins/operations-pro/README.md).

```
claude plugin install operations-pro@model-railroad-skills
```

## Live tools

Both servers are read-only by design and run on your machine.

| Server | Can do | Can't do | Settings |
|---|---|---|---|
| `jmri-json` | List or read turnouts, sensors, masts, blocks, roster, routes and more, plus power and version | Change anything, because it only sends GET requests | `JMRI_URL` (default `http://127.0.0.1:12080`) |
| `mqtt-layout` | Listen to a topic for up to 30 seconds and show retained and live messages | Publish, command a layout or clear retained messages | `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD` (default `127.0.0.1:1883`) |

JMRI's Web Server must be running for `jmri-json`. So far `jmri-json` has been tested against a stub server and `mqtt-layout` against a local Mosquitto broker, not a running layout.

## Tests

```
python3 -m unittest discover -s tests
```

The broker test runs only if `mosquitto` is installed.

## License

MIT
