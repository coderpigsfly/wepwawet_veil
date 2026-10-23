# veil/spoken.py - what was said for "the thing": a chore's name, a project's name. Any app.
#
# Two tools together. spaCy (the sentence diagram the router already loads) marks what is NOT
# the name: dates and times ("this Saturday morning", "next week"), and the phrases that say
# where or for whom ("to the house project", "for Beth", "on Thursday"). The name is then the
# words as said between the action's own words ("add a chore", "remind me to") and the first of
# those marks, so nothing inside the name is lost ("paint the back of the house").
#   thing(said, lead, people, stop_nouns)   -> the name, or "" when nothing's left
# lead: the action's own words, its topic's words, the vocab's little words; filler: um, uh
# people: the names that mean someone in the house; stop_nouns: words that end the name when a
# phrase points at them (the app's lists: project; its topic words: list, chores)
# Without spaCy (not installed), words alone: the lead words off the front, the rest kept.

import logging
import re

log = logging.getLogger("router")
_NLP = None
_TRIED = False

NAMING = None     # set from vocab (naming_words): "called", "named"


class Diagrams:
    """The model, each sentence diagrammed once: the same words asked about again (the decision, the
    app's checks, the name) get the diagram already made (Oct 21: lean, one diagram per sentence).
    The diagrams are only read, never changed, so one can be shared."""

    def __init__(self, model, keep=256):
        import collections
        self.model, self.keep, self.made = model, keep, collections.OrderedDict()
        self.parsed = self.reused = 0

    def __call__(self, text):
        d = self.made.get(text)
        if d is not None:
            self.made.move_to_end(text)
            self.reused += 1
            return d
        d = self.made[text] = self.model(text)
        self.parsed += 1
        if len(self.made) > self.keep:
            self.made.popitem(last=False)
        return d

    def __getattr__(self, name):
        return getattr(self.model, name)


def set_nlp(nlp):
    """The router's own spaCy model, shared (loaded once), each sentence diagrammed once."""
    global _NLP, _TRIED
    _NLP, _TRIED = (nlp if isinstance(nlp, Diagrams) or nlp is None else Diagrams(nlp)), True


def nlp():
    global _NLP, _TRIED
    if _NLP is None and not _TRIED:
        _TRIED = True
        try:
            import spacy
            from veil import config
            _NLP = Diagrams(spacy.load(config.section(config.settings(), "language").get("spacy_model") or "en_core_web_sm"))
        except Exception as e:
            log.info("  ! no sentence diagram for names (%s): words alone", e)
    return _NLP


def nouns(said):
    """The question's noun ("School House Rock": a person, place or thing): its noun phrases and
    proper nouns, without question words, pronouns and the little words in front ("When is Easter?" ->
    "Easter"; "When is the feast of St. Joseph?" -> "feast of St. Joseph"). "" without spaCy or a noun."""
    n = nlp()
    if n is None or not str(said or "").strip():
        return ""
    doc = n(said)
    keep = []
    for chunk in doc.noun_chunks:
        before = doc[chunk.start - 1] if chunk.start else None
        if any(t.tag_ in ("WP", "WDT", "WRB") for t in chunk) or (before is not None and before.tag_ == "WRB"):
            continue          # the question's own words ("how many days", "what date"): not the thing asked about
        toks = [t for t in chunk if t.tag_ not in ("PRP", "PRP$", "DT") and t.pos_ != "PRON"]
        if toks:
            keep.append(" ".join(t.text for t in toks))
    # a proper noun spaCy didn't put in a chunk ("When is Easter?" can read Easter as a verb's object alone)
    keep += [t.text for t in doc if t.pos_ == "PROPN" and not any(t.text in k.split() for k in keep)]
    return " ".join(keep).strip()


def _words_only(said, lead):
    toks = re.findall(r"[A-Za-z0-9'][A-Za-z0-9'\-]*", said)
    while toks and toks[0].lower() in lead:
        toks.pop(0)
    while toks and toks[-1].lower() in lead:
        toks.pop()
    return " ".join(toks)


