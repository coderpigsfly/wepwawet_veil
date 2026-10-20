# config.py - where Wepwawet Veil's files live, its settings with their defaults, safe
# comment-keeping writes for the pages, and secrets (the vault first, then .env).
#
# Everything the router, the pages and the tools read goes through here, so a path or a
# default lives in one place. ROOT is /app in the container; set ROUTER_ROOT to run the
# router from a checkout (tests do).
#
# Writing: the pages change settings.yaml, firewall.yaml and the personality files with
# ruamel.yaml's round trip, so your comments and layout survive. Every write is atomic
# (a .tmp file, then a rename) and, when FILE_OWNER is set (1000:1000), handed back to you
# so you can still edit it in your editor and commit it with git.

import copy
import logging
import os
import re
import threading

import yaml

log = logging.getLogger("router")

ROOT = os.environ.get("ROUTER_ROOT", "/app")


def path(*parts):
    return os.path.join(ROOT, *parts)


# The household's own files (settings, the firewall, voice maps, the keyword files, her
# personality...) are written at home and never shipped or touched by git. Each shipped one has
# a starting copy at the same place under defaults/, copied in whenever the household's file is
# missing. Examples (defaults/examples/, like an example assistant) are copied in only when that
# folder has nothing of that kind yet, so an example never lands beside your own, and they are
# never offered as "new" (veil/starting.py).
STARTING_DIR = path("defaults")
EXAMPLES = "examples"


def starting_copies(examples=False):
    """[(starting copy, the household's file)] under defaults/ (or only its examples)."""
    out = []
    for base, _dirs, files in os.walk(STARTING_DIR):
        for name in sorted(files):
            src = os.path.join(base, name)
            rel = os.path.relpath(src, STARTING_DIR)
            is_example = rel.split(os.sep)[0] == EXAMPLES
            if is_example != examples:
                continue
            out.append((src, path(rel.split(os.sep, 1)[1] if is_example else rel)))
    return out


def seed_household():
    """Copy in each missing household file from its starting copy, and the examples where a
    folder has none of its own yet. Never overwrites."""
    import shutil
    examples = starting_copies(examples=True)
    # which folders already have files of each kind, looked at once, before anything is copied
    had = {(os.path.dirname(dst), os.path.splitext(dst)[1]) for _src, dst in examples
           if os.path.isdir(os.path.dirname(dst)) and any(
               f.endswith(os.path.splitext(dst)[1]) and os.path.isfile(os.path.join(os.path.dirname(dst), f))
               for f in os.listdir(os.path.dirname(dst)))}
    made = []
    for src, dst in starting_copies() + [(s, d) for s, d in examples
                                          if (os.path.dirname(d), os.path.splitext(d)[1]) not in had]:
        if os.path.exists(dst):
            continue
        make_dirs(os.path.dirname(dst))
        shutil.copy2(src, dst)
        hand_back(dst)
        made.append(os.path.relpath(dst, ROOT))
    if made:
        log.info("  starting copies put in place (they were missing): %s", ", ".join(made))
    return made


SETTINGS_FILE = path("settings.yaml")
FIREWALL_FILE = path("firewall.yaml")
DATA_DIR = os.environ.get("ROUTER_DATA", path("data"))     # users, sessions, vault, database
STATE_DIR = path("state")

