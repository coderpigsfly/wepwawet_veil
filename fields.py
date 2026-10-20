# fields.py - generic field types for adding things through any app (the follow-up series).
# The router owns how each KIND of information is understood; connectors only say which
# fields an app has and what type each one is. Nothing app-specific lives here.
#
# Types: date, time, recurrence, duration, yesno, person, choice, text
#
#   parse_answer(text, fields, now, people=None, choices=None)
#     fields: {name: {"type": ..., "words": [words that name the field]}}, in offer order
#     -> {"values": {field: value}, "named": [fields named], "left": [words not understood],
#         "yes": bool, "no": bool}
#
# Each value is a dict with "say" (how she reads it back) plus type-specific keys.
# Pure functions: no files, no network, no clock (now is passed in), so tests are exact.

import datetime as dt
import os
import re

import yaml

# The language words live in vocab/language.yaml (no word lists in the code).
LANGUAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab", "language.yaml")
with open(LANGUAGE_FILE) as _f:
    LANG = yaml.safe_load(_f) or {}

WEEKDAYS = [str(w) for w in LANG["weekdays"]]
MONTHS = [str(m) for m in LANG["months"]]
UNITS = {str(k): str(v) for k, v in LANG["units"].items()}
MINUTES = {str(k): int(v) for k, v in LANG["unit_minutes"].items()}
FRACTIONS = {str(k): float(v) for k, v in (LANG.get("fractions") or {}).items()}
ONES = {str(k): int(v) for k, v in LANG["ones"].items()}
TENS = {str(k): int(v) for k, v in LANG["tens"].items()}
ORDS = {str(k): int(v) for k, v in LANG["ordinals"].items()}
BARE_HOURS_PM = {int(h) for h in LANG["bare_hours_pm"]}
PARTS_OF_DAY = tuple(str(w) for w in LANG["parts_of_day"])
PART_TIMES = {str(k): str(v) for k, v in (LANG.get("part_times") or {}).items()}   # a part said alone sets its time
BEFORE_WORDS = tuple(str(w) for w in LANG["before_words"])
AFTER_WORDS = tuple(str(w) for w in LANG["after_words"])
DATE_LEAD = tuple(str(w) for w in LANG["date_lead"])
YES = {str(w) for w in LANG["yes"]}
NO = {str(w) for w in LANG["no"]}
GLUE = {str(w) for w in LANG["glue"]} | YES | NO       # words that carry nothing of their own
REPEAT_WORDS = {str(k): str(v) for k, v in LANG["repeat_words"].items()}   # daily -> day
EVERY_WORDS = tuple(str(w) for w in LANG["every_words"])
NOON_WORDS = tuple(str(w) for w in LANG["noon_words"])


# ---------- words ----------

def words_of(text):
    """Lowercase words with number words turned into digits ('seven thirty' -> '7 30',
    'twenty first' -> '21st'), 'p.m.' -> 'pm', '7:30' kept whole."""
    t = text.lower().replace("’", "'")
    t = re.sub(r"\b([ap])\.\s?m\b\.?", r"\1m", t)                 # p.m. / a.m.
    t = re.sub(r"(\d)\s*([ap])\s?m\b", r"\1 \2m", t)              # 7pm, 7 p m
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1th", t)                # 1st -> 1th (one form)
    t = re.sub(r"[^a-z0-9:' ]+", " ", t)
    raw, out, i = t.split(), [], 0
    while i < len(raw):
        w = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if w in TENS and nxt in ORDS and ORDS[nxt] < 10:
            out.append(f"{TENS[w] + ORDS[nxt]}th"); i += 2; continue
        if w in TENS and nxt in ONES and ONES[nxt] < 10:
            out.append(str(TENS[w] + ONES[nxt])); i += 2; continue
        if w in ORDS:
            out.append(f"{ORDS[w]}th")
        elif w in ONES:
            out.append(str(ONES[w]))
        elif w in TENS:
            out.append(str(TENS[w]))
        elif w in NOON_WORDS:
            out.append("noon")
        else:
            out.append(w)
        i += 1
    return out


