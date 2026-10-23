# veil/speakers.py - who spoke (from Oread), who that is in the house, and her saying their
# name now and then.
#
# Oread (speech-to-text plus speaker ID) hears every request first. Home Assistant passes on
# only the words, so the router finds out who spoke itself (integrations: oread: source:):
#   wyoming         the agreed way: the router sits in the audio path in front of Oread
#                   (veil/wyoming.py) and reads who spoke from Oread's own answer as it passes,
#                   per device, with no token and no asking afterwards. The words must look like
#                   what the router heard (min_word_overlap) and be fresh (max_age_seconds).
#   oread           Oread's API: the newest clip for this device (GET /clips?status=all&device=
#                   &limit=1), with an Oread API token (stored here as oread_token; give it the
#                   role Oread's clips door asks for). Same freshness and word checks.
#   home_assistant  the sensor Oread sets in Home Assistant, sensor.oread_<device>_speaker,
#                   through Home Assistant's REST API (a long-lived token).
# Either way the answer is {person, speaker, label, score, by}; person is the household key
# (people: in settings.yaml: an Oread profile "Sam" with aliases owner: [sam] is "owner").
# No answer in time (integrations: oread: timeout) means nobody known: the request goes on.
#
# Her saying a name: each device's own rate (personality/<device>.yaml names: rate, on Name
# Sparkle) is the switch: above 0 it says names, 0 or none it doesn't (Oct 15: no house switch,
# no house rate). Only when the voice ID is sure (label in labels:, score >= min_score), only on some
# answers (rate, dealt like a shuffled deck so it's random but never too often, max_in_a_row),
# only on the paths listed. A phrase line can place it with [[name]]; otherwise it goes in
# front ("Owner, you have 3 chores") or, now and then, at the end ("... tomorrow, Owner.").
# Never after a question mark: she ends on the question to keep the mic open.

import logging
import random
import re
import time
from datetime import datetime


from veil import access, config

log = logging.getLogger("router")


def clean_words(text):
    return re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower().replace("’", "'")).split()


