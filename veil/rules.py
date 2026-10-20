# veil/rules.py - user rules: an app's own commands chained with the router's generic steps,
# built on the app's User rules tab and kept in connectors/<name>.yaml (rules:). Nothing here knows
# any one app: a rule names the app's commands, and each generic step takes its own parameters.
#
#   rules:
#     rename:
#       words: [rename]
#       steps:
#         - call: GET /chores                       # an app command; a list it answers is what Search reads
#         - search: {until: [to]}                   # what was said, up to "to", scored against the list
#         - match: {act: 85, ask: 45}               # sure, check first, or not found
#         - confirm: {}                             # "I believe I heard you say ...": yes goes on, no stops
#         - ask: {need: new_name, after: [to]}      # the words after "to", else she asks
#         - fresh_copy: {read: "GET /chores/{id}", set: {name: new_name}}
#         - call: PUT /chores                       # sends the copy
#         - say: {line: "Done. {item} is now {new_name}."}
#
# A rule waits on a question (confirm, which one, ask) as a pending question of kind "rule"; the
# answer resumes it at the next step (resume()). What it keeps between turns (state) is small:
# what was said, the step it's at, the values heard, the item picked and the few candidates.

import logging
import os
import random
import re

from veil import config, match, phases

log = logging.getLogger("router")

# The generic steps, as the builder shows them: what each does (the hover) and its parameters.
# A parameter: {name, kind (number, words, lines, text, choice, command, fields, yesno), default, about}.
STEPS = {
    "call": {"title": "Call a command", "about": "Calls one of the app's own commands. A list it answers is what "
             "Search reads; a path id ({id}) is the item Match picked; a body is the copy Fresh copy made, "
             "or the values heard with the same names as the fields the command requires.",
             "params": [{"name": "command", "kind": "command", "about": "the app command it calls"}]},
    "search": {"title": "Search", "about": "Scores every item of the list the last command answered against what "
               "was said: the words said, without the rule's own words, up to the first of the Until words.",
               "params": [{"name": "field", "kind": "text", "default": "name", "about": "the item's field to compare (its name)"},
                          {"name": "group", "kind": "text", "default": "", "about": "the item's field that groups it, named when it asks which (a project)"},
                          {"name": "until", "kind": "words", "default": [], "about": "the words where the item's name ends (\"to\" in rename X to Y)"},
                          {"name": "ignore", "kind": "words", "default": [], "about": "words that are never part of the name (\"project\" in the house project)"},
                          {"name": "last", "kind": "yesno", "default": False, "about": "\"that\" or \"it\" means the item it last named here (the one it read back)"},
                          {"name": "on_last", "kind": "words", "default": [], "about": "openings that mean the item it last named, what follows being the rest (\"call it ...\", \"it should be ...\"; with Last)"}]},
    "match": {"title": "Match", "about": "Picks from what Search found. At or above Act it's the item; between Ask and Act "
              "it's the item if you say yes (the next Confirm asks); below Ask it says it didn't find it.",
              "params": [{"name": "act", "kind": "number", "default": 85, "about": "% match to act on the item"},
                         {"name": "ask", "kind": "number", "default": 45, "about": "% match to ask about it first"},
                         {"name": "ties", "kind": "choice", "choices": ["ask", "first"], "default": "ask",
                          "about": "two items fit equally: ask which, or take the first"},
                         {"name": "clear", "kind": "number", "default": 20,
                          "about": "% the best of several names holding every word said must lead the next by, to be taken without asking which"},
                         {"name": "extra_words", "kind": "choice", "choices": ["ask", "ignore"], "default": "ask",
                          "about": "a word you said that the item lacks: ask first even above Act, or ignore it"},
                         {"name": "not_found", "kind": "text", "default": "", "about": "what it says below Ask (empty: its own line)"}]},
    "confirm": {"title": "Confirm", "about": "\"I believe I heard you say ...\", then waits for yes or no: yes goes on "
                "with the rule, no stops it with the No line. Asks only when Match wasn't sure, unless Always.",
                "params": [{"name": "always", "kind": "yesno", "default": False, "about": "ask even when Match was sure"},
                           {"name": "question", "kind": "text", "default": "", "about": "its question, {item} for the item (empty: its own line)"},
                           {"name": "no", "kind": "text", "default": "", "about": "what it says on no (empty: its own line)"}]},
    "ask": {"title": "Ask", "about": "A detail the rule needs (the new name): the words said after one of the After "
            "words, else it asks and your answer is the value. Later steps use it by its name.",
            "params": [{"name": "need", "kind": "text", "default": "", "about": "the value's name (new_name)"},
                       {"name": "after", "kind": "words", "default": [], "about": "words after which it was said (\"to\")"},
                       {"name": "question", "kind": "text", "default": "", "about": "its question (empty: its own line)"}]},
    "fresh_copy": {"title": "Fresh copy", "about": "Reads the item as it is now and keeps a copy with the changes, for "
                   "an app whose change command wants the whole item back (and its current values, like updatedAt). "
                   "The next Call sends it.",
                   "params": [{"name": "read", "kind": "command", "about": "the command that reads one item ({id}), or the list it's in"},
                              {"name": "set", "kind": "fields", "default": {}, "about": "field: the value heard that goes in it"},
                              {"name": "fill_empty", "kind": "fields", "default": {}, "about": "field: what goes in it when it's empty"}]},
    "who_spoke": {"title": "Who spoke (Name Sparkle)", "about": "Who is speaking, in {speaker}, weighed by Oread's score: "
                  "at or above Sure it's their name; between Hedge and Sure it says it thinks so (a Hedge line); below "
                  "Hedge, or with Oread not sure, a polite way out (an Unsure line) and the rule stops: never a name.",
                  "params": [{"name": "sure", "kind": "number", "default": 70, "about": "% of Oread's score to say who it is"},
                             {"name": "hedge", "kind": "number", "default": 60, "about": "% to say it thinks so (below it: a way out)"},
                             {"name": "name", "kind": "choice", "choices": ["own", "nickname"], "default": "own",
                              "about": "their own name (the voice ID's), or one of Name Sparkle's nicknames"},
                             {"name": "hedge_lines", "kind": "lines", "default": [], "about": "between Hedge and Sure: {speaker} for who it thinks (empty: its own lines)"},
                             {"name": "unsure", "kind": "lines", "default": [], "about": "the polite ways out (empty: its own lines)"}]},
    "filter": {"title": "Filter", "about": "Keeps only the things of the last list whose field has the value "
               "(holy_day_of_obligation: true): the rest are left out for the steps after.",
               "params": [{"name": "field", "kind": "text", "default": "", "about": "the things' field to look at"},
                          {"name": "value", "kind": "text", "default": "true", "about": "the value it must have (true, a word, a number)"}]},
    "by_date": {"title": "By date", "about": "Picks from the last list by its date, things in date order ('when' looks forward): "
                "the next (the first from today on), or those on the day said (today, tomorrow, Saturday, a date); "
                "several on that day are read as a list.",
                "params": [{"name": "which", "kind": "choice", "choices": ["next", "day said"], "default": "next",
                            "about": "the next one, or the day said"},
                           {"name": "field", "kind": "text", "default": "",
                            "about": "the things' date field (empty: the first field every one has as a date)"},
                           {"name": "not_found", "kind": "text", "default": "",
                            "about": "what it says when none is next or none is on that day ({day}; empty: its own line)"}]},
    "response": {"title": "Response", "about": "What it says when the rule is done, one of its lines each time (its flair "
                 "added): {item} is the item, {speaker} who spoke, and any value by its name; a date field's "
                 "{name_days} is the days from today to it (\"Easter is {date_days} days away\").",
                 "params": [{"name": "lines", "kind": "lines", "default": [], "about": "the lines it may say (empty: its own line)"},
                            {"name": "fields", "kind": "fields", "default": {},
                             "about": "name: one of the matched item's own fields, said as {name} (due: nextDueDate); a date is said as a day and time"},
                            {"name": "empty_lines", "kind": "lines", "default": [],
                             "about": "said instead when one of those fields is empty (\"{item} has no due date.\")"},
                            {"name": "list", "kind": "yesno", "default": False,
                             "about": "read the last Call's list out ({items} in its lines, the rest offered after a few, like any list); empty: its empty lines"},
                            {"name": "line", "kind": "text", "default": "",
                             "about": "with List: each thing read as this line of its own fields (\"{year}: {title}\"); empty: its name"},
                            {"name": "read_max", "kind": "number", "default": 0,
                             "about": "with List: how many she reads before \"Want to hear the rest?\" (0: the router's read_list_max)"},
                            {"name": "one", "kind": "choice", "choices": ["no", "random"], "default": "no",
                             "about": "say one thing of the last Call's list, at random, its fields by name in the lines (\"In {year}, {title}.\")"},
                            {"name": "past_lines", "kind": "lines", "default": [],
                             "about": "said instead when one of those fields is a date already gone (\"{item} was due {due}.\")"}]},
}
ALIASES = {"say": "response"}       # older names a saved rule may use


