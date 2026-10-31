# Model railroad skills

Claude Code skills and read-only live tools for model railroad software: JMRI, stock JMRI MQTT, CATS and STS.

## Install

```
claude plugin marketplace add lnevo/model-railroad-skills
claude plugin install model-railroad-skills@model-railroad-skills
```

The live tools need `python3` and nothing else.

## Skills

| Skill | Covers |
|---|---|
| `jmri-panel-xml` | Editing Layout Editor panel and tables XML safely |
| `jmri-sml-nx` | Signal Mast Logic, discovery and Entry/Exit |
| `jmri-dispatcher-system` | The stock jython Dispatcher System package |
| `jmri-mqtt-layout` | Stock JMRI MQTT topics, payloads and retained messages |
| `cats-on-jmri` | Running CATS with JMRI |
| `sts-docker` | Running the Shipper-driven Traffic Simulator in Docker |

Each skill says which source commit it was checked against. A rule is included only if it was confirmed in the source or official documentation.

## Live tools

Both servers are read-only by design and run on your machine.

| Server | Tools | Settings |
|---|---|---|
| `jmri-json` | `jmri_list`, `jmri_get`, `jmri_info` | `JMRI_URL` (default `http://127.0.0.1:12080`) |
| `mqtt-layout` | `mqtt_watch` | `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD` (default `127.0.0.1:1883`) |

`jmri-json` only sends GET requests. `mqtt-layout` has no publish code, so it cannot command a layout or clear a retained message. JMRI's Web Server must be running for `jmri-json`.

## Tests

```
python3 -m unittest discover -s tests
```

The broker test runs only if `mosquitto` is installed.

## License

MIT
