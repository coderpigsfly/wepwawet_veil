# veil/fleas.py - brain fleas: small true facts of the household ("We only buy pizza from Sal's",
# "who is talking to you"), answered at home before anything goes Off-Platform. Kept in
# learn/fleas.yaml (the household's own; a starting copy in defaults/learn/), on the Brain fleas page.
#
# A flea is a user rule with no app behind it (veil/rules.py): its words (the ways it's asked,
# "who is {speaking | talking} to you" for each choice) and its steps (Who spoke, Response...).
# The router is the "app" here: its commands list, add, change and forget fleas, so the voice
# rules that change fleas (add a brain flea...) are ordinary rules on those commands.
#
# Finding one is cheap: when the file loads (and again only when it changes), every way of asking
# is cut into trimmed words (veil/match.py) and indexed by word; a request scores only the fleas
# that share a word with it. A way of asking of one or two words is a key (all of it heard is a
# match: "pizza"); a flea that asks for a detail (add a brain flea ...) is picked by its words
# opening what was said; any other by how closely the whole sentence fits (match_at). Yes and no
# must agree: "that isn't nice" never answers "that is nice" (vocab/language.yaml negate, and n't).

import logging
import os
import re
import threading

from veil import config, match, rules

log = logging.getLogger("router")

FILE = config.path("learn", "fleas.yaml")
COMMANDS = {        # the router's own commands for its fleas, in the shape an app's spec gives
    "GET /FLEAS": {"api": "GET /fleas", "summary": "List the fleas (system ones left out)", "requires": [],
                   "returns": ["id", "name"]},
    "POST /FLEAS": {"api": "POST /fleas", "summary": "Add a flea from a fact", "requires": ["body: fact"], "returns": ["id"]},
    "PUT /FLEAS/{ID}": {"api": "PUT /fleas/{id}", "summary": "Change a flea's fact", "requires": ["path: id", "body: fact"],
                        "returns": []},
    "DELETE /FLEAS/{ID}": {"api": "DELETE /fleas/{id}", "summary": "Forget a flea", "requires": ["path: id"], "returns": []},
}
_LOCK = threading.Lock()


def expand(text):
    """Every way of saying a phrase with choices: "who is {speaking | talking} to you" -> two."""
    m = re.search(r"\{([^{}]*)\}", text or "")
    if not m:
        return [" ".join((text or "").split())]
    out = []
    for choice in m.group(1).split("|"):
        out += expand(text[:m.start()] + choice.strip() + text[m.end():])
    return [x for x in dict.fromkeys(out) if x]


_NEG = []


def negated(words):
    """Does a way of saying it say no ("not", "isn't", "never")? vocab/language.yaml negate, and any n't."""
    if not _NEG:
        path = config.path("vocab", "language.yaml")
        _NEG.append({str(w).lower() for w in (config.load_yaml(path).get("negate") if os.path.exists(path) else None) or []})
    return any(w in _NEG[0] or w.endswith("n't") for w in words)


def load():
    """The fleas file as written ({} when there isn't one)."""
    return config.load_yaml(FILE) if os.path.exists(FILE) else {}


def edit(change):
    """Change the fleas file in place, its comments kept (a voice add, change or forget), handed back to you."""
    with _LOCK:
        out = config.edit_yaml(FILE, change, width=4096)
        config.hand_back(FILE)
    return out


