#!/usr/bin/env python3
# tools/regress.py - runs the case files in tests/cases/ against the router's /explain door
# and shows what she would do, and why, for every case. A file whose requires: names a service
# that isn't in settings.yaml is skipped (someone without Donetick never runs chores tests).
# Run from ~/docker/house-router:
#   python3 tools/regress.py           decisions only (calls nothing)
#   python3 tools/regress.py --live    also fetches answers that change nothing
#   python3 tools/regress.py --why     show the reasons for every case, not just failures
# ROUTER_URL (default http://localhost:8770) and ROUTER_TOKEN (an API token, when
# security: tools_token_required is on) come from the environment.

import json
import os
import sys
import time
import urllib.request

import yaml

ROUTER = os.environ.get("ROUTER_URL", "http://localhost:8770").rstrip("/") + "/explain"
TOKEN = os.environ.get("ROUTER_TOKEN", "")
CASES_DIR = "tests/cases"
SETTINGS = "settings.yaml"
LIVE = "--live" in sys.argv
ALWAYS_WHY = "--why" in sys.argv


def ask(case):
    msgs = [{"role": "system", "content": f"{case.get('assistant', 'iris').title()} Personality"}]
    for i, turn in enumerate(case.get("history") or []):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": turn})
    msgs.append({"role": "user", "content": case["say"]})
    url = ROUTER + ("?live=true" if LIVE else "")
    req = urllib.request.Request(url, data=json.dumps({"messages": msgs, "fresh_context": bool(case.get("history")),
                                                  "pending": case.get("pending") or {},
                                                  "memory": case.get("memory") or {},
                                                  "turns": [dict(t, time=time.time() - t["ago"]) if "ago" in t else t
                                                            for t in case.get("turns") or []],   # ago: seconds before now
                                                  "asked": case.get("asked") or {},
                                                  "speaker": case.get("speaker") or {},
                                                  **({"firewall": case["firewall"]} if "firewall" in case else {})}).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    return json.load(urllib.request.urlopen(req, timeout=30))


def check(case, d):
    """List of mismatches between what was expected and what she decided."""
    exp, bad = case.get("expect") or {}, []
    for key in ("path", "topic", "action", "kind", "name_sure", "say_name_as"):
        if key in exp and str(d.get(key)) != str(exp[key]):
            bad.append(f"{key} {d.get(key)}, expected {exp[key]}")
    if LIVE:
        if "status" in exp and d.get("status") != exp["status"]:
            bad.append(f"status {d.get('status')}, expected {exp['status']}")
        if "reason" in exp and d.get("reason") != exp["reason"]:
            bad.append(f"reason {d.get('reason')}, expected {exp['reason']}")
    if "asks" in exp and bool(d.get("asks")) != bool(exp["asks"]) and (LIVE or d["path"] == "C"):
        bad.append(f"asks {bool(d.get('asks'))}, expected {exp['asks']}")
    if "speech_has" in exp and (LIVE or d["path"] in ("0", "C", "learn", "blocked")) and d.get("kind") != "add_name":
        if exp["speech_has"].lower() not in (d.get("speech") or "").lower():
            bad.append(f"answer doesn't contain '{exp['speech_has']}'")
    return bad


def case_files():
    """[(file name, cases)] for every case file whose required services (or integrations) are installed."""
    import os
    s = yaml.safe_load(open(SETTINGS)) or {}
    # a service by its name, or an integration switched on (requires: oread: a case file needing Oread running)
    services = set(s.get("services") or {}) | {n for n, v in (s.get("integrations") or {}).items()
                                               if isinstance(v, dict) and v.get("enabled", True) is not False}
    out = []
    for name in sorted(os.listdir(CASES_DIR)):
        if not name.endswith((".yaml", ".yml")):
            continue
        spec = yaml.safe_load(open(os.path.join(CASES_DIR, name))) or {}
        missing = [r for r in spec.get("requires") or [] if r not in services]
        if missing:
            print(f"skip  {name}: needs {', '.join(missing)} (not in settings.yaml, or switched off)")
            continue
        out.append((name, spec.get("cases") or []))
    return out


def main():
    counts = {"PASS": 0, "FAIL": 0, "KNOWN": 0, "FIXED": 0}
    cases = []
    for name, cs in case_files():
        cases += [dict(c, _file=name) for c in cs]
    last_file = None
    for case in cases:
        if case["_file"] != last_file:
            last_file = case["_file"]
            print(f"\n--- {last_file}")
        try:
            d = ask(case)
        except Exception as e:
            print(f"ERROR {case['name']}: {e}")
            counts["FAIL"] += 1
            continue
        bad = check(case, d)
        if case.get("known"):
            mark = "KNOWN" if bad else "FIXED"
        else:
            mark = "FAIL" if bad else "PASS"
        counts[mark] += 1
        score = f"{d['topic']} {d['score']:.0%}" if d.get("topic") and d.get("score") is not None else "-"
        action = f" {d['action']}" if d.get("action") else ""
        print(f"{mark:5} {case['name'][:44]:44} {d['path']:6} {score:14}{action}")
        if (LIVE or d["path"] in ("C", "learn")) and d.get("speech"):
            print(f"        says: {d['speech'][:110]}")
        elif LIVE and d.get("status"):
            print(f"        {d['status']}")
        if bad or ALWAYS_WHY or mark in ("KNOWN", "FIXED"):
            for b in bad:
                print(f"        ! {b}")
            for w in d.get("why") or []:
                print(f"        why: {w}")
            if case.get("known"):
                print(f"        known: {case['known']}")
    print("\n" + ", ".join(f"{n} {k.lower()}" for k, n in counts.items() if n))
    try:                                   # your recorded misses, replayed against today's code
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import misses
        topics = list(((yaml.safe_load(open(SETTINGS)) or {}).get("topics") or {}).keys())
        misses.show(misses.load(), topics)
        print("  (python3 tools/misses.py fix N makes one a test case; drop N takes it out)")
    except Exception as e:
        print(f"\n(miss review skipped: {e})")
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()