# Defaults for every knob, so an old settings.yaml (or one missing a section) still runs.
# settings.yaml always wins; these only fill gaps.
DEFAULTS = {
    "false_wake_max_letters": 1,
    "echo_overlap": 0.6,
    "echo_seconds": 30,
    "echo_min_words": 3,
    "echo_cover_longest": 2,                # her words brought back: what was heard at most this many times as long
    "echo_keeps_question": True,            # her waiting question survives her own words coming back
    "confidence_local": 0.85,
    "lone_door_max_words": 12,              # longer, with one door and no other topic word: not sure
    "followup_max_words": 4,
    "context_window_minutes": 2,
    "last_item_minutes": 30,
    "read_list_max": 5,
    "answer_max_words": 4,
    "gemini_conversation_minutes": 2,
    "turns_kept": 3,
    "miss_log_max": 500,
    "capture_keep": 0,
    "followup_lookback": 3,                 # earlier requests searched for the last topic (path B)
    # spoken needs the router hears itself, and what kind of detail each is; a required one
    # that isn't heard makes her ask before the app is called (the rest are the app's own)
    "heard_needs": {"who": "person", "when": "date"},
    "own_words_share": 0.90,                # your own words in a voice map count this strongly
    "verb_beats_object": 0.85,              # a change verb this sure beats an object noun
    "router": {
        "add_name_max_words": 8,            # longest name taken, said in the add or as the answer to "what's it called?"
        "quiet_paths": ["/v1/models", "/health", "/firewall/summary"],
        "check_app_versions_at_start": True,   # read each app's spec once at start-up and flag a new version
        "user_agent": "WepwawetVeil/1.0 (household voice router)",   # the router's name on every call out
        "check_app_versions_every_hours": 24,   # the version check reads a spec again only this long after the last
        # the Off-Platform model says first how it understood the request (dump13): one it cleaned up
        # into something answered at home is answered here instead, and kept as a mishearing
        "twin_seconds": 3,                  # the same words from another device this soon: left to the first (dump17)
        "app_answer_max_kb": 8192,          # an app's answer read at most this big (inbound defense 3)
        "spec_max_kb": 8192,                # and a spec, or a part of one
        "off_platform_heard": True,
        # her answer from an app on the internet, as a conversation going Off-Platform holds it (dump16)
        "outside_answer_note": "(answered at home, from an app on the internet)",
        "heard_tag": "HEARD:",
        "heard_instruction": ("Before anything else, write one line that starts with HEARD: and then the user's last request as you"
                              " understood it: the whole request, every detail kept, as a full sentence, only with misheard words "
                              "corrected (it came through speech to text). Things this house answers itself, so a request that "
                              "sounds like one is likely about it: {home}. Then a new line, then your answer as usual. Never "
                              "mention the HEARD line."),
    },
    "language": {
        "spacy_model": "en_core_web_sm",    # sentence diagramming (must be installed in the image)
    },
    "integrations": {
        "litellm": {
            "fallback_model": "gemini-lite",    # the LiteLLM model for everything not answered at home
            "timeout": 60,
            "key": "OFF_PLATFORM_KEY",          # the name of its key (the vault first, then .env); LITELLM_KEY still read
            "model_name": "house-router",       # what LiteLLM and Home Assistant see in /v1/models
            "own_time_header": "x-litellm-overhead-duration-ms",    # LiteLLM's own time in each answer
            "model_header": "x-litellm-model-name",                 # the model that really answered
            "fallbacks_header": "x-litellm-attempted-fallbacks",    # how many models it tried first
        },
        "oread": {
            "enabled": False,
            "source": "wyoming",
            "wyoming": {"host": "", "connect_timeout": 3, "devices": {}, "home_assistant_answered_after": 8,
                        "fix_mishearings": True},
            "min_word_overlap": 0.5,
            "url": "",
            "token": "OREAD_TOKEN",
            "verify_tls": False,
            "timeout": 0.8,
            "max_age_seconds": 20,
            "devices": {},
            "her_voices": [],               # the voice ID's profiles of the assistants' own voices: what they say is an echo (dump17)
        },
    },
    "names_in_replies": {
        "labels": ["known"],
        "paths": ["A", "B", "C"],
        "end_share": 0.35,
        "voice_id_from": "",          # the integration whose people list names them (User Sparkle)
        "calls": {},                  # voice ID name -> what she may call them (User Sparkle)
    },
    "topics": {},
    "services": {},
    "security": {
        "inbound_allowed": [],
        "admin_allowed": [],
        "outbound_allowed": [],
        "chat_token_required": False,            # the older switches: read only by a door without locked:
        "tools_token_required": False,
        "guard_token_required": False,
        "refused_warn_minutes": 60,              # Integrations warns of refusals this recent
        # the router's doors that can ask for an API token (settings.yaml security: doors:, where
        # more are added as they're needed); locked comes from settings.yaml or the Security page
        "doors": {
            "chat": {"description": "Home Assistant's requests, brought by LiteLLM",
                     "who": "LiteLLM (its api_key for the house-router model)",
                     "paths": ["/v1/chat/completions"], "role": "viewer", "program": "litellm"},
            "tools": {"description": "the command-line tools: what she would decide, and dropping misses",
                      "who": "the tools on myserver (ROUTER_TOKEN)",
                      "paths": ["/explain", "/learn/drop"], "role": "reviewer"},
            "guard": {"description": "Veil Guard Service asks the firewall before Home Assistant's own commands",
                      "who": "Veil Guard Service (its token: in Home Assistant's secrets.yaml)",
                      "paths": ["/firewall/check", "/firewall/summary"], "role": "viewer", "program": "home_assistant"},
        },
        "password_min_length": 10,
        "lock_after_failures": 5,
        "lock_minutes": 15,
        "session_idle_hours": 12,
        "session_max_days": 30,
    },
    "web": {"enabled": True, "port": 8771, "tls": "auto"},
    "activity": {"enabled": True, "keep_days": 14, "keep_rows": 20000, "bank": True, "bank_answers_kept": 5,
                 "bank_use_from": 0.2, "trim_days": 30, "bank_top": 25, "answer_from_bank": False,
                 "bank_similar": 0.8},       # an added saying answers words this near to it too (0: the same words only)
    "savings": {"tokens_per_request": 3000},
    "stats": {"sample_seconds": 60, "keep_days": 30, "slower_than_usual": 1.5, "slow_min_requests": 3,
              "top_cpu": 10, "top_cpu_days": 7,
              "internet_check": {"enabled": True, "servers": ["1.1.1.1", "8.8.8.8"], "routes": ["off_platform"],
                                 "cooldown_minutes": 5, "timeout_ms": 1000, "lookup_name": "example.com",
                                 "slower": 2.0, "min_outside_ms": 200}},
}


