#!/usr/bin/env python3
"""Read-only MCP server that watches an MQTT broker.

Set MQTT_HOST and MQTT_PORT if the broker is not at 127.0.0.1:1883, and
MQTT_USERNAME and MQTT_PASSWORD if it needs them. It speaks just enough MQTT
3.1.1 to subscribe. It has no publish code, so it cannot command the layout or
clear a retained message.
"""
from __future__ import annotations

import os
import socket
import struct
import time
import uuid

from mcp_stdio import Tool, serve

HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USERNAME = os.environ.get("MQTT_USERNAME", "")
PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MAX_SECONDS = 30.0
MAX_MESSAGES = 2000
CONNECT, CONNACK, PUBLISH, SUBSCRIBE, SUBACK = 1, 2, 3, 8, 9


def utf8(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def packet(kind: int, flags: int, body: bytes) -> bytes:
    length = bytearray()
    remaining = len(body)
    while True:
        remaining, digit = remaining // 128, remaining % 128
        length.append(digit | (0x80 if remaining else 0))
        if not remaining:
            break
    return bytes([(kind << 4) | flags]) + bytes(length) + body


def connect_packet(client_id: str, username: str = "", password: str = "") -> bytes:
    flags = 0x02  # Clean session: leave nothing behind on the broker.
    payload = utf8(client_id)
    if username:
        flags |= 0x80
        payload += utf8(username)
        if password:
            flags |= 0x40
            payload += utf8(password)
    return packet(CONNECT, 0, utf8("MQTT") + bytes([4, flags]) + struct.pack("!H", 30) + payload)


def subscribe_packet(topic: str) -> bytes:
    return packet(SUBSCRIBE, 2, struct.pack("!H", 1) + utf8(topic) + b"\x00")


def read_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Broker closed the connection")
        data += chunk
    return data


def read_packet(sock: socket.socket) -> tuple[int, int, bytes]:
    first = read_exact(sock, 1)[0]
    length, shift = 0, 0
    while True:
        digit = read_exact(sock, 1)[0]
        length |= (digit & 0x7F) << shift
        shift += 7
        if not digit & 0x80:
            break
    return first >> 4, first & 0x0F, read_exact(sock, length)


def parse_publish(flags: int, body: bytes) -> dict:
    size = struct.unpack("!H", body[:2])[0]
    topic = body[2 : 2 + size].decode("utf-8", "replace")
    start = 2 + size + (2 if flags & 0x06 else 0)
    return {
        "topic": topic,
        "payload": body[start:].decode("utf-8", "replace"),
        "retained": bool(flags & 0x01),
    }


def watch(args: dict) -> dict:
    """Subscribe for a fixed time and return what arrived."""
    topic = args.get("topic", "#")
    seconds = min(float(args.get("seconds", 3)), MAX_SECONDS)
    limit = min(int(args.get("max_messages", 500)), MAX_MESSAGES)
    messages: list[dict] = []
    try:
        sock = socket.create_connection((HOST, PORT), timeout=5)
    except OSError as exc:
        raise RuntimeError(f"Could not reach the broker at {HOST}:{PORT} ({exc})") from exc
    with sock:
        sock.sendall(connect_packet(f"mcp-read-{uuid.uuid4().hex[:12]}", USERNAME, PASSWORD))
        kind, _, body = read_packet(sock)
        if kind != CONNACK or body[1] != 0:
            raise RuntimeError(f"Broker refused the connection (code {body[1]})")
        sock.sendall(subscribe_packet(topic))
        deadline = time.monotonic() + seconds
        truncated = False
        while time.monotonic() < deadline:
            sock.settimeout(max(deadline - time.monotonic(), 0.01))
            try:
                kind, flags, body = read_packet(sock)
            except (socket.timeout, TimeoutError):
                break
            if kind == SUBACK and body[2] == 0x80:
                raise RuntimeError(f"Broker refused the subscription to {topic}")
            if kind == PUBLISH:
                if len(messages) == limit:
                    truncated = True
                    break
                messages.append(parse_publish(flags, body))
    return {"topic": topic, "seconds": seconds, "count": len(messages),
            "truncated": truncated, "messages": messages}


def tools() -> list[Tool]:
    schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic filter, e.g. track/turnout/#"},
            "seconds": {"type": "number", "description": "How long to listen, up to 30"},
            "max_messages": {"type": "integer", "description": "Stop after this many, up to 2000"},
        },
    }
    return [
        Tool(
            "mqtt_watch",
            "Listen to a topic filter for a few seconds. Returns retained messages "
            "first, then live traffic, each marked retained or not.",
            schema,
            watch,
        )
    ]


if __name__ == "__main__":
    serve("mqtt-layout", tools())
