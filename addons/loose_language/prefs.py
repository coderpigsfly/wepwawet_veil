# addons/loose_language/prefs.py - Loose language (an add-on, issue #25): each person's preferences for loose language (issue #19): what "morning" means to
# Mara, how she likes to be reminded. Only the answers given are kept, never a whole matrix: one row
# per (person, term, context), the value last picked. The offer is the most specific row there is:
#   (person, term, this day) -> (person, term, weekday | weekend) -> (person, term, any) -> none
# (none: the house default, vocab/language.yaml part_times, is offered and asked about).
# Kept in data/veil.db (never in git); a preference only changes new requests, never ones made.
#
#   prefs   person, term (morning, remind_by...), context (saturday, weekend, "" for any), value, picked

import datetime as dt
import os
import sqlite3
import threading

from veil import config

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_LOCK = threading.Lock()


def _db(path=None):
    db = sqlite3.connect(path or os.path.join(config.DATA_DIR, "veil.db"), timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS prefs (person TEXT NOT NULL, term TEXT NOT NULL, context TEXT NOT NULL,"
               " value TEXT NOT NULL, picked TEXT NOT NULL, PRIMARY KEY (person, term, context))")
    return db


def contexts(day):
    """The contexts a day belongs to, most specific first: its name, weekday or weekend, any ("")."""
    if day is None:
        return [""]
    name = WEEKDAYS[day.weekday()]
    return [name, "weekend" if day.weekday() >= 5 else "weekday", ""]


def offer(person, term, day=None, path=None):
    """The person's value for the term on that day (the most specific there is), or None."""
    if not person:
        return None
    with _LOCK:
        db = _db(path)
        try:
            for ctx in contexts(day):
                row = db.execute("SELECT value FROM prefs WHERE person = ? AND term = ? AND context = ?",
                                 (person, term, ctx)).fetchone()
                if row:
                    return row[0]
        finally:
            db.close()
    return None


def pick(person, term, value, day=None, path=None):
    """The person picked this value, asked on that day: kept for that day (its name), and as their
    any-day value, so a day with none of its own is offered their last pick."""
    if not person or value in (None, ""):
        return
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        db = _db(path)
        try:
            with db:
                ctx = contexts(day)[0]
                db.execute("INSERT OR REPLACE INTO prefs VALUES (?, ?, ?, ?, ?)", (person, term, ctx, str(value), now))
                if ctx:
                    db.execute("INSERT OR REPLACE INTO prefs VALUES (?, ?, '', ?, ?)", (person, term, str(value), now))
        finally:
            db.close()


def rows(person=None, path=None):
    """Every preference kept (one person's, or everyone's), for the pages and the tests."""
    with _LOCK:
        db = _db(path)
        try:
            q = "SELECT person, term, context, value, picked FROM prefs" + (" WHERE person = ?" if person else "")
            return [dict(zip(("person", "term", "context", "value", "picked"), r))
                    for r in db.execute(q + " ORDER BY person, term, context", (person,) if person else ())]
        finally:
            db.close()
