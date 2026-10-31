"""Server tests: protocol, HTTP against a stub, MQTT against a real local broker."""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SERVERS = Path(__file__).resolve().parents[1] / "servers"
sys.path.insert(0, str(SERVERS))

import mqtt_layout  # noqa: E402


def run_server(script, env, *messages):
    lines = "".join(json.dumps(m) + "\n" for m in messages)
    out = subprocess.run(
        [sys.executable, str(SERVERS / script)], input=lines, capture_output=True,
        text=True, env={**os.environ, **env}, timeout=30, check=True,
    )
    return [json.loads(line) for line in out.stdout.splitlines()]


def call(name, arguments, request_id=2):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"}}
NOTE = {"jsonrpc": "2.0", "method": "notifications/initialized"}


class Stub(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        Stub.seen.append(("GET", self.path))
        body = json.dumps([{"type": "turnout", "data": {"name": "IT1"}}]).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class JsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.env = {"JMRI_URL": f"http://127.0.0.1:{cls.http.server_port}"}

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()

    def test_handshake_lists_read_only_tools(self):
        out = run_server("jmri_json.py", self.env, INIT, NOTE,
                         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(out), 2)
        tools = out[1]["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"jmri_list", "jmri_get", "jmri_info"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))

    def test_list_and_get_use_get_requests(self):
        Stub.seen.clear()
        run_server("jmri_json.py", self.env, INIT,
                   call("jmri_list", {"type": "turnouts"}),
                   call("jmri_get", {"type": "turnout", "name": "Yard Lead"}, 3))
        self.assertEqual(Stub.seen, [("GET", "/json/turnouts"), ("GET", "/json/turnout/Yard%20Lead")])

    def test_unknown_type_is_refused_without_a_request(self):
        Stub.seen.clear()
        out = run_server("jmri_json.py", self.env, INIT, call("jmri_list", {"type": "../x"}))
        self.assertTrue(out[1]["result"]["isError"])
        self.assertEqual(Stub.seen, [])

    def test_jmri_down_gives_a_clear_error(self):
        out = run_server("jmri_json.py", {"JMRI_URL": "http://127.0.0.1:9"}, INIT,
                         call("jmri_list", {"type": "turnouts"}))
        self.assertIn("Web Server", out[1]["result"]["content"][0]["text"])


class ParsingTests(unittest.TestCase):
    def test_qos1_publish_skips_packet_id(self):
        body = b"\x00\x03a/b" + b"\x00\x07" + b"HI"
        self.assertEqual(mqtt_layout.parse_publish(0x02, body),
                         {"topic": "a/b", "payload": "HI", "retained": False})

    def test_no_publish_packet_exists(self):
        source = (SERVERS / "mqtt_layout.py").read_text()
        self.assertNotIn("packet(PUBLISH", source)


@unittest.skipUnless(shutil.which("mosquitto"), "mosquitto not installed")
class BrokerTests(unittest.TestCase):
    def test_reads_retained_then_live_and_leaves_retained_alone(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        broker = subprocess.Popen(["mosquitto", "-p", str(port)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        self.addCleanup(broker.wait)
        self.addCleanup(broker.terminate)
        time.sleep(0.5)
        pub = ["mosquitto_pub", "-h", "127.0.0.1", "-p", str(port)]
        subprocess.run([*pub, "-t", "track/turnout/1", "-m", "CLOSED", "-r"], check=True)
        mqtt_layout.HOST, mqtt_layout.PORT = "127.0.0.1", port
        timer = threading.Timer(
            0.5, lambda: subprocess.run([*pub, "-t", "track/sensor/2", "-m", "ACTIVE"], check=True))
        timer.start()
        result = mqtt_layout.watch({"topic": "track/#", "seconds": 1.5})
        timer.join()
        self.assertEqual(result["messages"], [
            {"topic": "track/turnout/1", "payload": "CLOSED", "retained": True},
            {"topic": "track/sensor/2", "payload": "ACTIVE", "retained": False},
        ])
        again = mqtt_layout.watch({"topic": "track/turnout/#", "seconds": 0.5})
        self.assertEqual(again["count"], 1)


if __name__ == "__main__":
    unittest.main()