def thing(said, lead=(), people=(), stop_nouns=(), naming=("called", "named", "titled"), filler=(),
          when_words=(), when_lead=(), every_units=()):
    """when_words: words that are a date or time on their own (weekdays, months, parts of the day,
    daily); when_lead: words that belong to the date after them (every, each, on, by, due);
    every_units: what "every" counts ("every day", "every other week", "every 2 weeks", "every weekday")."""
    every_units = {str(w).lower() for w in every_units}
    when_words = {str(w).lower() for w in when_words}
    when_lead = {str(w).lower() for w in when_lead}
    filler = {str(w).lower() for w in filler}
    lead = {str(w).lower() for w in lead} | filler
    people = {str(w).lower() for w in people}
    stop = {str(w).lower() for w in stop_nouns}
    naming = {str(w).lower() for w in naming}
    n = nlp()
    if n is None:
        low = said.lower()
        for w in naming:
            m = re.search(r"\b" + re.escape(w) + r"\b(.*)$", said, re.I)
            if m and low:
                return _words_only(m.group(1), lead)
        return _words_only(said, lead)
    d = n(said)
    drop = set()
    for e in d.ents:
        if e.label_ in ("DATE", "TIME"):
            drop.update(range(e.start, e.end))
    for t in d:                      # what the diagram missed: a weekday, "daily", "morning"
        if t.lower_ in when_words:
            drop.add(t.i)
    for t in d:                      # a repeat: "every day", "every other week", "every 2 weeks"
        if t.lower_ in when_lead and t.i + 1 < len(d):
            j = t.i + 1 + (d[t.i + 1].lower_ == "other" or d[t.i + 1].like_num)
            if j < len(d) and d[j].lower_ in every_units:
                drop.update(range(t.i, j + 1))
    for t in reversed(list(d)):      # "every" Tuesday, "due" Friday: the word before a date is the date's
        if t.lower_ in when_lead and t.i + 1 in drop:
            drop.add(t.i)
    for t in d:
        # a phrase that points at a date, a person, or one of the app's own nouns: not the name
        if t.dep_ == "prep" and any(c.i in drop or c.lemma_.lower() in stop or c.lower_ in stop or c.lower_ in people
                                    for c in t.children):
            drop.update(x.i for x in t.subtree)
    for t in d:                      # "at 3": a time the diagram didn't mark, after the phrases ("pick the kids up at 3" keeps its up)
        if t.lower_ == "at" and t.i + 1 < len(d) and d[t.i + 1].like_num:
            drop.update((t.i, t.i + 1))
    toks = [t for t in d if not t.is_punct]
    named = next((k for k, t in enumerate(toks) if t.lower_ in naming), None)
    if named is not None:
        span = toks[named + 1:]
    else:
        k = 0
        from veil import phases

        def surname_next(j):         # "Call John Smith": a first name with its last name is part of the name (dump15)
            return phases.on("dump15") and j + 1 < len(toks) and toks[j + 1].pos_ == "PROPN" and toks[j + 1].lower_ not in people \
                and toks[j + 1].lower_ not in lead
        while k < len(toks) and (toks[k].lower_ in lead or toks[k].lower_ in people and not surname_next(k) or toks[k].i in drop):
            k += 1
        span = toks[k:]
        if span and _you_do(span[0]):
            return ""                # "I need you to find the chore": asked of her, not a thing's name
    out = []
    for t in span:
        if t.i in drop:
            break                    # the name ends where the date, the project or the person starts
        if t.pos_ == "INTJ" or t.lower_ in filler or (t.lower_ in lead and not out):
            continue
        out.append(t)
    while out and out[-1].lower_ in lead and out[-1].dep_ != "prt":     # "pick the kids UP": the verb's own particle stays
        out.pop()
    # the words as said, spaced as said ("Newton's", not "Newton 's")
    name = "".join(t.text + (t.whitespace_ or (" " if n.i != t.i + 1 else "")) for t, n in zip(out, out[1:]))
    name += out[-1].text if out else ""
    return name[:1].upper() + name[1:]


def _you_do(t):
    """This word is "you" doing something, or a verb whose doer is "you"."""
    return t.lower_ == "you" and t.dep_ == "nsubj" or t.pos_ == "VERB" and any(
        c.dep_ == "nsubj" and c.lower_ == "you" for c in t.children)


def asked_of_you(said):
    """Is this asked of her ("can you mark the chore spray weeds complete")? A verb with "you"
    doing it; "thank you" isn't one."""
    n = nlp()
    return bool(n) and any(t.lower_ == "you" and t.dep_ == "nsubj" and t.head.pos_ in ("VERB", "AUX") for t in n(said))


