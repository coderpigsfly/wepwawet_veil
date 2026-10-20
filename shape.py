# shape.py - the last check before Gemini: what kind of sentence is this?
# Shared by router.py and tools/shape_test.py, so what's tested is what runs.
#
#   classify(said, words, nlp, vocab) -> (kind, parts)
#     kind: "fragment"  nothing to act on or look up ("My.", "EPI.")   -> "Sorry, I didn't catch that."
#           "ask"       not shaped like a request, or only nouns
#                       ("Cook of chew, but you go", "honda stock price") -> "Want me to ask around?"
#           "question" / "command" / "need" / "telling"                 -> straight to Gemini
#     parts: the words with their parts of speech, for the log
#   said:  what was heard, as is (a "?" at the end makes it a question)
#   words: the words after filler, her name and polite words are taken out
#   vocab: vocab/requests.yaml

import re

VERBS = {"VERB", "AUX"}
NOUNS = {"NOUN", "PROPN", "PRON"}
CONTENT = {"NOUN", "PROPN", "ADJ", "NUM"}       # words that carry something to look up


def _clean(t):
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", t.lower().replace("’", "'")).split())


def _shape(tokens, text, vocab):
    """question / command / need for one clause, else None."""
    if not tokens:
        return None
    first = tokens[0]
    if first.lower_ in set(vocab.get("question_words", [])) or first.tag_ in ("WDT", "WP", "WP$", "WRB"):
        return "question"
    if first.lower_ in set(vocab.get("asking_words", [])) or first.pos_ == "AUX":
        return "question"
    if first.lower_ in set(vocab.get("command_words", [])) or (first.pos_ == "VERB" and first.tag_ == "VB"):
        return "command"
    for n in vocab.get("need_starts", []):
        nc = _clean(n)
        if text == nc or text.startswith(nc + " "):
            return "need"
    return None


def classify(said, words, nlp, vocab):
    if nlp is None or not words:
        return "question", "no diagramming"          # without spaCy nothing is held back
    doc = nlp(" ".join(words))
    toks = [t for t in doc if not t.is_punct]
    parts = " ".join(f"{t.text}/{t.pos_}" for t in doc)
    tags = {t.pos_ for t in toks}
    first = toks[0].lower_ if toks else ""
    if len(toks) > 1 and first in set(vocab.get("command_words", [])):
        return "command", parts                       # "spell doctor": the tagger may miss the verb
    if len(toks) > 1 and first in set(vocab.get("question_words", [])):
        return "question", parts
    if not (VERBS & tags):
        # no verb: a few real words is something to look up ("honda stock price");
        # one word or less is nothing to act on ("My.", "EPI.")
        content = [t for t in toks if t.pos_ in CONTENT]
        return ("ask" if len(content) >= 2 else "fragment"), parts
    if not (NOUNS & tags):
        return "fragment", parts
    if said.strip().endswith("?"):
        return "question", parts
    text = _clean(" ".join(words))
    kind = _shape(toks, text, vocab)
    if kind:
        return kind, parts
    # a question after a lead-in: "in austin, what are...", "if i have garlic ... is it still fine"
    for i, t in enumerate(toks[:-1]):
        nxt = toks[i + 1]
        if t.pos_ == "AUX" and nxt.pos_ == "PRON" and i > 0:
            return "question", parts                  # "... is it ...", "... should i ..."
        if i == 0 and t.lower_ in ("if", "in", "within", "for", "at", "on", "about"):
            rest = toks[1:]
            if _shape(rest, _clean(" ".join(x.text for x in rest)), vocab) == "question":
                return "question", parts
    # telling her something: "I have a cat named Jojo", "You are a witch", "My cat is a girl".
    # Needs a real noun, not just pronouns, so overheard "we need to look at it" is still held.
    if first in set(vocab.get("telling_starts", [])) and len(toks) >= 3 \
            and any(t.pos_ in ("NOUN", "PROPN") for t in toks[1:]):
        return "telling", parts
    # said to the persona: "I love you", "you're funny", "thank you so much" (Oct 15): nothing at
    # home can answer it, and there's nothing to ask about, so it goes straight Off-Platform.
    # Overheard speech rarely names the persona as "you" ("we need to look at it" is still held).
    to_persona = set(vocab.get("said_to_words", []))
    if first in set(vocab.get("telling_starts", [])) and len(toks) >= 2 \
            and any(t.lower_ in to_persona for t in toks):
        return "telling", parts
    if "," in said:                                   # "in paris, what's the timezone"
        rest = _clean(said.split(",", 1)[1])
        rtoks = [t for t in nlp(rest) if not t.is_punct]
        k = _shape(rtoks, rest, vocab)
        if k:
            return k, parts
    return "ask", parts
