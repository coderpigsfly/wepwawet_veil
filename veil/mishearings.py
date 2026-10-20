# veil/mishearings.py - what speech-to-text heard, filed under what was really meant.
# learn/mishearings.yaml: each entry is an intention (meant: what you really said) with the ways
# speech-to-text heard it under it, each with its own count. Fed from Misheard on the
# Transactions page and from "What did you hear?" then "Record that as a misunderstanding".
# Capped by miss_log_max (settings.yaml, the Misses page's Rules tab; Oct 15): past it, the heard
# line heard least recently goes first. Until then a heard line stays, counting, until you drop it
# or the words tool takes it (taken: true). Collected here; only the differences marked Use it
# (swaps, below) change what is decided.
# One heard line belongs to one intention: recording it again under another moves it there.
# A heard line that came through the audio path keeps each Oread clip it was heard in (clips:
# clip id, device, when), so Oread can pull the list (GET /learn/mishearings) and look each clip
# up itself: which model heard it, the device's settings. Wepwawet never needs the model.

import os
import time

import yaml

from veil import config, util

FILE = config.path("learn", "mishearings.yaml")

HEADER = """# learn/mishearings.yaml - what speech-to-text heard, under what you really meant.
#   meant: what you really said (null: not given yet)
#   heard: each way speech-to-text heard it, with how many times (count)
#   taken: true once the words tool has taken that one into the words
#   clips: each Oread clip it was heard in (clip id, device, when), from the audio path
# Written by the router (Misheard on Transactions, "Record that as a misunderstanding", the
# Misses page). Capped by miss_log_max: past it, the line heard least recently goes first.

"""


def key(text):
    """Same words regardless of capitals, punctuation (apostrophes too) and spacing."""
    return util.words(text, apostrophes=False)


def tidy(text, most=300):
    return util.squash(text, most) or None


def load():
    try:
        with open(FILE) as f:
            return (yaml.safe_load(f) or {}).get("mishearings") or []
    except FileNotFoundError:
        return []


def _capped(items, most):
    """The heard lines past most (the least recently heard first) taken out."""
    lines = sorted(((str(c.get("last") or ""), id(c)) for p in items for c in p.get("heard") or []))
    over = len(lines) - most
    if most <= 0 or over <= 0:
        return items
    gone = {i for _, i in lines[:over]}
    for p in items:
        p["heard"] = [c for c in p.get("heard") or [] if id(c) not in gone]
    return items


def save(items):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    items = _capped(items, int(config.settings().get("miss_log_max", 500) or 0))
    items = [p for p in items if p.get("heard")]            # an intention with nothing under it goes
    tmp = FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(HEADER)
        yaml.safe_dump({"mishearings": items}, f, sort_keys=False, allow_unicode=True, width=120)
        f.write("\n")
    os.replace(tmp, FILE)
    config.hand_back(FILE)


def _parent(items, meant):
    """The intention with these words (made if it isn't there). None: not given yet."""
    k = key(meant) if meant else None
    for p in items:
        if (key(p.get("meant")) if p.get("meant") else None) == k:
            return p
    p = {"meant": meant, "heard": []}
    items.append(p)
    return p


def _take_out(items, heard):
    """Take a heard line out from under whatever intention it's in. Returns it, or None."""
    k = key(heard)
    for p in items:
        for c in p.get("heard") or []:
            if key(c.get("said")) == k:
                p["heard"].remove(c)
                return c
    return None


def find(heard, items=None):
    """(intention, heard line) for these words, or (None, None)."""
    k = key(heard)
    for p in items if items is not None else load():
        for c in p.get("heard") or []:
            if key(c.get("said")) == k:
                return p, c
    return None, None


def add(heard, meant=None, when=None, clip=None, device=None):
    """Record a mishearing: count it up if it's there, else add it. With meant, it goes under
    that intention (moving it if it was under another, or under not given yet); without, it
    stays where it was. clip, device: Oread's clip it was heard in, kept once on the heard line.
    Returns (intention, heard line)."""
    heard, meant = tidy(heard), tidy(meant)
    if not heard:
        raise ValueError("nothing was heard")
    now = when or time.strftime("%Y-%m-%d %H:%M")
    items = load()
    was_in, c = find(heard, items)
    if c:
        c["count"] = int(c.get("count", 1)) + 1
        c["last"] = now
        if meant and (key(was_in.get("meant")) if was_in.get("meant") else None) != key(meant):
            _take_out(items, heard)
            p = _parent(items, meant)
            p["heard"].append(c)
        else:
            p = was_in
    else:
        c = {"said": heard, "count": 1, "first": now, "last": now, "taken": False}
        p = _parent(items, meant)
        p["heard"].append(c)
    if clip and clip not in [k.get("clip") for k in c.get("clips") or []]:
        c.setdefault("clips", []).append({"clip": str(clip), "device": device, "when": now})
    save(items)
    return p, c


