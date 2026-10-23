"""addons/trainer: who has trainer mode on (dev-house-router #29). The core asks it, on each request, whether the
person the voice ID is sure of is being trained, and switches it (by voice or on its page); the routine itself (her
announcement, a chore's name, date, time and who it's for) is the core's pending question, kind trainer."""

import contextlib
import os
import sqlite3
import time

import yaml

SET = {"topics": [], "changers": [], "command_words": [], "on_words": [], "off_words": [], "condition_openers": [],
       "asking_after": [], "name_leads": []}
DB = None
SCHEMA = "create table if not exists people (name text primary key, on_ integer not null, by text, at real not null);"


def setup(folder):
    """Its own settings (settings.yaml beside it), and where it keeps who's on (the core's data folder)."""
    global DB
    path = os.path.join(folder, "settings.yaml")
    if os.path.exists(path):
        with open(path) as f:
            SET.update(yaml.safe_load(f) or {})
    try:
        from veil import config
        DB = config.path("data", "tables", "trainer.db")
    except Exception:
        DB = None


def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB, timeout=5)
    db.executescript(SCHEMA)
    return db


def settings():
    """Its settings, for the core (the topics it trains, the words that switch it)."""
    return SET


def is_on(person):
    """Is trainer mode on for this person (by name, any case)? Read on every request: a switch needs no restart."""
    if not DB or not person or not os.path.exists(DB):
        return False
    with contextlib.closing(_db()) as db:
        row = db.execute("select on_ from people where lower(name) = lower(?)", (str(person),)).fetchone()
    return bool(row and row[0])


def set_on(person, on, by=None):
    """Turn trainer mode on or off for a person; who did it and when are kept."""
    if not DB or not str(person or "").strip():
        return
    with contextlib.closing(_db()) as db, db:
        db.execute("delete from people where lower(name) = lower(?)", (str(person),))
        db.execute("insert into people values (?, ?, ?, ?)", (str(person).strip(), int(bool(on)), by, time.time()))


def people_on():
    """{person: {on, by, at}} for everyone ever switched."""
    if not DB or not os.path.exists(DB):
        return {}
    with contextlib.closing(_db()) as db:
        return {n: {"on": bool(o), "by": b, "at": a} for n, o, b, a in db.execute("select name, on_, by, at from people")}
