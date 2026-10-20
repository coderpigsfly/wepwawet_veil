#!/usr/bin/env python3
# tools/test_fields.py - checks fields.py (the generic field types) against tests/fields.yaml.
# Needs no router: run from ~/docker/house-router with  python3 tools/test_fields.py
#   --why   show what was understood for every case, not just failures

import datetime as dt
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fields  # noqa: E402

WHY = "--why" in sys.argv


def check(case, got):
    exp, bad = case.get("expect") or {}, []
    for name, say in (exp.get("values") or {}).items():
        v = got["values"].get(name)
        if not v:
            bad.append(f"{name} not filled, expected '{say}'")
        elif str(v["say"]) != str(say):
            bad.append(f"{name} '{v['say']}', expected '{say}'")
    if exp.get("values") == {} and got["values"]:
        bad.append(f"expected nothing understood, got {sorted(got['values'])}")
    for name in exp.get("empty") or []:
        if name in got["values"]:
            bad.append(f"{name} filled ('{got['values'][name]['say']}'), expected empty")
    if "left" in exp and sorted(exp["left"]) != sorted(got["left"]):
        bad.append(f"left {got['left']}, expected {exp['left']}")
    for name in exp.get("named") or []:
        if name not in got["named"]:
            bad.append(f"{name} not named")
    for key in ("yes", "no"):
        if key in exp and bool(exp[key]) != got[key]:
            bad.append(f"{key} {got[key]}, expected {exp[key]}")
    return bad


def main():
    spec = yaml.safe_load(open("tests/fields.yaml"))
    now = dt.datetime.fromisoformat(spec["now"])
    passed = failed = 0
    for case in spec["cases"]:
        got = fields.parse_answer(case["say"], spec["fields"], now,
                                  people=spec.get("people"), choices=spec.get("choices"))
        bad = check(case, got)
        mark = "FAIL" if bad else "PASS"
        passed += not bad
        failed += bool(bad)
        heard = ", ".join(f"{k}: {v['say']}" for k, v in got["values"].items()) or "nothing"
        print(f"{mark}  {case['say'][:52]:52} -> {heard[:70]}")
        if bad or WHY:
            for b in bad:
                print(f"        ! {b}")
            if got["left"] or WHY:
                print(f"        left over: {got['left']}  named: {got['named']}")
    print(f"\n{passed} pass" + (f", {failed} fail" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
