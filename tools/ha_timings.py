#!/usr/bin/env python3
# tools/ha_timings.py - Home Assistant's own timings for its last voice requests, next to the
# router's. The router can't see the trip back through LiteLLM to Home Assistant, or Home
# Assistant's text to speech; Home Assistant keeps a debug record of each of its last few voice
# runs (Settings, Voice assistants, Debug), and this reads them over its websocket API.
#
# Each run: when, which assistant (pipeline), the words, and how long each stage took:
#   speech to text  stt-start to stt-end (listening and Oread, as Home Assistant saw it)
#   conversation    intent-start to intent-end: LiteLLM and the router, there and back
#   router          the router's own time for the same words (its activity log), when found; every
#                   trip added (a tool call's second trip is a row of its own)
#   around router   conversation less router: Home Assistant and LiteLLM, both ways
#   text to speech  tts-start to tts-end (Home Assistant's own; the sound may stream after it)
#   whole run       run-start to run-end
#
# Needs settings.yaml integrations: home_assistant: url (http://<ha>:8123) and token (the name of
# a Home Assistant long-lived access token in the vault, Security page, or .env).
# Run it in the router's container, where its settings and vault are:
#   docker exec -w /app house-router python3 tools/ha_timings.py        every pipeline's last runs
#   docker exec -w /app house-router python3 tools/ha_timings.py -v     ...and each run's events

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from veil import config, util  # noqa: E402
from veil import hadebug  # noqa: E402
from veil.hadebug import between, stamp, words_of  # noqa: E402

MATCH_SECONDS = 5            # a router row with the same words up to this long after the run ended is its own


def router_ms(db, words, start, end):
    """The router's own time (ms) for the same words during this run: every trip added (a tool
    call comes back as a second trip, a row of its own). None when no row is found."""
    if not db or not words or not start:
        return None
    want = util.words(words)
    rows = [r for r in db.execute("SELECT heard, ms FROM activity WHERE time BETWEEN ? AND ? AND ms IS NOT NULL",
                                  (start, (end or start) + MATCH_SECONDS)).fetchall()
            if util.words(r[0] or "") == want]
    return round(sum(r[1] for r in rows)) if rows else None


def ms_text(x):
    return "-" if x is None else f"{x / 1000:.1f}s"


def main():
    verbose = "-v" in sys.argv[1:]
    ha = config.section(config.section(config.settings(), "integrations"), "home_assistant")
    url, token = str(ha.get("url") or "").rstrip("/"), config.secret(ha.get("token") or "")
    if not url or not token:
        sys.exit("Set integrations: home_assistant: url in settings.yaml, and its token (a Home Assistant "
                 f"long-lived access token) as {ha.get('token') or 'a secret'} in the vault (Security page).")
    try:
        got_runs = hadebug.runs(url, token)
    except PermissionError as e:
        sys.exit(f"{e}.")
    path = os.path.join(config.DATA_DIR, "veil.db")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True) if os.path.exists(path) else None
    rows = []
    for run in got_runs:
        events = run["events"]
        when = stamp(events[0]) if events else None
        words = words_of(events)
        conv = between(events, "intent-start", "intent-end")
        end = stamp(events[-1]) if events else None
        mine = router_ms(db, words, when, end)
        rows.append({"when": when, "pipeline": run["pipeline"], "words": words,
                     "stt": between(events, "stt-start", "stt-end"), "conv": conv,
                     "router": mine,
                     "around": round(conv - mine) if mine is not None and conv is not None else None,
                     "tts": between(events, "tts-start", "tts-end"), "run": between(events, "run-start", "run-end"),
                     "errors": [e for e in events if e.get("type") == "error"], "events": events})
    if not rows:
        print("Home Assistant holds no voice runs yet (it keeps the last few per assistant, until it restarts).")
        return
    rows.sort(key=lambda r: r["when"] or 0)
    print(f"{'when':8}  {'assistant':14}  {'speech to text':>14}  {'conversation':>12}  {'router':>6}  "
          f"{'around router':>13}  {'text to speech':>14}  {'whole run':>9}  words")
    for r in rows:
        print(f"{time.strftime('%H:%M:%S', time.localtime(r['when'])) if r['when'] else '?':8}  {r['pipeline'][:14]:14}  "
              f"{ms_text(r['stt']):>14}  {ms_text(r['conv']):>12}  {ms_text(r['router']):>6}  {ms_text(r['around']):>13}  "
              f"{ms_text(r['tts']):>14}  {ms_text(r['run']):>9}  {r['words']}")
        for e in r["errors"]:
            print(f"{'':10}! {(e.get('data') or {}).get('code')}: {(e.get('data') or {}).get('message')}")
        if verbose:
            t0 = r["when"] or 0
            for e in r["events"]:
                print(f"{'':10}+{((stamp(e) or t0) - t0) * 1000:7.0f} ms  {e.get('type')}")


if __name__ == "__main__":
    main()
