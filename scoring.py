# scoring.py - the router's scoring math, shared by router.py and tools/test_scores.py,
# so what is tested is exactly what runs.
#   - only words in the topic's generated files count, each word once (longest phrase wins)
#   - a door is required; no door means not this topic
#   - score = 1 - (chance that none of the matched words means the topic)
#   - a tentative door alone needs backup from another matched word

import os
import re

import yaml


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def prepare(scores):
    """Words longest-first, so phrases win over the single words inside them."""
    items = []
    for word, r in (scores.get("words") or {}).items():
        items.append((word, re.compile(r"\b" + re.escape(word) + r"\b"), r))
    items.sort(key=lambda x: -len(x[0]))
    return items


def score(text, items, lone_door_max=0, never=()):
    """Returns (score, matched words, reason): reason is ok, guard or no door.
    lone_door_max: a sentence of more words whose only topic word is its door is held (guard), unless
    the household pinned that word (a seed: "chore" in a long add is still a chore).
    never: words that never count toward a topic (numbers: "five hundred twenty-one divided by three")."""
    work = text.lower().replace("\u2019", "'")
    matched = []
    for word, pat, r in items:
        if never and (word in never or word.isdigit()):
            continue
        if pat.search(work):
            matched.append((word, r))
            work = pat.sub(" " * len(word), work)   # each word once; phrase wins
    doors = [(w, r) for w, r in matched if "doors" in r["where"]]
    if not doors:
        return 0.0, matched, "no door"
    # the strongest door opens the path; every other word (other doors too) confirms it
    entry = max(doors, key=lambda d: d[1].get("share") or 0)[0]
    none_mean_it = 1.0
    for w, r in matched:
        sh = r.get("share") if w == entry else (r.get("share_with_door") or r.get("share"))
        if sh is not None:
            none_mean_it *= (1 - sh)
    s = 1 - none_mean_it
    solid = [w for w, r in doors if not str(r.get("door_class", "")).startswith("tentative")]
    if not solid and len(matched) < 2:
        return s, matched, "guard"
    if lone_door_max and len(matched) == 1 and matched[0][1].get("door_class") != "strong (pinned)" \
            and len(re.findall(r"[a-z0-9']+", text.lower())) > lone_door_max:
        return s, matched, "guard"
    return s, matched, "ok"


class Scorer:
    """Every topic that has a scores file, ready to score a sentence."""

    def __init__(self, topics_dir, scores_dir, pinned=None, lone_door_max=0, never=()):
        """pinned: {topic: [words]} the household pins to a topic (settings.yaml); a pinned
        word is a strong door that counts fully, whatever the datasets measured.
        lone_door_max: settings lone_door_max_words (score())."""
        self.topics = {}
        self.lone_door_max = int(lone_door_max or 0)
        self.never = {str(w).lower() for w in never or ()}
        pinned = pinned or {}
        if not os.path.isdir(scores_dir):
            return
        for n in sorted(os.listdir(scores_dir)):
            if not n.endswith((".yaml", ".yml")):
                continue
            s = load_yaml(os.path.join(scores_dir, n))
            name = s.get("topic") or n.rsplit(".", 1)[0]
            tpath = os.path.join(topics_dir, f"{name}.yaml")
            t = load_yaml(tpath) if os.path.exists(tpath) else {}
            words = dict(s.get("words") or {})
            for w in pinned.get(name) or []:
                words[w.lower()] = {"share": 1.0, "share_with_door": 1.0, "where": ["doors"],
                                    "door_class": "strong (pinned)"}
            self.topics[name] = {"service": t.get("service"), "items": prepare({"words": words})}

    def rank(self, text):
        """[(topic, score, matched, reason)] for every topic with a door, best first."""
        out = []
        for name, t in self.topics.items():
            s, matched, why = score(text, t["items"], self.lone_door_max, self.never)
            if why != "no door":
                out.append((name, s, matched, why))
        out.sort(key=lambda x: -x[1])
        return out


def followup(text, items):
    """Score words that lean on a topic without a door of their own
    ('what about sunday' after a weather question). Uses the with-a-door shares,
    since the door was in the earlier request. Returns (score, matched)."""
    work = text.lower().replace("\u2019", "'")
    matched = []
    for word, pat, r in items:
        if "doors" in r["where"]:
            continue
        if pat.search(work):
            matched.append((word, r))
            work = pat.sub(" " * len(word), work)
    if not matched:
        return 0.0, matched
    none_mean_it = 1.0
    for _, r in matched:
        if r.get("share") is not None:
            none_mean_it *= (1 - r["share"])
    return 1 - none_mean_it, matched