class Fleas:
    """The fleas in memory, re-read only when the file changes; find(said) and the router's commands."""

    def __init__(self, filler=()):
        self.filler = {str(w).lower() for w in filler}
        self.mtime = None
        self.doc, self.rules, self.index, self.ways, self.broken = {}, {}, {}, {}, {}

    # ---------- loading ----------

    def fresh(self):
        """Re-read the file if it changed since the last look (one stat per request)."""
        try:
            m = os.stat(FILE).st_mtime
        except OSError:
            m = None
        if m != self.mtime:
            self.mtime = m
            self._build(load())
        return self

    def _build(self, doc):
        self.doc = doc or {}
        self.never = {str(w).lower() for w in self.doc.get("never_count") or []} | self.filler
        self.rules, self.index, self.ways, self.broken = {}, {}, {}, {}
        for name, r in (self.doc.get("fleas") or {}).items():
            if not isinstance(r, dict):
                continue
            wrong = rules.check(r, set(COMMANDS))
            if wrong:
                self.broken[name] = wrong
                log.info("  ! brain flea %s isn't used: %s", name, wrong)
                continue
            self.rules[name] = r
            asks = any(rules.kind_of(s)[0] == "ask" for s in r.get("steps") or [])
            ways = []
            for w in r.get("words") or []:
                for phrase in expand(str(w)):
                    raw = re.findall(r"[a-z0-9']+", phrase.lower())
                    seq = [match.stem(x) for x in raw if x not in self.never]
                    if seq:
                        ways.append((seq, asks, negated(raw)))
                        for x in seq:
                            self.index.setdefault(x, set()).add(name)
            self.ways[name] = ways
        log.info("brain fleas: %d (%d broken)", len(self.rules), len(self.broken))

    # ---------- finding ----------

    def find(self, said):
        """(flea, score, how) for the flea that fits what was said best, or (None, best score, '')."""
        self.fresh()
        raw = re.findall(r"[a-z0-9']+", (said or "").lower())
        seq = [match.stem(x) for x in raw if x not in self.never]
        heard, says_no = set(seq), negated(raw)
        best = (None, 0.0, "", 0)
        for name in set().union(*[self.index.get(x, set()) for x in heard]) if heard else ():
            for way, asks, no in self.ways.get(name) or []:
                own = set(way)
                shared = len(heard & own)
                if asks and seq[:len(way)] == way:
                    score, how = 1.0, "opens with its words"
                elif no != says_no:
                    continue        # one says no and the other doesn't: never the same question
                elif len(own) <= 2 and own <= heard and (not asks or seq[:1] == way[:1]):
                    # a flea that asks for a detail opens with its first word ("remember that ...",
                    # not "do you remember that song")
                    score, how = 1.0, "all its key words heard"
                else:
                    score, how = 2 * shared / (len(heard) + len(own)), "how closely it fits"
                if (score, len(own)) > (best[1], best[3]):
                    best = (name, score, how, len(own))
        at = float(self.doc.get("match_at", 0.8))
        return (best[0], best[1], best[2]) if best[0] and best[1] >= at else (None, best[1], "")

    def changes(self, name):
        """Does this flea change the fleas (a voice add, change or forget)?"""
        first = rules.first_change(self.rules.get(name) or {})
        return bool(first) and not first.upper().startswith("GET ")

    def may_change(self, person):
        """Only the people the page names (changers:) may change fleas by voice, and only when Oread is
        sure; any of the person's names in the people grid counts (veil/people.py)."""
        from veil import people
        allowed = {str(p).lower() for p in self.doc.get("changers") or []}
        return bool(person) and bool(people.names(person) & allowed)

    # ---------- the router's own commands (what a flea's Call steps reach) ----------

    def items(self):
        return [{"id": n, "name": (r.get("title") or n.replace("_", " "))}
                for n, r in (self.doc.get("fleas") or {}).items() if isinstance(r, dict) and not r.get("system")]

    async def api(self, method, path, json=None, **_):
        method, parts = method.upper(), path.strip("/").split("/")
        if parts[0] != "fleas":
            raise RuntimeError(f"the router has no {path}")
        if method == "GET":
            self.fresh()
            return self.items()
        fact = (json or {}).get("fact") or ""

        def change(doc):
            fleas = doc.setdefault("fleas", {})
            if method == "POST":
                name, flea = from_fact(fact, fleas)
                fleas[name] = flea
                return name
            if len(parts) != 2 or parts[1] not in fleas or (fleas[parts[1]] or {}).get("system"):
                raise RuntimeError(f"no flea {path}")
            if method == "DELETE":
                del fleas[parts[1]]
            elif method == "PUT":
                _, flea = from_fact(fact, {})
                for k in ("title", "words", "steps"):
                    fleas[parts[1]][k] = flea[k]
            return parts[1]
        name = edit(change)
        self.mtime = None          # read again now, whatever the clock says
        self.fresh()
        return {"id": name}


def from_fact(fact, taken):
    """A flea from a fact said aloud ("We only buy pizza from Sal's"): its key words are the fact's
    nouns and names (asking about any of them finds it), and she says the fact back."""
    fact = " ".join(str(fact).split()).strip(" .")
    if not fact:
        raise RuntimeError("no fact to remember")
    keys = []
    try:
        from veil import spoken
        keys = [t.text.lower().replace("'s", "") for t in spoken.nlp()(fact) if t.pos_ in ("NOUN", "PROPN")]
    except Exception:
        pass
    keys = list(dict.fromkeys(k for k in keys if k)) or [fact.lower()]
    base = re.sub(r"[^a-z0-9]+", "_", "_".join(keys[:3]))[:30].strip("_") or "flea"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name, {"title": " ".join(keys[:3]), "words": keys,
                  "steps": [{"response": {"lines": [fact[:1].upper() + fact[1:] + "."]}}]}


class House:
    """The router as the "app" a flea's rule runs on (veil/rules.py asks this of any app)."""
    name = "house"

    def __init__(self, fleas, say, thing_question):
        self.fleas, self.say, self.thing_question = fleas, say, thing_question
        self.api = fleas.api                 # the commands above
        self.commands = COMMANDS
        self.speaker, self.assistant = None, "any"

    @property
    def rules(self):
        return self.fleas.fresh().rules

    def drop_words(self):
        return self.fleas.never

    def never_words(self):
        return self.fleas.never

    async def refresh(self):
        return None
