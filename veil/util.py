# veil/util.py - small helpers every part of the router shares, so each is written once (Oct 15).

import re

_NOT_WORD = re.compile(r"[^a-z0-9' ]+")
_NOT_WORD_NO_APOS = re.compile(r"[^a-z0-9 ]+")


def words(text, apostrophes=True):
    """Words compared as said: lowercase, letters and digits (and apostrophes, unless
    apostrophes=False), single spaces; curly apostrophes count as straight ones. A list is
    joined first. The one normalizer for what was heard, bank keys, miss keys and rule words."""
    if isinstance(text, (list, tuple)):
        text = " ".join(str(t) for t in text)
    t = str(text or "").lower().replace("’", "'")
    if not apostrophes:
        return " ".join(_NOT_WORD_NO_APOS.sub(" ", t.replace("'", "")).split())
    return " ".join(_NOT_WORD.sub(" ", t).split())


def squash(text, most=None, lower=False):
    """The text with its spacing tidied (one space between words), cut to most characters."""
    t = " ".join(str(text or "").split())
    t = t.lower() if lower else t
    return t[:most] if most else t


_SLOT = re.compile(r"\s*\[\[\s*\w+\s*\]\]\s*")


HOLD = "\u2063"     # an add-on's mark on a line it holds (Loose language, until it has closed out its text): no
                     # dress add-on touches it, and it's taken out here, before it goes to Home Assistant


def unslot(text):
    """The text with every [[slot]] a phrase leaves for an add-on ([[opener]], [[name]]) and the held mark
    taken out and its spacing tidied: never spoken, whatever add-ons are on (issue #25)."""
    out = " ".join(_SLOT.sub(" ", (text or "").replace(HOLD, "")).split())
    return re.sub(r"\s+([,.!?;:])", r"\1", out)
