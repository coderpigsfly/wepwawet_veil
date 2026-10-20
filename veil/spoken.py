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


def set_nlp(nlp):
    """The router's own spaCy model, shared (loaded once)."""
    global _NLP, _TRIED
    _NLP, _TRIED = nlp, True


def nlp():
    global _NLP, _TRIED
    if _NLP is None and not _TRIED:
        _TRIED = True
        try:
            import spacy
            from veil import config
            _NLP = spacy.load(config.section(config.settings(), "language").get("spacy_model") or "en_core_web_sm")
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
          when_words=(), when_lead=()):
    """when_words: words that are a date or time on their own (weekdays, months, parts of the day,
    daily); when_lead: words that belong to the date after them (every, each, on, by, due)."""
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
    for t in reversed(list(d)):      # "every" Tuesday, "due" Friday: the word before a date is the date's
        if t.lower_ in when_lead and t.i + 1 in drop:
            drop.add(t.i)
    for t in d:
        # a phrase that points at a date, a person, or one of the app's own nouns: not the name
        if t.dep_ == "prep" and any(c.i in drop or c.lemma_.lower() in stop or c.lower_ in stop or c.lower_ in people
                                    for c in t.children):
            drop.update(x.i for x in t.subtree)
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
    while out and out[-1].lower_ in lead:
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


def said_outside(said, name, word):
    """Was word said somewhere other than inside the thing's own name? ("paint the back of the
    HOUSE": the House project wasn't named; "... to the HOUSE project": it was.)"""
    if not word:
        return False
    low = said.lower()
    if name:
        low = low.replace(name.lower(), " ", 1)
    return re.search(r"\b" + re.escape(str(word).lower()) + r"\b", low) is not None
