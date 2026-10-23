"""Loose language's own tests (run by tools/test_addon.py loose_language); the add itself is tested in
tools/test_veil.py and the series tests."""
import datetime as dt


class Conn:
    cache = {"items": [{"due": "2026-10-24T09:00:00Z"}]}

    def field(self, name):
        return "due" if name == "when" else None


def run(mod, check):
    import loose
    a, b = dt.date(2026, 10, 24), dt.date(2026, 10, 25)
    check("dealer's choice: the day in the span with the fewest things due", loose.dealers_choice(Conn(), a, b), b)
    check("the person's own weekday in the span", loose.day_in(None, "saturday", a, b, "week"), a)
    check("a pick not in the span: none", loose.day_in(None, "monday", a, b, "week"), None)
    check("its offer and before_event are its services", (callable(mod.offer), callable(mod.before_event)), (True, True))
    run_days(mod, check)
    picnic = {"name": "vikunja", "name_of": lambda x: x["title"],
              "items": [{"title": "Picnic", "due": "2099-10-28T16:00:00Z"}, {"title": "Mow the lawn", "due": "2099-10-29T16:00:00Z"}]}
    got = mod.fill({"need": "when", "about": "the picnic"}, {"suppliers": [picnic]})
    check("a thing named loosely: she asks to be sure, never puts it in unasked",
          (got["ask"].startswith("You mean the picnic on "), [c["name"] for c in got["choices"]]), (True, ["Picnic"]))
    check("no thing of that name: none (she asks when it is)", mod.fill({"need": "when", "about": "the parade"}, {"suppliers": [picnic]}), None)


def run_days(mod, check):
    """days: the words through Time (a stand-in for it here)."""
    class Services:
        def service(self, name, caller=None):
            assert (name, caller) == ("time.dated", "loose_language")
            return lambda said, ctx: ("buy palms on Sunday, March 21, 2027", "Palm Sunday (litcal) is Sunday, March 21, 2027", "litcal",
                                      {"name": "Palm Sunday", "date": "2027-03-21", "lead": "on"}) if "Palm Sunday" in said else None
    mod.SERVICES = Services()
    check("an add's day another app names is put as its date, through Time", mod.days("buy palms on Palm Sunday", {}),
          ("buy palms on Sunday, March 21, 2027", None))
    check("none named: as said", mod.days("buy palms on Saturday", {}), ("buy palms on Saturday", None))
