"""Time's own tests (run by tools/test_addon.py time)."""


def run(mod, check):
    feasts = [{"name": "Easter Sunday", "date": "2027-03-28T00:00:00Z", "grade": 7},
              {"name": "Saint Stephen, The First Martyr", "date": "2026-12-26T00:00:00Z", "grade": 4},
              {"name": "Saint Stephen of Hungary", "date": "2027-08-16T00:00:00Z", "grade": 2}]
    s = {"name": "litcal", "items": feasts, "name_of": lambda x: x["name"], "never": {"the", "of", "feast", "day", "a"},
         "alike": {"steven": "stephen"}, "weight": lambda x: -x["grade"], "anchors": {"feast"}}
    ctx = {"suppliers": [s], "own_words": {"rain", "snow"}, "little": {"when", "i", "am", "at", "on", "the", "will", "it"},
           "not_action": {"when", "i"}, "plain": {"sunday", "monday", "today", "tomorrow", "march", "december"}}
    got = mod.dated("Will it rain Easter Sunday", ctx)
    check("a thing named whole is put as its date", (got[0].startswith("Will it rain Sunday, March 28"), got[2]), (True, "litcal"))
    steven = "Will it snow on the Feast of Steven when I am at the picnic"
    check("two saints called Stephen: neither put in for sure", mod.dated(steven, ctx), None)
    asked = mod.fill({"need": "when", "about": "the feast of steven"}, dict(ctx, said=steven))
    check("the blank: she asks which, the feast first (Steven is Stephen)", (asked["ask"].startswith("Do you mean Saint Stephen, The First Martyr, on Saturday, December 26 or Saint Stephen of Hungary"),
                                                                         [c["replace"] for c in asked["choices"]]), (True, ["the Feast of Steven"] * 2))
    twice = mod.fill({"need": "when", "about": "the feast of steven"}, dict(ctx, said=steven, suppliers=[dict(s, items=feasts + feasts[1:2])]))
    check("one feast listed twice is still one of the two", [c["name"] for c in twice["choices"]],
          ["Saint Stephen, The First Martyr", "Saint Stephen of Hungary"])
    s1 = dict(s, items=feasts[:2])
    got = mod.dated(steven, dict(ctx, suppliers=[s1]))
    check("one Stephen: put in, the rest of the sentence kept", (got[0].startswith("Will it snow on Saturday, December 26"), got[0].endswith("when I am at the picnic")), (True, True))
    check("one Stephen fills the blank", mod.fill({"need": "when", "about": "the feast of steven"}, dict(ctx, suppliers=[s1], said=steven))["words"], got[0])
    check("a sentence with no thing of another app is handed back", mod.supply("Will it rain on Sunday", ctx), "Will it rain on Sunday")
    palm = dict(s, items=[{"name": "Palm Sunday", "date": "2027-03-21T00:00:00Z", "grade": 7}])
    check("a name's words said apart are not it: 'buy palms on Sunday' isn't Palm Sunday",
          (mod.dated("remind me to buy palms on Sunday", dict(ctx, suppliers=[palm])), bool(mod.dated("buy palms on Palm Sunday", dict(ctx, suppliers=[palm])))),
          (None, True))
    check("no suppliers: handed back", mod.supply("Will it rain Easter Sunday", {}), "Will it rain Easter Sunday")
