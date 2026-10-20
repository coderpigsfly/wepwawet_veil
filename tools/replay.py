#!/usr/bin/env python3
# tools/replay.py - what was heard, and where it went, from the saved requests in captures/.
# Each line: the time, what she heard, and the path the router would pick for it today
# (asked of the running router through /explain, so nothing is sent to Gemini or saved).
#
#   python3 tools/replay.py                  everything saved today
#   python3 tools/replay.py 20261010-14      only 10 Oct, 2 pm to 3 pm
#   python3 tools/replay.py 20261010-14 diaper    ...and only turns with "diaper" in them
#   python3 tools/replay.py FILE.json -v     one request in full: the conversation and every reason

import glob
import json
import os
import sys
import time
import urllib.request

ROUTER = os.environ.get("ROUTER_URL", "http://localhost:8770").rstrip("/") + "/explain"
TOKEN = os.environ.get("ROUTER_TOKEN", "")
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures")


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def explain(body):
    req = urllib.request.Request(ROUTER, data=json.dumps({"messages": body.get("messages") or []}).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as e:
        return {"path": "?", "why": [f"router not reachable: {e}"]}


def main():
    args = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv
    if args and args[0].endswith(".json"):
        files = [args[0] if os.path.exists(args[0]) else os.path.join(DIR, os.path.basename(args[0]))]
        word = None
        verbose = True
    else:
        prefix = args[0] if args else time.strftime("%Y%m%d")
        word = args[1].lower() if len(args) > 1 else None
        files = sorted(glob.glob(os.path.join(DIR, prefix + "*.json")))
    for f in files:
        body = json.load(open(f))
        msgs = body.get("messages") or []
        users = [text_of(m.get("content")) for m in msgs if m.get("role") == "user"]
        heard = users[-1] if users else ""
        if word and word not in heard.lower():
            continue
        d = explain(body)
        name = os.path.basename(f)
        print(f"{name[9:11]}:{name[11:13]}:{name[13:15]}  {d.get('path', '?'):7} {heard}   [{name}]")
        if verbose:
            print("   the conversation she was sent:")
            for m in msgs:
                if m.get("role") in ("user", "assistant"):
                    t = text_of(m.get("content")).replace("\n", " ")
                    print(f"     {m['role']:9} {t[:160]}")
            for w in d.get("why") or []:
                print(f"   why: {w}")
            print()


if __name__ == "__main__":
    main()
