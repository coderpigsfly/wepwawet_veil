# veil/activity.py - what came in, what went out, and the bank of Off-Platform answers.
# One SQLite file, data/veil.db (a "saved database type for now and for review").
#
#   activity   every request the router handles: when, which assistant, who spoke (if Oread
#              is on), what was heard, the path and why, who answered (the engine) and where it
#              went (sent_to: the Off-Platform model, e.g. gemini-lite), what she said, how long
#              each hop took (Time Routes), and whether the firewall stopped it. The Transactions
#              page. Kept activity: keep_days (14) / keep_rows (20000). Also how busy the whole
#              machine was (load) and, on routes that leave the house, the internet check
#              (net_ms, net_method, net_at: veil/netcheck.py), for Stats' Which leg. From the
#              audio path, Oread's clip id and device (clip, device), so a mishearing recorded
#              from the row keeps them (Oread pulls the list and looks the clip up itself).
#   bank       the Off-Platform bank, per personality (today the assistant: iris, felix;
#              a personality may move between devices later): one row per identical request
#              (the cleaned words, the key) that had to go Off-Platform, classified by the
#              sentence (question, command, need, telling...), with how often it was heard
#              (count) and how often it actually went Off-Platform (trips). A row you add (Add
#              on the Transactions page, or on the bank page) becomes a replacement answer.
#   bank_answers  the Off-Platform answers kept for a row: the newest T (activity:
#              bank_answers_kept), each a spoken answer or a device command (a tool call, with
#              the words she said after it).
#   bank_results  what the Off-Platform model turned each request into, counted: a tool call
#              (the command and its arguments, e.g. HassTurnOn {"name": "kitchen light"}) or an
#              answer. The same result from different wordings is one result with many variants.
#
# Answering from the bank (activity: answer_from_bank, off unless you turn it on), your formula:
#   N = trips - 1                (Off-Platform trips of these words; times the bank answered don't count)
#   T = bank_answers_kept        (answers kept per saying; one setting for every saying)
#   Q = N / T, at most 100%      (the quota)
#   U = bank_use_from            (the threshold)
# An added row with Q >= U is answered from the bank Q of the time (at random); the rest of the
# time it goes Off-Platform, which counts a trip, so Q climbs to 100%. From the bank: one of
# the kept answers at random; a device command only when every kept answer is that same
# command (otherwise it goes Off-Platform). One-offs (asked once, older than trim_days, not
# added or reviewed) are trimmed away.

import json
import os
import random
import sqlite3
import threading
import time