def is_num(w):
    return w.isdigit()


class Words:
    """The answer's words, with the ones already understood marked as used."""

    def __init__(self, text):
        self.w = words_of(text)
        self.used = [False] * len(self.w)

    def free(self, i):
        return 0 <= i < len(self.w) and not self.used[i]

    def get(self, i):
        return self.w[i] if self.free(i) else None

    def take(self, i, j):
        for k in range(i, j):
            self.used[k] = True

    def left(self):
        return [w for w, u in zip(self.w, self.used) if not u]


# ---------- recurrence ----------

def _days_list(W, i):
    """Weekday names from i on, joined by 'and' or commas: (days, next index)."""
    days, j = [], i
    while W.free(j):
        w = W.w[j].rstrip("s") if W.w[j].endswith("days") else W.w[j]
        if w in WEEKDAYS:
            days.append(WEEKDAYS.index(w)); j += 1
            if W.get(j) == "and" and W.get(j + 1) and (W.w[j + 1].rstrip("s") in WEEKDAYS):
                j += 1
            continue
        break
    return days, j


def _say_days(days):
    names = [WEEKDAYS[d].title() for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def parse_recurrence(W):
    n = len(W.w)
    for i in range(n):
        w = W.get(i)
        if w is None:
            continue
        nxt, nxt2 = W.get(i + 1), W.get(i + 2)
        if w in REPEAT_WORDS:
            unit = REPEAT_WORDS[w]
            W.take(i, i + 1); return {"every": 1, "unit": unit, "days": [], "say": f"every {unit}"}
        if w in ("weekdays",) and (i == 0 or W.w[i - 1] in ("every", "on", "repeat", "repeats")):
            W.take(i, i + 1)
            return {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4], "say": "every weekday"}
        if w == "once" and nxt == "a" and nxt2 in ("day", "week", "month", "year"):
            W.take(i, i + 3)
            return {"every": 1, "unit": nxt2, "days": [], "say": f"every {nxt2}"}
        if w in EVERY_WORDS:
            if nxt in ("day", "morning", "evening", "night"):
                W.take(i, i + 2); return {"every": 1, "unit": "day", "days": [], "say": "every day"}
            if nxt in ("week", "month", "year"):
                W.take(i, i + 2)
                return {"every": 1, "unit": nxt, "days": [], "say": f"every {nxt}"}
            if nxt in ("weekday", "weekdays") or (nxt == "week" and nxt2 == "day"):
                W.take(i, i + (3 if nxt2 == "day" else 2))
                return {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4], "say": "every weekday"}
            if nxt in ("weekend", "weekends"):
                W.take(i, i + 2)
                return {"every": 1, "unit": "week", "days": [5, 6], "say": "every weekend"}
            if nxt == "other" and nxt2 in ("day", "week", "month", "year"):
                W.take(i, i + 3)
                return {"every": 2, "unit": nxt2, "days": [], "say": f"every other {nxt2}"}
            if nxt and is_num(nxt) and nxt2 in UNITS and UNITS[nxt2] in ("day", "week", "month", "year"):
                W.take(i, i + 3)
                u = UNITS[nxt2]
                return {"every": int(nxt), "unit": u, "days": [], "say": f"every {nxt} {u}s"}
            days, j = _days_list(W, i + 1)
            if days:
                W.take(i, j)
                return {"every": 1, "unit": "week", "days": days, "say": "every " + _say_days(days)}
        # "on tuesdays", "tuesdays and thursdays": a plural weekday means a repeat
        if w.endswith("days") and w[:-1] in WEEKDAYS:
            start = i - 1 if i > 0 and W.get(i - 1) == "on" else i
            days, j = _days_list(W, i)
            W.take(start, j)
            return {"every": 1, "unit": "week", "days": days, "say": "every " + _say_days(days)}
    return None


