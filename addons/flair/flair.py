# flair.py - the flair level: an assistant's flourishes, added to some of her answers at home.
# Router-independent (tested by addons/flair/test_flair.py, no router needed).
#
# Each assistant has her own file, personality/<assistant>.yaml (the first word of her
# instructions: "Iris Personality" -> iris.yaml). No file -> plain answers.
#   rate:          share of answers that get flair (0.4 -> 4 of every 10, dealt like a deck)
#   max_in_a_row:  never more flourished answers than this back to back
#   flourishes:    each has text, slot (any, opener, closer, aside), topics, mood
#                  slot: opener goes before her answer, closer after it, aside only where a phrase
#                  line has a hand-placed [[aside]] (mid-sentence); any fits wherever there's room
# Plus the lines you approved from the books: personality/approved/<assistant>.yaml (written by
# addons/flair/tools/build_flair.py). Once she has any real lines (your own or approved), flourishes marked
# placeholder: true step aside.
#
# Where a flourish goes:
#   - A line with hand-placed slots ("[[opener]] Tomorrow will be sunny. [[closer]]") uses them.
#   - Any other line is wrapped: an opener before it, or a closer after it.
#   - Never a closer after a question: she has to end on the question to keep the mic open.
#   - Unfilled slots always vanish cleanly (strip()).
# Moods: every line is plain, warning (a freeze, a storm) or sorry (she couldn't do it),
# from the words in vocab/moods.yaml. A flourish with no mood fits plain lines only; warning
# and sorry lines only get flourishes tagged for that mood, so "Poof!" never lands on a
# freeze warning or a failed save.

import logging
import os
import random
import re

import yaml

from veil import personas, util

log = logging.getLogger("router")

NOT_PERSONALITIES = personas.NOT_PERSONALITIES
persona_words = personas.words      # the assistants' names as heard (core: veil/personas.py)


SLOT = re.compile(r"\s*\[\[\s*(\w+)\s*\]\]\s*")
SLOTS = ("opener", "aside", "closer")


def strip(line):
    """The line with every [[slot]] removed and its spacing tidied."""
    return " ".join(SLOT.sub(" ", line or "").split())


def slots_in(line):
    """Hand-placed slots in the line, in order."""
    return [m.group(1).lower() for m in SLOT.finditer(line or "")]


def _words(text):
    return " " + " ".join(re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower().replace("’", "'")).split()) + " "


def mood_of(line, moods):
    """plain, warning or sorry, from vocab/moods.yaml (warning wins over sorry)."""
    text = _words(strip(line))
    for mood in ("warning", "sorry"):
        if any(_words(w) in text for w in (moods or {}).get(mood) or []):
            return mood
    return "plain"


class Bag:
    """Every item once, in random order, before repeating; never the same twice in a row."""

    def __init__(self, items, rng):
        self.items, self.rng, self.bag, self.last = list(items), rng, [], None

    def draw(self):
        if not self.bag:
            self.bag = self.items[:]
            self.rng.shuffle(self.bag)
            if len(self.bag) > 1 and self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop()
        return self.last


