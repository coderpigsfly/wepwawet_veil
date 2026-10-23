"""addons/window: she asks before a misheard request leaves the house (the OSPRI lab, Oct 22). A never word
(chore heard as troll, tour, chew) in words that are going Off-Platform is put back as its seed word; when an
app at home would take the corrected words and its decision says so, she asks "Did you mean ...? Shall I?" (its own words; answered as the core's heard_as question: yes does it and keeps the mishearing; no sends the words out
as heard). Every window weighed is recorded (data/tables/window.db), asked or not, for the overnight numbers, and the
answer to her question with it (answered: yes, no, or a new request said instead).

The decision: odds.py beside it when it's there (a household's own odds, with its numbers), else the plain rule:
she asks whenever a never word is in a seed word's place and an app at home takes the corrected words."""

import contextlib
import importlib.util
import os
import re
import sqlite3
import time

import yaml

SET = {"ask_about": [], "seeds": {}}
ODDS = None         # odds.py beside it, when there is one: (p, l, parts) for a guess; None: the plain rule
DB = None           # data/tables/window.db, set up by setup(); None: nothing recorded (the gate)

SCHEMA = """
create table if not exists windows (id integer primary key, at real not null, assistant text, heard text not null,
    meant text not null, seed text, never text, close_by text, app text, a real, b real, lr real, k real, e real,
    p real, l real, asked integer not null, answer text, answer_heard text, answer_at real, clip text, device text,
    answer_clip text);
create index if not exists windows_at on windows (at);
"""
# added Oct 22, later: older tables get them (the answer; Oread's clip and device for the request and the answer)
ADDED = (("answer", "text"), ("answer_heard", "text"), ("answer_at", "real"), ("clip", "text"), ("device", "text"),
         ("answer_clip", "text"))
FIELDS = ("id", "at", "assistant", "device", "clip", "heard", "meant", "seed", "never", "close_by", "app", "a", "b", "lr", "k",
          "e", "p", "l", "asked", "answer", "answer_heard", "answer_clip", "answer_at")


def setup(folder):
    """Its own settings (settings.yaml beside it), its odds when there are any (odds.py), and where it records
    (the core's data folder)."""
    global DB, ODDS
    path = os.path.join(folder, "settings.yaml")
    if os.path.exists(path):
        with open(path) as f:
            SET.update(yaml.safe_load(f) or {})
    ODDS = None
    if os.path.exists(os.path.join(folder, "odds.py")):
        spec = importlib.util.spec_from_file_location("addon_window_odds", os.path.join(folder, "odds.py"))
        ODDS = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ODDS)
        ODDS.setup(folder)
    try:
        from veil import config
        DB = config.path("data", "tables", "window.db")
    except Exception:
        DB = None


def words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def slot_action(said, start, s):
    """The action word when the word starting at start is in the seed word's place: right after one of its
    action words (slot_after), a little word or two between ("add a ___", "mark my ___"), else None. A seed with
    no slot_after (a question: the weather) has no place: "" (anywhere)."""
    if not s.get("slot_after"):
        return ""
    before, little = words(said[:start]), set(SET.get("little_words") or [])
    i = len(before) - 1
    while i >= 0 and before[i] in little and len(before) - 1 - i < 2:
        i -= 1
    return before[i] if i >= 0 and before[i] in set(s["slot_after"]) else None


def corrected(said, seed):
    """{meant: the words with the never word put back as the seed word, never, near: close-by words said, head:
    the command up to the seed word, payload: the rest, as heard (a chore's name: never corrected)}, or None.
    A never word that is a word of its own too often (need_close_by) counts only with a close-by word; with a
    slot (slot_after), only the never word in the seed word's place counts, so "Add a shore. Pack for the shore."
    is "Add a chore", "Pack for the shore"."""
    s = SET["seeds"].get(seed) or {}
    heard = words(said)
    if any(w.startswith(r) for w in heard for r in s.get("roots") or []):
        return None
    near = sorted(set(heard) & set(s.get("close_by") or []))
    found = sorted((m.start(), m, never) for never in list(s.get("never") or []) + (list(s.get("need_close_by") or []) if near else [])
                   for m in re.finditer(r"(?<![a-z'])" + re.escape(never) + r"(s?)(?![a-z'])", said, re.I))
    for start, m, never in found:
        action = slot_action(said, start, s)
        if action is None:
            continue
        head = said[:start] + s.get("word", seed) + m.group(1)
        payload = ""
        if action in (s.get("names_after") or []):       # an add: the rest is the new thing's name
            rest = said[m.end():].strip(" .,;:!?").split()
            while rest and rest[0].lower() in (s.get("name_leads") or []):
                rest = rest[1:]
            payload = " ".join(rest)
        return {"meant": head + said[m.end():], "never": never, "near": near, "head": head.strip(), "payload": payload}
    return None


