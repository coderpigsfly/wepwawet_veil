#!/usr/bin/env python3
# tools/shape_test.py - measures the router's last check before Gemini (shape.py) on
#   real questions that should go straight to Gemini (tools/sources.yaml gate_test) -> should pass
#   the miss log and known nonsense                                     -> should be held
# Uses exactly the router's shape.py and vocab, so what's measured is what runs.
#
# Run on myserver with the router's own image (it already has spaCy):
#   cd ~/docker/house-router
#   docker run --rm -v "$PWD":/w -v ~/datasets:/root/datasets house-router-house-router \
#     python /w/tools/shape_test.py
# (or from the Tools page, which runs it inside the router's own container)

import os
import re
import sys

import spacy
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import shape  # noqa: E402
import datasets as D  # noqa: E402  (the test set: tools/sources.yaml gate_test)

SETTINGS = yaml.safe_load(open(os.path.join(ROOT, "settings.yaml"))) or {}
NLP = spacy.load(((SETTINGS.get("language") or {}).get("spacy_model")) or "en_core_web_sm")
MISSES = os.path.join(ROOT, "learn", "misses.yaml")
REQ = yaml.safe_load(open(os.path.join(ROOT, "vocab/requests.yaml"))) or {}
P0 = yaml.safe_load(open(os.path.join(ROOT, "vocab/path0.yaml"))) or {}
FILLER = set(P0.get("filler_words", []))
POLITE = sorted(P0.get("polite_phrases", []), key=len, reverse=True)
# the datasets were recorded with other assistants' wake words; HA removes the wake word
OTHER_WAKE = set(D.GATE.get("other_wake_words") or [])


def clean(t):
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", t.lower().replace("’", "'")).split())


def words_of(said):
    w = [x for x in clean(said).split() if x not in FILLER]
    while w and w[0] in OTHER_WAKE:
        w.pop(0)
    text = " " + " ".join(w) + " "
    for p in POLITE:
        text = text.replace(" " + clean(p) + " ", " ")
    return text.split()


def kind_of(said):
    w = words_of(said)
    if not w:
        return "polite"
    return shape.classify(said, w, NLP, REQ)[0]


def main():
    real = D.gate_real_requests()
    known = D.gate_known_nonsense()
    try:
        known += [m["heard"] for m in (yaml.safe_load(open(MISSES)) or {}).get("misses") or []]
    except Exception:
        pass
    known = list(dict.fromkeys(known))

    rs = [(kind_of(s), s) for s in real]
    print(f"\nReal questions for Gemini: {len(real)}")
    for k in ("question", "command", "need", "ask", "fragment", "polite"):
        n = sum(1 for kk, _ in rs if kk == k)
        if n:
            print(f"  {k:10} {n:4}  ({n / len(real):.1%})")
    straight = sum(1 for k, _ in rs if k in ("question", "command", "need"))
    print(f"  -> straight to Gemini: {straight / len(real):.1%}   "
          f"\"ask around?\": {sum(k == 'ask' for k, _ in rs) / len(real):.1%}   "
          f"\"didn't catch that\": {sum(k == 'fragment' for k, _ in rs) / len(real):.1%}")

    print("\nThe real misses and known nonsense (should be ask or fragment):")
    for s in known:
        print(f"  {kind_of(s):10} {s}")

    for label, k in (("asked \"ask around?\"", "ask"), ("told \"didn't catch that\"", "fragment")):
        hit = [s for kk, s in rs if kk == k]
        print(f"\nReal questions {label} ({len(hit)}):")
        for s in hit:
            print(f"  {s}")


if __name__ == "__main__":
    main()
