# veil/wyoming.py - the router in the audio path, in front of Oread (decided Oct 13).
#
#   satellite -> Home Assistant -> router (one listening port per device) -> Oread -> router
#   -> Home Assistant
#
# Home Assistant's Wyoming speech-to-text entries point at the router's listening ports instead
# of Oread's. Each connection is passed through to that device's Oread port untouched, byte for
# byte (audio, describe/info, transcribe...); the router only reads Oread's answer on its way
# back: the Transcript event carries the words and, in its context, who spoke (speaker, label,
# score, by). So the router knows which device it was (by the port) and who spoke, for the
# request that follows, without asking Oread afterwards and with no back-channel.
#
# settings.yaml, integrations: oread: (the ports open when enabled: true and source: wyoming;
# a change takes a restart)
#   wyoming: host:     Oread's address for its Wyoming ports
#            devices:  assistant: {listen: the router's port, oread: Oread's port}
#                      (the listen ports must be published in docker-compose.yml: 10410-10419)
#            connect_timeout: seconds to reach Oread before giving up on that request
# Who may connect: security: inbound_allowed (empty: the local network only).
# Oread sees the router as its client: keep the router's address permitted there (Oread's
# Connections page) and, if you like, switch off Oread's "Report who spoke" for those devices.
#
# The one thing changed on the way through (Oct 18): the mishearings marked Use it (learn/swaps.yaml)
# are fixed in Oread's words before Home Assistant gets them (wyoming: fix_mishearings), so Home
# Assistant's own sentences match too ("Is the watcher running?" -> "Is the washer running?").
# What Oread really heard is kept and logged beside it.

import asyncio
import json
import logging
import time

from veil import access

log = logging.getLogger("router")

HEARD = {}            # assistant -> {text, speaker, label, score, by, clip, device, time, speech_ms, stt_ms, claimed}
SERVERS = []
# Every word passes through the router both ways (Home Assistant and Oread never talk directly).
# Words handed back to Home Assistant that it sends on to neither the chat door nor Veil Guard
# Service within integrations: oread: wyoming: home_assistant_answered_after seconds were answered
# by Home Assistant itself (its own commands and answers, e.g. the weather with "Prefer handling commands
# locally"). The router sets ON_UNCLAIMED to log them, so every request heard is counted.
ON_UNCLAIMED = None
UNCLAIMED_AFTER = 8.0
SWAP = None           # the router sets it: words -> (fixed words, [(heard, meant)]), or None to pass them as heard
MAX_HEADER = 1 << 20


async def read_event(reader):
    """(type, data, raw bytes) for one Wyoming event, or None at the end."""
    line = await reader.readline()
    if not line:
        return None
    if len(line) > MAX_HEADER:
        raise ValueError("a Wyoming header that long isn't one")
    header = json.loads(line)
    data_len = int(header.get("data_length") or 0)
    payload_len = int(header.get("payload_length") or 0)
    data_bytes = await reader.readexactly(data_len) if data_len else b""
    payload = await reader.readexactly(payload_len) if payload_len else b""
    data = dict(header.get("data") or {})
    if data_bytes:
        try:
            data.update(json.loads(data_bytes))
        except ValueError:
            pass
    return header.get("type"), data, line + data_bytes + payload


def fixed(text):
    """(Oread's words with the mishearings marked Use it fixed, [(heard, meant)]); as heard when
    there's nothing to fix, no SWAP, or the fixing fails."""
    if not SWAP or not (text or "").strip():
        return text, []
    try:
        return SWAP(text)
    except Exception as e:                    # fixing never breaks the audio path
        log.info("  ! Wyoming: couldn't fix the mishearings: %s", e)
        return text, []


def rebuilt(raw, data):
    """The same Wyoming event with its data replaced (its header and payload kept)."""
    line, rest = raw.split(b"\n", 1)
    header = json.loads(line)
    header.pop("data", None)
    payload = rest[int(header.get("data_length") or 0):]
    body = json.dumps(data, ensure_ascii=False).encode()
    header["data_length"] = len(body)
    return json.dumps(header).encode() + b"\n" + body + payload


