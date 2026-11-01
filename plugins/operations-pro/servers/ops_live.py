"""The live lane: talk to a running JMRI over its JSON server.

Move and terminate use the stock JSON server. Build, reset, Set Car, save, reports and
automations go through jmri_agent.py, which ops_install_agent sets up. JMRI needs its web
server running, which is a Startup item in JMRI's Preferences.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import ops_store
from ops_store import Refused, resolve

DEFAULT_URL = "http://localhost:12080"
AGENT = Path(__file__).with_name("jmri_agent.py")
INSTALLED = "opspro_agent.py"
AGENT_VERSION = 1
REQUEST, REPLY, READY = "IMOPSPRO_REQUEST", "IMOPSPRO_REPLY", "IMOPSPRO_AGENT"
TIMEOUT = 10
LONG = {"build": 300, "automation": 150}
AWAKE_WAIT = 5


def base_url(url: str | None) -> str:
    return (url or os.environ.get("JMRI_URL") or DEFAULT_URL).rstrip("/")


def call(url: str, path: str, data=None) -> object:
    """One JSON request. The content type matters: JMRI ignores a form POST without saying so."""
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(f"{url}/json/{path}", data=body, method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise Refused(f"JMRI answered {exc.code}: {detail}") from exc
    except OSError as exc:
        raise Refused(f"No JMRI JSON server at {url}. Start JMRI with its web server on, or set "
                      f"JMRI_URL. ({exc})") from exc


def memory(url: str, name: str) -> str | None:
    """A Memory's value, or None if it does not exist or is empty."""
    try:
        return call(url, f"memory/{name}")["data"]["value"]
    except Refused as exc:
        if " 404" in str(exc):
            return None
        raise


def agent_version(url: str) -> str | None:
    """Reading trains loads Operations in JMRI, which runs the startup script."""
    call(url, "trains")
    deadline = time.monotonic() + AWAKE_WAIT
    while True:
        version = memory(url, READY)
        if version or time.monotonic() > deadline:
            return version
        time.sleep(0.2)


def ask(url: str, command: str, **fields) -> dict:
    """Send one command to the agent and wait for its answer."""
    if not agent_version(url):
        raise Refused("The Operations agent is not running in JMRI. Run ops_install_agent, apply its plan, "
                      "then restart JMRI.")
    job_id = uuid.uuid4().hex
    call(url, f"memory/{REQUEST}", {"value": json.dumps({"id": job_id, "command": command, **fields})})
    deadline = time.monotonic() + LONG.get(command, 30)
    while time.monotonic() < deadline:
        text = memory(url, REPLY)
        reply = json.loads(text) if text else {}
        if reply.get("id") == job_id:
            call(url, f"memory/{REPLY}", {"value": None})
            if not reply["ok"]:
                raise Refused(reply["error"])
            return reply["result"]
        time.sleep(0.2)
    raise Refused(f"JMRI did not answer {command} in {LONG.get(command, 30)} seconds. A train script may be "
                  "stuck, or a window may be open on the JMRI computer. It may still finish: check ops_live_status.")


def status(url: str | None = None) -> dict:
    """What is running, with or without the agent."""
    url = base_url(url)
    version = agent_version(url)
    if version:
        result = ask(url, "status")
        if version != str(AGENT_VERSION):
            result["warning"] = "The installed agent is out of date. Run ops_install_agent and restart JMRI."
    else:
        result = {"agent": None, "note": "Move and terminate work. Build, reset and the rest need ops_install_agent.",
                  "trains": [{"name": t["data"]["userName"], "status": t["data"]["status"],
                              "location": t["data"]["location"]} for t in call(url, "trains")]}
    return result


def _train_id(url: str, name: str) -> dict:
    for row in call(url, "trains"):
        if name in (row["data"]["userName"], row["data"]["name"]):
            return row["data"]
    raise Refused(f"No train {name}")


def _state(url: str, train_id: str) -> dict:
    data = call(url, f"train/{train_id}")["data"]
    return {"name": data["userName"], "status": data["status"], "location": data["location"]}


def move(train: str, location: str, url: str | None = None) -> dict:
    url = base_url(url)
    data = _train_id(url, train)
    call(url, f"train/{data['name']}", {"location": location})
    return _state(url, data["name"])


def terminate(train: str, url: str | None = None) -> dict:
    """Terminate one train, or all of them in departure order. Unbuilt trains are unaffected."""
    url = base_url(url)
    rows = [row["data"] for row in call(url, "trains")] if train == "all" else [_train_id(url, train)]
    done = []
    for data in sorted(rows, key=lambda d: d["departureTime"]):
        call(url, f"train/{data['name']}", {"location": None})
        done.append(_state(url, data["name"]))
    return {"trains": done}


def train_action(action: str, train: str, location: str | None = None, rebuild: bool = False,
                 url: str | None = None) -> dict:
    if action == "move":
        if not location:
            raise Refused("move needs a location")
        return move(train, location, url)
    if action == "terminate":
        return terminate(train, url)
    if action == "build":
        return ask(base_url(url), "build", train=train, rebuild=rebuild)
    if action == "reset":
        return ask(base_url(url), "reset", train=train)
    raise Refused("action must be build, move, terminate or reset")


def install_agent(directory: str | Path) -> dict:
    """Copy the agent beside the Operations files and plan its startup entry.

    Only the plan needs JMRI exited. The path is relative to the JMRI profile, so it
    follows a profile that moves or is shared.
    """
    base = resolve(directory)
    shutil.copyfile(AGENT, base / INSTALLED)
    path = f"preference:{base.name}/{INSTALLED}"
    result = ops_store.plan(base, [{"action": "add_startup_script", "path": path}])
    result["agent_copied_to"] = str(base / INSTALLED)
    result["next"] = ("Apply this plan with JMRI exited, then start JMRI with its web server on." if result["changed"]
                      else "Already registered. Restart JMRI to load the new copy.")
    return result
