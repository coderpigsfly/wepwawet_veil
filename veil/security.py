# veil/security.py - who may use Wepwawet Veil's pages and admin API: accounts, roles,
# sessions, first-run setup, API tokens and the audit log. The same model as Oread's.
#
# Roles, highest first. Each role can grant and manage only roles below its own
# (a super user can also make other super users):
#   super          everything: users, the vault, permitted addresses, API tokens
#   administrator  settings, topics and seeds, tools, integrations, firewall, people, flair files
#   reviewer       the Gemini answer bank, the miss log, flair candidates (keep / skip)
#   viewer         read only: overview, inbound, outbound
#
# Passwords are hashed with scrypt (a random salt each), never stored. Accounts live in
# data/users.json (mode 600). A session is a random ID in the browser's cookie, kept here
# only as a fingerprint (data/sessions.json), so a restart signs nobody out.
# Five wrong passwords in a row lock that name for 15 minutes.
#
# First run: while there are no accounts, a one-time setup code is printed in the log and
# kept in data/setup-code.txt (readable only on the server). Whoever enters it creates the
# first (super) account. Reading the code proves you control the server.
#
# API tokens (for programs: the tools, LiteLLM if you want the chat door locked) are kept
# only as SHA-256 fingerprints in data/tokens.json and shown once, when made.
#
# From the server:
#   docker compose exec house-router python -m veil.security reset <name>     new password
#   docker compose exec house-router python -m veil.security users            list accounts
#   docker compose exec house-router python -m veil.security token <name> [role]
#   docker compose exec house-router python -m veil.security tokens | revoke <name>

import base64
import getpass
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

from veil.errors import VeilError

log = logging.getLogger("router")

ROLES = ("viewer", "reviewer", "administrator", "super")
RANK = {role: i for i, role in enumerate(ROLES, start=1)}
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
_TOKEN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
_PREFIX = "veil_"
# the knobs below come from settings.yaml security: (use() sets them at start; these are the defaults)
MIN_PASSWORD = 10            # password_min_length
LOCK_AFTER = 5               # lock_after_failures
LOCK_SECONDS = 15 * 60       # lock_minutes
IDLE_SECONDS = 12 * 3600     # session_idle_hours
MAX_SECONDS = 30 * 86400     # session_max_days


def use(sec):
    """Take the knobs from settings.yaml security: (anything missing keeps its default)."""
    global MIN_PASSWORD, LOCK_AFTER, LOCK_SECONDS, IDLE_SECONDS, MAX_SECONDS
    sec = sec or {}
    MIN_PASSWORD = max(8, int(sec.get("password_min_length", MIN_PASSWORD)))
    LOCK_AFTER = max(1, int(sec.get("lock_after_failures", LOCK_AFTER)))
    LOCK_SECONDS = int(float(sec.get("lock_minutes", LOCK_SECONDS / 60)) * 60)
    IDLE_SECONDS = int(float(sec.get("session_idle_hours", IDLE_SECONDS / 3600)) * 3600)
    MAX_SECONDS = int(float(sec.get("session_max_days", MAX_SECONDS / 86400)) * 86400)
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
# made fresh each start, never stored: the Tools page hands it to the tools it runs (ROUTER_TOKEN)
# so they can use /explain and /learn/drop when security: tools_token_required is on
INTERNAL = _PREFIX + "internal_" + secrets.token_urlsafe(32)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _b64(raw):
    return base64.b64encode(raw).decode()


def _fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password, salt=None, params=None):
    salt = salt or secrets.token_bytes(16)
    params = params or _SCRYPT
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=128 * 2 ** 20, **params)
    return {"scheme": "scrypt", **params, "salt": _b64(salt), "hash": _b64(digest)}


def check_password(password, stored):
    params = {k: stored[k] for k in ("n", "r", "p")}
    again = hash_password(password, base64.b64decode(stored["salt"]), params)
    return hmac.compare_digest(again["hash"], stored["hash"])