def noted(assistant, data, marks=None, swaps=(), heard=None):
    """Keep what Oread said about this device's last request, and how long it took (Time
    Routes): speech_ms from the first audio to its end, stt_ms from the end of the audio to
    Oread's words. data: the words as Home Assistant gets them; swaps: the mishearings fixed in
    them (heard, meant); heard: what Oread really heard, when it was fixed."""
    ctx = data.get("context") or {}
    now = time.time()
    marks = marks or {}
    if not (data.get("text") or "").strip() and assistant in HEARD:
        # nothing heard (a reopened mic, a false wake): the last words and who said them stay,
        # so a request that follows without coming through here still knows its speaker
        log.info("Wyoming (%s): Oread heard \"\"; who spoke: %s (%s %s), the last speaker kept", assistant,
                 ctx.get("speaker") or "unknown", ctx.get("label"), ctx.get("score"))
        return
    start, stop = marks.get("audio-start"), marks.get("audio-stop")
    HEARD[assistant] = {"text": data.get("text") or "", "heard": heard or data.get("text") or "",
                        "swaps": list(swaps), "speaker": ctx.get("speaker"),
                        "label": ctx.get("label"), "guess": ctx.get("guess"), "score": ctx.get("score"),
                        "by": ctx.get("by"), "clip": ctx.get("clip"), "device": ctx.get("device"), "time": now,
                        "own_voice": bool(ctx.get("own_voice")),
                        "speech_ms": round((stop - start) * 1000, 1) if start and stop else None,
                        "stt_ms": round((now - stop) * 1000, 1) if stop else None}
    h = HEARD[assistant]
    log.info("Wyoming (%s): Oread heard \"%s\"%s; who spoke: %s (%s %s)", assistant, h["heard"],
             f'; Home Assistant gets "{h["text"]}" (a mishearing marked Use it)' if swaps else "",
             ctx.get("speaker") or "unknown", ctx.get("label"), ctx.get("score"))
    if h["text"].strip() and ON_UNCLAIMED:
        try:
            asyncio.get_running_loop().call_later(UNCLAIMED_AFTER, _unclaimed, assistant, h)
        except RuntimeError:          # no event loop (a test calling noted directly)
            pass


def _unclaimed(assistant, h):
    if not h.get("claimed") and ON_UNCLAIMED:
        try:
            ON_UNCLAIMED(assistant, h)
        except Exception as e:
            log.info("  ! Wyoming: couldn't log what Home Assistant answered itself: %s", e)


def recent(assistant, max_age):
    """What Oread said for this device's last request, if it's fresh, else None."""
    h = HEARD.get(assistant)
    if h and time.time() - h["time"] <= float(max_age):
        return h
    return None


