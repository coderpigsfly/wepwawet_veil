# veil/hadebug.py - Home Assistant's own record of its last voice runs (Settings, Voice
# assistants, Debug), read over its websocket API: each run's words and when each stage started
# and ended. tools/ha_timings.py prints them; the router reads them after an answer to time the
# way back (its answer leaving the router to Home Assistant done with it: LiteLLM and Home
# Assistant on the way back), which it can't see itself. Home Assistant keeps the last few runs
# per assistant, until it restarts.

import base64
import json
import os
import socket
import ssl
import struct
from datetime import datetime
from urllib.parse import urlparse

from veil import util


class Socket:
    """Just enough of a websocket client for Home Assistant's API (text frames, no extensions)."""

    def __init__(self, url, timeout=15):
        u = urlparse(url)
        port = u.port or (443 if u.scheme in ("https", "wss") else 80)
        raw = socket.create_connection((u.hostname, port), timeout=timeout)
        if u.scheme in ("https", "wss"):
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
        self.s = raw
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /api/websocket HTTP/1.1\r\nHost: {u.hostname}:{port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            got = self.s.recv(1)
            if not got:
                raise ConnectionError("Home Assistant closed the connection")
            head += got
        status = head.split(b"\r\n")[0].decode(errors="replace")
        if " 101 " not in status:
            raise ConnectionError(f"no websocket: {status}")
        self.n = 0

    def _read(self, n):
        out = b""
        while len(out) < n:
            got = self.s.recv(n - len(out))
            if not got:
                raise ConnectionError("Home Assistant closed the connection")
            out += got
        return out

    def send(self, obj):
        data = json.dumps(obj).encode()
        head = bytes([0x81])
        if len(data) < 126:
            head += bytes([0x80 | len(data)])
        elif len(data) < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", len(data))
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", len(data))
        mask = os.urandom(4)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        data = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if b1 & 0x0F == 0x8:
                raise ConnectionError("Home Assistant closed the connection")
            if b1 & 0x0F in (0x9, 0xA):          # ping or pong: not ours to answer here
                continue
            data += payload
            if b1 & 0x80:
                return json.loads(data)

    def call(self, kind, **fields):
        self.n += 1
        self.send({"id": self.n, "type": kind, **fields})
        while True:
            msg = self.recv()
            if msg.get("id") == self.n:
                if not msg.get("success"):
                    raise RuntimeError(f"{kind}: {(msg.get('error') or {}).get('message', msg)}")
                return msg.get("result")


def stamp(event):
    try:
        return datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def between(events, first, last):
    """ms from the first event of one type to the last of another, or None."""
    a = next((stamp(e) for e in events if e.get("type") == first), None)
    b = next((stamp(e) for e in reversed(events) if e.get("type") == last), None)
    return round((b - a) * 1000) if a and b and b >= a else None


def words_of(events):
    end = next((e for e in events if e.get("type") == "stt-end"), None)
    if end:
        return ((end.get("data") or {}).get("stt_output") or {}).get("text") or ""
    start = next((e for e in events if e.get("type") == "intent-start"), None)
    return ((start or {}).get("data") or {}).get("intent_input") or ""


def runs(url, token, timeout=15):
    """Every assistant's last runs: [{pipeline, events}] (blocking: call it in a thread)."""
    ws = Socket(url, timeout)
    try:
        hello = ws.recv()
        if hello.get("type") == "auth_required":
            ws.send({"type": "auth", "access_token": token})
            if ws.recv().get("type") != "auth_ok":
                raise PermissionError("Home Assistant refused the token")
        out = []
        for p in (ws.call("assist_pipeline/pipeline/list") or {}).get("pipelines") or []:
            for run in (ws.call("assist_pipeline/pipeline_debug/list", pipeline_id=p["id"]) or {}).get("pipeline_runs") or []:
                got = ws.call("assist_pipeline/pipeline_debug/get", pipeline_id=p["id"], pipeline_run_id=run["pipeline_run_id"]) or {}
                out.append({"pipeline": p.get("name") or p["id"], "events": got.get("events") or []})
        return out
    finally:
        try:
            ws.s.close()
        except OSError:
            pass


def back_ms(all_runs, words, left, within=60):
    """The way back for one answer: from it leaving the router (left, epoch seconds) to Home
    Assistant ending its conversation stage (intent-end), in ms, for the run with the same words
    that ended within `within` s after. None when no run fits. Never below 0 (clocks a little apart)."""
    want = util.words(words or "")
    best = None
    for r in all_runs:
        ev = r["events"]
        if not want or util.words(words_of(ev)) != want:
            continue
        end = next((stamp(e) for e in reversed(ev) if e.get("type") == "intent-end"), None)
        if end and left - 2 <= end <= left + within and (best is None or end < best):
            best = end
    return None if best is None else max(0, round((best - left) * 1000))