def check_new_password(password):
    if len(password or "") < MIN_PASSWORD:
        raise VeilError(f"Passwords need at least {MIN_PASSWORD} characters")
    if len(password) > 256:
        raise VeilError("That password is longer than 256 characters")


class JsonFile:
    """A small JSON file, private to the router, reloaded when changed from the command line."""

    def __init__(self, path, key):
        self.path, self.key = path, key
        self.items = {}
        self._mtime = 0.0
        self.reload()

    def reload(self):
        try:
            mtime = os.stat(self.path).st_mtime
        except FileNotFoundError:
            self.items, self._mtime = {}, 0.0
            return
        if mtime != self._mtime:
            with open(self.path) as f:
                self.items = json.load(f).get(self.key, {})
            self._mtime = mtime

    def write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        old = os.umask(0o077)
        try:
            with open(tmp, "w") as f:
                json.dump({self.key: self.items}, f, indent=2)
        finally:
            os.umask(old)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        self._mtime = os.stat(self.path).st_mtime


# ---------- the audit log ----------

class Audit:
    """Who changed what: data/audit.jsonl (newest KEEP lines). Nothing secret is written."""

    KEEP = 10000

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "audit.jsonl")
        self._lock = threading.Lock()
        self._lines = None

    def record(self, **event):
        row = {"time": _now(), **{k: v for k, v in event.items() if v is not None}}
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a") as f:
                    f.write(json.dumps(row) + "\n")
                if self._lines is None:
                    with open(self.path, "rb") as f:
                        self._lines = sum(1 for _ in f)
                else:
                    self._lines += 1
                if self._lines > self.KEEP * 1.2:
                    with open(self.path) as f:
                        keep = f.read().splitlines()[-self.KEEP:]
                    tmp = self.path + ".tmp"
                    with open(tmp, "w") as f:
                        f.write("".join(line + "\n" for line in keep))
                    os.replace(tmp, self.path)
                    self._lines = len(keep)
            except OSError:
                pass

    def recent(self, limit=200):
        try:
            with open(self.path) as f:
                lines = f.read().splitlines()[-limit:]
        except OSError:
            return []
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


# ---------- people who sign in ----------

