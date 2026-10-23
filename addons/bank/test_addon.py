"""The Bank's own tests (run by tools/test_addon.py bank)."""


class Act:
    answer_from_bank = True

    def bank_choose(self, who, key):
        return ({"kind": "answer", "text": "Paris.", "bank_id": 3, "q": 1.0}, "added, Q 100%") if key == "capital of france" else (None, "not added")


def run(mod, check):
    notes = []
    ctx = {"assistant": "iris", "key": "capital of france", "activity": Act(), "keeps": True, "step": notes.append}
    check("an added saying is answered from its kept words", (mod.before_off_platform("x", ctx) or {}).get("text"), "Paris.")
    check("one not added goes out", mod.before_off_platform("x", dict(ctx, key="what time is it")), None)
    off = Act()
    off.answer_from_bank = False
    check("Use the bank off: not looked in", (mod.before_off_platform("x", dict(ctx, activity=off)), notes[-1]),
          (None, "not looked in: Use the bank (answer_from_bank) is off"))
