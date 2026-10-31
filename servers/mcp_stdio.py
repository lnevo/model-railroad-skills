"""Minimal MCP stdio server using only the Python standard library."""
from __future__ import annotations

import json
import sys
from typing import Callable

PROTOCOL_VERSION = "2025-06-18"


class Tool:
    def __init__(self, name: str, description: str, schema: dict, run: Callable[[dict], object]):
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run


def handle(message: dict, server_name: str, tools: dict[str, Tool]) -> dict | None:
    """Return the response to one JSON-RPC message, or None for a notification."""
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result: dict = {
            "protocolVersion": message.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": server_name, "version": "0.1.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.schema,
                    "annotations": {"readOnlyHint": True},
                }
                for t in tools.values()
            ]
        }
    elif method == "tools/call":
        params = message.get("params", {})
        tool = tools.get(params.get("name"))
        if tool is None:
            return _error(request_id, -32602, f"Unknown tool {params.get('name')}")
        try:
            text = json.dumps(tool.run(params.get("arguments") or {}), indent=1)
            result = {"content": [{"type": "text", "text": text}]}
        except Exception as exc:  # A failed read is a tool result, not a server crash.
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    else:
        return _error(request_id, -32601, f"Unknown method {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(server_name: str, tools: list[Tool]) -> None:
    by_name = {t.name: t for t in tools}
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = handle(message, server_name, by_name)
        if response is not None:
            print(json.dumps(response), flush=True)