# ---------- duration ----------

def parse_duration(W):
    """'an hour before', '30 minutes', 'half an hour', 'every half hour', 'a quarter of an hour',
    'an hour and a half', '2 days ahead'."""
    n = len(W.w)
    for i in range(n):
        w = W.get(i)
        if w is None:
            continue
        span, minutes = None, None
        k = i + 1 if w in ("every", "a") else i           # "every half hour", "a quarter hour"
        if W.get(k) in FRACTIONS:
            j = k + 1 + (W.get(k + 1) == "of")                 # "quarter of an hour"
            j += W.get(j) in ("a", "an")                      # "half an hour", "half a day"
            if W.get(j) in UNITS and UNITS[W.get(j)] in MINUTES:
                span, minutes = (i, j + 1), round(FRACTIONS[W.get(k)] * MINUTES[UNITS[W.get(j)]])
        elif w == "every" and W.get(i + 1) in UNITS and UNITS[W.get(i + 1)] in MINUTES:
            span, minutes = (i, i + 2), MINUTES[UNITS[W.get(i + 1)]]      # "every hour"
        elif (w in ("a", "an") or is_num(w)) and W.get(i + 1) in UNITS \
                and UNITS[W.get(i + 1)] in MINUTES:
            unit = UNITS[W.get(i + 1)]
            count = 1 if w in ("a", "an") else int(w)
            span, minutes = (i, i + 2), count * MINUTES[unit]
            # "an hour and a half"
            if W.get(i + 2) == "and" and W.get(i + 3) == "a" and W.get(i + 4) == "half":
                span, minutes = (i, i + 5), minutes + MINUTES[unit] // 2
        if span:
            j, way = span[1], None
            if W.get(j) in BEFORE_WORDS:
                j, way = j + 1, "before"
            elif W.get(j) in AFTER_WORDS:
                j, way = j + 1, "after"
            if way and W.get(j) in ("to", "it's", "its", "the"):
                j += 1
            if way and W.get(j) in ("due", "it"):
                j += 1
            W.take(span[0], j)
            base = say_minutes(minutes)
            return {"minutes": minutes, "base": base, "way": way,
                    "say": base + " " + (way or "before")}
    return None


def say_minutes(m):
    for unit, size in (("week", 10080), ("day", 1440), ("hour", 60)):
        if m % size == 0 and m >= size:
            k = m // size
            return f"{'an' if unit == 'hour' and k == 1 else 'a' if k == 1 else k} {unit}{'s' if k > 1 else ''}"
    if m == 90:
        return "an hour and a half"
    if m == 30:
        return "half an hour"
    return f"{m} minutes"


# ---------- time ----------

def _hour24(h, ampm, part):
    if ampm == "am":
        return 0 if h == 12 else h
    if ampm == "pm" or (part in PARTS_OF_DAY and part != PARTS_OF_DAY[0]):
        return h if h == 12 else h + 12
    if part == PARTS_OF_DAY[0]:
        return 0 if h == 12 else h
    return h + 12 if h in BARE_HOURS_PM else h


def say_time(h, m):
    if (h, m) == (12, 0):
        return "noon"
    if (h, m) == (0, 0):
        return "midnight"
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def _part_of_day(W):
    """'in the morning', 'this evening', 'tonight' anywhere in the answer."""
    for i, w in enumerate(W.w):
        if w in PARTS_OF_DAY:
            return w, i
    return None, None