async def _pump(src, dst, on_event=None, relayed=None):
    """Pass events from src to dst. relayed(kind, ms): how long the router held one, from reading
    it to its having gone on (Stats: the hand-off to Oread and back)."""
    try:
        while True:
            ev = await read_event(src)
            if ev is None:
                break
            got = time.monotonic()
            kind, data, raw = ev
            if on_event:
                try:
                    raw = on_event(kind, data, raw) or raw      # an event changed on the way, or as it came
                except Exception as e:                # reading along never breaks the audio path
                    log.info("  ! Wyoming: couldn't read %s: %s", kind, e)
            dst.write(raw)
            await dst.drain()
            if relayed:
                relayed(kind, (time.monotonic() - got) * 1000)
    except (asyncio.IncompleteReadError, ConnectionError, ValueError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


def handler(assistant, host, oread_port, timeout):
    async def handle(reader, writer):
        peer = (writer.get_extra_info("peername") or ("", 0))[0]
        if not access.ACCESS.allowed("inbound_allowed", peer, f"Wyoming port for {assistant}"):
            access.ACCESS.note("inbound_allowed", peer, f"Wyoming port for {assistant}")
            writer.close()
            return
        try:
            access.ACCESS.check_outbound(f"tcp://{host}:{oread_port}")
            o_reader, o_writer = await asyncio.wait_for(asyncio.open_connection(host, oread_port), timeout)
        except Exception as e:
            log.info("  ! Wyoming (%s): couldn't reach Oread at %s:%s (%s)", assistant, host, oread_port, e)
            writer.close()
            return

        marks = {}

        def held(kind, ms):        # the router's own part: the end of the speech in, Oread's words out
            if kind == "audio-stop":
                marks["relay-in"] = ms
            elif kind == "transcript" and "relay_in" in HEARD.get(assistant, {}):
                HEARD[assistant]["relay_ms"] = round(HEARD[assistant].pop("relay_in", 0) + ms, 2)

        def on_audio(kind, data, raw):            # Home Assistant -> Oread: when the speech began and ended
            if kind == "audio-start" or (kind == "audio-chunk" and "audio-start" not in marks):
                marks.setdefault("audio-start", time.time())
            elif kind == "audio-stop":
                marks["audio-stop"] = time.time()

        def on_event(kind, data, raw):            # Oread -> Home Assistant: its words, mishearings fixed
            if kind == "transcript":
                text, swaps = fixed(data.get("text") or "")
                sent = dict(data, text=text) if swaps else data
                noted(assistant, sent, marks, swaps, data.get("text"))
                if text.strip():          # nothing heard keeps the last request's entry as it was
                    HEARD[assistant]["relay_in"] = marks.get("relay-in", 0)
                marks.clear()
                return rebuilt(raw, sent) if swaps else None

        await asyncio.gather(_pump(reader, o_writer, on_audio, held), _pump(o_reader, writer, on_event, held))
    return handle


def unclaimed_after(settings):
    o = ((settings.get("integrations") or {}).get("oread") or {})
    return float((o.get("wyoming") or {}).get("home_assistant_answered_after", 8))


def wanted(settings):
    """(host, connect_timeout, {assistant: (listen, oread)}) when the audio path is on, else None."""
    o = ((settings.get("integrations") or {}).get("oread") or {})
    if not o.get("enabled") or o.get("source", "wyoming") != "wyoming":
        return None
    w = o.get("wyoming") or {}
    devices = {}
    for assistant, ports in (w.get("devices") or {}).items():
        try:
            devices[str(assistant).lower()] = (int(ports["listen"]), int(ports["oread"]))
        except (KeyError, TypeError, ValueError):
            log.info("  ! Wyoming: %s needs listen: and oread: ports", assistant)
    return w.get("host") or "127.0.0.1", float(w.get("connect_timeout", 3)), devices


async def start(settings):
    """Open a listening port per device (integrations: oread: wyoming: devices:)."""
    want = wanted(settings)
    if not want:
        return []
    host, timeout, devices = want
    global UNCLAIMED_AFTER
    UNCLAIMED_AFTER = unclaimed_after(settings)
    for assistant, (listen, oread_port) in devices.items():
        try:
            server = await asyncio.start_server(handler(assistant, host, oread_port, timeout), "0.0.0.0", listen)
        except OSError as e:
            log.info("  ! Wyoming: couldn't listen on %d for %s (%s)", listen, assistant, e)
            continue
        SERVERS.append(server)
        log.info("Wyoming: %s listens on %d, passed to Oread at %s:%d", assistant, listen, host, oread_port)
    return SERVERS


def listening():
    """The ports open right now."""
    return sorted(sock.getsockname()[1] for server in SERVERS for sock in (server.sockets or []))


async def stop():
    for server in SERVERS:
        server.close()
    SERVERS.clear()


async def test(settings):
    """For the Integrations page: does Oread answer on each device's Wyoming port?"""
    want = wanted(settings)
    if not want:
        return {"ok": False, "detail": "Oread is off, or its source isn't wyoming"}
    host, timeout, devices = want
    if not devices:
        return {"ok": False, "detail": "no devices under integrations: oread: wyoming: devices:"}
    lines, ok = [], True
    for assistant, (listen, oread_port) in devices.items():
        try:
            access.ACCESS.check_outbound(f"tcp://{host}:{oread_port}")
            r, w = await asyncio.wait_for(asyncio.open_connection(host, oread_port), timeout)
            w.write(b'{"type": "describe"}\n')
            await w.drain()
            ev = await asyncio.wait_for(read_event(r), timeout)
            w.close()
            if not ev or ev[0] != "info":
                raise RuntimeError(f"answered {ev[0] if ev else 'nothing'}, not info")
            asr = [m.get("name") for a in (ev[1].get("asr") or []) for m in (a.get("models") or [])]
            last = HEARD.get(assistant)
            heard = f"; last heard {time.time() - last['time']:.0f}s ago" if last else ""
            lines.append(f"{assistant}: port {listen} -> Oread {host}:{oread_port} answers ({', '.join(asr) or 'speech'}){heard}")
        except Exception as e:
            ok = False
            lines.append(f"{assistant}: Oread {host}:{oread_port} didn't answer ({e})")
    return {"ok": ok, "detail": "; ".join(lines)}


def claim(assistant, heard, max_age=20, min_overlap=0.5):
    """A request that reached the router (or Veil Guard Service) with words Oread just heard on this
    device: marks them as arrived (so they aren't logged as answered by Home Assistant itself) and
    returns their hops for Time Routes, with Oread's clip and device for the activity row:
    {t_speech, t_stt, t_ha_in, clip, device, audio_swaps, oread_heard}; {} when nothing fresh matches.
    audio_swaps: the mishearings fixed on the way to Home Assistant; oread_heard: Oread's own words."""
    h = recent(assistant, max_age)
    if not h:
        return {}
    from veil import speakers
    if heard and h.get("text") and speakers.overlap(h["text"], heard) < float(min_overlap):
        return {}
    h["claimed"] = True
    return {"t_speech": h.get("speech_ms"), "t_stt": h.get("stt_ms"), "t_relay": h.get("relay_ms"), "ha_text": h.get("text"),
            "t_ha_in": round((time.time() - h["time"]) * 1000, 1), "clip": h.get("clip"), "device": h.get("device"),
            "audio_swaps": h.get("swaps") or [], "oread_heard": h.get("heard")}


hops = claim          # the older name