def _lang():
    path = config.path("vocab", "language.yaml")
    return config.load_yaml(path) if os.path.exists(path) else {}


def this_words():
    """Words that point at the item she last named ("rename that", "rename it"): vocab/language.yaml."""
    return {str(w).lower() for w in _lang().get("this_words") or []}


def this_phrases():
    """Phrases that point at it too ("the one you just added"): vocab/language.yaml, longest first."""
    return sorted({" ".join(str(w).lower().split()) for w in _lang().get("this_phrases") or []}, key=len, reverse=True)


def without_correction(said):
    """What was said without a correction opening it ("No, rename it to ...", "That's wrong. It should
    be ..."): vocab/language.yaml correction_openers. Unchanged when nothing follows the opener."""
    text = (said or "").strip()
    low = text.lower().replace("\u2019", "'")
    for w in sorted((str(x).lower() for x in _lang().get("correction_openers") or []), key=len, reverse=True):
        m = re.match(re.escape(w) + r"\b[\s,.!;:]*", low)
        if m and text[m.end():].strip():
            return text[m.end():].strip()
    return text


def _tokens(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower().replace("\u2019", "'"))


def points_back(before, drop):
    """Do these words (the item's part of what was said) point at the item she last named: only
    this_words ("that", "it") or one of this_phrases ("the one you just added"), and nothing else?"""
    text, hit = " " + " ".join(before) + " ", False
    for ph in this_phrases():
        if " " + ph + " " in text:
            text, hit = text.replace(" " + ph + " ", " "), True
    rest = [w for w in text.split() if w not in drop or w in this_words()]
    return (hit and set(rest) <= this_words()) or (bool(rest) and set(rest) <= this_words())


def on_last_opening(rule, said):
    """(the opening, the words after it) when what was said opens with one of the rule's Search
    on_last phrases ("call it buy single hole faucet"), else None."""
    search = next((p for k, p in map(kind_of, (rule or {}).get("steps") or []) if k == "search"), None)
    if not search or not param("search", search, "last"):
        return None
    toks = _tokens(without_correction(said))
    for w in sorted((" ".join(_tokens(x)) for x in param("search", search, "on_last") or []), key=len, reverse=True):
        n = len(w.split())
        if w and toks[:n] == w.split():
            return w, toks[n:]
    return None


