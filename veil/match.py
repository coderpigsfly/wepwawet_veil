# veil/match.py - which of an app's own things (a chore, a project, a recipe...) was named in
# what was said. Any app's helper uses it; nothing here knows any one app.
#
# The words on both sides are cut down the same way: lowercased, a few endings trimmed alike
# ("taking" and "take" both become "tak", "mowing" and "mow" both "mow"), and the app's own
# never-count words dropped after trimming. Then for each thing:
#   score = shared words against the words on both sides (2 x shared / (said + its own)), and it's
#   a candidate at the voice map's match_min or more.
# What comes back (Found.how):
#   sure     every word said is in its name (or its name is exactly what was said): act on it
#   confirm  the best candidate is missing a word that was said ("lawn pest" for "Mow Lawn"):
#            ask first ("Mow Lawn? Say yes...")
#   tie      two or more candidates fit equally well: ask which, naming each one's group (project)
#   weak     something shares words, but under match_min: nothing is changed
#   none     nothing shares a word
# Sound-alike (the voice map's sound_alike: true): when the words alone find nothing sure, the
# same scoring is tried again on how each word sounds (sound() below: "by", "bi" and "buy" all
# sound "b", "hole" and "whole" both "hl"), since speech-to-text writes the wrong one of words
# that sound the same. At least two words must agree by sound, and a thing found only that way is
# never acted on at once: she asks first.
# The app's own words (its voice map's language:, the Integrations tab), Oct 18:
#   alike   same meaning: a phrase -> what it means ("our lady" -> "mary"), on both sides alike
#   nearby  words that never decide alone ("mary", "joseph"): a thing that shares only them with
#           what was said isn't a fit; said alone, every thing with them is a choice (she asks which)

import re

ENDINGS = ("ing", "ed", "es", "s")