class Users:
    def __init__(self, data_dir, audit=None):
        self._lock = threading.Lock()
        self._users = JsonFile(os.path.join(data_dir, "users.json"), "users")
        self._sessions = JsonFile(os.path.join(data_dir, "sessions.json"), "sessions")
        self._code_file = os.path.join(data_dir, "setup-code.txt")
        self.audit = audit or (lambda **event: None)
        self._setup_code = None
        self._setup_failures = 0
        self._touched = {}

    # first run

    def needs_setup(self):
        with self._lock:
            self._users.reload()
            return not self._users.items

    def setup_code(self):
        """The one-time code: the same one across restarts until it's used."""
        code = None
        try:
            with open(self._code_file) as f:
                code = f.read().strip().upper() or None
        except OSError:
            pass
        if code is None:
            code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
            old = os.umask(0o077)
            try:
                os.makedirs(os.path.dirname(self._code_file), exist_ok=True)
                with open(self._code_file, "w") as f:
                    f.write(code + "\n")
            except OSError as e:
                log.info("  ! couldn't save the setup code (%s); it's only in this log", e)
            finally:
                os.umask(old)
        self._setup_code = _fingerprint(code)
        self._setup_failures = 0
        return code

    def setup(self, code, name, password, client):
        with self._lock:
            self._users.reload()
            if self._users.items:
                raise VeilError("Already set up; sign in instead", 409)
            if self._setup_code is None or self._setup_failures >= LOCK_AFTER:
                raise VeilError("Too many wrong setup codes. Restart the router "
                                "(docker compose restart) to try again.", 403)
            if not hmac.compare_digest(_fingerprint((code or "").strip().upper()), self._setup_code):
                self._setup_failures += 1
                self.audit(action="setup refused", client=client, detail="wrong setup code")
                raise VeilError("That setup code isn't right. On the server it's in "
                                "data/setup-code.txt, or: docker compose logs | grep \"setup code\"", 403)
            self._new_user(name, password, "super")
            self._setup_code = None
            self._users.write()
            try:
                os.remove(self._code_file)
            except OSError:
                pass
        self.audit(action="setup", who=name, client=client, detail="super user created")
        return self.public(self._find(name))

    # signing in

    def sign_in(self, name, password, client):
        refused = VeilError("Wrong username or password", 401)
        with self._lock:
            self._users.reload()
            key = self._find(name)
            user = self._users.items.get(key) if key else None
            if user is None:
                hash_password(password or "x")       # take as long as a real check
                self.audit(action="sign-in refused", who=name, client=client, detail="no such user")
                raise refused
            if user.get("locked_until", 0) > time.time():
                minutes = int((user["locked_until"] - time.time()) // 60) + 1
                self.audit(action="sign-in refused", who=key, client=client, detail="locked")
                raise VeilError(f"Too many wrong passwords. Try again in {minutes} minutes.", 429)
            if not check_password(password or "", user["password"]):
                user["failures"] = user.get("failures", 0) + 1
                detail = "wrong password"
                if user["failures"] >= LOCK_AFTER:
                    user["locked_until"] = time.time() + LOCK_SECONDS
                    user["failures"] = 0
                    detail = f"wrong password; locked for {LOCK_SECONDS // 60} minutes"
                self._users.write()
                self.audit(action="sign-in refused", who=key, client=client, detail=detail)
                raise refused
            user["failures"] = 0
            user.pop("locked_until", None)
            user["last_sign_in"] = _now()
            self._users.write()
            session = self._new_session(key)
        self.audit(action="sign-in", who=key, client=client)
        return session, self.public(key)

    def _new_session(self, name):
        session = secrets.token_urlsafe(32)
        now = time.time()
        self._sessions.reload()
        self._expire_sessions(now)
        self._sessions.items[_fingerprint(session)] = {"user": name, "created": now, "used": now}
        self._sessions.write()
        return session

    def session_user(self, session):
        if not session:
            return None
        fp = _fingerprint(session)
        with self._lock:
            self._sessions.reload()
            item = self._sessions.items.get(fp)
            now = time.time()
            if not item or now - item["used"] > IDLE_SECONDS or now - item["created"] > MAX_SECONDS:
                return None
            self._users.reload()
            if item["user"] not in self._users.items:
                return None
            if now - self._touched.get(fp, 0) > 60:
                item["used"] = now
                self._touched[fp] = now
                self._sessions.write()
            return self.public(item["user"])

    def sign_out(self, session):
        if not session:
            return
        with self._lock:
            self._sessions.reload()
            if self._sessions.items.pop(_fingerprint(session), None):
                self._sessions.write()

    def _expire_sessions(self, now):
        for fp, item in list(self._sessions.items.items()):
            if now - item["used"] > IDLE_SECONDS or now - item["created"] > MAX_SECONDS:
                del self._sessions.items[fp]

    def _end_sessions(self, name, keep=None):
        self._sessions.reload()
        keep_fp = _fingerprint(keep) if keep else None
        for fp, item in list(self._sessions.items.items()):
            if item["user"] == name and fp != keep_fp:
                del self._sessions.items[fp]
        self._sessions.write()

    # your own account

    def change_own_password(self, name, current, new, session):
        check_new_password(new)
        with self._lock:
            self._users.reload()
            user = self._users.items.get(name)
            if user is None or not check_password(current or "", user["password"]):
                raise VeilError("Your current password isn't right", 403)
            user["password"] = hash_password(new)
            self._users.write()
            self._end_sessions(name, keep=session)
        self.audit(action="password changed", who=name, detail="own password")

    # managing others, from the role down

    def list(self):
        with self._lock:
            self._users.reload()
            return [self.public(n) for n in sorted(self._users.items, key=str.lower)]

    def grantable(self, actor):
        if actor["role"] == "super":
            return list(ROLES)
        return [r for r in ROLES if RANK[r] < RANK[actor["role"]]]

    def create(self, actor, name, password, role):
        self._may_grant(actor, role)
        with self._lock:
            self._users.reload()
            self._new_user(name, password, role)
            self._users.write()
        self.audit(action="user created", who=actor["name"], target=name, detail=role)
        return self.public(self._find(name))

    def update(self, actor, name, role=None, password=None):
        with self._lock:
            self._users.reload()
            key = self._find(name)
            if key is None:
                raise VeilError(f"No user named '{name}'", 404)
            user = self._users.items[key]
            self._may_manage(actor, key, user["role"])
            changes = []
            if role and role != user["role"]:
                self._may_grant(actor, role)
                if user["role"] == "super" and role != "super" and self._supers() == 1:
                    raise VeilError("That's the last super user; make another one first", 409)
                user["role"] = role
                changes.append(f"role {role}")
            if password:
                check_new_password(password)
                user["password"] = hash_password(password)
                user["failures"] = 0
                user.pop("locked_until", None)
                changes.append("password reset")
            if changes:
                self._users.write()
                self._end_sessions(key)
        if changes:
            self.audit(action="user changed", who=actor["name"], target=key, detail=", ".join(changes))
        return self.public(key)

    def delete(self, actor, name):
        with self._lock:
            self._users.reload()
            key = self._find(name)
            if key is None:
                raise VeilError(f"No user named '{name}'", 404)
            if key == actor["name"]:
                raise VeilError("You can't delete your own account", 409)
            self._may_manage(actor, key, self._users.items[key]["role"])
            if self._users.items[key]["role"] == "super" and self._supers() == 1:
                raise VeilError("That's the last super user", 409)
            del self._users.items[key]
            self._users.write()
            self._end_sessions(key)
        self.audit(action="user deleted", who=actor["name"], target=key)

    # helpers

    def public(self, name):
        user = self._users.items[name]
        return {"name": name, "role": user["role"], "created": user["created"],
                "last_sign_in": user.get("last_sign_in"),
                "locked": user.get("locked_until", 0) > time.time()}

    def _find(self, name):
        lowered = (name or "").strip().lower()
        return next((n for n in self._users.items if n.lower() == lowered), None)

    def _new_user(self, name, password, role):
        name = (name or "").strip()
        if not _NAME.match(name):
            raise VeilError("Usernames are 2-32 letters, digits, or . _ - (starting with a letter or digit)")
        if role not in RANK:
            raise VeilError(f"Roles are: {', '.join(ROLES)}")
        if self._find(name):
            raise VeilError(f"A user named '{name}' already exists", 409)
        check_new_password(password)
        self._users.items[name] = {"role": role, "password": hash_password(password),
                                   "created": _now(), "last_sign_in": None, "failures": 0}

    def _supers(self):
        return sum(u["role"] == "super" for u in self._users.items.values())

    def _may_grant(self, actor, role):
        if role not in RANK:
            raise VeilError(f"Roles are: {', '.join(ROLES)}")
        if role not in self.grantable(actor):
            raise VeilError(f"A {actor['role']} can't grant the {role} role", 403)

    def _may_manage(self, actor, name, role):
        if name == actor["name"]:
            raise VeilError("Change your own password on the Account page", 409)
        if actor["role"] != "super" and RANK[role] >= RANK[actor["role"]]:
            raise VeilError(f"A {actor['role']} can't change a {role}", 403)


# ---------- API tokens ----------

class Tokens:
    def __init__(self, data_dir):
        self._file = JsonFile(os.path.join(data_dir, "tokens.json"), "tokens")
        self._lock = threading.Lock()
        self._last_write = {}

    def create(self, name, role="administrator", door=None):
        name = (name or "").strip()
        if not _TOKEN_NAME.match(name):
            raise VeilError("Token names are 1-40 letters, digits, spaces, or _ . -")
        if role not in RANK:
            raise VeilError(f"Roles are: {', '.join(ROLES)}")
        with self._lock:
            self._file.reload()
            if any(n.lower() == name.lower() for n in self._file.items):
                raise VeilError(f"A token named '{name}' already exists", 409)
            token = _PREFIX + secrets.token_urlsafe(32)
            self._file.items[name] = {"fingerprint": _fingerprint(token), "created": _now(),
                                      "last_used": None, "role": role, "door": door or None}
            self._file.write()
            return token

    def revoke(self, name):
        with self._lock:
            self._file.reload()
            if name not in self._file.items:
                raise VeilError(f"No token named '{name}'", 404)
            del self._file.items[name]
            self._file.write()

    def tie(self, name, door):
        """Which door a token is for (the Security page shows them on that door's row)."""
        with self._lock:
            self._file.reload()
            if name not in self._file.items:
                raise VeilError(f"No token named '{name}'", 404)
            self._file.items[name]["door"] = door or None
            self._file.write()

    def list(self):
        with self._lock:
            self._file.reload()
            return [{"name": n, "role": t.get("role", "administrator"), "created": t["created"],
                     "last_used": t["last_used"], "door": t.get("door")} for n, t in sorted(self._file.items.items())]

    def check(self, token):
        """{name, role} if the token is permitted, else None."""
        if not token:
            return None
        if hmac.compare_digest(token, INTERNAL):
            return {"name": "the Tools page", "role": "administrator"}
        fp = _fingerprint(token)
        with self._lock:
            self._file.reload()
            for name, info in self._file.items.items():
                if hmac.compare_digest(info["fingerprint"], fp):
                    now = time.monotonic()
                    if now - self._last_write.get(name, 0) > 60:
                        info["last_used"] = _now()
                        self._last_write[name] = now
                        self._file.write()
                    return {"name": name, "role": info.get("role", "administrator")}
        return None


def bearer(headers):
    """The token in an Authorization: Bearer header, or None."""
    value = headers.get("authorization") or ""
    return value[7:].strip() if value.lower().startswith("bearer ") else None


# ---------- the command line ----------

def main(argv):
    from veil import config
    data = config.DATA_DIR
    audit = Audit(data)
    users, tokens = Users(data, audit.record), Tokens(data)
    usage = ("usage: python -m veil.security users | reset <name> | "
             "token <name> [role] | tokens | revoke <name>")
    try:
        if argv == ["users"]:
            for u in users.list():
                print(f"{u['name']:24} {u['role']:14} last sign-in {u['last_sign_in'] or 'never'}")
        elif argv[:1] == ["reset"] and len(argv) == 2:
            users._users.reload()
            key = users._find(argv[1])
            if key is None:
                sys.exit(f"No user named '{argv[1]}'")
            pw = getpass.getpass("New password: ") if sys.stdin.isatty() else sys.stdin.readline().strip()
            check_new_password(pw)
            user = users._users.items[key]
            user["password"] = hash_password(pw)
            user["failures"] = 0
            user.pop("locked_until", None)
            users._users.write()
            users._end_sessions(key)
            audit.record(action="password reset", who="server command line", target=key)
            print(f"Password for '{key}' reset; their sessions were signed out")
        elif argv[:1] == ["token"] and len(argv) in (2, 3):
            token = tokens.create(argv[1], argv[2] if len(argv) == 3 else "administrator")
            audit.record(action="token created", who="server command line", target=argv[1])
            print(f"Token '{argv[1]}' (copy it now; it won't be shown again):\n{token}")
        elif argv == ["tokens"]:
            for t in tokens.list():
                print(f"{t['name']:20} {t['role']:14} created {t['created']}  last used {t['last_used'] or 'never'}")
        elif argv[:1] == ["revoke"] and len(argv) == 2:
            tokens.revoke(argv[1])
            audit.record(action="token revoked", who="server command line", target=argv[1])
            print(f"Revoked '{argv[1]}'")
        else:
            sys.exit(usage)
    except VeilError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main(sys.argv[1:])