def load_yaml(file):
    with open(file) as f:
        return yaml.safe_load(f) or {}


def merged(base, over):
    """base with over laid on top, one level of dicts deep at a time."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merged(out[k], v)
        else:
            out[k] = v
    return out


def settings():
    """settings.yaml with every default filled in."""
    try:
        own = load_yaml(SETTINGS_FILE)
    except FileNotFoundError:
        own = {}
    return merged(DEFAULTS, own)


def section(s, name):
    return s.get(name) or {}


# Settings that moved on Oct 15, by where they were before: an older settings.yaml still works.
_MOVED = {"followup_lookback": ("router",), "heard_needs": ("router",), "own_words_share": ("router",),
          "verb_beats_object": ("router",)}
_LITELLM_WAS = {"fallback_model": ("llm",), "timeout": ("llm",), "key": ("llm",), "model_name": ("router",)}


def own():
    """settings.yaml as written, with no defaults filled in: to tell what the file itself sets."""
    try:
        return load_yaml(SETTINGS_FILE) or {}
    except FileNotFoundError:
        return {}


def knob(s, key, default=None):
    """A top-level setting the file sets, or where it lived before Oct 15, or the default."""
    mine = own()
    if key in mine:
        return mine[key]
    for where in _MOVED.get(key, ()):
        if key in section(mine, where):
            return section(mine, where)[key]
    return (s or {}).get(key, default)


def litellm(s=None):
    """Everything about talking to LiteLLM (integrations: litellm:, its Integrations tab), with the
    older llm: and router: model_name read when the newer one isn't in the file."""
    mine = own()
    out = dict(DEFAULTS["integrations"]["litellm"])
    for k, (where,) in _LITELLM_WAS.items():
        if k in section(mine, where):
            out[k] = section(mine, where)[k]
    out.update({k: v for k, v in section(section(mine, "integrations"), "litellm").items() if v not in (None, "")})
    return out