def about_last(rule, said, drop):
    """Does what was said mean the rule on the item she last named (its Search has Last): an on_last
    opening, or the item's part pointing back ("rename that to ...")?"""
    search = next((p for k, p in map(kind_of, (rule or {}).get("steps") or []) if k == "search"), None)
    if not search or not param("search", search, "last"):
        return False
    if on_last_opening(rule, said):
        return True
    return any(points_back(before, drop) for before, _, _ in
               splits(without_correction(said), rule.get("words") or [], param("search", search, "until") or []))


def kind_of(step):
    """('call', {command}) or (a generic step, its parameters) for one step as saved."""
    if not isinstance(step, dict) or len(step) != 1:
        return None, {}
    name, params = next(iter(step.items()))
    if name == "call":
        return "call", {"command": " ".join(str(params or "").split())}
    params = dict(params or {})
    if name == "say":           # Say became Response (Oct 16): its one line is one of the lines
        params = {"lines": [params["line"]] if params.get("line") else []}
    if name == "who_spoke" and isinstance(params.get("unsure"), str):     # one line before Oct 16, evening
        params["unsure"] = [params["unsure"]] if params["unsure"] else []
    return ALIASES.get(name, name), params


def param(name, params, key):
    """A step's parameter, else its default."""
    if key in params and params[key] not in (None, ""):
        return params[key]
    for p in STEPS.get(name, {}).get("params") or []:
        if p["name"] == key:
            return p.get("default")
    return None


def says_day(rule):
    """Does one of the rule's Responses say the day said ({day_said})? Then the rule is about a day named."""
    return any("{day_said}" in str(x) for k, p in map(kind_of, (rule or {}).get("steps") or []) if k == "response"
               for x in list(param("response", p, "lines") or []) + list(param("response", p, "empty_lines") or []))


def first_change(rule):
    """The command a rule changes something with (the first call that isn't a GET), else its first call:
    so the router knows whether the rule changes anything."""
    calls = [kind_of(s)[1].get("command", "") for s in (rule or {}).get("steps") or [] if kind_of(s)[0] == "call"]
    return next((c for c in calls if not c.upper().startswith("GET ")), calls[0] if calls else "")


def check(rule, commands=None):
    """What's wrong with a rule, as a sentence, or None. commands: the app's commands, when read."""
    steps = (rule or {}).get("steps") or []
    if not steps:
        return "it has no steps"
    for i, s in enumerate(steps, 1):
        name, params = kind_of(s)
        if name is None or (name != "call" and name not in STEPS):
            return f"step {i} isn't a step the router knows"
        if name == "call" and not re.fullmatch(r"(GET|POST|PUT|PATCH|DELETE) /\S*", params["command"], re.I):
            return f"step {i}: pick the command it calls"
        if name == "call" and commands is not None and params["command"].upper() not in commands:
            return f"step {i}: {params['command']} isn't one of the app's commands (Commands tab)"
        if name != "call":
            known = {p["name"] for p in STEPS[name]["params"]}
            odd = [k for k in params if k not in known]
            if odd:
                return f"step {i}: {STEPS[name]['title']} has no setting {', '.join(odd)} (the helper changed?)"
            for p in STEPS[name]["params"]:
                if p["kind"] == "command" and params.get(p["name"]) and commands is not None \
                        and str(params[p["name"]]).upper() not in commands:
                    return f"step {i}: {params[p['name']]} isn't one of the app's commands (Commands tab)"
        if name == "ask" and not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", str(params.get("need") or "")):
            return f"step {i}: Ask needs the value's name, one word (new_name)"
        if name == "match" and not 0 <= float(param(name, params, "ask")) <= float(param(name, params, "act")) <= 100:
            return f"step {i}: Match's Ask % must be 0 to 100 and no more than its Act %"
        if name == "who_spoke" and not 0 <= float(param(name, params, "hedge")) <= float(param(name, params, "sure")) <= 100:
            return f"step {i}: Who spoke's Hedge % must be 0 to 100 and no more than its Sure %"
    return None


