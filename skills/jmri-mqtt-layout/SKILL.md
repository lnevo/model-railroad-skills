---
name: jmri-mqtt-layout
description: Explains stock JMRI MQTT behaviour, covering connection settings, channel and topic prefixes and how to change them, per-type topics and payloads, which directions JMRI publishes and subscribes, retained messages, content parsers, MQTT signal masts, power and reporters. Use when someone configures an MQTT connection in JMRI, works out which topic or payload a turnout, sensor, light, mast, power or reporter uses, sees wrong state after a restart, finds retained messages replaying, gets feedback that seems false, or installs a custom parser. Mosquitto retain behaviour is included only where it affects JMRI. Not for custom bridges, gateways or device firmware.
---

# JMRI MQTT layout connections

JMRI is an MQTT client. It builds each bean's topics when the bean is created and subscribes at that moment. Work from the defaults below, then check against the broker with `mosquitto_sub`.

## Connection settings

Set these in Preferences, Connections, with System manufacturer MQTT and System connection MQTT Connection. Save and restart after any change.

- Host: broker IP address, host name or `localhost`.
- Port: default 1883, under Additional Connection Settings.
- Connection prefix: default `M`, giving system names `MT...`, `MS...`, `ML...`, `MR...`.
- User and password: optional. They are only sent if the user name is set.
- Channel: default blank. Set it with no leading slash and with a trailing slash, such as `layout/`.
- Last will: default topic `track/state`, message `OFFLINE`. Set both to use it. It is sent with the current QoS and always retained. JMRI publishes an empty message to the will topic on each connect, which clears it.

Help says JMRI handles only one MQTT connection at a time.

The client ID is the Railroad Name with non-alphanumerics removed, plus `JMRI`, a node hash and the system prefix, trimmed to 23 characters. Use it to find JMRI in broker logs.

## Topic construction

Full topic = channel + type topic with the name suffix inserted.

- JMRI inserts no slashes. Concatenation is literal.
- `{0}` in a type topic is replaced with the system name suffix, the part after `MT`, `MS` and so on. With no `{0}`, the suffix goes on the end.
- Use `/` in a suffix for another topic level. `MTpanel1/x3` becomes `track/turnout/panel1/x3`.
- Avoid apostrophes and stray braces in turnout, sensor, light and reporter topics. These go through `java.text.MessageFormat`.

| Type | Send default | Receive default | JMRI sends | JMRI accepts |
|---|---|---|---|---|
| Turnout | `track/turnout/{0}` | same | `CLOSED` `THROWN` | also `UNKNOWN` `INCONSISTENT` |
| Sensor | `track/sensor/{0}` | same | `ACTIVE` `INACTIVE` | same |
| Light | `track/light/{0}` | same | `ON` `OFF` `INTENSITY 0.35` | same |
| Reporter | none | `track/reporter/{0}` | nothing | `tagid free text`, or empty |
| Signal mast | `track/signalmast/{0}` | same topic, see below | `Clear; Lit; Unheld` | same |
| Power | `track/power` | `track/power` | `ON` `OFF` | same |
| Throttle speed | `cab/{0}/throttle` | same | `0` to `100` | same |
| Direction | `cab/{0}/direction` | same | `FORWARD` `REVERSE` `STOP` | same |
| Function | `cab/{0}/function/{1}` | same | `ON` `OFF` | same |
| Consist | `cab/{0}/consist` | none | loco list | none |

Payloads are case sensitive.

Ignore the Signal Head topic field. No code reads it, and JMRI has no MQTT signal head. Use a script, or a turnout-based head on MQTT turnouts.

## Changing topics

- Use Preferences for permanent changes. Separate send and receive fields exist for turnouts, sensors, lights, power and the throttle topics.
- To set a prefix by script, run it before panels load. Topics are fixed when each bean is created, so existing beans keep their old topics.

```python
import jmri
m = jmri.InstanceManager.getNullableDefault(jmri.jmrix.mqtt.MqttTurnoutManager)
m.setSendTopicPrefix("layout/cmd/turnout/")
m.setRcvTopicPrefix("layout/state/turnout/")
```

## Direction: shared topics echo

Defaults use one topic for send and receive, so JMRI subscribes to what it publishes and gets its own messages back. The help text says JMRI does not subscribe to its own turnout and light messages, but that only holds once you set different topics.

- Use separate send and receive topics when you need real feedback from a device.
- Do not use MONITORING with shared topics. The echo of JMRI's own command sets Known State at once, so it proves nothing about the device.
- Do not set Inverted on a turnout with shared topics and the default parser. JMRI inverts what it sends but not what it receives, so the echo flips the turnout back. Use separate topics or a parser that handles inversion.

## Turnouts

- JMRI publishes on the send topic when the turnout is commanded. It subscribes only to the receive topic.
- A message on the receive topic sets Known State in DIRECT and MONITORING modes. In other feedback modes it does nothing.
- A message on a shared topic also sets Commanded State, in every mode.
- An inbound message never republishes a command.
- Any payload outside the four accepted words logs a warning and sets the turnout to UNKNOWN. That includes an empty payload.

## Sensors

