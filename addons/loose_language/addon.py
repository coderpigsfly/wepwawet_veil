"""addons/loose_language: the add said loosely, filled and offered (issue #25, step 5). The connector's add calls
offer and before_event (connector.LOOSE, set by the router while it's on); the router hands it an add's words
first (days): loose language(time(the words)), a day another integration names put as its date."""
import loose
from veil import match, rules

offer, before_event = loose.offer, loose.before_event


def days(said, ctx):
    """(an add's words with a day another integration names put as its date, the event or None), through the
    Time add-on it needs: "remind me to buy palms on Palm Sunday" -> "... on Sunday, March 21, 2027"; "bake a
    cake for Easter Sunday" -> "bake a cake for Sunday, March 28, 2027" and the event (Easter Sunday, that day):
    the chore is done before it, so the days before it are offered (before_event). As said when there's none."""
    got = SERVICES.service("time.dated", "loose_language")(said, ctx)  # noqa: F821  (set when it loads)
    if not got:
        return said, None
    (ctx.get("step") or (lambda text: None))(f"{got[1]}: added as \"{got[0]}\"")
    put = got[3] if len(got) > 3 else {}
    return got[0], (put if put.get("lead") in ("for", "before") else None)


THE = {"the", "my", "our", "your", "a", "an"}


def fill(blank, ctx):
    """The claimer's blank (need: when) for a thing named loosely ("rain for the picnic"): the other apps'
    things that hold its words and have a day ("Picnic", this Wednesday) are offered, never put in unasked:
    "You mean the picnic on Wednesday?" ({ask, choices}); none, None (she asks when it is)."""
    if (blank or {}).get("need") != "when" or not blank.get("about"):
        return None
    want = set(match.words(blank["about"])) - THE
    if not want:
        return None
    found = []
    for s in ctx.get("suppliers") or []:
        for x in s.get("items") or []:
            if not isinstance(x, dict) or not want <= set(match.words(s["name_of"](x))):
                continue
            f = rules.date_field([x])
            if f and rules.days_until(x[f]) is not None and rules.days_until(x[f]) >= 0:
                found.append({"name": s["name_of"](x), "say": rules._spoken(x[f]), "days": rules.days_until(x[f])})
    found.sort(key=lambda c: c["days"])
    if not found:
        return None
    about = blank["about"]
    if len(found) == 1:
        return {"ask": f"You mean {about} on {found[0]['say']}?", "choices": found[:1]}
    days = [c["say"] for c in found[:3]]
    return {"ask": f"You mean {about} on " + ", ".join(days[:-1]) + " or " + days[-1] + "?", "choices": found[:3]}
