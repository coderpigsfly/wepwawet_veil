#!/usr/bin/env python3
# tools/test_flair.py - checks the flair engine (flair.py) against a pretend personality,
# so your real personality files can change without breaking a test.
# Needs no router: run from ~/docker/house-router with  python3 tools/test_flair.py
# Also prints a sample of how each real personality file would dress a few lines.

import os
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import flair  # noqa: E402

MOODS = yaml.safe_load(open(os.path.join(ROOT, "vocab/moods.yaml")))

PRETEND = {
    "rate": 0.4,
    "max_in_a_row": 1,
    "flourishes": [
        {"text": "OPEN-ANY.", "slot": "opener", "topics": ["any"]},
        {"text": "OPEN-WEATHER.", "slot": "opener", "topics": ["weather"]},
        {"text": "CLOSE-ANY.", "slot": "closer", "topics": ["any"]},
        {"text": "ASIDE-ANY,", "slot": "aside", "topics": ["any"]},
        {"text": "WARN-OPEN.", "slot": "opener", "topics": ["weather"], "mood": ["warning"]},
        {"text": "SORRY-CLOSE.", "slot": "closer", "topics": ["any"], "mood": ["sorry"]},
    ],
}
FLOURISHES = {f["text"] for f in PRETEND["flourishes"]}


def engine(spec=PRETEND, seed=1):
    d = tempfile.mkdtemp()
    if spec is not None:
        with open(os.path.join(d, "tester.yaml"), "w") as f:
            yaml.safe_dump(spec, f)
    return flair.Flair(d, moods=MOODS, seed=seed)


def added(said, line):
    """The flourishes in what she said that weren't in the line."""
    return [t for t in FLOURISHES if t in said and t not in line]


checks = []


def check(name, ok, detail=""):
    checks.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   ({detail})" if detail and not ok else ""))


