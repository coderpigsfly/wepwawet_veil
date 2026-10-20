#!/usr/bin/env python3
# tools/test_scores.py - scores every sentence in the doors datasets with the
# router's own math (scoring.py) and reports how well a topic's cut-off works.
# Run from ~/docker/house-router:
#   python3 tools/test_scores.py weather              uses confidence_local from settings.yaml
#   python3 tools/test_scores.py weather 0.8 0.85 0.9 compare several cut-offs
#   python3 tools/test_scores.py --held-back weather  stricter: scores built (in a throwaway folder) from four
#                                                     of every five sentences, tested on the fifth they never saw

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_scores as bs                     # same dataset readers as the build tool
from scoring import load_yaml, prepare, score  # same math as the router


def main():
    held = "--held-back" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--held-back"]
    topic = args[0] if args else "weather"
    cuts = [float(x) for x in args[1:]] or [float(bs.SETTINGS.get("confidence_local", 0.85))]

    if held:                 # built from four of five sentences, in a throwaway folder; the fifth is the test
        import tempfile
        tmp = tempfile.mkdtemp(prefix="held-back-")
        bs.HOLD_OUT, bs.TOPICS_DIR, bs.SCORES_DIR = 5, os.path.join(tmp, "topics"), os.path.join(tmp, "scores")
        data = bs.build()
    items = prepare(load_yaml(f"{bs.SCORES_DIR}/{topic}.yaml"))
    topic_def = bs.load_topics()[topic]

    if not held:
        print("Loading sources:")
        data = bs.load_all_sources()
    rows = [(n, r) for n in data if "doors" in bs.SOURCES[n]["use"] for r in data[n]]
    if held:
        rows = [x for i, x in enumerate(rows) if i % 5 == 0]
        print(f"\nheld back: {len(rows)} sentences the scores never saw")

    scored = []
    for n, r in rows:
        s, matched, why = score(r["text"], items)
        scored.append((bs.claims(topic_def, n, r["label"]), s, why, r["text"], matched, r["label"]))

    yes = [x for x in scored if x[0]]
    no = [x for x in scored if not x[0]]
    no_door = [x for x in yes if x[2] == "no door"]
    answerable = [x for x in yes if x[2] != "no door"]
    print(f"\n{topic}: {len(yes)} topic sentences, {len(no)} other sentences")
    print(f"  not a {topic} request (no door, set aside): {len(no_door)}")
    print(f"  answerable {topic} requests: {len(answerable)}\n")

    for cut in cuts:
        local = lambda x: x[2] == "ok" and x[1] >= cut
        hit = [x for x in answerable if local(x)]
        miss = [x for x in answerable if not local(x)]
        false = [x for x in no if local(x)]
        guard = sum(1 for x in miss if x[2] == "guard")
        below = len(miss) - guard
        print(f"=== cut-off {cut:.0%} ===")
        print(f"  {topic} answered locally:   {len(hit):>5} of {len(answerable)} ({len(hit)/len(answerable):.0%})")
        print(f"  {topic} held back:          {len(miss):>5}  (guard {guard}, below line {below})")
        print(f"  other wrongly answered:  {len(false):>5} of {len(no)} ({len(false)/len(no):.2%})")

        def show(title, group):
            if not group:
                return
            print(f"  {title}:")
            for _, s, why, text, matched, label in group[:8]:
                words = ", ".join(f"{w} {r['share']:.0%}" if r.get('share') is not None else w
                                  for w, r in matched) or "-"
                print(f"    {s:>4.0%} [{why}] {text}   ({words})   <{label}>")

        show("examples held back, below the line",
             sorted([x for x in miss if x[2] == "ok"], key=lambda x: -x[1]))
        show("examples wrongly answered", sorted(false, key=lambda x: -x[1]))
        print()


if __name__ == "__main__":
    main()