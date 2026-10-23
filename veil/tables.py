# veil/tables.py - a slow app's table: its own SQLite file, data/tables/<app>.db (Oct 21).
#
# Data that changes slowly (Liturgical calendar's feasts, Wikipedia's on-this-day) is read from the app
# once and kept here until its hold runs out (services: <app>: table: hold_days, 180 for the calendar),
# so it goes Off-Platform a few times a year instead of every hour. Fast data (the weather) is never
# kept, and an app's own records (Vikunja's chores) are read live when a request involves them.
#
# One file per app: SQLite locks a whole file, so a refill never waits on another app or on the
# activity log; an app's table is rebuilt by replacing its file; the nightly backup copies it.
#
#   reads    address, at, answer        each GET the app answered, as it came (JSON), and when
#   things   address, id, name, day, weight, item
#            the things in that answer, one row each, with the fields its list card names (its id and
#            name; its date and its weight when it has them) and the whole thing as it came (JSON)
#
# The router reads the answer back as it came; the rows are its things with known fields, for a
# question asked of the table itself (what's on a day, a name) and for a person to look at.

import contextlib
import json
import logging
import os
import sqlite3
import threading
import time

log = logging.getLogger("router")

SCHEMA = """
create table if not exists reads (address text primary key, at real not null, answer text not null);
create table if not exists things (address text not null, id text not null, name text, day text, weight real,
                                   item text not null, primary key (address, id));
create index if not exists things_name on things (name);
create index if not exists things_day on things (day);
"""


class Table:
    """One slow app's reads and things (data/tables/<app>.db), held hold_days."""

    def __init__(self, app, folder, hold_days):
        self.app, self.hold = app, float(hold_days) * 86400
        self.path = os.path.join(folder, f"{app}.db")
        self._lock = threading.Lock()
        os.makedirs(folder, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level="IMMEDIATE")      # a writer waits its turn
        try:
            db.execute("pragma journal_mode=wal")
            with db:
                yield db
        finally:
            db.close()

    def get(self, address, stale=False):
        """(when it was read, the answer as it came) while it's held (stale: however old), else None."""
        with self._lock, self._db() as db:
            row = db.execute("select at, answer from reads where address = ?", (address,)).fetchone()
        if not row or (not stale and time.time() - row[0] > self.hold):
            return None
        return row[0], json.loads(row[1])

    def put(self, address, answer, things=None, card=None):
        """The app's answer for an address, and the things in it as rows (card: its list card's id, name and
        weight fields; the date is the first field every thing has as a date)."""
        from veil import rules
        card = card or {}
        rows = []
        things = [x for x in things or [] if isinstance(x, dict)]
        if things:
            idf, nf = card.get("id") or "id", card.get("name") or "name"
            df = rules.date_field(things)
            wf = (card.get("weight") or {}).get("field")
            for n, x in enumerate(things):
                w = x.get(wf) if wf else None
                rows.append((address, str(x.get(idf) if x.get(idf) is not None else n), str(x.get(nf) or ""),
                             str(x.get(df))[:10] if df and x.get(df) else None,
                             float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None,
                             json.dumps(x, default=str)))
        with self._lock, self._db() as db:
            db.execute("insert or replace into reads values (?, ?, ?)", (address, time.time(), json.dumps(answer, default=str)))
            db.execute("delete from things where address = ?", (address,))
            db.executemany("insert or replace into things values (?, ?, ?, ?, ?, ?)", rows)
        log.info("  %s: kept in its table (%s), %d things, for %.0f days", self.app, address, len(rows), self.hold / 86400)

    def on_day(self, day):
        """The things on a day (YYYY-MM-DD), from every address: the table asked directly."""
        with self._lock, self._db() as db:
            return [json.loads(r[0]) for r in db.execute("select item from things where day = ? order by weight desc", (day,))]

    def size(self):
        """(addresses, things) kept."""
        with self._lock, self._db() as db:
            return (db.execute("select count(*) from reads").fetchone()[0], db.execute("select count(*) from things").fetchone()[0])