def main():
    print("\nflair engine")
    line = "Tomorrow will be sunny, with a high of 64."

    # the deck: exactly rate x 10 in every full deck of 10, for many shuffles
    f = engine()
    n = sum(bool(added(f.dress("tester", line, "weather")[0], line)) for _ in range(200))
    check("40% means 40%: exactly 80 of 200 answers", n == 80, f"{n} of 200")

    # never two in a row with max_in_a_row: 1
    f = engine()
    run = [bool(added(f.dress("tester", line, "weather")[0], line)) for _ in range(200)]
    check("never two flourished answers in a row", not any(a and b for a, b in zip(run, run[1:])))

    # a rate too high for the limit: the limit wins (0.8 with never two in a row -> every other)
    f = engine(dict(PRETEND, rate=0.8))
    n = sum(bool(added(f.dress("tester", line)[0], line)) for _ in range(100))
    check("a rate too high for max_in_a_row: the limit wins (50 of 100)", n == 50, f"{n} of 100")

    # rate 0 and 1
    f = engine(dict(PRETEND, rate=0))
    check("rate 0: always plain", all(f.dress("tester", line)[0] == line for _ in range(30)))
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    check("rate 1, no limit: always flair", all(added(f.dress("tester", line)[0], line) for _ in range(30)))

    # one flourish at a time
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    check("only one flourish per answer",
          all(len(added(f.dress("tester", line, "weather")[0], line)) == 1 for _ in range(50)))

    # topics: a weather flourish never on chores
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    chores = "You have 3 chores due today."
    check("a weather flourish never lands on chores",
          all("OPEN-WEATHER." not in f.dress("tester", chores, "chores")[0] for _ in range(60)))

    # questions: no closer, she ends on the question
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    q = "Shall I read the rest?"
    outs = [f.dress("tester", q, "chores")[0] for _ in range(40)]
    check("a question always ends on the question", all(o.endswith("?") for o in outs), outs[0])

    # moods
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    warn = "Tonight there's a freeze warning, low of 28."
    outs = {f.dress("tester", warn, "weather")[0] for _ in range(40)}
    check("a warning line only gets warning flourishes",
          all(added(o, warn) in ([], ["WARN-OPEN."]) for o in outs), str(outs))
    sorry = "I couldn't find a chore like that, so I didn't change anything."
    outs = {f.dress("tester", sorry, "chores")[0] for _ in range(40)}
    check("a sorry line only gets sorry flourishes",
          all(added(o, sorry) in ([], ["SORRY-CLOSE."]) for o in outs), str(outs))
    check("mood words: 'nice' is not 'ice'", flair.mood_of("A nice day.", MOODS) == "plain")

    # hand-placed slots
    f = engine(dict(PRETEND, rate=1, max_in_a_row=0))
    placed = "Tomorrow, [[aside]] it will be sunny."
    outs = {f.dress("tester", placed, "weather")[0] for _ in range(20)}
    check("a hand-placed slot is used", outs == {"Tomorrow, ASIDE-ANY, it will be sunny."}, str(outs))
    f = engine(dict(PRETEND, rate=0))
    check("an unfilled slot vanishes cleanly",
          f.dress("tester", "[[opener]] Tomorrow will be sunny. [[closer]]")[0] == "Tomorrow will be sunny.")
    check("strip() clears slots (what local_reply always does)",
          flair.strip("Hi [[ opener ]] there.[[closer]]") == "Hi there.")

    # approved lines from the books push the placeholders aside
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "approved"))
    yaml.safe_dump({"rate": 1, "max_in_a_row": 0, "flourishes": [
        {"text": "PLACEHOLDER.", "slot": "opener", "placeholder": True}]},
        open(os.path.join(d, "tester.yaml"), "w"))
    f = flair.Flair(d, moods=MOODS, seed=3)
    check("no real lines yet: placeholders speak",
          any("PLACEHOLDER." in f.dress("tester", line)[0] for _ in range(20)))
    yaml.safe_dump({"rate": 1, "max_in_a_row": 0, "flourishes": [
        {"text": "PLACEHOLDER.", "slot": "opener", "placeholder": True},
        {"text": "MINE.", "slot": "closer"}]}, open(os.path.join(d, "tester.yaml"), "w"))
    f = flair.Flair(d, moods=MOODS, seed=3)
    outs = {f.dress("tester", line)[0] for _ in range(20)}
    check("your own lines: placeholders step aside",
          not any("PLACEHOLDER." in o for o in outs) and any("MINE." in o for o in outs), str(outs))
    yaml.safe_dump({"flourishes": [{"text": "BOOK.", "slot": "opener"}]},
                   open(os.path.join(d, "approved", "tester.yaml"), "w"))
    f = flair.Flair(d, moods=MOODS, seed=3)
    outs = {f.dress("tester", line)[0] for _ in range(30)}
    check("approved lines and your own lines speak; placeholders step aside",
          not any("PLACEHOLDER." in o for o in outs) and any("BOOK." in o for o in outs)
          and any("MINE." in o for o in outs), str(outs))

    # switches
    f = engine()
    check("no personality file: plain", f.dress("someone_else", line)[0] == line)
    f = engine(dict(PRETEND, rate=0))
    check("rate 0 -> plain (rate is the switch)", all(f.dress("tester", line)[0] == line for _ in range(10)))

    # slot any: fits wherever there's room (before, after, or a placed aside)
    anyspec = {"rate": 1, "max_in_a_row": 0, "flourishes": [{"text": "ANYWHERE.", "slot": "any", "topics": ["any"]}]}
    f = engine(anyspec)
    spots = set()
    for _ in range(30):
        said = f.dress("tester", line)[0]
        spots.add("before" if said.startswith("ANYWHERE.") else "after" if said.endswith("ANYWHERE.") else "none")
    check("slot any: used before and after", spots == {"before", "after"}, spots)
    said = f.dress("tester", "Shall I read the rest?")[0]
    check("slot any: never after a question", not said.endswith("ANYWHERE."), said)
    said = f.dress("tester", "Tomorrow, [[aside]] it will be sunny.")[0]
    check("slot any: fills a placed aside", said == "Tomorrow, ANYWHERE. it will be sunny.", said)

    # an assistant's name, and how speech-to-text hears it, are filler (router: without_filler)
    d = tempfile.mkdtemp()
    for name, spec in (("iris", {"heard_as": ["Irus", "eyeris"], "rate": 0.2}), ("felix", {"rate": 0}),
                       ("sources", {"heard_as": ["not a name"]})):
        with open(os.path.join(d, name + ".yaml"), "w") as f:
            yaml.safe_dump(spec, f)
    check("persona words: each assistant's name and its heard_as, lowercase; sources.yaml isn't an assistant",
          flair.persona_words(d) == {"iris", "irus", "eyeris", "felix"}, sorted(flair.persona_words(d)))
    check("persona words: no folder, none", flair.persona_words(os.path.join(d, "none")) == set())

    print(f"\n{sum(checks)} of {len(checks)} pass")

    # a look at the real files
    real = flair.Flair(os.path.join(ROOT, "personality"), moods=MOODS, seed=7)
    samples = [("weather", "Tomorrow will be partly cloudy, with a high of 64."),
               ("weather", "Tonight there's a freeze warning, low of 28."),
               ("chores", "Marked spray weeds done."),
               ("chores", "I couldn't find a chore like that, so I didn't change anything."),
               ("chores", "You have 7 chores: a, b, c, d, e. Plus 2 more. Shall I read the rest?")]
    for name in real.names():
        print(f"\n{name}: rate {real.people[name].rate}, {len(real.people[name].flourishes)} flourishes")
        for topic, s in samples * 2:
            said, why = real.dress(name, s, topic)
            print(f"  {why:34} {said}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
