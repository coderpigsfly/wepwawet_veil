#!/usr/bin/env python3
# tools/test_series.py - plays the conversations in tests/series.yaml through series.py.
# Needs no router: run from ~/docker/house-router with  python3 tools/test_series.py

import datetime as dt
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import series  # noqa: E402

PHRASES = yaml.safe_load(open(os.path.join(ROOT, "phrases/router.yaml")))
STOP = yaml.safe_load(open(os.path.join(ROOT, "vocab/answers.yaml"))).get("stop", [])


def say(section, **v):
    return PHRASES[section]["any"][0].format(**v)


def main():
    spec = yaml.safe_load(open(os.path.join(ROOT, "tests/series.yaml")))
    now = dt.datetime.fromisoformat(spec["now"])
    passed = failed = 0
    for conv in spec["conversations"]:
        print(f"\n{conv['name']}")
        filled = {k: {"say": v} for k, v in (conv.get("filled") or {}).items()}
        state, ok, cur = None, True, dict(filled)
        for turn in conv["turns"]:
            exp = turn.get("expect") or {}
            changes = {}
            if turn.get("start"):
                line, state = series.start(conv["item"], spec["noun"], spec["fields"], filled, say)
                heard = "(start)"
            else:
                line, after, changes = series.answer(state, turn["say"], now, say, STOP)
                heard = turn["say"]
                if line is not None:
                    state = after
                    cur.update(changes)
            bad = []
            if exp.get("dropped") and line is not None:
                bad.append("expected dropped (not an answer)")
            if "says" in exp and exp["says"].lower() not in (line or "").lower():
                bad.append(f"expected her line to contain '{exp['says']}'")
            if exp.get("done") and state is not None:
                bad.append("expected the series to end")
            for f, want in (exp.get("filled") or {}).items():
                if f not in cur or cur[f]["say"] != want:
                    bad.append(f"{f}: {cur.get(f, {}).get('say')}, expected {want}")
            mark = "FAIL" if bad else "PASS"
            ok &= not bad
            print(f"  {mark}  you: {heard[:44]:44}  her: {line}")
            for b in bad:
                print(f"          ! {b}")
        passed += ok
        failed += not ok
    print(f"\n{passed} conversations pass" + (f", {failed} fail" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
