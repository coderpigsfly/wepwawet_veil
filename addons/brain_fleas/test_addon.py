"""Brain fleas' own tests (run by tools/test_addon.py brain_fleas)."""


def run(mod, check):
    mod.make(["um", "uh"], lambda section, **v: section, lambda ask: "which?")
    notes = []
    ctx = {"step": notes.append, "telling": lambda s: False}
    check("a flea is found by its own words", (mod.key_word("who is talking to you", ctx) or {}).get("action"),
          "device_who_is_speaking_to_you")
    check("words no flea has: none", mod.key_word("turn on the kitchen light", ctx), None)
    check("why none: the best and the bar", notes[-1].startswith("none fits"), True)
    check("its names are the names taken", "add_flea" in mod.names(), True)