def set_meant(heard, meant):
    """What was really said, for a heard line already recorded: it moves under that intention,
    keeping its count. Returns (intention, heard line), or (None, None) if it isn't there."""
    meant = tidy(meant)
    if not meant:
        raise ValueError("type what was really said")
    items = load()
    c = _take_out(items, heard)
    if not c:
        return None, None
    p = _parent(items, meant)
    p["heard"].append(c)
    save(items)
    return p, c


def drop(heard):
    """Take one heard line out. True if it was there."""
    items = load()
    if not _take_out(items, heard):
        return False
    save(items)
    return True


def mark_taken(heard, taken=True):
    """For the words tool: this heard line has been taken into the words."""
    items = load()
    _, c = find(heard, items)
    if not c:
        return False
    c["taken"] = bool(taken)
    save(items)
    return True


def total(p):
    return sum(int(c.get("count", 1)) for c in p.get("heard") or [])


def from_misses(misses_file):
    """Once: mishearings recorded before this file existed (kind misheard in learn/misses.yaml)
    move here, with their counts and dates, and leave that log. Returns how many moved."""
    try:
        with open(misses_file) as f:
            old = (yaml.safe_load(f) or {}).get("misses") or []
    except FileNotFoundError:
        return 0
    moving = [m for m in old if m.get("kind") == "misheard" and tidy(m.get("heard"))]
    if not moving:
        return 0
    items = load()
    for m in moving:
        heard = tidy(m.get("heard"))
        was_in, c = find(heard, items)
        if c:
            c["count"] = int(c.get("count", 1)) + int(m.get("count", 1))
            continue
        p = _parent(items, tidy(m.get("should_be")))
        p["heard"].append({"said": heard, "count": int(m.get("count", 1)), "first": m.get("first") or "",
                           "last": m.get("last") or "", "taken": False})
    save(items)
    return len(moving)


# ---------- swaps: mishearings pushed back (learn/swaps.yaml) ----------
# A swap is one difference you marked Use it on the Misses page ("grainsplate" heard, "brain flea"
# meant). Before anything is decided, each swap's heard words are replaced by what was meant, as
# whole words only, longest first; the trace says which. Nothing else in a mishearing is used.

SWAPS_FILE = config.path("learn", "swaps.yaml")
_SWAPS = {"mtime": None, "swaps": []}


def swaps():
    """The swaps in use, re-read only when the file changes: [{heard, meant, added}] (added: when
    it was marked Use it, "" for one from before Oct 18)."""
    try:
        m = os.stat(SWAPS_FILE).st_mtime
    except OSError:
        return []
    if m != _SWAPS["mtime"]:
        with open(SWAPS_FILE) as f:
            got = (yaml.safe_load(f) or {}).get("swaps") or []
        _SWAPS.update(mtime=m, swaps=[{"heard": str(s["heard"]), "meant": str(s["meant"]), "added": str(s.get("added") or "")} for s in got
                                      if isinstance(s, dict) and str(s.get("heard") or "").strip() and s.get("meant") is not None])
    return _SWAPS["swaps"]


def use(heard, meant, on=True):
    """Mark one difference Use it (on) or stop using it. Returns the swaps in use."""
    import re
    heard = " ".join(re.findall(r"[a-z0-9']+", str(heard or "").lower()))
    meant = " ".join(str(meant or "").split())
    if not heard:
        raise ValueError("there are no heard words to swap")
    import datetime as dt
    kept = [dict((k, v) for k, v in s.items() if v != "") for s in swaps() if s["heard"] != heard]
    if on:
        kept.append({"heard": heard, "meant": meant, "added": dt.datetime.now().strftime("%Y-%m-%d %H:%M")})
    os.makedirs(os.path.dirname(SWAPS_FILE), exist_ok=True)
    with open(SWAPS_FILE, "w") as f:
        f.write("# learn/swaps.yaml - mishearings pushed back (the Misses page, Use it): before anything is decided,\n"
                "# each heard is replaced by meant, as whole words only, longest first.\n")
        yaml.safe_dump({"swaps": kept}, f, sort_keys=False, allow_unicode=True, width=4096)
    config.hand_back(SWAPS_FILE)
    _SWAPS["mtime"] = None
    return swaps()


def swap(text):
    """(text with the swaps made, [(heard, meant)] made), whole words only, longest first."""
    import re
    done = []
    for s in sorted(swaps(), key=lambda s: -len(s["heard"])):
        pattern = r"(?<![\w'])" + r"[\W_]+".join(re.escape(w) for w in s["heard"].split()) + r"(?![\w'])"
        new, n = re.subn(pattern, s["meant"], text, flags=re.I)
        if n:
            text = " ".join(new.split())
            done.append((s["heard"], s["meant"]))
    return text, done