# ---------- the house: where it is and its clock (Settings, The house) ----------

def house(s=None):
    """settings.yaml house: {timezone}: the house's clock, for the router and every app."""
    return dict((s or settings()).get("house") or {})


def house_timezone(s=None):
    """The house's timezone name (like America/New_York), or None when it isn't set."""
    tz = str(house(s).get("timezone") or "").strip()
    return tz or None


def use_house_clock(s=None):
    """Run this process on the house's clock, so today, tomorrow and Saturday, the due dates sent
    to apps and the Stats days all agree. Not set, or not a timezone: the container's clock, said
    in the log."""
    tz = house_timezone(s)
    if not tz:
        log.info("  ! no house timezone (Settings, The house): using the container's clock")
        return None
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
    except Exception:
        log.info("  ! the house timezone %r isn't a timezone (like America/New_York): using the container's clock", tz)
        return None
    os.environ["TZ"] = tz
    import time as _time
    _time.tzset()
    return tz


def service_enabled(svc):
    """A service runs unless it says enabled: false."""
    return bool((svc or {}).get("enabled", True))


# ---------- writes that keep comments ----------

_lock = threading.Lock()


def _rt(width=120):
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.width = width
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def hand_back(file):
    """Give a file the router wrote back to you (FILE_OWNER=uid:gid in .env)."""
    owner = os.environ.get("FILE_OWNER", "")
    if not owner:
        return
    try:
        uid, _, gid = owner.partition(":")
        os.chown(file, int(uid), int(gid or uid))
    except (OSError, ValueError) as e:
        log.info("  ! couldn't hand %s back to %s: %s", file, owner, e)


def make_dirs(folder):
    """os.makedirs, and each folder it made handed back to you too (FILE_OWNER), so a new install's
    personality/, learn/ and the like stay yours to edit without sudo."""
    folder = folder or "."
    made = []
    d = os.path.abspath(folder)
    while d and not os.path.exists(d):
        made.append(d)
        d = os.path.dirname(d)
    os.makedirs(folder, exist_ok=True)
    for d in made:
        hand_back(d)


def stamp(file, key):
    """A short fingerprint of one section of a YAML file as it is now (its rules:, actions: or
    fleas:): a page keeps the one it opened with and sends it back on Save, so a save from an old
    copy is refused (check_stamp). Only that section counts: another tab saving another part of
    the same file doesn't make this page's copy old."""
    import hashlib
    import json
    part = load_yaml(file).get(key) if os.path.exists(file) else None
    return hashlib.sha256(json.dumps(part, sort_keys=True, default=str).encode()).hexdigest()[:16]


def check_stamp(file, key, given):
    """Refuse a save made from an old copy: the section changed (by voice, in the file, or on
    another page) after the page was opened. No stamp given (a tool, an older page): not checked."""
    if given and str(given) != stamp(file, key):
        from veil.errors import VeilError
        raise VeilError(f"The {key} in {os.path.basename(file)} changed since you opened the page: reload first, "
                        "then make your change again (saving now would undo the newer change).", 409)


def write_text(file, text):
    make_dirs(os.path.dirname(file))
    tmp = file + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    try:
        os.replace(tmp, file)
    except OSError:
        # a file mounted into the container on its own can't be replaced, only rewritten
        with open(file, "w") as f:
            f.write(text)
        os.remove(tmp)
    hand_back(file)


