# series.py - the generic follow-up series for adding things through any app.
# After an item is created, she offers the extra fields still open, understands answers
# (fields.py), reads the whole item back after every addition, and keeps offering what's
# left until a stop answer, nothing is left, or the question is dropped.
# Nothing app-specific: the app's fields come from its connector map; wording comes from
# phrases (passed in as say). Pure: no files, no network, no clock (now is passed in).
#
#   start(name, noun, fields, filled, say)                      -> (line, state or None)
#   answer(state, text, now, say, stop_words, people, choices)  -> (line, state, changes)
#       line None means "not an answer": drop the question, handle the words as new.
#       changes: fields newly filled by this answer (the app saves them as an edit).
#
# A field: {"type": date|time|recurrence|duration|yesno|person|choice|text,
#           "kind": required|default|extra|optional, "words": [...], "only_if": field,
#           "offer": "an alert", "readback": "alert {say}"}   (offer/readback optional)

import datetime as dt

import fields as F

# how each type of field is read back ("due Tuesday", "at 7 pm"): vocab/language.yaml readback
READBACK = {str(k): str(v) for k, v in (F.LANG.get("readback") or {}).items()}


def offer_name(name, f):
    return f.get("offer") or name.replace("_", " ")


def open_extras(fields, filled):
    """Extras not filled yet whose only_if is met, in the map's order."""
    return [n for n, f in fields.items()
            if f.get("kind") == "extra" and n not in filled
            and (not f.get("only_if") or f["only_if"] in filled)]


def join_or(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + ", or " + items[-1]


def readback(name, fields, filled):
    """'Clean the gutters, due Tuesday at 7 pm, repeats every Tuesday'. A time joins
    the date before it without a comma."""
    text = name[:1].upper() + name[1:]
    for n, f in fields.items():
        if n in filled and f.get("kind") == "extra":
            tmpl = f.get("readback") or READBACK.get(f.get("type"), "{say}")
            part = tmpl.format(**dict(filled[n]))
            text += (" " if f.get("type") == "time" else ", ") + part
    return text


OFFER_MAX = int(F.LANG.get("series_offer_max") or 3)      # vocab/language.yaml: how many she names at once


def _offers(fields, filled, more=()):
    return join_or(([offer_name(n, fields[n]) for n in open_extras(fields, filled)] + list(more))[:OFFER_MAX])


def start(name, noun, fields, filled, say, more=()):
    """Right after the item was created. more: other things she can do with it, offered last
    ("rename it": the app's user rules on the thing just named)."""
    if not open_extras(fields, filled):
        return say("series_added_done", name=name), None
    state = {"kind": "series", "name": name, "noun": noun, "fields": fields, "filled": filled}
    return say("series_added", name=name, noun=noun, offers=_offers(fields, filled, more)), state


def _infer(fields, filled, new, now):
    """A repeat on named days also gives the due date (the next of those days); a time said with
    no day gives today, or tomorrow once that time has passed (Oct 15: "remind me at 4:30")."""
    today = now.date() if isinstance(now, dt.datetime) else now
    for n, v in list(new.items()):
        if fields[n].get("type") == "recurrence" and v.get("days"):
            for dn, df in fields.items():
                if df.get("type") == "date" and dn not in filled and dn not in new:
                    ahead = min((d - today.weekday()) % 7 for d in v["days"])
                    d = today + dt.timedelta(days=ahead)
                    new[dn] = {"date": d.isoformat(), "say": F.say_date(d, today), "inferred": True}
                    break
    for n, v in list(new.items()):
        dn = fields[n].get("only_if")
        if fields[n].get("type") == "time" and dn and (fields.get(dn) or {}).get("type") == "date" \
                and dn not in filled and dn not in new and isinstance(now, dt.datetime):
            passed = (v["hour"], v["minute"]) <= (now.hour, now.minute)
            d = today + dt.timedelta(days=1 if passed else 0)
            new[dn] = {"date": d.isoformat(), "say": F.say_date(d, today), "inferred": True}
    return new


def settle(fields, filled, got, now):
    """What an answer adds, or the opening sentence (an app's add uses it too): a field named with
    no value takes its default ("nag me"), a repeat on named days or a time alone gives the date,
    and only values whose only_if is met stay."""
    vals = dict(got["values"])
    for n in got["named"]:
        if n not in vals and fields[n].get("default"):
            d = F.parse_answer(fields[n]["default"], {n: fields[n]}, now)["values"].get(n)
            if d:
                vals[n] = d
    new = _infer(fields, filled, vals, now)
    for _ in range(len(new)):
        for n in list(new):
            dep = fields[n].get("only_if")
            if dep and dep not in filled and dep not in new:
                del new[n]
    return new


def answer(state, text, now, say, stop_words=(), people=None, choices=None):
    fields, filled = state["fields"], dict(state["filled"])
    # open extras, and the date and time even when set: a day said to "anything else?" moves it
    # ("Remind me on Saturday at three", Oct 21: it was taken as a new chore)
    extras = {n: f for n, f in fields.items() if f.get("kind") == "extra"
              and (n not in filled or f.get("type") in ("date", "time"))}
    got = F.parse_answer(text, extras, now, people=people, choices=choices)

    words = " ".join(F.words_of(text))
    stops = (" ".join(F.words_of(w)) for w in stop_words)
    if not got["values"] and (got["no"] or any(words == s or words.startswith(s + " ") for s in stops)):
        return say("series_done"), None, {}

    # words that aren't about the offered fields, with no yes and no field named:
    # this isn't an answer ("what's the weather tomorrow"), so the question is dropped
    if got["left"] and not got["yes"] and not got["named"]:
        return None, None, {}

    new = settle(fields, filled, got, now)

    if new:
        filled.update(new)
        line = say("series_readback", item=readback(state["name"], fields, filled))
        if open_extras(fields, filled):
            line += " " + say("series_more", offers=_offers(fields, filled))
            return line, dict(state, filled=filled), new
        return line, None, new

    offers = _offers(fields, filled)
    if got["yes"] and not got["left"] and not got["named"]:
        return say("series_bare_yes", offers=offers), state, {}
    if got["yes"] or got["named"]:
        return say("series_reoffer", offers=offers), state, {}
    return None, None, {}      # not an answer: the question is dropped