def is_task(name):
    """Is this a thing to do: a sentence's action with its noun ("Pick up my tuxedo", "Call the vet")?
    "Before" or "Funeral" alone isn't one (Oct 21: the owner's test of a chore). No diagramming: yes."""
    n = nlp()
    if not n or not str(name or "").strip():
        return bool(str(name or "").strip())
    # read as something to do ("I need to water the fern"): alone, "water" reads as a noun
    name = str(name).strip()
    # its first word lowercased (it's the action), the rest as said: a capital marks a name ("Turing")
    d = list(n("i need to " + name[:1].lower() + name[1:]))[3:]
    # it opens with the action, as a thing to do does ("Water the fern"; "That's very fun" doesn't)
    acts = bool(d) and (d[0].pos_ == "VERB" or (d[0].pos_ == "AUX" and d[0].dep_ in ("xcomp", "ROOT")))    # "be at Owen's"
    # its noun: a thing or a person; "it", "that" point back at one, so they aren't a thing of its own
    # (the small model reads a name ending in -ing as a verb, "have Turing euthanized": a capital after
    # the first word, or the thing acted on, is the noun all the same)
    return acts and any(t.pos_ in ("NOUN", "PROPN") or (t.pos_ == "PRON" and t.lower_ not in ("it", "that", "this", "them"))
                        or (k and t.text[:1].isupper()) or t.dep_ in ("dobj", "pobj") for k, t in enumerate(d))


def requested_of_you(said):
    """Is this a request of her ("can you mark the chore done", "I need you to find it")? "You" doing
    something with can, could, would or will, or wanted of her. Telling her something isn't one
    ("You already have a name for it", Oct 21)."""
    n = nlp()
    if not n:
        return False
    for t in n(said):
        if t.lower_ != "you":
            continue
        h = t.head
        if t.dep_ == "nsubj" and any(c.dep_ == "aux" and c.lower_ in ("can", "could", "would", "will") for c in h.children):
            return True
        if t.dep_ in ("dobj", "nsubj") and h.lemma_.lower() in ("need", "want", "like") and t.i > h.i:
            return True
        if h.dep_ in ("xcomp", "ccomp") and h.head.lemma_.lower() in ("need", "want", "like") and h.head.i < t.i:
            return True            # "I need you to find it": you, doing what's wanted
    return False


def main_verb(said, strip=()):
    """The verb the request hangs on, as its dictionary form ("find" in "I need you to find the
    chore", "add" in "I need to add milk"), or None: none, or only helpers and strip_away words
    ("what's on my list"). The first sentence with a verb at its root decides."""
    n = nlp()
    if n is None:
        return None
    strip = {str(w).lower() for w in strip}
    # lowercased: the diagram takes a capital at the start for a name ("Delete" as a proper noun)
    for sent in n(said.lower()).sents:
        v = sent.root
        if v.pos_ not in ("VERB", "AUX"):
            continue
        while v.pos_ == "AUX" or v.lemma_.lower() in strip:
            nxt = next((c for c in v.children if c.dep_ in ("xcomp", "ccomp") and c.pos_ == "VERB"), None)
            if nxt is None:
                break
            v = nxt
        return v.lemma_.lower() if v.pos_ == "VERB" and v.lemma_.lower() not in strip else None
    return None


def without_group(said, heard):
    """The words said without a group named for the thing ("... to Mara's morning briefing", "...
    in the house project"): only where a word puts it there (to, in, on) or its noun follows, so
    "paint the house" keeps its house."""
    if not heard:
        return said
    pat = (r"(?:\b(?:to|in|into|on|onto|under)\s+(?:(?:the|my|her|his|their|our)\s+)?" + re.escape(heard) +
           r"(?:\s+(?:project|list))?|\b" + re.escape(heard) + r"\s+(?:project|list))\b")
    return re.sub(r"\s{2,}", " ", re.sub(pat, " ", said.replace("\u2019", "'"), count=1, flags=re.I)).strip()


def said_outside(said, name, word):
    """Was word said somewhere other than inside the thing's own name? ("paint the back of the
    HOUSE": the House project wasn't named; "... to the HOUSE project": it was.)"""
    if not word:
        return False
    low = said.lower()
    if name:
        low = low.replace(name.lower(), " ", 1)
    return re.search(r"\b" + re.escape(str(word).lower()) + r"\b", low) is not None