- JMRI subscribes to the receive topic. It publishes on the send topic whenever the sensor is set in JMRI, including by a panel click or a script.
- A click on a shared topic overwrites the device's retained state.
- Inversion is applied in both directions.
- An unknown payload logs a warning and leaves the state unchanged.
- Make devices publish sensor state with retain on. JMRI cannot poll, since `requestUpdateFromLayout` does nothing, so a sensor stays UNKNOWN until a message arrives.

## Lights

- Treat inbound light messages as commands that can publish. A received `ON` or `OFF` that differs from the current state goes through `setState`, which publishes on the send topic.
- Expect a retained `ON` to be republished at startup, since lights start OFF.
- Keep payloads valid. An unknown payload is read as UNKNOWN, and `setState` then publishes `OFF`. The help says the state becomes UNKNOWN, but the code also sends OFF.
- `INTENSITY n` on the receive topic sets the observed intensity and does not change on or off.

## Signal masts

- Create them from the Signal Mast table with the MQTT mast driver. Set the Topic Suffix field. The system name is like `IF$mqm:basic:one-searchlight($0001)`, and the topic suffix is what sits between `($` and `)`.
- Change the Signal Mast topic field to a plain prefix such as `track/signalmast/`. Mast topics are plain concatenation with no `{0}` handling, so the default value puts the literal text `{0}` in the topic, as `track/signalmast/{0}0001`. Check with `mosquitto_sub` before wiring a device to it.
- Expect one topic. There is no separate receive topic. JMRI subscribes to the send topic and accepts state back on it.
- JMRI publishes on every call to set aspect, held or lit, in the form `aspect; Lit|Unlit; Held|Unheld`.
- Inbound messages update the mast with no republish. Only the aspect is required. A second part other than `Unlit` means lit, and a third part other than `Held` means unheld.
- An aspect the mast's map does not have, or a disabled aspect, throws. The log shows `MqttEventListener exception` and the mast is unchanged.
- Set the aspect before held or lit. Publishing with no aspect yet sends the literal `null` as the aspect, and that echo is rejected as above.

## Power

- Make something answer on the receive topic, or keep shared topics. `setPower` only publishes. JMRI's power state changes only when `ON` or `OFF` arrives on the receive topic.
- With separate topics and no responder, the power state never updates.
- Inbound messages do not republish.
- Select MQTT as the default for Power Control to get publishes from the WiThrottle server and from scripts using the default power manager.

## Reporters

- Reporters only receive. Send `tagid free text` on `track/reporter/<suffix>`.
- The first space-separated word becomes the IdTag. The rest goes in its `content` property.
- An empty message clears the report.

## Retained messages

JMRI publishes everything at QoS 2 with retain on. Both settings are adapter-wide public fields, and JMRI reads them on each publish, so a change takes effect immediately.

```python
import jmri
a = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo).getMqttAdapter()
a.retained = False
a.qosflag = 1
```

Use `publish(topic, payload, False)` to skip retain on one message. The channel is added for you. The LogixNG Publish action has its own Default, Yes and No retain setting.

Plan for replay:

- Subscriptions happen when beans are created, usually when tables load, so retained messages arrive then.
- JMRI resubscribes to all topics after a lost connection, so retained messages arrive again.
- Retained commands on send topics also reach any device when it subscribes, so a device restart can repeat the last command.
- On shared topics a retained message from JMRI's last session restores state at the next start. For turnouts, sensors, masts and power this does not publish. Lights are the exception above.

Mosquitto behaviour that affects this:

- A retained message stays until replaced or cleared. Retained data survives a broker restart only with `persistence true`.
- Clear one topic with `mosquitto_pub -t track/turnout/x3 -r -n`.
- Clear a tree with `mosquitto_sub -t 'track/#' --remove-retained`.
- Clear with JMRI stopped. A zero-length message reaching a live turnout sets it UNKNOWN, and on a live light it publishes OFF.
- Mosquitto 2.0 and later needs a config file with `listener 1883`, and `allow_anonymous true` if JMRI has no user name.

## Content parsers

Implement `jmri.jmrix.mqtt.MqttContentParser` with `beanFromPayload(bean, payload, topic)` and `payloadFromBean(bean, newState)`.

- Install with `setParser(p)` on `MqttTurnoutManager` or `MqttSensorManager`. That covers beans created later, so run the script before panels load, or also call `setParser` on each existing bean.
- For lights, call `setParser` on each `MqttLight`. The light manager has none.
- Expect a light parser to affect inbound only. Lights publish fixed text, and `INTENSITY` is handled before the parser.
- Masts, reporters and power have no parser.
- Handle inversion yourself. The sample `jython/MQTT/SetMqttParser.py` shows it, including JSON.

Other samples are in `jython/MQTT/`: `SendMqttMessage.py`, `ReceiveMqttMessage.py`, `SetMqttPrefix.py` and `SetMqttOptions.py`.

## Debugging

- Watch everything with `mosquitto_sub -h localhost -v -t '#'`.
- Check the exact topic against channel + prefix + suffix.
- `Trying to subscribe before connect/configure is done` means a bean was created with no live connection.
- `saw unknown state` means the payload did not match. Check case and whitespace.
- `got a message whose topic ... wasn't for me` means the bean's listener saw a topic that matches neither of its own topics.

Checked against JMRI source at commit bd71f7f (2026-10-31).