def parse_time(W):
    n = len(W.w)
    part, part_i = _part_of_day(W)
    for i in range(n):
        w = W.get(i)
        if w is None:
            continue
        if w == "noon":
            W.take(i - 1 if W.get(i - 1) == "at" else i, i + 1)
            return {"hour": 12, "minute": 0, "say": "noon"}
        if w == "midnight":
            W.take(i - 1 if W.get(i - 1) == "at" else i, i + 1)
            return {"hour": 0, "minute": 0, "say": "midnight"}
        h = m = None
        j = i
        if re.fullmatch(r"\d{1,2}:\d{2}", w):
            h, m = map(int, w.split(":")); j = i + 1
        elif is_num(w) and 1 <= int(w) <= 12:
            nxt = W.get(i + 1)
            if nxt and is_num(nxt) and len(nxt) == 2 and int(nxt) < 60:      # "7 30"
                h, m, j = int(w), int(nxt), i + 2
            elif nxt and re.fullmatch(r"[1-5]", nxt) and W.get(i + 2) and is_num(W.get(i + 2)):
                h, m, j = int(w), int(nxt) * 10 + int(W.get(i + 2)), i + 3    # "7 4 5" (seven forty five, said apart)
            elif nxt in ("am", "pm", "o'clock", "oclock") or W.get(i - 1) == "at" \
                    or (part and part_i is not None and abs(part_i - i) <= 4):
                h, m, j = int(w), 0, i + 1
        elif w in ("quarter", "half") and W.get(i + 1) in ("past", "after", "to") \
                and W.get(i + 2) and is_num(W.get(i + 2)):
            base = int(W.get(i + 2))
            add = 15 if w == "quarter" else 30
            if W.get(i + 1) == "to":
                h, m = (base - 1) or 12, 60 - add
            else:
                h, m = base, add
            j = i + 3
        if h is None or h > 23 or m > 59:
            continue
        ampm = None
        if W.get(j) in ("am", "pm"):
            ampm = W.get(j); j += 1
        elif W.get(j) in ("o'clock", "oclock"):
            j += 1
            if W.get(j) in ("am", "pm"):
                ampm = W.get(j); j += 1
        start = i - 1 if W.get(i - 1) == "at" else i
        h24 = h if h > 12 else _hour24(h, ampm, part)
        W.take(start, j)
        if part_i is not None and W.free(part_i) and part != "tonight":
            # "in the morning" / "this evening" was only telling us am or pm
            k = part_i
            W.take(k, k + 1)
            for back in (1, 2):
                if W.get(k - back) in ("in", "the", "this"):
                    W.take(k - back, k - back + 1)
        return {"hour": h24, "minute": m, "say": say_time(h24, m)}
    if part in PART_TIMES and part_i is not None and W.free(part_i):
        # a part of the day with no time said: its own time (vocab/language.yaml part_times)
        hh, mm = (int(x) for x in PART_TIMES[part].split(":"))
        if part != "tonight":                  # "tonight" is a day as well: left for the date reader
            W.take(part_i, part_i + 1)
            for back in (1, 2):
                if W.get(part_i - back) in ("in", "the", "this"):
                    W.take(part_i - back, part_i - back + 1)
        return {"hour": hh, "minute": mm, "say": say_time(hh, mm)}
    return None


# ---------- date ----------

def say_date(d, today):
    if d == today:
        return "today"
    if d == today + dt.timedelta(days=1):
        return "tomorrow"
    if 0 < (d - today).days < 7:
        return d.strftime("%A")
    from veil import phases
    if phases.on("dump14") and d.year != today.year:      # another year says which ("Sunday, August 15, 2027")
        return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}"


def _date(d, today):
    return {"date": d.isoformat(), "say": say_date(d, today)}


def _month_day(today, month, day):
    year = today.year
    try:
        d = dt.date(year, month, day)
        if d < today:
            d = dt.date(year + 1, month, day)
        return d
    except ValueError:
        return None


