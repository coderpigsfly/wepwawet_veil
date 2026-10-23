"""addons/loose_language/loose.py - Loose language (an add-on, issue #25, step 5; issue #19): what was said
loosely in an add ("this weekend", "tomorrow morning", "remind me to ..."), filled from the person's own
preferences (prefs.py) and offered, two details to a question. The app that claimed the request (chore)
hands its add here: chore(loose language(the words)). While she's asking, her line is held (util.HOLD): the
dress add-ons leave it alone until the add is closed out. Moved out of the connector with the add-on."""
import re

import prefs
from veil import util

from connector import REMIND_BY


SOFT_LEAD = {"on", "this", "next", "at", "for", "in", "of", "every", "each", "after", "from"}


def day_kind(said):
    """What the date said is (the owner, Oct 21): "deadline" when it's the last possible moment ("submit tax
    documents by April 15", or written as part of what it is: "renew car registration Sept 30"); "after" when
    the reminder comes after it ("until Friday": when, not said); "remind" when
    it's said before what to do ("remind me tomorrow morning to stop at Dunkin"); "day" when it's the day to do
    it ("on Sunday", "mow the lawn Saturday"); None when no day was said."""
    import fields as F
    words = F.words_of(said)
    to = next((k for k in range(1, len(words)) if words[k] == "to" and "remind" in words[k - 2:k]), None)
    to = to if to is not None else next((k for k, x in enumerate(words) if x == "to" and any(y.startswith("remind") for y in words[:k])), None)
    for i, w in enumerate(words):
        if not (w in F.WEEKDAYS or w in F.MONTHS or w in ("today", "tonight", "tomorrow") or re.fullmatch(r"\d{1,2}th", w)):
            continue
        j = i - 1
        while j >= 0 and words[j] in ("the", "this", "next"):
            j -= 1
        lead = words[j] if j >= 0 else ""
        if lead in F.DEADLINE_WORDS:
            return "deadline"
        if lead in F.UNTIL_WORDS:
            return "after"
        if to is not None and i < to:
            return "remind"
        if lead in SOFT_LEAD or w in F.WEEKDAYS or w in ("today", "tonight", "tomorrow"):
            return "day"
        return "deadline"
    return None