class Personality:
    """One assistant's flair: her deck (flair or plain) and her flourishes."""

    DECK = 10

    def __init__(self, spec, rng):
        spec = spec or {}
        self.rng = rng
        self.rate = max(0.0, min(1.0, float(spec.get("rate", 0) or 0)))
        self.max_in_a_row = int(spec.get("max_in_a_row", 1) or 0)
        self.flair_cards = round(self.rate * self.DECK)
        self.deck = []
        self.streak = 0
        self.flourishes = []
        approved = [f for f in (spec.get("approved") or []) if f]
        hand = [f for f in (spec.get("flourishes") or []) if f]
        if approved or any(not f.get("placeholder") for f in hand):
            # she has real lines (your own, or approved from the books): placeholders step aside
            hand = [f for f in hand if not f.get("placeholder")]
        for f in hand + approved:
            if not str(f.get("text") or "").strip():
                continue
            self.flourishes.append({
                "text": str(f["text"]).strip(),
                "slot": str(f.get("slot") or "opener").lower(),
                "topics": [str(t).lower() for t in (f.get("topics") or ["any"])],
                "mood": [str(m).lower() for m in (f.get("mood") or ["plain"])],
            })
        self.bags = {}

    def _fits(self, f, slot, topic, mood):
        return f["slot"] in (slot, "any") and mood in f["mood"] and \
            ("any" in f["topics"] or (topic or "router") in f["topics"])

    def pick(self, slot, topic, mood):
        """A flourish for this slot, topic and mood, or None (each fitting set is its own bag)."""
        fits = [f["text"] for f in self.flourishes if self._fits(f, slot, topic, mood)]
        if not fits:
            return None
        key = (slot, topic, mood)
        if key not in self.bags or self.bags[key].items != fits:
            self.bags[key] = Bag(fits, self.rng)
        return self.bags[key].draw()

    def _new_deck(self):
        """A shuffled deck of DECK cards, flair_cards of them flair, laid out so no run of flair
        is longer than max_in_a_row (counting the run still going from the last deck): the
        plain cards make gaps, and each flair card drops into a gap with room."""
        plain = self.DECK - self.flair_cards
        limit = self.max_in_a_row or self.DECK
        room = [limit] * (plain + 1)
        if self.max_in_a_row:
            room[0] = max(0, limit - self.streak)
        gaps = [0] * (plain + 1)
        for _ in range(self.flair_cards):
            open_gaps = [i for i, r in enumerate(room) if gaps[i] < r]
            if not open_gaps:        # a rate too high for the limit: the limit wins
                break
            gaps[self.rng.choice(open_gaps)] += 1
        deck = []
        for i, n in enumerate(gaps):
            deck += [True] * n
            if i < plain:
                deck.append(False)
        return deck

    def dealt(self):
        """Does this answer get flair? The next card in her deck decides."""
        if not self.deck:
            self.deck = self._new_deck()
        card = self.deck.pop(0)
        self.streak = self.streak + 1 if card else 0
        return card


class Flair:
    """All assistants' personalities, loaded from personality/*.yaml."""

    def __init__(self, folder, moods=None, seed=None):
        self.moods = moods or {}
        self.rng = random.Random(seed)
        self.people = {}
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if name.endswith((".yaml", ".yml")) and not name.startswith(NOT_PERSONALITIES):
                    who = name.rsplit(".", 1)[0].lower()
                    with open(os.path.join(folder, name)) as fh:
                        spec = yaml.safe_load(fh) or {}
                    if not isinstance(spec, dict):
                        log.warning("  ! personality/%s isn't a personality (not key: value lines): left out", name)
                        continue
                    # lines you approved from the books (addons/flair/tools/build_flair.py approve <who>)
                    book = os.path.join(folder, "approved", name)
                    if os.path.exists(book):
                        with open(book) as fh:
                            spec["approved"] = (yaml.safe_load(fh) or {}).get("flourishes") or []
                    self.people[who] = Personality(spec, self.rng)

    def names(self):
        return sorted(self.people)

    def flaired(self):
        """The personalities with flair on: a rate above 0 is the switch (Oct 15)."""
        return [w for w in self.names() if self.people[w].rate > 0]

    def dress(self, assistant, line, topic=None):
        """(what she says, why) - the line with or without a flourish, slots always cleared."""
        plain = strip(line)
        p = self.people.get((assistant or "").lower())
        if not p or not plain or p.rate <= 0:
            return plain, "no flair: " + ("no personality file" if not p else
                                          "empty line" if not plain else "rate 0")
        mood = mood_of(plain, self.moods)
        if not p.dealt():
            return plain, f"no flair this time (deck, mood {mood})"
        placed = slots_in(line)
        question = plain.endswith("?")
        choices = [s for s in (placed or ["opener", "closer"]) if s in SLOTS]
        if question:
            # she must end on the question: no closer, and no slot after the question starts
            choices = [s for s in choices if s != "closer"]
        self.rng.shuffle(choices)
        for slot in choices:
            text = p.pick(slot, topic, mood)
            if not text:
                continue
            if placed:
                done, out = [False], line

                def fill(m, slot=slot, text=text):
                    if not done[0] and m.group(1).lower() == slot:
                        done[0] = True
                        return " " + text + " "
                    return " "
                out = SLOT.sub(fill, out)
                return " ".join(out.split()), f"flair: {slot} (placed), mood {mood}"
            said = f"{text} {plain}" if slot == "opener" else f"{plain} {text}"
            return said, f"flair: {slot}, mood {mood}"
        p.streak = 0          # dealt flair but nothing fit: counts as plain
        return plain, f"no flourish fits (mood {mood}, topic {topic or 'router'})"
