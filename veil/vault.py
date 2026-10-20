# veil/vault.py - keys the router sends to other programs (LiteLLM, Donetick, Oread, Home
# Assistant). The same design as Oread's vault.
#
# Tokens that call INTO the router are kept only as fingerprints (security.py). These are the
# other way round: the router must send them, so it must read them back. They're encrypted
# (Fernet: AES with a tamper check) in data/vault.json; the encryption key lives apart, in
# data/keys/veil.key (or the VEIL_VAULT_KEY environment variable). Back the key up separately.
#
# A service's secret: in settings.yaml (DONETICK_TOKEN, OREAD_TOKEN...) is looked up here first,
# then in .env, so nothing breaks while the vault is empty. Names in the vault are lowercase;
# DONETICK_TOKEN is found as donetick_token.
#
# The pages never show a key back: only its name, what it's for and its last 4 characters.
# From the server:
#   docker compose exec house-router python -m veil.vault set <name> [service]   (asks for the key)
#   docker compose exec house-router python -m veil.vault list | delete <name>

import getpass
import json
import logging
import os
import re
import sys
import threading
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from veil.errors import VeilError

log = logging.getLogger("router")
_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,39}$")
_ENV = "VEIL_VAULT_KEY"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hint(value):
    return "…" + value[-4:] if len(value) >= 12 else "(short)"


def load_key(keys_dir):
    env = os.environ.get(_ENV)
    if env:
        return Fernet(env.encode()), f"the {_ENV} environment variable"
    path = os.path.join(keys_dir, "veil.key")
    if not os.path.exists(path):
        os.makedirs(keys_dir, exist_ok=True)
        old = os.umask(0o077)
        try:
            with open(path, "wb") as f:
                f.write(Fernet.generate_key())
        finally:
            os.umask(old)
        log.info("Created a new vault key in %s. Back it up apart from data/.", path)
    os.chmod(path, 0o600)
    with open(path, "rb") as f:
        return Fernet(f.read().strip()), "data/keys/veil.key"


class Vault:
    def __init__(self, path, keys_dir):
        self.path = path
        self.keys_dir = keys_dir
        self._fernet = None
        self.key_source = None
        self._lock = threading.Lock()
        self._items = {}
        self._mtime = 0.0
        self._reload()

    @property
    def fernet(self):
        # the key file is only made when the vault is first used for real
        if self._fernet is None:
            self._fernet, self.key_source = load_key(self.keys_dir)
        return self._fernet

    def _reload(self):
        try:
            mtime = os.stat(self.path).st_mtime
        except FileNotFoundError:
            self._items, self._mtime = {}, 0.0
            return
        if mtime != self._mtime:
            with open(self.path) as f:
                self._items = json.load(f).get("keys", {})
            self._mtime = mtime

    def _write(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        old = os.umask(0o077)
        try:
            with open(tmp, "w") as f:
                json.dump({"keys": self._items}, f, indent=2)
        finally:
            os.umask(old)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        self._mtime = os.stat(self.path).st_mtime

    def _readable(self, name):
        try:
            self.fernet.decrypt(self._items[name]["secret"].encode())
            return True
        except (InvalidToken, KeyError):
            return False

    def set(self, name, value, service=None, note=None):
        name = (name or "").strip().lower()
        value = (value or "").strip()
        if not _NAME.match(name):
            raise VeilError("Key names are 1-40 lowercase letters, digits, or _ . -")
        if not value:
            raise VeilError("The key is empty")
        if len(value) > 8192:
            raise VeilError("That key is longer than 8 KB")
        with self._lock:
            self._reload()
            old = self._items.get(name, {})
            self._items[name] = {
                "service": (service if service is not None else old.get("service")) or None,
                "note": (note if note is not None else old.get("note")) or None,
                "hint": _hint(value), "created": old.get("created", _now()), "updated": _now(),
                "last_used": old.get("last_used"),
                "secret": self.fernet.encrypt(value.encode()).decode(),
            }
            self._write()
            return self._public(name)

    def get(self, name):
        """The key itself, for the router's own calls; '' when there's no such key."""
        name = (name or "").strip().lower()
        with self._lock:
            self._reload()
            item = self._items.get(name)
            if not item:
                return ""
            try:
                value = self.fernet.decrypt(item["secret"].encode()).decode()
            except InvalidToken as e:
                raise VeilError(f"Key '{name}' can't be read with the current vault key; set it again", 409) from e
            if (item.get("last_used") or "")[:10] != _now()[:10]:
                item["last_used"] = _now()
                self._write()
            return value

    def delete(self, name):
        name = (name or "").strip().lower()
        with self._lock:
            self._reload()
            if name not in self._items:
                raise VeilError(f"No key named '{name}' in the vault", 404)
            del self._items[name]
            self._write()

    def list(self):
        with self._lock:
            self._reload()
            keys = [self._public(n) for n in sorted(self._items)]
            return {"encryption_key_from": self.key_source or ("not made yet" if not keys else None),
                    "keys": keys}

    def _public(self, name):
        item = self._items[name]
        return {"name": name, "service": item.get("service"), "note": item.get("note"),
                "ends_with": item["hint"], "created": item["created"], "updated": item["updated"],
                "last_used": item.get("last_used"), "readable": self._readable(name)}


def main(argv):
    from veil import config
    v = Vault(os.path.join(config.DATA_DIR, "vault.json"), os.path.join(config.DATA_DIR, "keys"))
    usage = "usage: python -m veil.vault set <name> [service] | list | delete <name>"
    try:
        if argv[:1] == ["set"] and len(argv) in (2, 3):
            value = getpass.getpass("Key: ") if sys.stdin.isatty() else sys.stdin.read()
            item = v.set(argv[1], value, argv[2] if len(argv) == 3 else None)
            print(f"Saved '{item['name']}' (ends with {item['ends_with']})")
        elif argv == ["list"]:
            listing = v.list()
            print(f"Encryption key from {listing['encryption_key_from']}")
            for k in listing["keys"]:
                flag = "" if k["readable"] else "  CAN'T BE READ: set it again"
                print(f"{k['name']:24} {k['service'] or '-':16} {k['ends_with']:8} updated {k['updated']}{flag}")
        elif argv[:1] == ["delete"] and len(argv) == 2:
            v.delete(argv[1])
            print(f"Deleted '{argv[1]}'")
        else:
            sys.exit(usage)
    except VeilError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main(sys.argv[1:])