def parse_date(W, today):
    n = len(W.w)
    for i in range(n):
        w = W.get(i)
        if w is None:
            continue
        before = i - 1 if W.get(i - 1) in DATE_LEAD else i
        if w in ("today", "tonight"):
            W.take(before, i + 1); return _date(today, today)
        if w == "tomorrow":
            W.take(before, i + 1); return _date(today + dt.timedelta(days=1), today)
        if w == "day" and W.get(i + 1) == "after" and W.get(i + 2) == "tomorrow":
            start = i - 1 if W.get(i - 1) == "the" else i
            W.take(start, i + 3); return _date(today + dt.timedelta(days=2), today)
        if w == "in" and W.get(i + 1) and (is_num(W.get(i + 1)) or W.get(i + 1) in ("a", "an")) \
                and W.get(i + 2) in UNITS and UNITS[W.get(i + 2)] in ("day", "week"):
            k = 1 if W.get(i + 1) in ("a", "an") else int(W.get(i + 1))
            days = k * (7 if UNITS[W.get(i + 2)] == "week" else 1)
            W.take(i, i + 3); return _date(today + dt.timedelta(days=days), today)
        if w in ("this", "next") and W.get(i + 1) in WEEKDAYS:
            continue      # handled when the weekday itself is reached
        if w in WEEKDAYS:
            start = before
            if W.get(i - 1) in ("this", "next"):
                start = i - 1
                if W.get(i - 2) in DATE_LEAD:
                    start = i - 2
            ahead = (WEEKDAYS.index(w) - today.weekday()) % 7
            W.take(start, i + 1); return _date(today + dt.timedelta(days=ahead), today)
        if w in MONTHS:
            nxt = W.get(i + 1)
            m = MONTHS.index(w) + 1
            if nxt and re.fullmatch(r"\d{1,2}(th)?", nxt):                 # october 14 / 14th
                d = _month_day(today, m, int(nxt.rstrip("th")))
                if d:
                    W.take(before, i + 2); return _date(d, today)
        if re.fullmatch(r"\d{1,2}th", w):                                  # the 14th (of october)
            day = int(w[:-2])
            start = i - 1 if W.get(i - 1) == "the" else i
            if W.get(start - 1) in DATE_LEAD:
                start -= 1
            if W.get(i + 1) == "of" and W.get(i + 2) in MONTHS:
                d = _month_day(today, MONTHS.index(W.get(i + 2)) + 1, day)
                if d:
                    W.take(start, i + 3); return _date(d, today)
            if W.get(i + 1) in MONTHS:
                d = _month_day(today, MONTHS.index(W.get(i + 1)) + 1, day)
                if d:
                    W.take(start, i + 2); return _date(d, today)
            month, year = today.month, today.year
            if day < today.day:
                month, year = (1, year + 1) if month == 12 else (month + 1, year)
            try:
                d = dt.date(year, month, day)
            except ValueError:
                continue
            W.take(start, i + 1); return _date(d, today)
    return None


# ---------- person, choice, yes/no ----------

def parse_person(W, people):
    """people: {spoken name: canonical}. 'for Beth', 'assign it to Beth'."""
    for i, w in enumerate(W.w):
        if W.free(i) and w in (people or {}):
            if w in PRONOUNS and W.get(i - 1) not in ("for", "to"):
                continue          # "alert me", "nag me": not an assignment; "for me" is
            start = i - 1 if W.get(i - 1) in ("for", "to") else i
            W.take(start, i + 1)
            return {"person": people[w], "say": people[w]}
    return None


def parse_choice(W, options):
    """options: names (e.g. Donetick's projects). All of an option's words must be heard."""
    best = None
    for opt in options or []:
        ow = words_of(opt)
        if not ow:
            continue
        for i in range(len(W.w) - len(ow) + 1):
            if all(W.free(i + k) and W.w[i + k] == ow[k] for k in range(len(ow))):
                if not best or len(ow) > len(best[1]):
                    best = (i, ow, opt)
    if best:
        i, ow, opt = best
        W.take(i, i + len(ow))
        return {"choice": opt, "say": opt}
    return None


