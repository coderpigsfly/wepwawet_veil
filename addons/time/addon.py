"""addons/time: a day another integration names, put as its date for the app that claimed the request (issue
#25, step 5). The core hands it the things the other integrations have on hand (their copies, no call) as
suppliers; each that finds none of its own things in the words hands them back unchanged.
A supplier: {name, items, name_of, never (its never-in-names), alike (its same-meaning words), weight (a thing ->
its sort key, most important first), anchors (its own topic words said: "feast")}."""
import re

from veil import match, rules, util

clean = util.words


def _together(name, said_run, never):
    """Are a name's own words said together, in order ("on Palm Sunday", not "buy palms on Sunday", Oct 21)?
    Its little words (of, the) may be said between them or left out."""
    own = [w for w in clean(name).split() if w not in never]
    if not own:
        return False
    gap = r"\s(?:(?:" + "|".join(map(re.escape, sorted(never) or ["the"])) + r")\s)*"
    return bool(re.search(r"\s" + gap.join(re.escape(w) for w in own) + r"\s", said_run))


def _whole(said, s):
    """A thing named whole: every word of its name said ("Ash Wednesday", "paint the fence"; two words at least,
    so one common word isn't taken for a thing), the longest."""
    heard = set(match.words(said))       # every word, a weekday too (the "Wednesday" of Ash Wednesday)
    said_run = " " + " ".join(clean(said).split()) + " "
    whole = [x for x in s["items"] if isinstance(x, dict) and len(match.words(s["name_of"](x))) >= 2
             and set(match.words(s["name_of"](x))) <= heard and _together(s["name_of"](x), said_run, s["never"])]
    return max(whole, key=lambda x: len(match.words(s["name_of"](x))), default=None)


def _same(word, name_words, alike):
    """Is a word said one of a name's words: as it is, as the app's same-meaning word (Steven, Stephen), or
    as it sounds?"""
    w = match.canon(word, alike).strip()
    return w in name_words or any(len(w) > 3 and match.sound(w) == match.sound(n) for n in name_words)


def _anchored(said, s, ctx, every=False):
    """(the thing, first, last word) for the words right after the app's own word ("the Feast of Steven
    when ..."): every one of them in its name, up to the first little word. Two or more that fit, with
    different days: none for sure (fill asks which); every: ([the things, most important first], first, last)."""
    toks = said.split()
    low = [clean(t) for t in toks]
    stop = set(ctx.get("little") or ()) | set(ctx.get("own_words") or ())
    for i, w in enumerate(low):
        if w not in s["anchors"]:
            continue
        j = i + 1
        while j < len(low) and low[j] in s["never"]:
            j += 1
        k = j
        while k < len(low) and low[k] and low[k] not in stop and low[k] not in s["never"]:
            k += 1
        said_words = low[j:k]
        if not said_words:
            continue
        fits = [x for x in s["items"] if isinstance(x, dict)
                and all(_same(w2, set(match.words(match.canon(s["name_of"](x), s["alike"]))), s["alike"]) for w2 in said_words)]
        if not fits:
            continue
        fits.sort(key=s["weight"])
        lo = i
        while lo > 0 and low[lo - 1] in s["never"]:
            lo -= 1
        if every:
            return fits, lo, k - 1
        if len({s["name_of"](x) for x in fits}) > 1:
            continue            # two saints called Stephen: not one of them for sure (the owner, Oct 21: ask)
        return fits[0], lo, k - 1
    return None


def _rest(said, s, ctx):
    """The one thing whose name holds every word left once the asking topic's own words, the little words,
    this app's never-in-names and the plain day words are taken out ("rain on the feast of the Assumption"; a
    weekday alone is the core's plain date, never a thing: "rain on Sunday" isn't Easter Sunday)."""
    heard = set(match.words(said))
    rest = heard - set(ctx.get("own_words") or ()) - set(match.words(" ".join(ctx.get("little") or ()))) - set(match.words(" ".join(s["never"]))) \
        - set(match.words(" ".join(ctx.get("plain") or ())))
    fits = [x for x in s["items"] if isinstance(x, dict) and rest and rest <= set(match.words(s["name_of"](x)))]
    return fits[0] if len({s["name_of"](x) for x in fits}) == 1 else None