from veil import util

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time REAL NOT NULL,
  assistant TEXT, speaker TEXT, speaker_score REAL, speaker_label TEXT,
  heard TEXT, path TEXT, kind TEXT, topic TEXT, score REAL, why TEXT,
  engine TEXT, sent_to TEXT, answer TEXT, ms REAL, blocked TEXT, status INTEGER, est_tokens INTEGER,
  bank_id INTEGER, t_speech REAL, t_stt REAL, t_ha_in REAL, t_decide REAL, t_engine REAL, marked TEXT,
  cpu_ms REAL, load REAL, net_ms REAL, net_method TEXT, net_at REAL, clip TEXT, device TEXT,
  t_litellm REAL, repeats INTEGER, t_relay REAL, t_back REAL
);
CREATE INDEX IF NOT EXISTS activity_time ON activity(time);
CREATE TABLE IF NOT EXISTS bank (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  personality TEXT NOT NULL DEFAULT '',
  key TEXT NOT NULL,
  heard TEXT, class TEXT, qword TEXT, topic_guess TEXT, topic_score REAL,
  assistant TEXT, count INTEGER DEFAULT 1, trips INTEGER DEFAULT 0, used INTEGER DEFAULT 0,
  first REAL, last REAL, review TEXT DEFAULT 'new', note TEXT DEFAULT '', added REAL,
  generic INTEGER DEFAULT 0,
  UNIQUE (personality, key)
);
CREATE TABLE IF NOT EXISTS bank_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_id INTEGER NOT NULL, time REAL, answer TEXT, model TEXT, ms REAL, tool_calls TEXT, kind TEXT
);
CREATE INDEX IF NOT EXISTS bank_answers_bank ON bank_answers(bank_id);
CREATE TABLE IF NOT EXISTS bank_results (
  bank_id INTEGER NOT NULL, sig TEXT NOT NULL, kind TEXT, name TEXT, args TEXT,
  count INTEGER DEFAULT 0, first REAL, last REAL, final TEXT,
  PRIMARY KEY (bank_id, sig)
);
CREATE INDEX IF NOT EXISTS bank_results_sig ON bank_results(sig);
CREATE TABLE IF NOT EXISTS route_days (
  day TEXT NOT NULL, route TEXT NOT NULL, assistant TEXT NOT NULL DEFAULT '', n INTEGER, ms TEXT,
  PRIMARY KEY (day, route, assistant)
);
CREATE TABLE IF NOT EXISTS resources (
  hour INTEGER PRIMARY KEY, minutes INTEGER, cpu_sum REAL, cpu_max REAL, mem_sum REAL, mem_max REAL
);
"""

BANK_COLUMNS = ("id", "personality", "key", "heard", "class", "qword", "topic_guess", "topic_score", "assistant",
                "count", "trips", "used", "first", "last", "review", "note", "added")
HOPS = ("t_speech", "t_stt", "t_relay", "t_ha_in", "t_decide", "t_litellm", "t_engine", "ms", "t_back")

# columns added later: (table, column, type); added to an older veil.db at start
MIGRATIONS = [("activity", "est_tokens", "INTEGER"), ("activity", "bank_id", "INTEGER"),
              ("activity", "t_speech", "REAL"), ("activity", "t_stt", "REAL"), ("activity", "t_ha_in", "REAL"),
              ("activity", "t_decide", "REAL"), ("activity", "t_engine", "REAL"),
              ("activity", "marked", "TEXT"), ("bank_answers", "kind", "TEXT"), ("activity", "cpu_ms", "REAL"),
              ("bank", "generic", "INTEGER DEFAULT 0"), ("activity", "load", "REAL"), ("activity", "net_ms", "REAL"),
              ("activity", "net_method", "TEXT"), ("activity", "net_at", "REAL"),
              ("activity", "clip", "TEXT"), ("activity", "device", "TEXT"), ("activity", "t_litellm", "REAL"),
              ("activity", "repeats", "INTEGER"), ("activity", "t_relay", "REAL"), ("activity", "t_back", "REAL")]

REVIEWS = ("new", "keep", "ignore", "promote")
QWORDS = ("what", "when", "where", "who", "whom", "whose", "why", "which", "how",
          "is", "are", "was", "were", "do", "does", "did", "can", "could", "will", "would",
          "should", "shall", "may", "might", "have", "has")


def signature(tool_calls):
    """(sig, names, args json) for what Gemini asked Home Assistant to do: the same commands
    with the same arguments are the same result, whatever words led there."""
    calls = []
    for c in tool_calls or []:
        args = c.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except ValueError:
                args = {"raw": args}
        if isinstance(args, dict):
            args = {k: (v.lower().strip() if isinstance(v, str) else v) for k, v in sorted(args.items())}
        calls.append({"name": c.get("name") or "", "arguments": args})
    names = ", ".join(c["name"] for c in calls)
    sig = "; ".join(f"{c['name']} {json.dumps(c['arguments'], sort_keys=True)}" for c in calls)
    return sig, names, json.dumps(calls)


key_of = util.words          # the bank key: the cleaned words, in order (veil/util.py)


class Activity:
    def __init__(self, path, keep_days=14, keep_rows=20000, answers_kept=5, trim_days=30,
                 use_from=0.2, rng=None):
        self.path = path
        self.keep_days = float(keep_days)
        self.keep_rows = int(keep_rows)
        self.answers_kept = int(answers_kept)          # T
        self.use_from = float(use_from)                # U
        self.trim_days = float(trim_days or 0)
        self.answer_from_bank = False
        self.bank_top = 25
        self.summary_days = 30                         # the days a route's daily summary is kept (Stats' 30-day usual)
        self.rng = rng or random.Random()
        self._lock = threading.Lock()
        self._writes = 0
        self._commanded = {}       # bank row -> (time, sig) of the device command its last trip became
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._db() as db:
            self._bank_v2(db)                            # before SCHEMA, so the old bank is rebuilt
            db.executescript(SCHEMA)
            for table, col, kind in MIGRATIONS:          # columns added after the first release
                have = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
                if col not in have:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
            self._answers_v2(db)
            # device commands are never kept as bank answers (decided Oct 14): the ones kept before go
            db.execute("DELETE FROM bank_answers WHERE kind = 'tool'")

    @staticmethod
    def _bank_v2(db):
        """An older veil.db had one bank for every personality (key UNIQUE). Rebuild it per
        personality (the row's assistant), keeping every id, so answers and results still match;
        its trips start as its count (until now every count was a trip out)."""
        have = {r[1] for r in db.execute("PRAGMA table_info(bank)")}
        if not have or "personality" in have:
            return
        db.execute("ALTER TABLE bank RENAME TO bank_v1")
        db.executescript(SCHEMA)
        cols = [c for c in BANK_COLUMNS if c in have and c not in ("personality", "trips", "used")]
        db.execute(f"INSERT INTO bank ({', '.join(cols)}, personality, trips, used) "
                   f"SELECT {', '.join(cols)}, COALESCE(assistant, ''), count, 0 FROM bank_v1")
        db.execute("DROP TABLE bank_v1")

    @staticmethod
    def _answers_v2(db):
        """Older answers have no kind: a tool call, or words. Words said right after a tool call
        (the second trip) were kept as their own answer; they belong to the tool call."""
        rows = db.execute("SELECT id, bank_id, time, answer, tool_calls FROM bank_answers WHERE kind IS NULL "
                          "ORDER BY bank_id, id").fetchall()
        prev = None
        for r in rows:
            if r[4]:
                db.execute("UPDATE bank_answers SET kind = 'tool' WHERE id = ?", (r[0],))
            elif prev and prev[1] == r[1] and prev[4] and r[2] - prev[2] < 120:
                db.execute("UPDATE bank_answers SET answer = ? WHERE id = ?", (r[3], prev[0]))
                db.execute("DELETE FROM bank_answers WHERE id = ?", (r[0],))
                continue
            else:
                db.execute("UPDATE bank_answers SET kind = 'answer' WHERE id = ?", (r[0],))
            prev = r

    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    # ---------- activity ----------

    def add(self, **row):
        row = dict(row)
        row.setdefault("time", time.time())
        if isinstance(row.get("why"), (list, tuple)):
            row["why"] = json.dumps(list(row["why"]))
        cols = ("time", "assistant", "speaker", "speaker_score", "speaker_label", "heard", "path",
                "kind", "topic", "score", "why", "engine", "sent_to", "answer", "ms", "blocked", "status",
                "est_tokens", "bank_id", "t_speech", "t_stt", "t_ha_in", "t_decide", "t_engine", "cpu_ms", "load",
                "clip", "device", "t_litellm", "t_relay")
        vals = [row.get(c) for c in cols]
        with self._lock, self._db() as db:
            cur = db.execute(f"INSERT INTO activity ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
            self._writes += 1
            if self._writes % 50 == 1:
                self._prune(db)
            return cur.lastrowid

    def finish(self, rid, **changes):
        """Fill in what's known only after the answer (Gemini's words, the time taken)."""
        if not rid or not changes:
            return
        sets = ", ".join(f"{k} = ?" for k in changes)
        with self._lock, self._db() as db:
            db.execute(f"UPDATE activity SET {sets} WHERE id = ?", [*changes.values(), rid])

    def repeated(self, rid):
        """The same request came in again while this one was being answered (Stats: Sent again)."""
        if rid:
            with self._lock, self._db() as db:
                db.execute("UPDATE activity SET repeats = COALESCE(repeats, 0) + 1 WHERE id = ?", (rid,))

    @staticmethod
    def _midnight(t):
        """The house's midnight (its clock: config.use_house_clock) starting the day t is in."""
        lt = time.localtime(t)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))

    def _summarize(self, db, now=None):
        """One summary row per day, route and assistant for each whole day before today (the house's
        days): how many and every time (ms) taken, so Stats' usual covers 30 days while the log
        keeps its own keep_days (14). Days summarized once stay as they were; older than
        summary_days go."""
        now = now or time.time()
        done = {r[0] for r in db.execute("SELECT DISTINCT day FROM route_days")}
        groups = {}
        for r in db.execute("SELECT time, path, engine, ms, COALESCE(assistant, '') a FROM activity "
                            "WHERE time < ? AND ms IS NOT NULL", (self._midnight(now),)):
            day = time.strftime("%Y-%m-%d", time.localtime(r["time"]))
            if day not in done:
                groups.setdefault((day, self.route_of(r), r["a"]), []).append(round(r["ms"], 1))
        for (day, route, who), ms in groups.items():
            db.execute("INSERT OR IGNORE INTO route_days (day, route, assistant, n, ms) VALUES (?, ?, ?, ?, ?)",
                       (day, route, who, len(ms), json.dumps(sorted(ms))))
        db.execute("DELETE FROM route_days WHERE day < ?",
                   (time.strftime("%Y-%m-%d", time.localtime(now - float(self.summary_days) * 86400)),))

    def swap_uses(self, heards):
        """How many logged requests had each swap made, and the last (epoch seconds): {heard: (n, last)}.
        Found in each request's trace, where a swap says it was made (the words step's 'heard "X",
        used', or the audio path's 'for "X"')."""
        out = {}
        with self._db() as db:
            for w in heards:
                r = db.execute("SELECT COUNT(*), MAX(time) FROM activity WHERE why LIKE ? OR why LIKE ?",
                               (f'%heard \\"{w}\\", used%', f'%for \\"{w}\\"%')).fetchone()   # the trace is kept as JSON (quotes as \\")
                out[w] = (r[0], r[1])
        return out

    def usual_since(self, assistant=None):
        """The first day Stats' usual covers (epoch seconds of its midnight), or None."""
        with self._db() as db:
            q, args = ("SELECT MIN(day) FROM route_days WHERE assistant = ?", (assistant,)) if assistant \
                else ("SELECT MIN(day) FROM route_days", ())
            day = db.execute(q, args).fetchone()[0]
        if not day:
            return None
        y, m, d = (int(x) for x in day.split("-"))
        return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))

    def _prune(self, db):
        self._summarize(db)                  # before the log's own old rows go
        if self.trim_days:
            cut = time.time() - float(self.trim_days) * 86400
            for r in db.execute("SELECT id FROM bank WHERE count <= 1 AND last < ? AND review = 'new' "
                                "AND added IS NULL", (cut,)).fetchall():   # one-offs, not added or reviewed
                for t in ("bank_answers", "bank_results"):
                    db.execute(f"DELETE FROM {t} WHERE bank_id = ?", (r["id"],))
                db.execute("DELETE FROM bank WHERE id = ?", (r["id"],))
        db.execute("DELETE FROM activity WHERE time < ?", (time.time() - self.keep_days * 86400,))
        db.execute("DELETE FROM activity WHERE id <= (SELECT MAX(id) FROM activity) - ?", (self.keep_rows,))

    # the Transactions page's sortable columns: name -> what it sorts by (ties: newest first)
    SORTS = {
        "time": ["a.id {dir}"],
        "assistant": ["a.assistant IS NULL", "a.assistant COLLATE NOCASE {dir}"],
        "speaker": ["a.speaker IS NULL", "a.speaker COLLATE NOCASE {dir}"],
        "heard": ["a.heard IS NULL", "a.heard COLLATE NOCASE {dir}"],
        "went": ["CASE WHEN a.blocked IS NOT NULL THEN 'blocked' ELSE COALESCE(a.engine, '') END {dir}",
                 "COALESCE(a.sent_to, '') {dir}", "COALESCE(a.topic, '') {dir}"],
        "said": ["a.answer IS NULL", "a.answer COLLATE NOCASE {dir}"],
    }

    def echoes(self, limit=500):
        """The echoes of her own answers that have a clip (newest first): clip, device, heard, when, why."""
        with self._lock, self._db() as db:
            rows = db.execute("SELECT time, device, clip, heard, why FROM activity WHERE kind = 'echo' AND clip IS NOT NULL "
                              "ORDER BY time DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"clip": r["clip"], "device": r["device"], "heard": r["heard"], "why": r["why"],
                 "when": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(r["time"]))} for r in rows]

    def recent(self, limit=100, before=None, direction=None, assistant=None, search=None, handled="all",
               sort="time", descending=True, offset=0):
        """Newest first, each with in_bank (its bank row was added). direction: 'out' = what left
        the router (Off-Platform or an app), 'gemini' = what went Off-Platform, 'home' = answered
        at home (the bank included), 'blocked' = stopped by the firewall. handled: 'hide' leaves
        out the rows dealt with (recorded as misheard or banked: activity.marked; or a saying
        that's in the bank, Oct 14: once banked it doesn't stay on the list), 'only' shows just
        those, 'all' both. sort: a column of SORTS, descending or not; sorted by anything but time,
        the next page is by offset (before is the newest-first cursor)."""
        q, args = ("SELECT a.*, b.added in_bank FROM activity a LEFT JOIN bank b ON b.id = a.bank_id "
                   "WHERE 1=1"), []
        sort = sort if sort in self.SORTS else "time"
        if before and sort == "time" and descending:
            q += " AND a.id < ?"
            args.append(int(before))
        if direction == "out":
            q += " AND (a.engine IS NOT NULL AND a.engine NOT IN ('router', '') OR a.sent_to IS NOT NULL)"
        elif direction == "gemini":
            q += " AND a.engine = 'gemini'"
        elif direction == "home":
            q += " AND a.engine IS NOT NULL AND a.engine != 'gemini' AND a.blocked IS NULL"
        elif direction == "blocked":
            q += " AND a.blocked IS NOT NULL"
        dealt = "(a.marked IS NOT NULL OR b.added IS NOT NULL)"
        if handled == "hide":
            q += f" AND NOT {dealt}"
        elif handled == "only":
            q += f" AND {dealt}"
        if assistant:
            q += " AND a.assistant = ?"
            args.append(assistant)
        if search:
            q += " AND (a.heard LIKE ? OR a.answer LIKE ?)"
            args += [f"%{search}%", f"%{search}%"]
        way = "DESC" if descending else "ASC"
        order = [x.format(dir=way) for x in self.SORTS[sort]]
        if sort != "time":
            order.append("a.id DESC")
        q += " ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?"
        args += [max(1, min(int(limit), 500)), max(0, int(offset or 0))]
        with self._db() as db:
            rows = [dict(r) for r in db.execute(q, args)]
        for r in rows:
            r["in_bank"] = bool(r.get("in_bank"))
            try:
                r["why"] = json.loads(r["why"]) if r.get("why") else []
            except ValueError:
                r["why"] = [r["why"]]
        return rows

    def bank_add_from(self, activity_id):
        """The + on the Transactions page: add that request's bank row as a replacement answer."""
        with self._lock, self._db() as db:
            a = db.execute("SELECT bank_id, engine, heard FROM activity WHERE id = ?", (int(activity_id),)).fetchone()
            if not a:
                raise ValueError("That transaction isn't in the log any more")
            if a["engine"] not in ("gemini", "bank") or not a["bank_id"]:
                raise ValueError("Only a request that went Off-Platform can be added to the bank")
            db.execute("UPDATE bank SET added = COALESCE(added, ?) WHERE id = ?", (time.time(), a["bank_id"]))
            db.execute("UPDATE activity SET marked = 'banked' WHERE id = ?", (int(activity_id),))   # this row: handled
            row = db.execute("SELECT * FROM bank WHERE id = ?", (a["bank_id"],)).fetchone()
        if not row:
            raise ValueError("Its bank row was trimmed away")
        return dict(row)

    def bank_upload(self, personality, key, heard, answers, generic=True):
        """A saying and the ways it may be answered, put in the bank by hand (the generic upload, dump19):
        added, generic as said, with trips enough that the bank always answers it (Q = 100%: no
        Off-Platform trip needed). Returns its bank row's id."""
        now = time.time()
        pers = str(personality or "")
        with self._lock, self._db() as db:
            row = db.execute("SELECT id FROM bank WHERE personality = ? AND key = ?", (pers, key)).fetchone()
            trips = max(1, int(self.answers_kept)) + 1
            if row:
                bid = row["id"]
                db.execute("UPDATE bank SET added = COALESCE(added, ?), generic = ?, trips = MAX(trips, ?), last = ? WHERE id = ?",
                           (now, 1 if generic else 0, trips, now, bid))
            else:
                bid = db.execute("INSERT INTO bank (personality, key, heard, class, qword, topic_guess, topic_score, assistant, "
                                 "count, trips, used, first, last, added, generic) VALUES (?, ?, ?, 'uploaded', '', NULL, NULL, ?, 0, ?, 0, ?, ?, ?, ?)",
                                 (pers, key, heard, pers, trips, now, now, now, 1 if generic else 0)).lastrowid
            for a in answers:
                db.execute("INSERT INTO bank_answers (bank_id, time, answer, model, ms, tool_calls, kind) "
                           "VALUES (?, ?, ?, 'uploaded', NULL, NULL, 'answer')", (bid, now, a))
            self._keep_newest(db, bid)
        return bid

    def bank_row(self, bank_id):
        """A bank row and the answers kept for it ({..., answers: [...]}), or None."""
        with self._db() as db:
            row = db.execute("SELECT * FROM bank WHERE id = ?", (int(bank_id),)).fetchone()
            if not row:
                return None
            kept = [r["answer"] for r in db.execute("SELECT answer FROM bank_answers WHERE bank_id = ? AND kind = 'answer' "
                                                     "ORDER BY id DESC", (int(bank_id),)) if (r["answer"] or "").strip()]
        return dict(row, answers=kept)

    def similar_key(self, personality, key, drop, share):
        """An added saying of this personality's whose words are nearly these (share of the words of
        both, little words left out: "what's the capital of pennsylvania" and "what is pennsylvania's
        capital"), or None: the bank answers similar sayings too (dump19)."""
        words = {w for w in str(key).split() if w not in drop}
        if not words or not share:
            return None
        best = None
        with self._db() as db:
            for r in db.execute("SELECT key FROM bank WHERE personality = ? AND added IS NOT NULL", (str(personality or ""),)):
                other = {w for w in str(r["key"]).split() if w not in drop}
                if not other:
                    continue
                s = len(words & other) / len(words | other)
                if s >= share and (best is None or s > best[0]):
                    best = (s, r["key"])
        return best[1] if best else None

    def bank_set_added(self, bank_id, added):
        with self._lock, self._db() as db:
            db.execute("UPDATE bank SET added = ? WHERE id = ?", (time.time() if added else None, int(bank_id)))
            row = db.execute("SELECT * FROM bank WHERE id = ?", (int(bank_id),)).fetchone()
        return dict(row) if row else None

    def delete(self, activity_id):
        """Delete on the Transactions page: a transaction that teaches nothing (right, and routed
        right). Its bank row, if any, keeps its counts."""
        with self._lock, self._db() as db:
            n = db.execute("DELETE FROM activity WHERE id = ?", (int(activity_id),)).rowcount
        if not n:
            raise ValueError("That transaction isn't in the log any more")

    def mark(self, activity_id, what):
        """Misheard on the Transactions page: the row shows it was recorded."""
        with self._lock, self._db() as db:
            db.execute("UPDATE activity SET marked = ? WHERE id = ?", (what, int(activity_id)))

    def get(self, activity_id):
        with self._db() as db:
            r = db.execute("SELECT * FROM activity WHERE id = ?", (int(activity_id),)).fetchone()
        return dict(r) if r else None

    @staticmethod
    def route_of(r):
        """The route a logged request took (Stats): off_platform, bank, home_assistant, musings (the
        router's own small things that aren't apps: brain fleas, Stats' Wepwawet Musings), router or
        app:<name>. Her words after a device command are an Off-Platform trip like any other."""
        if "path" in r.keys() and r["path"] == "flea":
            return "musings"
        engine = r["engine"]
        if engine == "gemini":
            return "off_platform"
        if engine in ("bank", "home_assistant"):
            return engine
        if engine == "router" or not engine:
            return "router"
        return "app:" + engine

    @staticmethod
    def _spread(vals):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        return {"n": len(vals), "median": round(vals[len(vals) // 2], 1),
                "p90": round(vals[min(len(vals) - 1, int(len(vals) * 0.9))], 1),
                "mean": round(sum(vals) / len(vals), 1), "total": round(sum(vals), 1)}

    @staticmethod
    def _who(assistant):
        """(extra SQL, its value) for one assistant's requests only (Stats: the Assistant choice)."""
        return (" AND assistant = ?", (assistant,)) if assistant else ("", ())

    def time_routes(self, since, limit=5000, assistant=None):
        """Time Routes: for each route a request took, how long each hop took and the router's CPU
        for it (median, slowest tenth, mean and total, in ms), from the newest rows since a time;
        stt_per_s: Oread's time per second of speech (its time grows with how long the person spoke);
        repeats: the same request coming in again while it was being answered (LiteLLM's retry)."""
        with self._db() as db:
            extra, val = self._who(assistant)
            rows = db.execute(f"SELECT path, engine, cpu_ms, repeats, {', '.join(HOPS)} FROM activity WHERE time >= ?{extra} "
                              "ORDER BY id DESC LIMIT ?", (since, *val, int(limit))).fetchall()
        groups = {}
        for r in rows:
            groups.setdefault(self.route_of(r), []).append(r)
        out = []
        for route, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            hops = {}
            for h in HOPS + ("cpu_ms",):
                got = self._spread(r[h] for r in rs)
                if got:
                    hops[h] = got
            per_s = self._spread(r["t_stt"] / (r["t_speech"] / 1000) for r in rs if r["t_stt"] is not None and r["t_speech"])
            if per_s:
                hops["stt_per_s"] = per_s
            # the model's own share of the Off-Platform hop: the hop less LiteLLM's own time
            model = self._spread(r["t_engine"] - r["t_litellm"] for r in rs if r["t_engine"] is not None and r["t_litellm"] is not None)
            if model:
                hops["t_model"] = model
            out.append({"route": route, "requests": len(rs), "hops": hops,
                        "repeats": sum(r["repeats"] or 0 for r in rs)})
        return out

    def span(self, since, assistant=None):
        """How much the log really holds since a time: the oldest and newest request, and how many
        (a period longer than the log is kept shows only what's there)."""
        with self._db() as db:
            extra, val = self._who(assistant)
            r = db.execute(f"SELECT MIN(time) AS first, MAX(time) AS last, COUNT(*) AS n FROM activity WHERE time >= ?{extra}",
                           (since, *val)).fetchone()
        return dict(r)

    def legs(self, now, tz_minutes=0, slower=1.5, min_requests=3, net_slower=2.0, assistant=None, show=10):
        """Which leg was slow: for each route today against usual (every kept day before today),
        the typical time of the router's own work (own_ms: its time less the outside hop), its
        CPU, how busy the machine was (load) and the outside hop (t_engine), each slow: true at
        `slower` times usual or more (today has min_requests). The internet checks today against
        usual (one per check, same method only), slow at `net_slower` times. And the newest
        `show` requests whose outside hop was `slower` times its route's typical, with the
        internet check they carry (net_after: seconds from the request to the check; below 0 the
        last check, taken before it inside the cool-down)."""
        with self._db() as db:
            extra, val = self._who(assistant)
            rows = db.execute(f"SELECT id, time, heard, path, engine, ms, t_engine, cpu_ms, load, net_ms, net_method, net_at "
                              f"FROM activity WHERE ms IS NOT NULL{extra} ORDER BY time", val).fetchall()
        day_of = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t + tz_minutes * 60))   # noqa: E731
        today = day_of(now)
        legs = {"own_ms": lambda r: r["ms"] - (r["t_engine"] or 0), "cpu_ms": lambda r: r["cpu_ms"],
                "load": lambda r: r["load"], "t_engine": lambda r: r["t_engine"]}
        by = {}
        for r in rows:
            by.setdefault(self.route_of(r), []).append(r)
        compare = lambda t_, u_, n, x: {"today": t_, "usual": u_, "times": round(t_["median"] / u_["median"], 1),   # noqa: E731
                                        "slow": t_["n"] >= n and t_["median"] >= x * u_["median"]}             if t_ and u_ and u_["median"] > 0 else {"today": t_, "usual": u_}
        routes = []
        for route, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            now_, before = [r for r in rs if day_of(r["time"]) == today], [r for r in rs if day_of(r["time"]) != today]
            routes.append({"route": route, "today": len(now_), "usual": len(before),
                           "legs": {k: compare(self._spread(f(r) for r in now_), self._spread(f(r) for r in before),
                                               int(min_requests), float(slower)) for k, f in legs.items()}})
        checks = {}
        for r in rows:
            if r["net_at"] and r["net_ms"] is not None:
                checks[r["net_at"]] = (r["net_ms"], r["net_method"])
        method = checks[max(checks)][1] if checks else None
        same = {t: ms for t, (ms, m) in checks.items() if m == method}
        usual_net = self._spread(same.values())
        internet = dict(compare(self._spread(ms for t, ms in same.items() if day_of(t) == today),
                                self._spread(ms for t, ms in same.items() if day_of(t) != today), 1, float(net_slower)),
                        method=method, checks=len(same))
        typical = {route: self._spread(r["t_engine"] for r in rs) for route, rs in by.items()}
        slow = []
        for r in reversed(rows):
            t = typical.get(self.route_of(r))
            if len(slow) >= int(show):
                break
            if r["net_at"] and r["t_engine"] is not None and t and t["n"] >= int(min_requests) \
                    and r["t_engine"] >= float(slower) * t["median"]:
                slow.append({"id": r["id"], "time": r["time"], "heard": r["heard"], "route": self.route_of(r),
                             "t_engine": r["t_engine"], "typical": t["median"], "net_ms": r["net_ms"],
                             "net_method": r["net_method"], "net_after": round(r["net_at"] - r["time"]),
                             "net_usual": usual_net["median"] if usual_net and r["net_method"] == method else None,
                             "net_slow": bool(usual_net and r["net_ms"] is not None and r["net_method"] == method
                                              and r["net_ms"] >= float(net_slower) * usual_net["median"])})
        return {"routes": routes, "internet": internet, "slow_requests": slow, "slower": float(slower),
                "net_slower": float(net_slower), "first": rows[0]["time"] if rows else None}

    def route_trend(self, now, tz_minutes=0, days=30, slower=1.5, min_requests=3, assistant=None):
        """Is anything slow? Each route's typical time in the router (ms: the router's own work plus
        the app or the model it waited for) today, over 7 days and over 30, with slow: true when
        today's typical is at least `slower` times the 30-day typical (and today has min_requests);
        and the typical time day by day for the trend chart (None on a day without requests).
        The days before today come from the daily summaries (route_days), so the 30 days don't
        depend on how long the log keeps its rows; today comes from the log itself."""
        since = now - days * 86400
        day_of = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t + tz_minutes * 60))   # noqa: E731
        today = day_of(now)
        week_from = day_of(now - 7 * 86400)
        with self._lock, self._db() as db:
            self._summarize(db, now)
            extra, val = self._who(assistant)
            rows = db.execute(f"SELECT time, path, engine, ms FROM activity WHERE time >= ? AND ms IS NOT NULL{extra}",
                              (self._midnight(now), *val)).fetchall()
            q, args = "SELECT day, route, ms FROM route_days WHERE day >= ? AND day < ?", [day_of(since), today]
            if assistant:
                q, args = q + " AND assistant = ?", args + [assistant]
            sums = db.execute(q, args).fetchall()
        all_days = []
        t = since
        while t <= now + 86400:
            d = day_of(t)
            if d <= today and d not in all_days:
                all_days.append(d)
            t += 86400
        by = {}
        group = lambda route: by.setdefault(route, {"today": [], "week": [], "month": [], "days": {}})   # noqa: E731
        for r in sums:
            g, ms = group(r["route"]), json.loads(r["ms"] or "[]")
            g["month"] += ms
            if r["day"] >= week_from:
                g["week"] += ms
            g["days"].setdefault(r["day"], []).extend(ms)
        for r in rows:
            g = group(self.route_of(r))
            g["month"].append(r["ms"])
            g["week"].append(r["ms"])
            g["today"].append(r["ms"])
            g["days"].setdefault(today, []).append(r["ms"])
        routes = []
        for route, g in sorted(by.items(), key=lambda kv: -len(kv[1]["month"])):
            row = {"route": route, **{k: self._spread(g[k]) for k in ("today", "week", "month")}}
            t_, m_ = row["today"], row["month"]
            row["slow"] = bool(t_ and m_ and t_["n"] >= int(min_requests)
                               and m_["median"] > 0 and t_["median"] >= float(slower) * m_["median"])
            row["by_day"] = [(self._spread(g["days"].get(d, [])) or {}).get("median") for d in all_days]
            routes.append(row)
        return {"days": all_days, "routes": routes, "slower": float(slower), "min_requests": int(min_requests)}

    def top_cpu(self, since, n=10, assistant=None):
        """The requests that cost the router the most CPU since a time, one line per saying (the
        same cleaned words): the words as heard (to try again), times seen, the most and the
        typical CPU, the typical time, and the route it took last."""
        with self._db() as db:
            rows = db.execute("SELECT time, heard, path, engine, cpu_ms, ms, assistant, t_ha_in, t_decide, t_engine FROM activity "
                              f"WHERE time >= ? AND cpu_ms IS NOT NULL AND heard IS NOT NULL AND heard != ''{self._who(assistant)[0]} "
                              "ORDER BY id", (since, *self._who(assistant)[1])).fetchall()
        groups = {}
        for r in rows:
            k = key_of(r["heard"])
            if k:
                groups.setdefault(k, []).append(r)
        out = []
        for rs in groups.values():
            last = rs[-1]
            cpu = self._spread(r["cpu_ms"] for r in rs)
            out.append({"heard": last["heard"], "assistant": last["assistant"], "route": self.route_of(last),
                        "count": len(rs), "cpu_max": round(max(r["cpu_ms"] for r in rs), 1),
                        "cpu_median": cpu["median"], "ms_median": (self._spread(r["ms"] for r in rs) or {}).get("median"),
                        # the hops, typical: the front end and LiteLLM on the way in, the router deciding,
                        # the app or Off-Platform (to see whether a slow one was slow before the router)
                        **{f"{k}_median": (self._spread(r[k] for r in rs if r[k] is not None) or {}).get("median")
                           for k in ("t_ha_in", "t_decide", "t_engine")},
                        "last": last["time"]})
        out.sort(key=lambda x: -x["cpu_max"])
        return out[:max(1, int(n))]

    # ---------- what the router costs to run (veil/resources.py notes it) ----------

    def note_resources(self, now, cpu, mem, keep_days=30):
        hour = int(now // 3600 * 3600)
        with self._lock, self._db() as db:
            db.execute("INSERT INTO resources (hour, minutes, cpu_sum, cpu_max, mem_sum, mem_max) "
                       "VALUES (?, 1, ?, ?, ?, ?) ON CONFLICT(hour) DO UPDATE SET minutes = minutes + 1, "
                       "cpu_sum = cpu_sum + excluded.cpu_sum, cpu_max = MAX(cpu_max, excluded.cpu_max), "
                       "mem_sum = mem_sum + excluded.mem_sum, mem_max = MAX(mem_max, excluded.mem_max)",
                       (hour, cpu, cpu, mem, mem))
            db.execute("DELETE FROM resources WHERE hour < ?", (now - float(keep_days) * 86400,))

    def resources(self, now, periods=(("last_hour", 1), ("last_24_hours", 24), ("last_7_days", 168),
                                       ("last_30_days", 720))):
        """CPU and memory over each period (averages and peaks, from the hours), requests in it,
        and hour by hour over the last 7 days for the chart."""
        with self._db() as db:
            hours = [dict(r) for r in db.execute("SELECT * FROM resources WHERE hour >= ? ORDER BY hour",
                                                 (now - 720 * 3600,)).fetchall()]
            counts = {}
            for label, n in periods:
                counts[label] = db.execute("SELECT COUNT(*) FROM activity WHERE time >= ?",
                                           (now - n * 3600,)).fetchone()[0]
        out = {}
        for label, n in periods:
            rs = [h for h in hours if h["hour"] > now - n * 3600 - 3600]
            minutes = sum(h["minutes"] for h in rs)
            if not minutes:
                continue
            out[label] = {"hours_recorded": round(minutes / 60, 1),
                          "cpu_average": round(sum(h["cpu_sum"] for h in rs) / minutes, 1),
                          "cpu_busiest": round(max(h["cpu_max"] for h in rs), 1),
                          "memory_average": round(sum(h["mem_sum"] for h in rs) / minutes),
                          "memory_highest": round(max(h["mem_max"] for h in rs)),
                          "requests": counts[label]}
        week = [{"hour": h["hour"], "cpu_average": round(h["cpu_sum"] / h["minutes"], 1),
                 "cpu_busiest": round(h["cpu_max"], 1)} for h in hours if h["hour"] >= now - 168 * 3600 and h["minutes"]]
        return {"periods": out, "week": week}

    def shares(self, since, tz_minutes=0, assistant=None):
        """For the charts on Overview and Stats: where requests were answered (at home, the
        Off-Platform bank, Off-Platform, blocked), in all and day by day (days in the viewer's
        time zone: tz_minutes east of UTC), and how many came from each assistant."""
        with self._db() as db:
            extra, val = self._who(assistant)
            rows = db.execute(f"SELECT time, engine, blocked, assistant FROM activity WHERE time >= ?{extra}",
                              (since, *val)).fetchall()
        where = {"home": 0, "bank": 0, "off_platform": 0, "blocked": 0}
        days, assistants = {}, {}
        for r in rows:
            if r["blocked"]:
                k = "blocked"
            elif r["engine"] == "gemini":
                k = "off_platform"
            elif r["engine"] == "bank":
                k = "bank"
            else:
                k = "home"
            where[k] += 1
            day = time.strftime("%Y-%m-%d", time.gmtime(r["time"] + tz_minutes * 60))
            days.setdefault(day, dict.fromkeys(where, 0))[k] += 1
            a = r["assistant"] or "unknown"
            assistants[a] = assistants.get(a, 0) + 1
        # every day of the period, the empty ones too, so the days line up
        t, end = since, time.time()
        while t <= end + 86400:
            day = time.strftime("%Y-%m-%d", time.gmtime(t + tz_minutes * 60))
            if t <= end or day == time.strftime("%Y-%m-%d", time.gmtime(end + tz_minutes * 60)):
                days.setdefault(day, dict.fromkeys(where, 0))
            t += 86400
        return {"where": where, "by_day": [dict(day=d, **v) for d, v in sorted(days.items())],
                "by_assistant": sorted(assistants.items(), key=lambda kv: -kv[1])}

    def counts(self, since):
        with self._db() as db:
            rows = db.execute("SELECT path, engine, COUNT(*) n FROM activity WHERE time >= ? "
                              "GROUP BY path, engine", (since,)).fetchall()
            blocked = db.execute("SELECT COUNT(*) FROM activity WHERE time >= ? AND blocked IS NOT NULL",
                                 (since,)).fetchone()[0]
        out = {"total": 0, "home": 0, "gemini": 0, "home_assistant": 0, "blocked": blocked, "by_path": {}}
        for r in rows:
            out["total"] += r["n"]
            out["by_path"][r["path"] or "?"] = out["by_path"].get(r["path"] or "?", 0) + r["n"]
            if r["engine"] == "gemini":
                out["gemini"] += r["n"]
            elif r["engine"]:
                out["home"] += r["n"]
        return out

    # ---------- savings: trips and tokens kept in the house ----------

    def savings(self, since, tokens_per_request):
        """What answering at home saved since a time: a calculation, not a meter. Every request
        answered at home (or stopped) is a trip to the cloud model that didn't happen; each is
        counted at tokens_per_request, and also at its own measured size (est_tokens: the
        request's text and tools, about 4 characters a token)."""
        home_q = ("FROM activity WHERE time >= ? AND engine IS NOT NULL AND engine NOT IN ('gemini', 'home_assistant')"
                  " AND path != 'tool'")
        with self._db() as db:
            home = db.execute(f"SELECT COUNT(*) n, COALESCE(SUM(est_tokens), 0) t, COUNT(est_tokens) m {home_q}",
                              (since,)).fetchone()
            out = db.execute("SELECT COUNT(*) n, COALESCE(SUM(est_tokens), 0) t, COUNT(est_tokens) m FROM activity "
                             "WHERE time >= ? AND engine = 'gemini'", (since,)).fetchone()
            days = [dict(r) for r in db.execute(
                "SELECT date(time, 'unixepoch', 'localtime') day, "
                "SUM(CASE WHEN engine = 'gemini' THEN 1 ELSE 0 END) gemini, "
                "SUM(CASE WHEN engine IS NOT NULL AND engine NOT IN ('gemini', 'home_assistant') AND path != 'tool' "
                "THEN 1 ELSE 0 END) home, "
                "SUM(CASE WHEN engine IS NOT NULL AND engine NOT IN ('gemini', 'home_assistant') AND path != 'tool' "
                "THEN COALESCE(est_tokens, 0) ELSE 0 END) home_tokens "
                "FROM activity WHERE time >= ? GROUP BY day ORDER BY day", (since,))]
            engines = [dict(r) for r in db.execute(
                f"SELECT engine, COUNT(*) n {home_q} GROUP BY engine ORDER BY n DESC", (since,))]
        tpr = int(tokens_per_request)
        total = home["n"] + out["n"]
        avg_out = round(out["t"] / out["m"]) if out["m"] else None
        for d in days:
            d["tokens"] = d["home"] * tpr
        return {
            "trips_saved": home["n"], "trips_out": out["n"], "requests": total,
            "home_share": round(home["n"] / total, 3) if total else None,
            "tokens_per_request": tpr, "tokens_saved": home["n"] * tpr,
            "tokens_saved_measured": home["t"], "measured_rows": home["m"],
            "avg_tokens_per_trip_out": avg_out, "by_day": days, "by_engine": engines,
        }

    # ---------- the Off-Platform bank ----------

    def bank_add(self, key, heard, klass, qword, topic, topic_score, assistant, personality=None):
        """Count these words as heard for this personality; returns the bank row's id."""
        if not key:
            return None
        pers = str(personality or assistant or "")
        now = time.time()
        with self._lock, self._db() as db:
            row = db.execute("SELECT id FROM bank WHERE personality = ? AND key = ?", (pers, key)).fetchone()
            if row:
                db.execute("UPDATE bank SET count = count + 1, last = ?, heard = ?, assistant = ? "
                           "WHERE id = ?", (now, heard, assistant, row["id"]))
                return row["id"]
            cur = db.execute("INSERT INTO bank (personality, key, heard, class, qword, topic_guess, topic_score, "
                             "assistant, count, trips, used, first, last) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0, ?, ?)",
                             (pers, key, heard, klass, qword, topic, topic_score, assistant, now, now))
            return cur.lastrowid

    def bank_trip(self, bank_id):
        """These words went Off-Platform (N counts only these)."""
        if bank_id:
            with self._lock, self._db() as db:
                db.execute("UPDATE bank SET trips = trips + 1 WHERE id = ?", (bank_id,))

    def bank_used(self, bank_id):
        """The bank answered these words (counted apart: it doesn't raise N)."""
        if bank_id:
            with self._lock, self._db() as db:
                db.execute("UPDATE bank SET used = used + 1 WHERE id = ?", (bank_id,))

    def bank_answer(self, bank_id, answer, model=None, ms=None, tool_calls=None, after_command=None):
        """Keep an Off-Platform answer for a bank row (the newest T), and count what the request
        became. Only words are kept (decided Oct 14: a banked answer is just what to say when it's
        drawn on). A device command is only counted (What it became), never kept: it can carry a
        misheard name ("Gsurd Test"), it depends on the moment, and Home Assistant does devices
        itself. The words after a command (its second trip: after_command=True, as the router knows
        it) belong to it: they're its "said after" on What it became, never a kept answer (said
        without the command they'd be untrue). None guesses: within 2 minutes of a command."""
        if not bank_id or not (answer or tool_calls):
            return
        now = time.time()
        with self._lock, self._db() as db:
            if tool_calls:
                sig, name, args = signature(tool_calls)
                self._count_result(db, bank_id, sig, "tool", name, args, now, answer or None)
                self._commanded[bank_id] = (now, sig)
                return
            last = self._commanded.get(bank_id)
            recent = bool(last) and now - last[0] < 120
            if after_command or (after_command is None and recent):
                if last:
                    db.execute("UPDATE bank_results SET final = ? WHERE bank_id = ? AND sig = ?", (answer, bank_id, last[1]))
                self._commanded.pop(bank_id, None)
                return
            self._count_result(db, bank_id, "answer", "answer", None, None, now, answer)
            if int(self.answers_kept) <= 0:          # answers kept 0: counted, nothing kept to answer with
                return
            db.execute("INSERT INTO bank_answers (bank_id, time, answer, model, ms, tool_calls, kind) "
                       "VALUES (?, ?, ?, ?, ?, NULL, 'answer')", (bank_id, now, answer, model, ms))
            self._keep_newest(db, bank_id)

    def _keep_newest(self, db, bank_id):
        db.execute("DELETE FROM bank_answers WHERE bank_id = ? AND id NOT IN (SELECT id FROM "
                   "bank_answers WHERE bank_id = ? ORDER BY id DESC LIMIT ?)",
                   (bank_id, bank_id, max(1, int(self.answers_kept))))

    @staticmethod
    def _count_result(db, bank_id, sig, kind, name, args, now, final):
        db.execute("INSERT INTO bank_results (bank_id, sig, kind, name, args, count, first, last, final) "
                   "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?) ON CONFLICT(bank_id, sig) DO UPDATE SET "
                   "count = count + 1, last = excluded.last, final = COALESCE(excluded.final, final)",
                   (bank_id, sig, kind, name, args, now, now, final))

    def quota(self, trips):
        """Your formula: N = trips - 1, Q = N / T (at most 1). Returns (N, T, Q)."""
        t = max(1, int(self.answers_kept))
        n = max(0, int(trips or 0) - 1)
        return n, t, min(1.0, n / t)

    def bank_choose(self, personality, key):
        """Whether the bank answers these words this time: ({kind: tool | answer, ...}, why) or
        (None, why). Only an added row, with Q >= U; then Q of the time, at random.
        Her own saying comes first. If she has none she can use (not there, not added, no answers
        yet, Q below U), another personality's saying of the same words marked generic may answer
        (decided Oct 14: some answers suit everyone, and her own flair is added to them); the
        hit then carries generic_from. A draw that says Off-Platform this time is final."""
        with self._db() as db:
            own = db.execute("SELECT * FROM bank WHERE personality = ? AND key = ?",
                             (str(personality or ""), key)).fetchone()
            shared = db.execute("SELECT * FROM bank WHERE key = ? AND personality != ? AND generic = 1 "
                                "AND added IS NOT NULL ORDER BY trips DESC", (key, str(personality or ""))).fetchall()
            kept_of = {r["id"]: [dict(k) for k in db.execute(
                "SELECT * FROM bank_answers WHERE bank_id = ? ORDER BY id DESC LIMIT ?",
                (r["id"], max(1, int(self.answers_kept))))] for r in ([own] if own else []) + list(shared)}
        whys = []
        if own:
            if own["added"] is None:
                whys.append("in the bank's counts, but not added")
            else:
                hit, why, decided = self._from_row(own, kept_of[own["id"]])
                if hit or decided:
                    return hit, why
                whys.append(why)
        for row in shared:
            hit, why, decided = self._from_row(row, kept_of[row["id"]])
            why = f"generic, {row['personality']}'s: {why}"
            if hit:
                hit["generic_from"] = row["personality"]
                return hit, why
            if decided:
                return None, "; ".join(whys + [why])
            whys.append(why)
        if not whys:
            return None, "not in the bank"
        return None, "; ".join(whys)

    def _from_row(self, row, kept):
        """One added saying's answer by the formula: (hit or None, why, decided). decided: Q reached
        U and the draw was made (a no then means Off-Platform this time, not "try another").
        Words only: a device command is never kept, so never handed out (Oct 14)."""
        kept = [k for k in kept if k.get("kind") != "tool"]
        n, t, q = self.quota(row["trips"])
        u = float(self.use_from)
        pct = lambda x: f"{round(x * 100)}%"          # noqa: E731
        shown = f"N {n} (trips {row['trips']} - 1) / T {t} = Q {pct(q)}, U {pct(u)}"
        if not kept:
            return None, f"added, but no Off-Platform answers kept yet ({shown})", False
        if q < u:
            return None, f"added; Q below U ({shown})", False
        draw = self.rng.random()
        if draw >= q:
            return None, f"added; this time Off-Platform ({shown}, drew {draw:.2f})", True
        pick = self.rng.choice(kept)
        return ({"kind": "answer", "bank_id": row["id"], "text": pick["answer"],
                 "n": n, "t": t, "q": q, "u": u}, f"from the bank: one of {len(kept)} kept answers ({shown}, drew {draw:.2f})", True)

    def bank_set_generic(self, bank_id, generic):
        """Generic on the bank page: this saying's answers suit every personality (each adds her own flair)."""
        with self._lock, self._db() as db:
            db.execute("UPDATE bank SET generic = ? WHERE id = ?", (1 if generic else 0, int(bank_id)))
            row = db.execute("SELECT * FROM bank WHERE id = ?", (int(bank_id),)).fetchone()
        return dict(row) if row else None

    def by_result(self, limit=25, personality=None):
        """The top results the Off-Platform model produced, with every wording that led to each."""
        where, args = "", []
        if personality:
            where, args = " AND b.personality = ?", [personality]
        with self._db() as db:
            tops = [dict(r) for r in db.execute(
                "SELECT r.sig, r.kind, r.name, SUM(r.count) count, MAX(r.last) last, MAX(r.final) final "
                "FROM bank_results r JOIN bank b ON b.id = r.bank_id "
                f"WHERE r.kind = 'tool'{where} GROUP BY r.sig ORDER BY count DESC LIMIT ?",
                (*args, max(1, int(limit))))]
            for t in tops:
                t["variants"] = [dict(v) for v in db.execute(
                    "SELECT b.id, b.heard, b.key, b.personality, r.count, b.class FROM bank_results r "
                    f"JOIN bank b ON b.id = r.bank_id WHERE r.sig = ?{where} ORDER BY r.count DESC",
                    (t["sig"], *args))]
            answers = db.execute("SELECT COUNT(DISTINCT r.bank_id) rows, COALESCE(SUM(r.count), 0) asked "
                                 f"FROM bank_results r JOIN bank b ON b.id = r.bank_id WHERE r.kind = 'answer'{where}",
                                 args).fetchone()
        return {"results": tops, "answers": dict(answers)}

    def trim(self, days):
        """Take out one-offs: asked once, last seen more than days ago, not added or reviewed."""
        cut = time.time() - float(days) * 86400
        with self._lock, self._db() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM bank WHERE count <= 1 AND last < ? AND review = 'new' "
                                               "AND added IS NULL", (cut,))]
            for i in ids:
                db.execute("DELETE FROM bank_answers WHERE bank_id = ?", (i,))
                db.execute("DELETE FROM bank_results WHERE bank_id = ?", (i,))
                db.execute("DELETE FROM bank WHERE id = ?", (i,))
        return len(ids)

    def bank_export(self):
        """The whole bank as plain data (learn/bank.yaml, for git: the database itself never goes
        there): each saying with its counts, review, note, whether it was added, its kept answers and
        what the Off-Platform model turned it into. Times as local dates."""
        day = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else None   # noqa: E731
        out = []
        with self._db() as db:
            for r in db.execute("SELECT * FROM bank ORDER BY personality, count DESC, last DESC"):
                r = dict(r)
                answers = []
                for a in db.execute("SELECT time, answer, model, ms, tool_calls, kind FROM bank_answers "
                                    "WHERE bank_id = ? ORDER BY id DESC", (r["id"],)):
                    a = dict(a)
                    one = {"time": day(a["time"]), "kind": a["kind"] or "answer", "model": a["model"]}
                    if a["tool_calls"]:
                        try:
                            one["command"] = signature(json.loads(a["tool_calls"]))[0]
                        except (ValueError, TypeError, KeyError, IndexError):
                            one["command"] = a["tool_calls"]
                    if a["answer"]:
                        one["said"] = a["answer"]
                    answers.append(one)
                results = [{"became": x["sig"], "kind": x["kind"], "times": x["count"], "last": day(x["last"])}
                           for x in db.execute("SELECT sig, kind, count, last FROM bank_results WHERE bank_id = ? "
                                               "ORDER BY count DESC", (r["id"],))]
                out.append({"heard": r["heard"], "key": r["key"], "personality": r["personality"],
                            "class": r["class"], "qword": r["qword"], "closest_topic": r["topic_guess"],
                            "topic_score": round(r["topic_score"], 2) if r["topic_score"] is not None else None,
                            "heard_times": r["count"], "trips": r["trips"], "answered_by_bank": r["used"],
                            "first": day(r["first"]), "last": day(r["last"]), "added": day(r["added"]),
                            "review": r["review"], "note": r["note"] or "", "generic": bool(r["generic"]),
                            "answers": answers, "became": results})
        return out

    def bank(self, review=None, klass=None, search=None, order="last", limit=200, added=None, personality=None):
        """The bank page: each saying with how often it was heard, its trips, N, Q and whether the
        bank may answer it (Q >= U), and its kept answers."""
        q, args = "SELECT * FROM bank WHERE 1=1", []
        if added is True:
            q += " AND added IS NOT NULL"
        elif added is False:
            q += " AND added IS NULL"
        if personality:
            q += " AND personality = ?"
            args.append(personality)
        if review:
            q += " AND review = ?"
            args.append(review)
        if klass:
            q += " AND class = ?"
            args.append(klass)
        if search:
            q += " AND (heard LIKE ? OR key LIKE ?)"
            args += [f"%{search}%", f"%{search}%"]
        q += " ORDER BY " + ("count DESC, last DESC" if order == "count" else "last DESC")
        q += " LIMIT ?"
        args.append(max(1, min(int(limit), 1000)))
        with self._db() as db:
            rows = [dict(r) for r in db.execute(q, args)]
            for r in rows:
                r["answers"] = [dict(a) for a in db.execute(
                    "SELECT time, answer, model, ms, tool_calls, kind FROM bank_answers WHERE bank_id = ? "
                    "ORDER BY id DESC LIMIT ?", (r["id"], max(1, int(self.answers_kept))))]
                n, t, qq = self.quota(r["trips"])
                r.update(n=n, t=t, q=round(qq, 4), usable=bool(r["added"]) and qq >= self.use_from and bool(r["answers"]))
            classes = [dict(r) for r in db.execute(
                "SELECT class, COUNT(*) rows, SUM(count) asked FROM bank GROUP BY class ORDER BY asked DESC")]
            people = [r[0] for r in db.execute("SELECT DISTINCT personality FROM bank ORDER BY personality")]
        return {"rows": rows, "classes": classes, "reviews": list(REVIEWS), "personalities": people,
                "t": max(1, int(self.answers_kept)), "u": self.use_from}

    def bank_review(self, bank_id, review=None, note=None):
        if review is not None and review not in REVIEWS:
            raise ValueError(f"review is one of {', '.join(REVIEWS)}")
        with self._lock, self._db() as db:
            if review is not None:
                db.execute("UPDATE bank SET review = ? WHERE id = ?", (review, bank_id))
            if note is not None:
                db.execute("UPDATE bank SET note = ? WHERE id = ?", (note[:500], bank_id))
            row = db.execute("SELECT * FROM bank WHERE id = ?", (bank_id,)).fetchone()
        return dict(row) if row else None

    def bank_delete(self, bank_id):
        with self._lock, self._db() as db:
            db.execute("DELETE FROM bank_results WHERE bank_id = ?", (bank_id,))
            db.execute("DELETE FROM bank_answers WHERE bank_id = ?", (bank_id,))
            db.execute("DELETE FROM bank WHERE id = ?", (bank_id,))
