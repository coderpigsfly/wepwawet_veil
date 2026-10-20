# veil/starting.py - what's new in the starting copies (defaults/) that the household's own
# files don't have yet, and Add for each.
#
# The household's files (settings, the firewall, voice maps, ...) are never shipped or touched by
# git; an update ships new starting copies instead. Here each starting copy is compared with the
# household's file at the same place: a key it has that yours doesn't, or a word in one of its
# lists that yours doesn't. Nothing is changed until you press Add; "Not for us" hides one for
# good (kept in data/, the household's own). Changed values aren't offered: yours win. Files the
# tools write (marked GENERATED) are rebuilt by the tools, not offered here.

import hashlib
import json
import os

import yaml

from veil import config

DISMISSED_FILE = os.path.join(config.DATA_DIR, "starting-dismissed.json")


def _generated(file):
    try:
        with open(file) as f:
            head = "".join(f.readline() for _ in range(3))
    except OSError:
        return True
    return "GENERATED" in head


def _scalar(v):
    return isinstance(v, (str, int, float, bool)) or v is None


def _walk(start, mine, path, out):
    if isinstance(start, dict) and isinstance(mine, dict):
        for k, v in start.items():
            if k not in mine:
                out.append({"kind": "key", "path": path + [k], "value": v})
            else:
                _walk(v, mine[k], path + [k], out)
    elif isinstance(start, list) and isinstance(mine, list):
        for v in start:
            if _scalar(v) and v not in mine:
                out.append({"kind": "item", "path": path, "value": v})


def _id(file, item):
    raw = json.dumps([file, item["kind"], item["path"], item["value"]], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def dismissed():
    try:
        with open(DISMISSED_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def new_items():
    """[{id, file, kind (key | item), path, value}] in the starting copies that yours don't have."""
    gone = dismissed()
    out = []
    for src, dst in config.starting_copies():
        if not src.endswith((".yaml", ".yml")) or not os.path.exists(dst) or _generated(src):
            continue
        try:
            start, mine = config.load_yaml(src), config.load_yaml(dst)
        except (OSError, yaml.YAMLError):
            continue
        rel = os.path.relpath(dst, config.ROOT)
        found = []
        _walk(start, mine, [], found)
        for item in found:
            item["file"] = rel
            item["id"] = _id(rel, item)
            if item["id"] not in gone:
                out.append(item)
    return out


def _find(item_id):
    for item in new_items():
        if item["id"] == item_id:
            return item
    from veil.errors import VeilError
    raise VeilError("That isn't new any more (added, or hidden): reload the page", 404)


def add(item_id):
    """Put one new key or list word into the household's file, comments kept."""
    item = _find(item_id)

    def change(doc):
        node = doc
        for k in item["path"][:-1] if item["kind"] == "key" else item["path"]:
            node = node[k]
        if item["kind"] == "key":
            node[item["path"][-1]] = item["value"]
        else:
            node.append(item["value"])

    config.edit_yaml(config.path(item["file"]), change)
    return item


def dismiss(item_id):
    item = _find(item_id)
    gone = dismissed() | {item_id}
    os.makedirs(os.path.dirname(DISMISSED_FILE), exist_ok=True)
    tmp = DISMISSED_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(gone), f)
    os.replace(tmp, DISMISSED_FILE)
    return item