def _named(W, words):
    """Indexes where any of a field's naming words appear (multi-word allowed)."""
    hits = []
    for phrase in words or []:
        pw = words_of(phrase)
        for i in range(len(W.w) - len(pw) + 1):
            if W.w[i:i + len(pw)] == pw:
                hits.append((i, len(pw)))
    return hits


NEGATE = {str(w) for w in LANG["negate"]}
PRONOUNS = {str(w) for w in LANG["pronouns"]}


# ---------- the whole answer ----------

def parse_answer(text, fields, now, people=None, choices=None):
    """Which of the offered fields this answer fills. Order matters: the most specific
    types are read first, so 'every Tuesday at 7 pm' isn't also taken as a date."""
    today = now.date() if isinstance(now, dt.datetime) else now
    W = Words(text)
    first = next((w for w in W.w if w not in ("um", "uh", "well", "oh")), "")
    out = {"values": {}, "named": [], "left": [], "yes": first in YES, "no": first in NO}

    # which fields were named ("alert", "nag", "due date"), before values are taken
    named_at = {}
    for name, f in fields.items():
        hits = _named(W, f.get("words"))
        if hits:
            named_at[name] = hits
            out["named"].append(name)

    # the naming words themselves are understood, and carry no value of their own
    for hits in named_at.values():
        for i, ln in hits:
            W.take(i, i + ln)

    def open_of(kind):
        return [n for n, f in fields.items() if f.get("type") == kind and n not in out["values"]]

    def place(kind, value):
        cands = open_of(kind)
        if kind == "duration":
            # a field can say which way it counts (direction: before | after); a duration
            # said with "after" only fits an after field, and "before" (or neither) a before one
            way = value.get("way")
            fit = [c for c in cands if (fields[c].get("direction") or "before") == (way or "before")]
            if way is None:
                named_any = [c for c in cands if c in named_at]
                fit = named_any or fit or cands
            cands = fit
            if cands:
                d = fields[cands[0]].get("direction") or "before"
                value = dict(value, way=d, say=value["base"] + " " + d)
        if not cands:
            return
        # prefer a field of this type that was named; else the first one offered
        named = [c for c in cands if c in named_at]
        out["values"][(named or cands)[0]] = value

    readers = [("recurrence", lambda: parse_recurrence(W)),
               ("date", lambda: _in_n_days(W, today)),
               ("duration", lambda: parse_duration(W)),
               ("time", lambda: parse_time(W)),
               ("date", lambda: parse_date(W, today)),
               ("person", lambda: parse_person(W, people)),
               ("choice", lambda: parse_choice(W, choices))]
    for kind, read in readers:
        while open_of(kind):
            v = read()
            if not v:
                break
            place(kind, v)

    # yes/no fields: named means yes, unless negated just before ("no nag", "don't nag me")
    for name, f in fields.items():
        if f.get("type") == "yesno" and name in named_at and name not in out["values"]:
            i, ln = named_at[name][0]
            neg = any(W.w[k] in NEGATE for k in range(max(0, i - 2), i))
            out["values"][name] = {"value": not neg, "say": ("no " if neg else "") + name.replace("_", " ")}

    out["rest"] = W.left()          # unused words in order (an item's name comes from these)
    out["left"] = [w for w in W.left() if w not in GLUE and w not in NEGATE]
    return out


def _in_n_days(W, today):
    """'in 3 days' as a date, read before durations so it isn't taken as '3 days before'."""
    for i in range(len(W.w)):
        if W.get(i) == "in" and W.get(i + 1) and (is_num(W.get(i + 1)) or W.get(i + 1) in ("a", "an")) \
                and W.get(i + 2) in UNITS and UNITS[W.get(i + 2)] in ("day", "week"):
            k = 1 if W.get(i + 1) in ("a", "an") else int(W.get(i + 1))
            days = k * (7 if UNITS[W.get(i + 2)] == "week" else 1)
            W.take(i, i + 3)
            return _date(today + dt.timedelta(days=days), today)
    return None