def dated(said, ctx):
    """(what was said with another app's thing put as its date, why, the app, {name, date, say, lead: the word
    before it}) when it names one of another app's things that has a date ("Will it rain on Ash Wednesday?" -> "... on Wednesday, February 17, 2027"),
    else None. ctx: suppliers, own_words (the asking topic's words said), little (little words), not_action,
    plain (the plain day words: weekdays, months, today)."""
    for s in ctx.get("suppliers") or []:
        span = None
        item = _whole(said, s)
        if item is None:
            span = _anchored(said, s, ctx)
            item = span[0] if span else _rest(said, s, ctx)
        f = rules.date_field([item]) if item else None
        if not f:
            continue
        day = rules._spoken(item[f])
        toks = said.split()
        if span:
            lo, hi = span[1], span[2]
        else:
            names = set(clean(s["name_of"](item)).split())
            hit = [i for i, t in enumerate(toks) if clean(t) in names]
            if not hit:
                continue
            lo, hi = hit[0], hit[-1]
            # "the feast of All Saints Day": the app's own words around the name go with it (when one of them is
            # more than a little word: "when I paint the fence" keeps its "I")
            never, little = s["never"], set(ctx.get("not_action") or ())
            a, b = lo, hi
            while a > 0 and clean(toks[a - 1]) in never:
                a -= 1
            while b + 1 < len(toks) and clean(toks[b + 1]) in never:
                b += 1
            if any(clean(t) not in little for t in toks[a:lo]):
                lo = a
            if any(clean(t) not in little for t in toks[hi + 1:b + 1]):
                hi = b
        tail = re.search(r"[?.!,]+$", toks[hi])
        lead = clean(toks[lo - 1]) if lo > 0 else ""
        f = rules.date_field([item])
        put = {"name": s["name_of"](item), "date": str(item[f])[:10], "say": day, "lead": lead}    # what it put in, after which word
        return " ".join(toks[:lo] + [day + (tail.group(0) if tail else "")] + toks[hi + 1:]), f"{s['name_of'](item)} ({s['name']}) is {day}", s["name"], put
    return None


def _day_of(item):
    f = rules.date_field([item])
    return rules._spoken(item[f]) if f else None


def fits(said, ctx):
    """(the app, a day one of them is on) when a few of another app's things fit the words after its own word
    (two saints called Stephen): the request is still about that app's day, for the claimer to ask which."""
    for s in ctx.get("suppliers") or []:
        found = _anchored(said, s, ctx, every=True)
        days = [d for d in (_day_of(x) for x in (found or ([],))[0]) if d]
        if days:
            return s["name"], days[0]
    return None


def fill(blank, ctx):
    """The claimer's blank (need: when) filled from another app's thing named in what was said: one, put as
    its date ({words}); a few that fit, her question which ({ask, choices}); none, None."""
    if (blank or {}).get("need") != "when":
        return None
    said = ctx.get("said") or ""
    got = dated(said, ctx)
    if got:
        return {"words": got[0], "why": got[1]}
    for s in ctx.get("suppliers") or []:
        found = _anchored(said, s, ctx, every=True)
        if not found:
            continue
        fits, lo, hi = found
        choices, seen = [], set()
        for x in fits:              # each name once (a list can hold one feast twice), the most important first
            if s["name_of"](x) not in seen and _day_of(x):
                seen.add(s["name_of"](x))
                choices.append({"name": s["name_of"](x), "say": _day_of(x), "replace": " ".join(said.split()[lo:hi + 1])})
        choices = choices[:3]
        if len(choices) > 1:
            names = [f"{c['name']}, on {c['say']}" for c in choices]
            return {"ask": "Do you mean " + ", ".join(names[:-1]) + " or " + names[-1] + "?", "choices": choices}
    return None


def supply(said, ctx):
    """The words for the app that claimed them, with another app's thing put as its date (the step says so)."""
    got = dated(said, ctx)
    if not got:
        return said
    (ctx.get("step") or (lambda text: None))(f"{got[1]}: asked as \"{got[0]}\"")
    return got[0]