def edit_yaml(file, change, header=None, width=120):
    """Load file keeping its comments, let change(doc) edit it in place, write it back.
    change may return a value, which edit_yaml returns. A missing file starts empty
    (with header, a comment block, at the top). width: where long lines wrap (a voice map's
    one-line word lists use a wide one, so they stay on one line)."""
    import io
    y = _rt(width)
    with _lock:
        if os.path.exists(file):
            with open(file) as f:
                doc = y.load(f)
        else:
            doc = None
        if doc is None:
            from ruamel.yaml.comments import CommentedMap
            doc = CommentedMap()
        result = change(doc)
        doc = quoted(doc)
        buf = io.StringIO()
        if header and not os.path.exists(file):
            buf.write(header.rstrip() + "\n\n")
        y.dump(doc, buf)
        text = buf.getvalue().rstrip() + "\n\n\n"       # blank lines at the end, for HA-style editors
        try:
            yaml.safe_load(text)       # what's written must read back, by the router and the tools
        except yaml.YAMLError as e:
            from veil.errors import VeilError
            raise VeilError(f"Not saved: {os.path.basename(file)} wouldn't read back ({e})", 500)
        write_text(file, text)
    return result


_PLAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./'-]*$")
_YAML11 = {"yes", "no", "on", "off", "true", "false", "y", "n", "null", "none", "~"}


def quoted(node):
    """Put quotes on strings a YAML reader could take for something else ("kill*", "yes", "3")."""
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString, ScalarString

    def fix(v):
        if isinstance(v, str) and not isinstance(v, ScalarString):
            risky = not _PLAIN.match(v) or v.lower() in _YAML11 or re.fullmatch(r"[0-9.:+\-eE]+", v) \
                or v != v.strip() or "'" in v[:1]
            return DoubleQuotedScalarString(v) if risky and v else v
        return quoted(v)
    if isinstance(node, dict):
        for k in list(node.keys()):
            node[k] = fix(node[k])
    elif isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = fix(v)
    return node


YAML11_WORDS = {"y", "n", "yes", "no", "on", "off", "true", "false", "null", "~"}


def flow_list(items=()):
    """A YAML list written on one line ([a, b, c]), for edit_yaml. A word YAML would read as true,
    false or nothing (on, off, yes, no...) is quoted, so it stays a word."""
    from ruamel.yaml.comments import CommentedSeq
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString
    seq = CommentedSeq([DoubleQuotedScalarString(x) if isinstance(x, str) and x.lower() in YAML11_WORDS else x
                        for x in items])
    seq.fa.set_flow_style()
    return seq


def map_in(node, key, block=False):
    """node[key] as a map (made if missing or not a map), for edit_yaml; block=True writes it one
    entry to a line rather than {a: 1, b: 2}."""
    from ruamel.yaml.comments import CommentedMap
    m = node.get(key)
    if not isinstance(m, dict):
        node[key] = m = CommentedMap()
    if block and hasattr(m, "fa"):
        m.fa.set_block_style()
    return m


def set_in(doc, keys, value):
    """doc[k1][k2]... = value, making the dicts on the way."""
    from ruamel.yaml.comments import CommentedMap
    node = doc
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            node[k] = CommentedMap()
        node = node[k]
    node[keys[-1]] = value


def plain(value):
    """ruamel's types back to plain dicts and lists (for JSON)."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


# ---------- secrets ----------

_vault = None


def vault():
    global _vault
    if _vault is None:
        try:
            from veil import vault as vault_mod
            _vault = vault_mod.Vault(os.path.join(DATA_DIR, "vault.json"), os.path.join(DATA_DIR, "keys"))
        except Exception as e:      # no cryptography, or no data folder: .env only
            log.info("  ! the vault isn't available (%s): secrets come from .env only", e)
            _vault = False
    return _vault or None


def secret(name):
    """A secret by name: the vault first (set on the Security page), then .env."""
    if not name:
        return ""
    v = vault()
    if v:
        try:
            got = v.get(name)
            if got:
                return got
        except Exception:
            pass
    return os.environ.get(name, "")


def secret_source(name):
    """Where a secret would come from: 'vault', '.env' or None (for the pages; never the value)."""
    if not name:
        return None
    v = vault()
    if v:
        try:
            if v.get(name):
                return "vault"
        except Exception:
            pass
    return ".env" if os.environ.get(name) else None


# at start-up, before anything reads them: a household file that's missing gets its starting copy
seed_household()