def lead_before(due, remind_at, days):
    """A reminder days before a due moment, at the person's reminder time: (minutes before it, how it's said)."""
    import datetime as dt
    import fields as F
    h, m = map(int, str(remind_at).split(":"))
    at = dt.datetime.combine(due.date() - dt.timedelta(days=days), dt.time(h, m), tzinfo=due.tzinfo)
    when = "the day before" if days == 1 else "a week before" if days == 7 else f"{days} days before"
    return int((due - at).total_seconds() // 60), f"{when} at {F.say_time(h, m)}"


def until(conn, filled, answer, asked, chosen, today):
    """"... until Friday" (the owner, Oct 21): the reminder comes after that day, but when wasn't said. She offers
    the day after at the person's reminder time; yes takes it, a day or "three days after" sets it, and no asks
    when, then. The chore is due on the day chosen, reminded at it. Her question, or None."""
    import datetime as dt
    import fields as F
    d = filled.get("due_date") or {}
    base = dt.date.fromisoformat(chosen.get("until") or d["date"])
    chosen["until"] = base.isoformat()
    h, m = map(int, str(conn.opt("default_chore_time") or "09:00").split(":"))
    day = chosen.get("after")
    if day is None and answer is not None and "after" in asked:
        low = set(F.words_of(answer))
        dur = F.parse_duration(F.Words(answer))
        got = F.parse_date(F.Words(answer), today)
        if got and not got.get("span"):
            day = got["date"]
        elif dur and dur["minutes"] >= 1440:
            day = (base + dt.timedelta(days=dur["minutes"] // 1440)).isoformat()
        elif low & F.YES and not (asked.get("after") or {}).get("refused"):
            day = (base + dt.timedelta(days=1)).isoformat()
        elif low & F.NO:
            return {"after": {"say": F.say_date(base, today), "refused": True, "section": "offer_after_when"}}
        if day:
            chosen["after"] = day
    if day is None:
        nxt = base + dt.timedelta(days=1)
        return {"after": {"say": F.say_date(base, today), "lead": f"{F.say_date(nxt, today)} at {F.say_time(h, m)}"}}
    on = dt.date.fromisoformat(day)
    filled["due_date"] = {"date": on.isoformat(), "say": F.say_date(on, today)}
    if not filled.get("due_time"):
        filled["due_time"] = {"hour": h, "minute": m, "say": F.say_time(h, m)}
    filled["remind_at_due"] = {"value": True, "say": "remind at due"}
    return None


def deadline(conn, said, filled, answer, asked, chosen, today):
    """The owner's rule (Oct 21): a hard deadline is the last possible moment, so it's the due date (the end of
    that day, when no time was said), and she asks whether to remind before it. "Remind me to ... on Sunday"
    is unclear, so she asks first which it is: the day to remind, or the day it's due. Her one question this
    time ({which} or {before}), or None (filled is filled in place)."""
    import datetime as dt
    import fields as F
    d = filled.get("due_date") or {}
    if not d.get("date") or d.get("span") or d.get("term") or d.get("loose") or filled.get("repeat"):
        return None
    kind = day_kind(said)
    if kind == "after":
        return until(conn, filled, answer, asked, chosen, today)
    reminder = bool(re.search(r"\bremind", said.lower()))
    which = chosen.get("which")
    if kind == "day" and reminder and which is None:
        if answer is not None and "which" in asked:
            low = set(F.words_of(answer))
            own = set(F.words_of(said)) - {"remind", "me", "to", "on", "the", "a", "an", "please", "can", "you"} \
                - set(F.WEEKDAYS) - set(F.MONTHS) - {"today", "tomorrow", "tonight"}
            if low & {"remind", "reminder", "reminding", "reminded"}:
                which = "remind"
            elif low & ({"due", "deadline", "do", "done", "last"} | own):
                which = "do"
            if which:
                chosen["which"] = which
        if which is None:
            again = answer is not None and "which" in asked        # her answer didn't say which: another way
            return {"which": {"say": d.get("say") or F.say_date(dt.date.fromisoformat(d["date"]), today),
                              **({"section": "offer_which_again"} if again else {})}}
    if not (kind == "deadline" or which == "do") or "remind_before" in filled or chosen.get("before") == "none":
        return None
    if kind == "deadline" and not filled.get("due_time"):
        filled["due_time"] = {"hour": 23, "minute": 59, "say": F.say_time(23, 59)}       # the last possible moment
    t = filled.get("due_time") or {}
    due = dt.datetime.combine(dt.date.fromisoformat(d["date"]), dt.time(t.get("hour", 23), t.get("minute", 59))).astimezone()
    remind_at = str(conn.opt("default_chore_time") or "09:00")
    days = 1 if (due.date() - today).days <= 14 else 7
    if (due.date() - today).days < 1:
        return None                                    # due today: no day before it to remind on
    lead = chosen.get("before")
    if lead is None and answer is not None and "before" in asked:
        low = set(F.words_of(answer))
        dur = F.parse_duration(F.Words(answer))
        day = F.parse_date(F.Words(answer), today)
        if low & F.NO and not dur:
            lead = "none"
        elif dur and dur["minutes"] >= 1440:
            lead = dur["minutes"] // 1440
        elif day and not day.get("span"):
            lead = max(1, (dt.date.fromisoformat(d["date"]) - dt.date.fromisoformat(day["date"])).days)
        elif low & F.YES:
            lead = days
        if lead is not None:
            chosen["before"] = lead
    if lead is None:
        again = answer is not None and "before" in asked
        return {"before": {"say": d.get("say") or F.say_date(dt.date.fromisoformat(d["date"]), today),
                           "lead": lead_before(due, remind_at, days)[1], **({"section": "offer_before_again"} if again else {})}}
    if lead != "none":
        minutes, say = lead_before(due, remind_at, int(lead))
        filled["remind_before"] = {"minutes": minutes, "say": say}
    return None


def offer(conn, said, filled, person, names):
    """Loose language in an add (issue #19), filled from the person's own preferences (veil/prefs.py):
    a day said only as a span ("this week", "the weekend", "next month"), a time said only as a part
    of the day ("tomorrow morning", "after school") and, when "remind" was said, how it comes. What
    has none yet is offered, two details to a question ("Would Saturday work for the weekend, and
    6 AM for the morning?"); her answer (the add again, resume: offer) fills them, and what's still
    open is asked next. Said by the person it's for, the answer is kept as theirs. Nobody sure who
    it's for: the house's offer (dealer's choice for a day), nothing asked or kept.
    Her question, or None when nothing is asked (filled is filled in place)."""
    import datetime as dt
    import fields as F
    import prefs
    who = str(person[1]).lower() if person else None
    today = dt.datetime.now().astimezone().date()
    state = conn.OFFER.get()
    if isinstance(state, str):           # the answer alone: to everything she'd ask now
        state = {"answer": state}
    state = state or {}
    answer, asked, chosen = state.get("answer"), state.get("offer"), dict(state.get("chosen") or {})
    if answer is not None and asked is None:
        asked = {"day": 1, "time": 1, "means": 1}
    asked = asked or {}
    keep = False
    if answer is not None:
        asker = conn.speaker_person(names) or (None if conn.VOICE.get() else conn.default_person(names))
        keep = bool(who) and asker == person
    offers = {}
    if answer is not None:
        # a detail said in the answer counts even when she didn't ask for it ("I prefer 11 a.m." to
        # "Is Monday OK?", Oct 21): an explicit day or time is taken; an offer stands only where asked
        w = F.Words(answer)
        got_t = F.parse_time(w)
        got_d = F.parse_date(w, today)
        if got_t and not got_t.get("part") and "time" not in asked:
            asked = dict(asked, time={"explicit": True})
        if got_d and not got_d.get("span") and "day" not in asked:
            asked = dict(asked, day={"explicit": True})
        if any(re.search(r"\b" + re.escape(x) + r"\b", answer.lower()) for ws in REMIND_BY.values() for x in ws) \
                and "means" not in asked:
            asked = dict(asked, means={"explicit": True})
    first = deadline(conn, said, filled, answer, asked, chosen, today)     # the day's kind and a reminder before it
    if first:
        key = next(iter(first))
        speech = conn.say(first[key].get("section") or "offer_" + key, day=first[key]["say"], lead=first[key].get("lead", ""))
        heard = [x for x in ((filled.get("due_date") or {}).get("say") if chosen.get("which") == "do" else None,) if x]
        if answer is not None and heard:
            speech = conn.say("offer_heard", heard=f"due {heard[0]}") + " " + speech
        return {"status": "answered", "speech": util.HOLD + speech,
                "ask": {"kind": "offer", "said": said, "action": "add", "offer": first, "chosen": chosen, "question": speech,
                        "for": state.get("for")}}
    reminder = bool(re.search(r"\bremind", said.lower()))
    probe = reminder and not any(filled.get(k) for k in ("due_date", "due_time", "repeat"))
    is_event = (filled.get("due_date") or {}).get("term") == "event_day"
    if probe:
        # "remind me to ..." with no day or time: she asks what day and what time (Oct 21: "these are
        # the probes"), after how; offered as dealer's choice this week, at the person's usual time
        a = today + dt.timedelta(days=1)
        filled["due_date"] = {"date": a.isoformat(), "span": [a.isoformat(), (today + dt.timedelta(days=6)).isoformat()],
                              "term": "remind_day", "said": "the reminder", "unit": "week"}
        filled["due_time"] = F.part_time("remind_time", str(conn.opt("default_chore_time") or "09:00"))

    # the day: a span said ("the weekend"): the person's own day in it, else dealer's choice
    d = filled.get("due_date") or {}
    if d.get("span"):
        a, b = (dt.date.fromisoformat(x) for x in d["span"])
        offered = dt.date.fromisoformat(d["offer"]) if d.get("offer") else dealers_choice(conn, a, b)
        if "day" in chosen:
            day = dt.date.fromisoformat(chosen["day"])
        elif answer is not None and "day" in asked:
            got = F.parse_date(F.Words(answer), today)
            day = dt.date.fromisoformat(got["date"]) if got and not got.get("span") else \
                dt.date.fromisoformat(asked["day"]["value"]) if (asked.get("day") or {}).get("value") else offered
            if not a <= day <= b:       # "Sunday", "the 12th": that one in the span, when it has one
                day = day_in(conn, F.WEEKDAYS[day.weekday()] if d["unit"] == "week" else str(day.day), a, b, d["unit"]) or day
            chosen["day"] = day.isoformat()
            if keep and d["term"] not in ("remind_day", "before_event", "event_day"):     # a weekday means nothing for those
                prefs.pick(who, d["term"], F.WEEKDAYS[day.weekday()] if d["unit"] == "week" else str(day.day))
        else:
            # what's offered: her last pick in the span, else dealer's choice; either way it's confirmed
            day = day_in(conn, prefs.offer(who, d["term"]) if who else None, a, b, d["unit"]) or offered
            if who:
                offers["day"] = {"term": d["term"], "value": day.isoformat(), "say": F.say_date(day, today),
                                 "for": d["said"] if d["term"] == "before_event" else "for " + d["said"]}
        filled["due_date"] = {"date": day.isoformat(), "say": F.say_date(day, today), "loose": True}
        if d["term"] in ("weekend", "next_weekend") and day.weekday() == 4 and not filled.get("due_time") \
                and "night" in F.PART_TIMES:
            filled["due_time"] = F.part_time("night")         # the weekend starts Friday night
    on = (filled.get("due_date") or {}).get("date")
    day = dt.date.fromisoformat(on) if on else None
    if on and not filled.get("due_time") and (reminder or d.get("span")):
        # a day with no time, for a reminder or a day she offers: the time is asked too (Oct 21: "you're
        # allowed to prompt for two items"), the person's usual reminder time, else the chore time
        filled["due_time"] = F.part_time("remind_time", str(conn.opt("default_chore_time") or "09:00"))

    # the time: a part of the day, or what ends at an hour nobody said
    t = filled.get("due_time") or {}
    if who and t.get("part"):
        o = {"term": t["part"], "value": f"{t['hour']:02d}:{t['minute']:02d}", "say": t["say"],
             "for": "for the reminder" if t["part"] in ("remind_time", "event_time") else
                    "for " + (("the " + t["part"]) if t["part"] in F.PARTS_OF_DAY else t["part"])}
        mine = prefs.offer(who, t["part"], day)      # her last pick is what's offered, to be confirmed
        if mine and not t.get("event"):
            h, m = map(int, mine.split(":"))
            o.update(value=mine, say=F.say_time(h, m))
        hm = chosen.get("time")
        if hm is None and answer is not None and "time" in asked:
            # a bare hour leans to the part said ("8" in the morning); for "after school", the afternoon;
            # for a reminder's own time, the house's rule for a bare hour ("at 10" is 10 am)
            hint = t["part"] if t["part"] in F.PARTS_OF_DAY else None if t["part"] == "remind_time" else "afternoon"
            got = F.parse_time(F.Words(f"{answer} in the {hint}" if hint else answer))
            hm = f"{got['hour']:02d}:{got['minute']:02d}" if got and not got.get("part") else o["value"]
            chosen["time"] = hm
            if keep and not t.get("event"):
                prefs.pick(who, t["part"], hm, day)
        if hm is None:
            offers["time"] = o
            filled["due_time"] = dict(t, hour=int(o["value"][:2]), minute=int(o["value"][3:]), say=o["say"])
        if hm:
            h, m = map(int, hm.split(":"))
            filled["due_time"] = {"hour": h, "minute": m, "say": F.say_time(h, m), "loose": True}

    # how the reminder comes, when "remind" was said
    if who and REMIND_BY and re.search(r"\bremind", said.lower()) and "remind_by" not in filled:
        how = chosen.get("means")
        mine = prefs.offer(who, "remind_by", day)
        mine = mine if mine in REMIND_BY else None
        if how is None and answer is not None and "means" in asked:
            low = answer.lower()
            how = next((k for k, ws in REMIND_BY.items() if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in ws)), None) \
                or (asked["means"].get("value") if isinstance(asked["means"], dict) else None)   # a plain yes: her last pick
            if how:
                chosen["means"] = how
                if keep:
                    prefs.pick(who, "remind_by", how)
        if how is None and not (answer is not None and "means" in asked):
            offers["means"] = {"term": "remind_by", "value": mine}      # her last pick offered, to be confirmed
        if how:
            filled["remind_by"] = conn.remind_by(how)

    if not offers:
        return None
    # two of the three at most, in a mixed order (the owner, Oct 21); the third after, with what was
    # heard said back first
    import random
    pending = [k for k in ("day", "time", "means") if k in offers]
    if "day" in pending and is_event:
        pending = ["day"]          # an event: the reminder's day first, alone (the larger unit), then its time
    elif len(pending) == 3:
        pending = random.choice([["day", "time"], ["time", "means"], ["day", "means"]])
    ask = {k: offers[k] for k in pending[:2]}
    section = "offer_" + "_".join(k for k in ("day", "time", "means") if k in ask)
    if section == "offer_day_time" and probe:
        section = "offer_when"
    if section == "offer_day" and is_event:
        section = "offer_event_day"
    speech = conn.say(section, day=ask.get("day", {}).get("say", ""), span=ask.get("day", {}).get("for", ""),
                      time=ask.get("time", {}).get("say", ""), part=ask.get("time", {}).get("for", ""))
    heard = [x for x in ((filled.get("due_date") or {}).get("say") if "day" in chosen else None,
                         f"at {filled['due_time']['say']}" if "time" in chosen and filled.get("due_time") else None,
                         (filled.get("remind_by") or {}).get("say") if "means" in chosen else None) if x]
    if answer is not None and heard:          # what she heard, said back before the next question
        speech = conn.say("offer_heard", heard=" ".join(heard)) + " " + speech
    # held: no dress add-on touches her question until the add is closed out (util.HOLD, taken out
    # before it's spoken)
    return {"status": "answered",
            "speech": util.HOLD + speech,
            "ask": {"kind": "offer", "said": said, "action": "add", "offer": ask, "chosen": chosen, "question": speech,
                    "for": state.get("for")}}


def before_event(conn, name, filled, today):
    """A day said for something the thing is for ("get my tuxedo cleaned for Janine's wedding on
    Sunday", Oct 21): the day is the event's, and the thing is done before it, so the days from
    tomorrow to the day before are offered. Only for an event of two words or more, not a person
    ("for Mom on Sunday" stays Sunday)."""
    import datetime as dt
    import fields as F
    import connector
    d = filled.get("due_date") or {}
    ev = connector.EVENT_DAY.get()
    if ev and d.get("date") == ev.get("date") and not d.get("span") and not filled.get("repeat"):
        # "bake a cake for Easter Sunday": Time put its day in for the name, the chore is done before it
        on = dt.date.fromisoformat(ev["date"])
        a, b = today + dt.timedelta(days=1), on - dt.timedelta(days=1)
        if b >= a:
            filled["due_date"] = {"date": a.isoformat(), "span": [a.isoformat(), b.isoformat()], "term": "before_event",
                                  "said": f"before {ev['name']} on {F.say_date(on, today)}", "unit": "week"}
        return
    m = re.search(r"\b(?:for|before)\s+(.+)$", name, re.I)
    if not d.get("date") or d.get("span") or filled.get("repeat") or not m:
        return
    event = m.group(1).strip()
    if len(event.split()) < 2 or event.lower() in conn.people:
        return
    on = dt.date.fromisoformat(d["date"])
    a, b = today + dt.timedelta(days=1), on - dt.timedelta(days=1)
    if b < a:
        return
    filled["due_date"] = {"date": a.isoformat(), "span": [a.isoformat(), b.isoformat()], "term": "before_event",
                          "said": f"before {event} on {F.say_date(on, today)}", "unit": "week"}


def day_in(conn, value, a, b, unit):
    """The day from a to b that is the person's own pick for its span (a weekday, or a day of the
    month), or None."""
    import datetime as dt
    import fields as F
    if not value:
        return None
    for k in range((b - a).days + 1):
        x = a + dt.timedelta(days=k)
        if (F.WEEKDAYS[x.weekday()] if unit == "week" else str(x.day)) == str(value).lower():
            return x
    return None


def dealers_choice(conn, a, b):
    """The day from a to b with the fewest things already due on it (the copy on hand), the
    earliest of those: the same request gets the same offer (issue #19)."""
    import datetime as dt
    counts = {}
    for it in conn.cache.get("items") or []:
        v = it.get(conn.field("when")) if isinstance(it, dict) and conn.field("when") else None
        try:
            due = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone().date() if v else None
        except ValueError:
            due = None
        if due and a <= due <= b:
            counts[due] = counts.get(due, 0) + 1
    days = [a + dt.timedelta(days=k) for k in range((b - a).days + 1)]
    return min(days, key=lambda x: (counts.get(x, 0), x))