def decide(near, meant):
    """(p, l, the parts) from the odds (odds.py), or (None, None, {}) for the plain rule: always asked."""
    return ODDS.odds(near, meant) if ODDS else (None, None, {})


def before_off_platform(said, ctx):
    """Her question ({kind: ask, meant, by: window, head, payload: said back apart, in quotes}) in place of going
    out, else None.
    ctx: at_home (the core's: the app or flea that takes these words at home, else None), assistant, clip and
    device (Oread's, from the audio path, kept with the window),
    rewrite (words a yes or a no already sent out as asked: never asked again), step (the request's why)."""
    at_home, step = ctx.get("at_home"), ctx.get("step") or (lambda text: None)
    if not callable(at_home) or ctx.get("rewrite") or not (said or "").strip() or len(said) > 300:
        return None
    best = None
    for seed in SET.get("ask_about") or []:
        fix = corrected(said, seed)
        if not fix:
            continue
        meant, never, near = fix["meant"], fix["never"], fix["near"]
        app = at_home(meant)
        if not app:
            step(f'"{never}" might be {seed}, but "{meant}" isn\'t taken at home: not asked')
            continue
        p, l, parts = decide(near, meant)
        row = dict({k: None for k in ("a", "b", "lr", "k", "e")}, **parts, heard=said, meant=meant, seed=seed, never=never, close_by=" ".join(near), app=app, p=p, l=l,
                   head=fix["head"], payload=fix["payload"])
        if not best or (p is not None and p > best["p"]):
            best = row
    if not best:
        return None
    best["asked"] = best["p"] is None or best["p"] > best["l"]
    best.update(clip=ctx.get("clip"), device=ctx.get("device"))
    record(ctx.get("assistant"), best)
    how = ("the plain rule" if best["p"] is None else
           f'p {best["p"]:.2f} {">" if best["asked"] else "<="} l {best["l"]:.2f}')
    step(f'"{best["never"]}" might be {best["seed"]} ("{best["meant"]}", {best["app"]}): {how}: '
         + ("she asks" if best["asked"] else "not asked"))
    return {"kind": "ask", "meant": best["meant"], "by": "window", "head": best["head"],
            "payload": best["payload"]} if best["asked"] else None


def _open():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB, timeout=5)
    db.executescript(SCHEMA)
    have = {c[1] for c in db.execute("pragma table_info(windows)")}
    for name, kind in ADDED:
        if name not in have:
            db.execute(f"alter table windows add column {name} {kind}")
    return db


def answered(assistant, answer, heard, clip=None):
    """The answer to her last question on this assistant (yes, no, or new request: something else said), with
    the words as heard, before any clean-up, and Oread's clip of it: kept on the newest window she asked, never
    on an older one."""
    if not DB:
        return
    try:
        with contextlib.closing(_open()) as db, db:
            db.execute("update windows set answer = ?, answer_heard = ?, answer_at = ?, answer_clip = ? where answer is null "
                       "and id = (select max(id) from windows where assistant is ? and asked = 1)",
                       (answer, heard, time.time(), clip, assistant))
    except Exception:
        pass


def rows(since=0.0, limit=1000):
    """The windows weighed since a time (seconds since 1970), oldest first, for Oread to pull (GET /learn/windows):
    each with Oread's clip of the request and of the answer, so the yes and no answers are labeled audio."""
    if not DB or not os.path.exists(DB):
        return []
    with contextlib.closing(_open()) as db:
        got = db.execute(f"select {', '.join(FIELDS)} from windows where at > ? order by id limit ?",
                         (float(since or 0), max(1, min(int(limit or 1000), 5000)))).fetchall()
    return [dict(zip(FIELDS, r)) for r in got]


def record(assistant, row):
    """A window weighed, asked or not (data/tables/window.db). Never fails the request."""
    if not DB:
        return
    try:
        with contextlib.closing(_open()) as db, db:
            db.execute("insert into windows (at, assistant, heard, meant, seed, never, close_by, app, a, b, lr, k, e, p, l, "
                       "asked, clip, device) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (time.time(), assistant, row["heard"], row["meant"], row["seed"], row["never"], row["close_by"],
                        row["app"], row["a"], row["b"], row["lr"], row["k"], row["e"],
                        None if row["p"] is None else round(row["p"], 4), None if row["l"] is None else round(row["l"], 4),
                        int(row["asked"]), row.get("clip"), row.get("device")))
    except Exception:
        pass
