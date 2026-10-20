# learn.py - the learn level's miss log (learn/misses.yaml) and what was just asked.
# A miss is saved only when you say "Record that as a miss", right after asking
# "Who answered that?" (an engine miss) or "What did you hear?" (a speech-to-text miss).
# Mishearings go to learn/mishearings.yaml (veil/mishearings.py), under what was meant.
# Kept small: the same words with the same kind count up on one record; past miss_log_max
# the oldest are dropped; misses that a change fixes leave the log (they become test cases).

import os
import time

import yaml

from veil import config  # noqa: E402
from veil import mishearings, util  # noqa: E402

MISSES_FILE = config.path("learn", "misses.yaml")
ASKED_FILE = config.path("state", "learn.json")
KINDS = {"who": "engine", "heard": "misheard"}

HEADER = """# learn/misses.yaml - wrong-part misses you flagged ("Who answered that?", then "Record that as a
# misunderstanding"), each kind: engine. Mishearings (after "What did you hear?") go to
# learn/mishearings.yaml instead, under what was really said.
#   should_be: your note ("That should have been weather"), for the review; never acted on.
#   count: how many times the same words had the same kind of miss.
# Written by the router; you can read it, and delete a record once it's dealt with.

"""


_key = util.words


def load():
    try:
        with open(MISSES_FILE) as f:
            return (yaml.safe_load(f) or {}).get("misses") or []
    except FileNotFoundError:
        return []


def save(misses):
    config.make_dirs(os.path.dirname(MISSES_FILE))
    tmp = MISSES_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(HEADER)
        yaml.safe_dump({"misses": misses}, f, sort_keys=False, allow_unicode=True, width=120)
        f.write("\n\n")
    os.replace(tmp, MISSES_FILE)


def add_miss(kind, turn, assistant, note=None, max_records=500):
    """Save (or count up) a miss for this turn. Returns the record. A mishearing goes to
    learn/mishearings.yaml instead (under what was meant, never cut for size)."""
    if kind == "misheard":
        p, c = mishearings.add(turn.get("heard"), note, clip=turn.get("clip"), device=turn.get("device"))
        return {"kind": "misheard", "heard": c["said"], "should_be": p.get("meant"), "count": c["count"],
                "first": c.get("first"), "last": c.get("last")}
    misses = load()
    now = time.strftime("%Y-%m-%d %H:%M")
    key = (kind, _key(turn.get("heard")))
    for m in misses:
        if (m.get("kind"), _key(m.get("heard"))) == key:
            m["count"] = int(m.get("count", 1)) + 1
            m["last"] = now
            m["engine"], m["answer"] = turn.get("engine"), turn.get("answer", "")
            if note:
                m["should_be"] = note
            save(misses)
            return m
    rec = {"kind": kind, "heard": turn.get("heard", ""), "assistant": assistant,
           "engine": turn.get("engine"), "path": turn.get("path"), "topic": turn.get("topic"),
           "score": turn.get("score"), "why": turn.get("why") or [],
           "answer": turn.get("answer", ""), "before": turn.get("before") or {},
           "count": 1, "first": now, "last": now}
    if note:
        rec["should_be"] = note
    misses.append(rec)
    if len(misses) > max_records:                     # the ceiling: oldest go first
        misses.sort(key=lambda m: m.get("last", ""))
        misses = misses[-max_records:]
    save(misses)
    return rec


def add_note(heard, kind, note):
    """'That should have been weather' on a miss already saved. Returns the record or None.
    For a mishearing, what was really said: it moves under that intention."""
    if kind == "misheard":
        p, c = mishearings.set_meant(heard, note)
        return {"kind": "misheard", "heard": c["said"], "should_be": p.get("meant")} if c else None
    misses = load()
    for m in misses:
        if m.get("kind") == kind and _key(m.get("heard")) == _key(heard):
            m["should_be"] = note
            save(misses)
            return m
    return None


def drop(kind, heard):
    """Take one miss out of the log (after tools/misses.py fix or drop). True if it was there."""
    if kind == "misheard":
        return mishearings.drop(heard)
    misses = load()
    keep = [m for m in misses if (m.get("kind"), _key(m.get("heard"))) != (kind, _key(heard))]
    if len(keep) == len(misses):
        return False
    save(keep)
    return True
