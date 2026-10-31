#!/usr/bin/env python3
"""Read-only MCP server for the JMRI web server's JSON interface.

Set JMRI_URL if JMRI is not at http://127.0.0.1:12080. This server only sends
GET requests, so it cannot throw a turnout or change anything.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from mcp_stdio import Tool, serve

BASE = os.environ.get("JMRI_URL", "http://127.0.0.1:12080").rstrip("/")
TIMEOUT = float(os.environ.get("JMRI_TIMEOUT", "5"))
LIST_TYPES = (
    "turnouts", "sensors", "signalMasts", "signalHeads", "blocks", "layoutBlocks",
    "lights", "memories", "reporters", "routes", "roster", "cars", "locations", "trains",
)
GET_TYPES = (
    "turnout", "sensor", "signalMast", "signalHead", "block", "layoutBlock",
    "light", "memory", "reporter", "route",
)
INFO_TYPES = ("power", "metadata", "panels", "version")


def fetch(path: str) -> object:
    url = f"{BASE}/json/{path}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"JMRI returned {exc.code} for {url}") from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not reach JMRI at {BASE}. Is the Web Server running? ({exc})"
        ) from exc


def checked(value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"type must be one of: {', '.join(allowed)}")
    return value


def list_items(args: dict) -> object:
    return fetch(checked(args["type"], LIST_TYPES))


def get_item(args: dict) -> object:
    kind = checked(args["type"], GET_TYPES)
    return fetch(f"{kind}/{urllib.parse.quote(args['name'], safe='')}")


def info(args: dict) -> object:
    return fetch(checked(args["type"], INFO_TYPES))


def tools() -> list[Tool]:
    def schema(allowed: tuple[str, ...], name: bool = False) -> dict:
        props: dict = {"type": {"type": "string", "enum": list(allowed)}}
        if name:
            props["name"] = {"type": "string", "description": "System name or user name"}
        return {
            "type": "object",
            "properties": props,
            "required": ["type", "name"] if name else ["type"],
        }

    return [
        Tool("jmri_list", "List every item of one type from JMRI.", schema(LIST_TYPES), list_items),
        Tool("jmri_get", "Read one item from JMRI by name.", schema(GET_TYPES, True), get_item),
        Tool("jmri_info", "Read JMRI power, metadata, panels or version.", schema(INFO_TYPES), info),
    ]


if __name__ == "__main__":
    serve("jmri-json", tools())