def _fill(line, values):
    """A line with {item} and the values heard filled in; anything unknown left as it was."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), str(line or ""))


def _cut(text, words):
    """Text up to the first of the words (before), and what follows it (after)."""
    toks = re.findall(r"[a-z0-9']+", (text or "").lower())
    for i, w in enumerate(toks):
        if w in words:
            return toks[:i], toks[i + 1:]
    return toks, []


def _named(toks, drop, said=""):
    """Words as a name: the leading filler and lead words gone, its first letter capitalized, and
    each word as it was said (Sal's, not sal's) when it can be found in what was said."""
    while toks and toks[0] in drop:
        toks = toks[1:]
    text = " ".join(toks)
    m = re.search(r"\b" + r"\W+".join(re.escape(t) for t in toks) + r"\b", said or "", re.I) if toks else None
    if m:
        text = m.group(0).strip(" .,!?")
    return text[:1].upper() + text[1:]


def splits(said, rule_words, until):
    """The ways what was said divides into the item and what follows it: the rule's own words taken
    out (once), then cut at each Until word ("rename go to the store to shop": at either "to"), or kept whole.
    [(the item's words, the words after, the Until word)]."""
    text = " " + " ".join(re.findall(r"[a-z0-9']+", (said or "").lower())) + " "
    for w in sorted(rule_words, key=len, reverse=True):       # the first (the rule's opening), once
        if " " + str(w).lower() + " " in text:
            text = text.replace(" " + str(w).lower() + " ", " ", 1)
            break
    toks = text.split()
    until = {str(u).lower() for u in until}
    return [(toks[:i], toks[i + 1:], w) for i, w in enumerate(toks) if w in until] or [(toks, [], None)]


def candidates(text, items, field, group, never, by_sound=False, alike=None, nearby=None):
    """Every item that shares a word with the text, best first: {id, name, group, fields, score, whole,
    exact, alone}. fields: the item's own plain values, for a Response to say. by_sound: the words as
    they sound (the voice map's sound_alike), at least two agreeing; found that way, never sure.
    alike, nearby: the app's own words (veil/match.py); alone: nothing but nearby words was said."""
    things = [{"id": it.get("id"), "name": str(it.get(field) or ""), "group": _group(it.get(group)) if group else None,
               "fields": {k: v for k, v in it.items() if isinstance(v, (str, int, float, bool)) or v is None}}
              for it in items if isinstance(it, dict)]
    if by_sound:
        heard = {match.sound(w) for w in match.words(text, never)} - {""}
        things = [t for t in things if len(heard & ({match.sound(w) for w in match.words(t["name"], never)} - {""})) >= 2]
    only = match.alone(text, never, alike, nearby)
    out = [dict(t, score=round(s, 3), whole=whole and not by_sound, exact=exact and not by_sound, by_sound=by_sound, alone=only)
           for s, whole, exact, t in match.scores(text, things, never, by_sound, alike, nearby)]
    return sorted(out, key=lambda c: -c["score"])


def _plain(v, most=300):
    """Outside text as plain words to say (inbound defense 1, dump4): no markup, links or control
    characters, one line, at most `most` characters; an app's data is spoken, never obeyed."""
    if not isinstance(v, str):
        return v
    if not phases.on("dump4"):
        return v
    t = re.sub(r"<[^>]*>", " ", v)                                  # markup
    t = re.sub(r"(?i)\b(?:https?://|www\.)\S+", " ", t)              # links
    t = re.sub(r"[\x00-\x1f\x7f]", " ", t)                          # control characters
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= most else t[:most].rsplit(" ", 1)[0] + "..."


def unsaid(text, words):
    """The app's text without its not_said words or phrases ("(pictured)"; a * stands for any words,
    "(* pictured)" for "(aftermath pictured)"), when dump12 is on."""
    if not phases.on("dump12") or not words or not isinstance(text, str):
        return text
    for w in sorted(words, key=len, reverse=True):
        pat = re.escape(w).replace(r"\*", r"[^()]*?")
        text = re.sub(r"\s*" + pat + (r"\b" if w[-1:].isalnum() else ""), "", text, flags=re.I)
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


def _when(v):
    """A field's value as a moment (datetime, house time) or a day (date): an ISO date, or a date and
    time; a date and time at exactly midnight UTC is how APIs write a plain day (a feast), so it's that
    day, never the evening before in the house's time. None when it's neither."""
    import datetime as dt
    if not isinstance(v, str) or not re.match(r"\d{4}-\d{2}-\d{2}", v):
        return None
    try:
        if len(v) == 10:
            return dt.date.fromisoformat(v)
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None and d.utcoffset() == dt.timedelta(0) and (d.hour, d.minute, d.second) == (0, 0, 0):
        return d.date()
    return d.astimezone()


def _spoken(v, now=None):
    """A field's value as she says it: a day as a day ("Saturday, August 15"), a date and time as a day
    and time ("Tuesday at 1 pm"), else as it is."""
    import datetime as dt
    import fields as F
    w = _when(v)
    if w is None:
        return str(v)
    today = (now or dt.datetime.now().astimezone()).date()
    if not isinstance(w, dt.datetime):
        return F.say_date(w, today)
    day = F.say_date(w.date(), today)
    return day if (w.hour, w.minute) == (0, 0) else f"{day} at {F.say_time(w.hour, w.minute)}"


def days_until(v, now=None):
    """Days from today to a date field's value (0 today, negative when gone), or None when it isn't one."""
    import datetime as dt
    w = _when(v)
    if w is None:
        return None
    today = (now or dt.datetime.now().astimezone()).date()
    return ((w.date() if isinstance(w, dt.datetime) else w) - today).days


def _gone(v, now=None):
    """Is this value already past: a day before today, a date and time before now?"""
    import datetime as dt
    w = _when(v)
    now = now or dt.datetime.now().astimezone()
    if w is None:
        return False
    return w < now if isinstance(w, dt.datetime) else w < now.date()


def _is(v, want):
    """Does a field's value match the Filter's (true, false, a word, a number)?"""
    w = str(want).strip().lower()
    if isinstance(v, bool) or w in ("true", "false", "yes", "no"):
        return bool(v) == (w in ("true", "yes"))
    return str(v).strip().lower() == w


def date_field(items, field=None):
    """The things' date field: the one given, else the first every one of them has as a date."""
    things = [x for x in items if isinstance(x, dict)]
    if field:
        return field
    return next((k for k in (things[0] if things else {}) if all(_when(x.get(k)) is not None for x in things)), None)


def by_date(items, which, said, field=None, now=None):
    """([the things picked], the day said): "next": the first from today on, in date order; "day said":
    those on the day named in what was said (today, tomorrow, a weekday, a date: fields.py)."""
    import datetime as dt
    import fields as F
    f = date_field(items, field)
    if not f:
        return [], None
    now = now or dt.datetime.now().astimezone()

    def day(x):
        w = _when(x.get(f))
        return w.date() if isinstance(w, dt.datetime) else w
    dated = sorted((x for x in items if isinstance(x, dict) and day(x) is not None), key=day)
    if which == "day said":
        got = F.parse_date(F.Words(said), now.date())
        if not got:
            return [], None
        want = dt.date.fromisoformat(got["date"])
        return [x for x in dated if day(x) == want], got.get("say")
    ahead = [x for x in dated if not _gone(x.get(f), now)]
    return [x for x in ahead if day(x) == day(ahead[0])] if ahead else [], None     # all on the next day: each one's favorite


def upcoming(items, id_field):
    """Each thing once, at its next date from today on, else its last ("it was ..."): the date being the
    first field every one of them has as a date. Things without an id are kept as they are."""
    import datetime as dt
    things = [x for x in items if isinstance(x, dict)]
    field = next((k for k in (things[0] if things else {}) if all(_when(x.get(k)) is not None for x in things)), None)
    if not field:
        return items
    today = dt.datetime.now().astimezone()

    def day(x):
        w = _when(x.get(field))
        return w.date() if isinstance(w, dt.datetime) else w
    best = {}
    for x in sorted(things, key=day):
        key = x.get(id_field)
        if key is None:
            continue
        if key not in best or _gone(best[key].get(field), today):      # the next one, else the latest gone
            best[key] = x
    seen, out = set(), []
    for x in sorted(things, key=day):
        key = x.get(id_field)
        if key is None:
            out.append(x)
        elif key not in seen and best.get(key) is x:
            seen.add(key)
            out.append(x)
    return out


def _group(v):
    return str(v.get("name") or "") if isinstance(v, dict) else (str(v) if v is not None else None)


def _as_list(answer):
    """The list an app answered with: the answer itself, or the list inside a wrapper object (of
    several, the longest list of things: Liturgical calendar's litcal beside its messages)."""
    if isinstance(answer, list):
        return answer
    if isinstance(answer, dict):
        lists = [v for v in answer.values() if isinstance(v, list)]
        things = [v for v in lists if v and all(isinstance(x, dict) for x in v)]
        if len(lists) == 1:
            return lists[0]
        if things:
            return max(things, key=len)
    return None


async def run(conn, name, said, state=None, memory=None):
    """Run the rule from where state says (the start, or the step after her question was answered).
    memory: what she last answered here (last_chore: the item she last named, for "rename that").
    Returns the connector's reply shape; a question carries ask: {kind: rule, ...} to wait on."""
    rule = (conn.rules or {}).get(name) or {}
    steps = rule.get("steps") or []
    st = dict(state or {}, said=(state or {}).get("said") or without_correction(said))
    st.setdefault("at", 0)
    st.setdefault("values", {})
    say = conn.say
    label = name.replace("_", " ")
    listed, body, listed_as = None, st.pop("body", None), None

    gone = getattr(conn, "not_said", None) or []       # the app's words she leaves out (dump12)
    plain = lambda x: unsaid(_plain(x), gone)  # noqa: E731

    def values():
        v = dict(st["values"])
        if st.get("item"):
            v["item"] = plain(st["item"]["name"])
        return v

    def wait(mode, speech, **more):
        log.info("  rule %s, step %d: asks (%s)", name, st["at"] + 1, mode)
        keep = {k: st[k] for k in ("said", "at", "values", "item", "unsure", "rest", "remember", "named", "field") if k in st}
        return {"status": "answered", "speech": speech,
                "ask": dict({"kind": "rule", "mode": mode, "action": name, "said": st["said"], "state": keep}, **more)}

    def stop(speech):
        log.info("  rule %s, step %d: stops", name, st["at"] + 1)
        return {"status": "answered", "speech": speech}

    async def done(speech):
        if not first_change(rule).strip().upper().startswith("GET "):
            await conn.refresh()          # it changed something: the copy on hand is read again
        reply = {"status": "answered", "speech": speech}
        if st.get("items") is not None:
            reply["items"] = st["items"]          # read out by the router, a few at a time
            if st.get("read_max"):
                reply["read_max"] = st["read_max"]     # this rule's own read length (dump14)
        if st.get("remember") and st.get("item"):
            # the item it changed, as she now names it: "rename that" again means this one
            reply["chore"] = {"id": st["item"]["id"], "name": st.get("named") or st["item"]["name"], "action": name}
        return reply

    while st["at"] < len(steps):
        kind, p = kind_of(steps[st["at"]])
        log.info("  rule %s, step %d: %s %s", name, st["at"] + 1, kind, p.get("command", "") if kind == "call" else "")
        if kind == "call":
            method, _, path = p["command"].partition(" ")
            listed_as = path            # as the spec lists it: the app adds the query its command takes
            if hasattr(conn, "own_path"):
                path = conn.own_path(path)      # the start its spec gives but its address leaves out (dump6)
            if "{" in path:
                # its {names}: the app's own (its options, today's year), the values heard, the item picked ({id})
                v = dict(getattr(conn, "values", dict)(), **values(), **({"id": st["item"]["id"]} if st.get("item") else {}))
                if phases.on("dump1") and hasattr(conn, "date_values"):
                    said_day = conn.date_values(listed_as, st["said"])      # the day said, as the app writes it
                    if phases.on("dump21") and not said_day.get("day_said") and says_day(rule):
                        # its lines say the day ("On {day_said} ..."), and none was said ("on Victory Day"): she asks
                        return stop(say("rule_which_day"))
                    v.update(said_day)
                    if said_day.get("day_said"):
                        st["values"]["day_said"] = said_day["day_said"]    # "{day_said}" in a Response: "December 7"
                missing = [k for k in re.findall(r"\{(\w+)\}", path) if k not in v]
                if missing:
                    return stop(say("generic_cannot", action=label))
                path = re.sub(r"\{(\w+)\}", lambda m: str(v[m.group(1)]), path)
            if method.upper() == "GET" and hasattr(conn, "listing"):
                answer, listed = await conn.listing(path, command=listed_as)     # both years, its skips (connector.py)
            elif method.upper() == "GET":
                answer = await conn.api("GET", path, command=listed_as)
                listed = _as_list(answer)
            else:
                if body is None:
                    body, unfilled = {}, []
                    for req in (conn.commands.get(p["command"].upper()) or {}).get("requires") or []:
                        where, _, field = req.partition(": ")
                        if where == "body" and field:
                            if field in st["values"]:
                                body[field] = st["values"][field]
                            else:
                                unfilled.append(field)
                    if unfilled:
                        return stop(say("generic_missing", action=label, fields=", ".join(unfilled)))
                accepts = (getattr(conn, "commands", {}).get(p["command"].upper()) or {}).get("accepts") or []
                if body and accepts and phases.on("dump15") and (getattr(conn, "svc", None) or {}).get("send_only_accepted"):
                    body = {k: v for k, v in body.items() if k in accepts}     # an app that refuses fields it doesn't take
                await conn.api(method.upper(), path, command=listed_as, json=body) if body \
                    else await conn.api(method.upper(), path, command=listed_as)
                body = None
        elif kind == "search":
            if listed is None:
                return stop(say("rule_no_list", action=label))
            st["remember"] = bool(param(kind, p, "last"))
            st["field"] = param(kind, p, "field")
            drop = conn.drop_words() | {str(w).lower() for w in param(kind, p, "ignore") or []}
            # each way of cutting what was said is tried; the cut whose words match an item best wins
            best = None
            last = (memory or {}).get("last_chore") or {}

            def the_last(text, after, word):
                # "rename that", "call it ...": the item she last named, no matching and no question
                own = next((c["fields"] for c in candidates(last.get("name") or "", listed, st["field"], "", ())
                            if c["id"] == last["id"]), {})
                return (text, [{"id": last["id"], "name": last.get("name") or "", "group": None,
                                "fields": own, "score": 1.0, "whole": True, "exact": True}], after, word)
            named = st["values"].get("_name") if phases.on("dump15") else None    # her "Which one?" answered
            lead = on_last_opening(rule, st["said"]) if st["remember"] and not named else None
            if lead:
                if not last.get("id"):
                    return stop(say("rule_no_last", action=label))
                best = the_last(lead[0], lead[1], lead[0])
            for before, after, word in ([] if lead else splits(named or st["said"], [] if named else rule.get("words") or [],
                                                                 param(kind, p, "until") or [])):
                said_words = [w for w in before if w not in drop]
                if st["remember"] and points_back(before, drop):
                    if not last.get("id"):
                        return stop(say("rule_no_last", action=label))
                    best = the_last(" ".join(before), after, word)
                    break
                text = " ".join(said_words)
                words_ = {"alike": getattr(conn, "alike", None), "nearby": getattr(conn, "nearby", None)}
                # its Ignore words are never part of a name, on the items' side too ("the", "of" in a feast's name)
                never = conn.never_words() | {str(w).lower() for w in param(kind, p, "ignore") or []}
                full = candidates(text, listed, param(kind, p, "field"), param(kind, p, "group"), never, **words_)
                found = full[:5]
                if not any(c["exact"] or c["whole"] for c in found):
                    # nothing whole as heard: its abbreviations spelled out ("St. Joseph": Saint Joseph)
                    for alt in match.expansions(text, getattr(conn, "abbrev", None)):
                        tried = candidates(alt, listed, param(kind, p, "field"), param(kind, p, "group"), never, **words_)[:5]
                        if tried and (any(c["exact"] or c["whole"] for c in tried) or tried[0]["score"] > (found[0]["score"] if found else 0)):
                            found, full = tried, tried
                            break
                if getattr(conn, "sound_alike", False) and not any(c["exact"] for c in found):
                    # the voice map's sound-alike, as in the app's own find: "by single hole faucet" for "Buy single whole faucet"
                    heard = candidates(text, listed, param(kind, p, "field"), param(kind, p, "group"), never, True, **words_)[:5]
                    if heard and heard[0]["score"] > (found[0]["score"] if found else 0):
                        found = heard
                if best is None or (found and found[0]["score"] > (best[1][0]["score"] if best[1] else 0)):
                    # how many fit in all, not only the five best kept ("There are several of them")
                    best = (text, found, after, word, sum(1 for c in full if c["whole"]) or len(full))
            if phases.on("dump15") and not lead and not named and not best[0].strip():
                # nothing said to search by ("Find the task."): she asks which one, and searches by the answer
                # (the list is read again first, from the copy on hand: it goes on at the call before)
                st["at"] = max([i for i in range(st["at"]) if kind_of(steps[i])[0] == "call"] or [st["at"]])
                return wait("ask", say("rule_which_name"), need="_name")
            text, st["found"], after, word = best[:4]
            st["searched"] = text
            st["found_n"] = best[4] if len(best) > 4 else len(st["found"])
            if word:
                st["rest"] = {"word": word, "words": after, "on_last": bool(lead)}     # what Ask reads when it waits on the same word
            log.info("  rule %s: searched \"%s\": %s", name, text,
                     ", ".join(f"{c['name']} {c['score']:.0%}" + (" by sound" if c.get("by_sound") else "") for c in st["found"])
                     or "nothing shares a word")
        elif kind == "match":
            found = st.get("found") or []
            act, ask = float(param(kind, p, "act")) / 100, float(param(kind, p, "ask")) / 100
            exact = [c for c in found if c["exact"]]
            # the matching ladder ("When to ask", Oct 18): a name holding every word said is a fit even
            # below Ask (the Assumption of the Blessed Virgin Mary for "the Assumption")
            fit = [c for c in found if c["score"] >= ask or c["whole"]]
            wholes = [c for c in fit if c["whole"]]
            if not exact and not fit:
                if hasattr(conn, "not_kept") and listed_as:
                    # only in the list of what should be: superseded this year, said so (the collision hook)
                    gone = await conn.not_kept(listed_as, " ".join(w for w in st.get("searched", "").split()), st.get("field") or "name",
                                               conn.never_words())
                    if gone:
                        return stop(gone)
                return stop(_fill(p.get("not_found"), values()) or say("rule_not_found", action=label))
            pool = None                   # the choices she could weigh, when she asks which
            if found[0].get("alone"):
                top, pool = found[:3], found  # nothing but a word that never decides alone ("Mary"): which one
            elif exact:
                top = exact[:1]
            elif len(wholes) > 1 and not (wholes[0]["score"] >= act
                                          and wholes[0]["score"] - wholes[1]["score"] >= float(param(kind, p, "clear")) / 100):
                top, pool = wholes[:3], wholes   # several hold every word said, none clearly first: which one
            elif len(wholes) == 1:
                top = wholes              # one name holds every word said: it, over a shorter name that doesn't
            else:
                top = [c for c in fit if c["score"] == fit[0]["score"]]
            if len(top) > 1 and (param(kind, p, "ties") == "ask" or top[0].get("alone")):
                choices = [{k: c.get(k) for k in ("id", "name", "group", "fields")} for c in top]
                weigh = getattr(conn, "weigh", None)
                ordered, w = weigh(listed_as, [{k: c.get(k) for k in ("id", "name", "group", "fields")} for c in pool or top]) \
                    if weigh else (choices, None)
                st["at"] += 1
                if w:
                    # by the card's weight: the main one first, and how many there are ("When to ask", 3)
                    ask_ = {"mode": "main", "choices": ordered, "weight": w,
                            "more": phases.on("dump14") and int(st.get("found_n") or 0) > len(ordered)}
                    return wait("main", conn.thing_question(ask_), choices=ordered)
                return wait("which", conn.thing_question({"mode": "which", "choices": choices}), choices=choices)
            pick = top[0]
            # the only name holding every word said is it, however long the name ("The Immaculate
            # Conception of the Blessed Virgin Mary, Patronal feastday of the United States of America")
            only_whole = pick["whole"] and len(wholes) == 1 and not pick.get("by_sound")
            sure = bool(exact) or only_whole or (pick["score"] >= act and not pick.get("by_sound")
                                                 and (pick["whole"] or param(kind, p, "extra_words") == "ignore"))
            st["item"] = {k: pick.get(k) for k in ("id", "name", "group", "fields")}
            st["unsure"] = not sure
            log.info("  rule %s: %s %s (%.0f%%)", name, "sure of" if sure else "not sure of", pick["name"], pick["score"] * 100)
        elif kind == "filter":
            if listed is None:
                return stop(say("rule_no_list", action=label))
            listed = [x for x in listed if isinstance(x, dict) and _is(x.get(param(kind, p, "field")), param(kind, p, "value"))]
            log.info("  rule %s: filtered to %d", name, len(listed))
        elif kind == "by_date":
            if listed is None:
                return stop(say("rule_no_list", action=label))
            picked, day = by_date(listed, param(kind, p, "which"), st["said"], param(kind, p, "field"))
            w = (conn.card_for(f"GET {listed_as}").get("weight") or {}) if listed_as and hasattr(conn, "card_for") else {}
            if w.get("field"):           # several on the day: the main one first (the card's weight)
                picked = sorted(picked, key=lambda x: conn.weight_of(x, w))
            if not picked:
                return stop(_fill(p.get("not_found"), dict(values(), day=day or "")) or say("rule_not_found", action=label))
            first = picked[0]
            if day:
                st["values"]["day"] = day          # "{day}" in a Response: "tomorrow", "Saturday"
            id_ = getattr(conn, "field", lambda k: k)("id") or "id"
            st["item"] = {"id": first.get(id_), "name": str(first.get(st.get("field") or "name") or ""), "group": None,
                          "fields": {k: v for k, v in first.items() if isinstance(v, (str, int, float, bool)) or v is None}}
            st["unsure"] = False
            listed = picked                  # several that day: a Response with List reads them all
            log.info("  rule %s: by date (%s%s): %s", name, param(kind, p, "which"), f", {day}" if day else "",
                     ", ".join(str(x.get("name")) for x in picked[:5]))
        elif kind == "confirm":
            if st.get("unsure") or param(kind, p, "always"):
                question = _fill(p.get("question"), values()) or say("rule_confirm", item=st["item"]["name"] if st.get("item") else label)
                no = _fill(p.get("no"), values())
                st["at"] += 1
                st["unsure"] = False
                return wait("confirm", question, no=no)
        elif kind == "ask":
            need = str(p.get("need") or "")
            if need not in st["values"]:
                words = {str(a).lower() for a in param(kind, p, "after") or []}
                rest = st.get("rest") or {}
                after = rest["words"] if rest.get("word") in words or rest.get("on_last") else _cut(st["said"], words)[1]
                while after and after[0] in words:      # "a brain flea THAT we only buy...": not the value
                    after = after[1:]
                heard = _named(after, conn.drop_words(), st["said"])
                if heard:
                    st["values"][need] = heard
                else:
                    return wait("ask", _fill(p.get("question"), values()) or say("rule_ask", need=need.replace("_", " ")), need=need)
        elif kind == "fresh_copy":
            if not st.get("item"):
                return stop(say("generic_cannot", action=label))
            method, _, path = str(p.get("read") or "").partition(" ")
            fresh = await conn.api("GET", path.replace("{id}", str(st["item"]["id"])))
            if "{id}" not in path:
                # the app reads only the whole list (Donetick's projects): the item is picked out of it by id
                fresh = next((x for x in _as_list(fresh) or [] if isinstance(x, dict)
                              and str(x.get("id")) == str(st["item"]["id"])), None)
                if fresh is None:
                    return stop(say("rule_not_found", action=label))
            body = dict(fresh) if isinstance(fresh, dict) else {}
            for field, value_name in (param(kind, p, "set") or {}).items():
                body[field] = st["values"].get(value_name, value_name)
                if field == st.get("field", "name"):
                    st["named"] = body[field]
            for field, value in (param(kind, p, "fill_empty") or {}).items():
                if body.get(field) in (None, "", [], {}):
                    body[field] = value
        elif kind == "who_spoke":
            who = getattr(conn, "speaker", None) or {}
            score = float(who.get("score") or 0) * 100
            pick = lambda key: random.choice([str(x) for x in param(kind, p, key) or [] if str(x).strip()] or [None])   # noqa: E731
            if not who.get("own") or not who.get("known") or score < float(param(kind, p, "hedge")):
                log.info("  rule %s: who spoke not sure enough (%s %.0f%%): a way out", name, who.get("own") or "nobody", score)
                return stop(_fill(pick("unsure") or say("rule_who_unsure"), values()))
            nick = [n.strip().rstrip(".!") for n in who.get("nicknames") or [] if n.strip()]
            st["values"]["speaker"] = random.choice(nick) if param(kind, p, "name") == "nickname" and nick else who["own"]
            if score < float(param(kind, p, "sure")):
                log.info("  rule %s: who spoke between Hedge and Sure (%.0f%%): she thinks so", name, score)
                return stop(_fill(pick("hedge_lines") or say("rule_who_hedge", speaker=st["values"]["speaker"]), values()))
        elif kind == "response":
            lines = [str(x) for x in param(kind, p, "lines") or [] if str(x).strip()]
            v, own = values(), (st.get("item") or {}).get("fields") or {}
            if phases.on("dump3") and param(kind, p, "one") == "random":
                things = [x for x in listed or [] if isinstance(x, dict)]
                if not things:
                    lines = [str(x) for x in param(kind, p, "empty_lines") or [] if str(x).strip()] or lines
                else:
                    pick = random.choice(things)            # a fun fact, not a recital
                    v.update({k: plain(x) for k, x in pick.items() if isinstance(x, (str, int, float))})
            if param(kind, p, "list"):
                # each thing by its name: the Search's field, else the list card's (a title)
                card = conn.card_for(f"GET {listed_as}") if listed_as and hasattr(conn, "card_for") else {}
                nf = st.get("field") or card.get("name") or "name"
                names = [str(x.get(nf)) for x in listed or [] if isinstance(x, dict) and x.get(nf)]
                if phases.on("dump2") and param(kind, p, "line"):
                    # each thing read by a line of its own fields ("1781: Surrender of Lord Cornwallis")
                    names = [_fill(param(kind, p, "line"), {k: plain(y) for k, y in x.items() if isinstance(y, (str, int, float))})
                             for x in listed or [] if isinstance(x, dict)]
                if phases.on("dump4"):
                    names = [plain(n) for n in names]
                if names:
                    st["items"] = names
                    if phases.on("dump14") and param(kind, p, "read_max"):
                        st["read_max"] = int(param(kind, p, "read_max"))
                else:
                    lines = [str(x) for x in param(kind, p, "empty_lines") or [] if str(x).strip()] or lines
            for said_as, field in (param(kind, p, "fields") or {}).items():
                if own.get(field) in (None, ""):
                    lines = [str(x) for x in param(kind, p, "empty_lines") or [] if str(x).strip()] or lines
                else:
                    v[str(said_as)] = plain(_spoken(own[field])) if phases.on("dump4") else _spoken(own[field])
                    n = days_until(own[field])
                    if n is not None:
                        v[f"{said_as}_days"] = n      # "how many days until Easter": {date_days}
                    if _gone(own[field]):        # Oct 17: "is due Friday" when Friday was yesterday
                        lines = [str(x) for x in param(kind, p, "past_lines") or [] if str(x).strip()] or lines
            note = await conn.gives_way(listed_as, st.get("item")) if hasattr(conn, "gives_way") and listed_as and st.get("item") else ""
            return await done((_fill(random.choice(lines), v) if lines else say("rule_done", action=label)) + note)
        st["at"] += 1
    return await done(say("rule_done", action=label))


def resume(p, said, kind_of_answer, pick, words, words_max):
    """An answer to a rule's question. words: the answer's words without filler.
    Returns (state, None) to go on, (None, 'no') to stop, (None, None) when it isn't an answer."""
    st = dict(p.get("state") or {})
    mode = p.get("mode")
    if mode == "confirm":
        k = kind_of_answer(said)
        return (st, None) if k == "yes" else (None, "no") if k == "no" else (None, None)
    if mode == "main":
        # "The main one is ... Is that the one?": yes is the main one; a name or "the second" picks another
        k = kind_of_answer(said)
        c = (p.get("choices") or [None])[0] if k == "yes" else (None if k == "no" else pick(said, p.get("choices") or []))
        if k == "no":
            return None, "no"
        if not c:
            return None, None
        st["item"], st["unsure"] = {k_: c.get(k_) for k_ in ("id", "name", "group", "fields")}, False
        return st, None
    if mode == "which":
        c = pick(said, p.get("choices") or [])
        if not c:
            return None, None
        st["item"], st["unsure"] = {k: c.get(k) for k in ("id", "name", "group", "fields")}, False
        return st, None
    if mode == "ask":
        if kind_of_answer(said) == "no":
            return None, "no"
        if not 0 < len(words) <= words_max:
            return None, None
        st.setdefault("values", {})[p.get("need")] = _named(list(words), (), said)
        return st, None
    return None, None