def stem(word):
    """The same trimming for what was said and for every name."""
    w = word.lower().strip("'")
    if w.endswith("'s"):           # "Joseph's feast": Joseph
        w = w[:-2]
    for end in ENDINGS:
        if w.endswith(end) and len(w) - len(end) >= 3:
            w = w[:-len(end)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def sound(word):
    """How a trimmed word sounds, roughly: its consonants, spelled one way each ("whole" and "hole"
    -> "hl", "buy" and "by" -> "b", "faucet" -> "fst"). Plain spelling rules, no word lists."""
    w = re.sub(r"[^a-z]", "", word.lower())
    for a, b in (("^wh(?=o)", "h"), ("^wh", "w"), ("^kn", "n"), ("^wr", "r"), ("ph", "f"), ("ck", "k"),
                 ("c(?=[eiy])", "s"), ("c", "k"), ("q", "k"), ("x", "ks"), ("z", "s"), ("dg", "j")):
        w = re.sub(a, b, w)
    w = w[:1] + re.sub(r"[aeiouyhw]", "", w[1:])
    w = re.sub(r"^[aeiouy]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


def canon(text, alike=None):
    """The text with each same-meaning phrase as what it means ("the assumption of our lady" ->
    "the assumption of mary"), the longest phrase first."""
    t = " " + " ".join(re.findall(r"[a-z0-9']+", (text or "").lower().replace("\u2019", "'"))) + " "
    for k in sorted(alike or {}, key=len, reverse=True):
        t = t.replace(" " + k + " ", " " + alike[k] + " ")
    return t


def words(text, never=(), alike=None):
    """The meaningful words of a text, trimmed; never-count words are dropped after trimming."""
    drop = {stem(w) for w in never}
    return {stem(w) for w in re.findall(r"[a-z0-9']+", canon(text, alike) if alike else (text or "").lower())} - drop - {""}


def near(nearby, alike=None):
    """The words that never decide alone, trimmed as everything else is."""
    return {w for x in nearby or () for w in words(x, (), alike)}


def expansions(text, abbrev, most=8):
    """What was said with its abbreviations spelled out ("st joseph" -> "saint joseph", "street joseph"),
    each meaning tried, at most `most` texts; none when it has no abbreviation."""
    toks = re.findall(r"[a-z0-9']+", (text or "").lower())
    if not abbrev or not any(t in abbrev for t in toks):
        return []
    outs = [[]]
    for t in toks:
        outs = [o + [m] for o in outs for m in ([str(x) for x in abbrev[t]] if t in abbrev else [t])][:most]
    return [" ".join(o) for o in outs]


def alone(said, never=(), alike=None, nearby=None):
    """Was nothing said but words that never decide alone ("When is Mary's feast?")?"""
    heard = words(said, never, alike)
    return bool(heard) and bool(nearby) and heard <= near(nearby, alike)


class Found:
    def __init__(self, how, thing=None, choices=None):
        self.how, self.thing, self.choices = how, thing, choices or []

    def __repr__(self):
        return f"Found({self.how}, {self.thing and self.thing.get('name')}, {len(self.choices)} choices)"


def scores(said, things, never=(), by_sound=False, alike=None, nearby=None):
    """[(score, every word said is in its name, its name is exactly what was said, thing)] for each
    thing that shares a word with what was said (user rules' Search reads them all). by_sound:
    the words as they sound (sound()); a word with no consonants to go by isn't counted. A thing
    sharing only nearby words isn't one; nothing but nearby words said: none is whole or exact."""
    heard = words(said, never, alike)
    nb, only = near(nearby, alike), alone(said, never, alike, nearby)
    if by_sound:
        heard = {sound(w) for w in heard} - {""}
    out = []
    for t in things if heard else ():
        own = words(t.get("name"), never, alike)
        if by_sound:
            own = {sound(w) for w in own} - {""}
        common = heard & own
        if not by_sound and common and common <= nb and not only:
            continue            # "Saint Joseph" shares only Joseph with the Holy Family of Jesus, Mary and Joseph
        if own and common:
            out.append((2 * len(common) / (len(heard) + len(own)), heard <= own and not only, own == heard and not only, t))
    return out


def find(said, things, never=(), match_min=None, group_first=None, sound_alike=False, ask_min=None, alike=None, nearby=None,
         abbrev=None):
    """things: [{"id", "name", "group" (optional: its project or list)}]. group_first: the group
    named first when she asks which (the app's default project). sound_alike: when the words find
    nothing (none or weak), try how they sound; what that finds is asked first (confirm or tie).
    ask_min: a weak match at or above it, or one whose name has every word said, is asked about
    ("Spray weeds?" for "spray the wheat") instead of not found; None = off. alike, nearby: the
    app's own words (above); nothing but nearby words said is "nearby": she asks which, never acts."""
    scored = scores(said, things, never, alike=alike, nearby=nearby)
    if scored and alone(said, never, alike, nearby):
        return Found("nearby", choices=[x[3] for x in sorted(scored, key=lambda x: -x[0])[:3]])
    found = _find(scored, match_min, group_first)
    if found.how in ("none", "weak") and abbrev:
        # what was heard matches nothing: its abbreviations spelled out ("St. Joseph": Saint Joseph)
        for alt in expansions(said, abbrev):
            f = _find(scores(alt, things, never, alike=alike, nearby=nearby), match_min, group_first)
            if f.how in ("sure", "confirm", "tie"):
                return f
    if sound_alike and match_min is not None and found.how in ("none", "weak"):
        # by sound, at least two words must agree: one alone is too loose ("path" sounds like "put")
        said_s = {sound(w) for w in words(said, never, alike)} - {""}
        two = [t for t in things if len(said_s & ({sound(w) for w in words(t.get("name"), never, alike)} - {""})) >= 2]
        heard = _find(scores(said, two, never, by_sound=True, alike=alike), match_min, group_first)
        if heard.how in ("sure", "confirm"):
            return Found("confirm", heard.thing, [heard.thing])
        if heard.how == "tie":
            return heard
    if ask_min is not None and match_min is not None and found.how == "weak":
        near = [x for x in scored if x[0] >= ask_min or x[1]]
        if near:
            best = max(x[0] for x in near)
            top = [x[3] for x in near if x[0] == best]
            return Found("confirm", top[0], top) if len(top) == 1 else Found("tie", choices=top)
    return found


def _find(scored, match_min, group_first):
    if not scored:
        return Found("none")
    if match_min is None:
        return Found("weak", choices=[x[3] for x in scored])
    fit = [x for x in scored if x[0] >= match_min]
    if not fit:
        # a name holding every word said is a fit below match_min too (the ladder: "Easter" for Easter
        # Sunday of the Resurrection of the Lord): one is asked about, several are which
        wholes = [x for x in scored if x[1]]
        if len(wholes) == 1:
            return Found("confirm", wholes[0][3], [wholes[0][3]])
        if len(wholes) > 1:
            return Found("tie", choices=[x[3] for x in sorted(wholes, key=lambda x: -x[0])])
        return Found("weak", choices=[max(scored, key=lambda x: x[0])[3]])
    exact = [x for x in fit if x[2]]
    if len(exact) == 1:
        return Found("sure", exact[0][3])
    whole = [x for x in fit if x[1]]                # every word said is in its name
    pool = whole or fit
    best = max(x[0] for x in pool)
    top = [x[3] for x in pool if x[0] == best]
    if len(top) > 1:
        first = str(group_first or "").lower()
        top.sort(key=lambda t: (str(t.get("group") or "").lower() != first, str(t.get("group") or "")))
        return Found("tie", choices=top)
    return Found("sure" if whole else "confirm", top[0], [top[0]])


def pick(answer, choices, never=(), ordinals=None):
    """Which of the choices an answer to "which one?" means: by order ("the first one", "two"), or
    by a word only that one has in its name or group ("Voice Tech", "the house one"). None if unclear."""
    said = re.findall(r"[a-z0-9']+", (answer or "").lower())
    heard = words(answer, never)
    hits = []
    for c in choices:
        mine = words(f"{c.get('name', '')} {c.get('group') or ''}", never)
        others = set().union(*[words(f"{o.get('name', '')} {o.get('group') or ''}", never)
                               for o in choices if o is not c]) if len(choices) > 1 else set()
        if heard & (mine - others):
            hits.append(c)
    if len(hits) == 1:                  # a word only that one has wins ("the house one")
        return hits[0]
    if hits:
        return None
    for w in said:                      # else by order ("the first one", "two", "the last one")
        n = len(choices) if w == "last" else (ordinals or {}).get(w)
        if isinstance(n, int) and 1 <= n <= len(choices):
            return choices[n - 1]
    return None