def overlap(a, b):
    """Share of the shorter text's words found in the other (0 to 1)."""
    wa, wb = set(clean_words(a)), set(clean_words(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def in_order(a, b):
    """Share of a's word pairs (each word with the next) found in b (0 to 1): her own words coming
    back keep their order; a new request that only borrows a few of them doesn't."""
    wa, wb = clean_words(a), clean_words(b)
    pa, pb = list(zip(wa, wa[1:])), set(zip(wb, wb[1:]))
    if not pa or not pb:
        return 0.0
    return sum(p in pb for p in pa) / len(pa)


def covered(a, b):
    """Share of a's words (each once) found in b (0 to 1): her answer coming back misheard and
    with room talk on the end still brings most of her words; a request borrowing a few doesn't."""
    wa, wb = set(clean_words(a)), set(clean_words(b))
    return len(wa & wb) / len(wa) if wa else 0.0


# ---------- the household ----------

def person_for(speaker):
    """Who spoke, as the voice ID names them, exactly as sent (Oct 15: no household keys in
    between; the voice ID's own name is the person everywhere: names, apps, the firewall)."""
    return str(speaker).strip() or None if speaker else None


# ---------- asking Oread ----------

def _parse_time(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


async def lookup(assistant, heard, s):
    """{person, speaker, label, score, by, source} for this request, or {} when unknown.
    s: the settings. Never raises; never waits longer than the timeout."""
    o = (s.get("integrations") or {}).get("oread") or {}
    if not o.get("enabled"):
        return {}
    device = ((o.get("devices") or {}).get(assistant)) or assistant
    timeout = float(o.get("timeout", 0.8))
    max_age = float(o.get("max_age_seconds", 20))
    source = o.get("source", "wyoming")
    started = time.monotonic()
    try:
        if source == "wyoming":
            got = _from_wyoming(assistant)
        elif source == "home_assistant":
            got = await _from_home_assistant(device, s, timeout)
        else:
            got = await _from_oread(device, o, timeout)
    except Exception as e:
        log.info("  ! who spoke: %s didn't answer (%s)", source, e)
        return {"error": str(e)[:200]}
    if not got:
        return {}
    when = got.pop("_time", None)
    if when and time.time() - when > max_age:
        log.info("  who spoke: the newest %s clip is %.0fs old - nobody known", device, time.time() - when)
        return {"stale": True}
    words = got.pop("_words", None)
    if words and heard and overlap(words, heard) < float(o.get("min_word_overlap", 0.5)):
        log.info("  who spoke: Oread's clip (\"%s\") isn't this request - nobody known", words)
        return {"mismatch": True}
    got["person"] = person_for(got.get("speaker"))
    got["ms"] = round((time.monotonic() - started) * 1000, 1)
    got["source"] = source
    return got


def _from_wyoming(assistant):
    from veil import wyoming
    h = wyoming.HEARD.get(str(assistant).lower())
    if not h:
        return None
    return {"speaker": h.get("speaker"), "label": h.get("label"), "guess": h.get("guess"),
            "score": h.get("score"), "by": h.get("by"), "clip": h.get("clip"), "own_voice": h.get("own_voice"),
            "_time": h.get("time"), "_words": h.get("text")}


async def _from_oread(device, o, timeout):
    url = (o.get("url") or "").rstrip("/")
    if not url:
        raise RuntimeError("integrations: oread: url isn't set")
    token = config.secret(o.get("token") or "OREAD_TOKEN")
    verify = o.get("verify_tls", False)
    async with access.client(timeout, verify) as c:
        r = await c.get(url + "/clips", params={"status": "all", "device": device, "limit": 1},
                        headers={"Authorization": f"Bearer {token}"} if token else {})
    if r.status_code >= 300:
        raise RuntimeError(f"Oread answered {r.status_code}")
    clips = r.json() or []
    if not clips:
        return None
    clip = clips[0]
    res = clip.get("result") or {}
    return {"speaker": res.get("speaker"),
            "label": res.get("label"), "guess": res.get("guess"), "score": res.get("score"),
            "by": res.get("by"), "clip": clip.get("id"),
            "_time": _parse_time(clip.get("time")), "_words": clip.get("transcript")}


async def _from_home_assistant(device, s, timeout):
    ha = (s.get("integrations") or {}).get("home_assistant") or {}
    url = (ha.get("url") or "").rstrip("/")
    if not url:
        raise RuntimeError("integrations: home_assistant: url isn't set")
    token = config.secret(ha.get("token") or "HA_TOKEN")
    entity = "sensor.oread_" + re.sub(r"[^a-z0-9_]", "_", device.lower()) + "_speaker"
    async with access.client(timeout) as c:
        r = await c.get(f"{url}/api/states/{entity}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 404:
        return None
    if r.status_code >= 300:
        raise RuntimeError(f"Home Assistant answered {r.status_code}")
    st = r.json()
    a = st.get("attributes") or {}
    state = st.get("state")
    return {"speaker": state if state not in ("unknown", "too short", "unavailable", None) else None,
            "label": a.get("label"), "guess": a.get("guess"), "score": a.get("score"),
            "by": a.get("by"), "clip": a.get("clip"), "_time": _parse_time(a.get("heard_at"))}


async def test(s):
    """For the Integrations page: can the router reach Oread, and what does it say?"""
    o = (s.get("integrations") or {}).get("oread") or {}
    url = (o.get("url") or "").rstrip("/")
    if o.get("source", "wyoming") == "wyoming":
        from veil import wyoming
        return await wyoming.test(s)
    if o.get("source") == "home_assistant":
        try:
            device = next(iter(o.get("devices") or {}), None)
            if not device:
                return {"ok": False, "detail": "No devices under integrations.oread.devices to ask about"}
            got = await _from_home_assistant(device, s, 3)
            return {"ok": True, "detail": f"Home Assistant answered: {got}"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}
    if not url:
        return {"ok": False, "detail": "integrations: oread: url isn't set"}
    token = config.secret(o.get("token") or "OREAD_TOKEN")
    try:
        async with access.client(3, o.get("verify_tls", False)) as c:
            r = await c.get(url + "/status", headers={"Authorization": f"Bearer {token}"} if token else {})
        if r.status_code == 401:
            return {"ok": False, "detail": "Oread refused the token (make one on Oread: POST /tokens, "
                                           "role reviewer, and store it here as oread_token)"}
        if r.status_code >= 300:
            return {"ok": False, "detail": f"Oread answered {r.status_code}"}
        d = r.json()
        devices = [x.get("name") for x in (d.get("devices") or []) if isinstance(x, dict)] or d.get("devices")
        return {"ok": True, "detail": f"Oread {d.get('version', '')} answered; devices: {devices}"}
    except Exception as e:
        return {"ok": False, "detail": f"Couldn't reach {url}: {e}"}
