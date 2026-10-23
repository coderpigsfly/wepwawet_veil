"""Name Sparkle's own tests (run by tools/test_addon.py name_sparkle)."""
import random


def run(mod, check):
    import names
    check("the name in front lowers the first word", names.place("You have 3 chores.", "Owner", random.Random(5)), "Owner, you have 3 chores.")
    check("never after a question", names.place("Want to hear the rest?", "Beth", random.Random(0)), "Beth, want to hear the rest?")
    n = names.Names({"names_in_replies": {"calls": {"sam": ["Sir"]}}}, {"iris": {"names": {"rate": 1.0}}}, seed=3)
    sure = {"speaker": "sam", "label": "known", "score": 0.9}
    out, _ = n.dress("iris", "[[name]], it's done.", sure, "A")
    check("a [[name]] is filled where the phrase put it", out, "Sir, it's done.")
    out, _ = n.dress("iris", "It's done.", {"speaker": "sam", "label": "maybe", "score": 0.5}, "A")
    check("not sure who spoke: no name", out, "It's done.")
