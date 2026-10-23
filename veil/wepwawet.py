# veil/wepwawet.py - the Wepwawet standard, version 2 (issue #24): an app's actions as declarations.
#
# A user rule (veil/rules.py) is a chain of steps the household builds by hand. Most follow one of a
# few shapes, and version 2 of the x-wepwawet section names them, so an app (or the compliant copy
# Veil writes of an app that has no section) declares the action and the rule comes from it:
#
#   change   find one item by what was said, ask for the value, send the change   (rename)
#   act      find one item, ask first, call the command                           (delete)
#   read     find one item, say its fields                                         (find, when is)
#   list     read a list (only some of it, by date or a field), say it             (what's next, born today)
#
#   x-wepwawet:
#     actions:
#       rename:
#         starts: [rename]            # the words a request for it opens with
#         objects: []                 # a noun that must be said too (a project)
#         target:                     # one item of a list, found by what was said
#           from: GET /tasks          #   the command that lists them
#           find: {field: title, until: [to], last: true, act: 85, ask: 45}
#         confirm: {}                 # ask first: only when unsure; {always: true}: every time
#         value: {need: new_name, after: [to], question: "What should I call it?",
#                 read_back: {always: true, question: "Rename {item} to {new_name}?"}}   # said back first
#         send: {whole: "GET /tasks/{id}", set: {title: new_name}}   # the app wants the whole item back
#         command: "POST /tasks/{id}"  # what it calls
#         says: {lines: ["{item} is now {new_name}."]}
#
# compile(section) gives the rules; push_back(rules) writes the declarations for the rules that have
# one of those shapes, and leaves the rest custom (a rule the household keeps by hand).

import copy

from veil import rules

SEARCH_KEYS = ("field", "group", "until", "ignore", "last", "on_last")
MATCH_KEYS = ("act", "ask", "ties", "clear", "extra_words", "not_found")


def _clean(d):
    return {k: v for k, v in (d or {}).items() if v not in (None, "", [], {})}


def compile_action(name, a):
    """One declared action as a user rule ({words, objects, steps}), or None when it has no shape."""
    a = a or {}
    steps = []
    t = a.get("target")
    if t:
        find = dict(t.get("find") or {})
        steps += [{"call": t["from"]},
                  {"search": _clean({k: find[k] for k in SEARCH_KEYS if k in find})},
                  {"match": _clean({k: find[k] for k in MATCH_KEYS if k in find})}]
        if "confirm" in a:
            steps.append({"confirm": _clean(a.get("confirm"))})
        if a.get("value"):
            v = dict(a["value"])
            back = v.pop("read_back", None)
            steps.append({"ask": _clean(v)})
            if back is not None:            # the value said back before it's sent ("Rename Get to Me?")
                steps.append({"confirm": _clean(back)})
        if a.get("send"):
            s = a["send"]
            steps.append({"fresh_copy": _clean({"read": s.get("whole"), "set": s.get("set"), "fill_empty": s.get("fill_empty")})})
        if a.get("command"):
            steps.append({"call": a["command"]})
    elif a.get("from"):
        steps.append({"call": a["from"]})
        for p in a.get("pick") or []:          # [{filter: {...}}, {by_date: {...}}], in order
            steps.append(copy.deepcopy(p))
    else:
        return None
    steps.append({"response": _clean(a.get("says"))})
    out = {"words": list(a.get("starts") or []), "steps": steps}
    if a.get("objects"):
        out["objects"] = list(a["objects"])
    return out


def compile(section):
    """{name: rule} for every action the x-wepwawet section declares (version 2)."""
    out = {}
    for name, a in ((section or {}).get("actions") or {}).items():
        r = compile_action(str(name), a)
        if r:
            out[str(name)] = r
    return out


def _shape(kinds):
    """Which declared shape a rule's step kinds are, or None (custom)."""
    if kinds[:3] == ["call", "search", "match"]:
        rest = kinds[3:]
        rest = rest[1:] if rest[:1] == ["confirm"] else rest
        if rest == ["response"]:
            return "read"
        if rest == ["call", "response"]:
            return "act"
        tail = rest[2:] if rest[:2] == ["ask", "confirm"] else rest[1:] if rest[:1] == ["ask"] else None
        if tail in (["call", "response"], ["fresh_copy", "call", "response"]):
            return "change"
        return None
    if kinds[:1] == ["call"] and kinds[-1:] == ["response"] and all(k in ("filter", "by_date") for k in kinds[1:-1]):
        return "list"
    return None


def push_back(name, rule):
    """(the declaration, its shape) for a rule of one of the shapes, else (None, why it stays custom)."""
    steps = [rules.kind_of(s) for s in (rule or {}).get("steps") or []]
    kinds = [k for k, _ in steps]
    shape = _shape(kinds)
    if not shape:
        return None, "its steps aren't one of the shapes"
    says = dict(steps[-1][1])
    if says.get("one") not in (None, "", "no"):
        return None, "it says one thing at random"
    a = {"starts": list(rule.get("words") or [])}
    if rule.get("objects"):
        a["objects"] = list(rule["objects"])
    if shape == "list":
        a["from"] = steps[0][1]["command"]
        picks = [{k: p} for k, p in steps[1:-1]]
        if picks:
            a["pick"] = picks
    else:
        p = dict(steps[1][1], **steps[2][1])
        a["target"] = {"from": steps[0][1]["command"], "find": p}
        for k, p in steps[3:-1]:
            if k == "confirm" and "value" in a:
                a["value"]["read_back"] = p
            elif k == "confirm":
                a["confirm"] = p
            elif k == "ask":
                a["value"] = dict(p)
            elif k == "fresh_copy":
                a["send"] = _clean({"whole": p.get("read"), "set": p.get("set"), "fill_empty": p.get("fill_empty")})
            elif k == "call":
                a["command"] = p["command"]
    a["says"] = says
    return a, shape


def copy_of(app, hand_rules, version=None):
    """The Wepwawet section Veil writes for an app that has none (its compliant copy): each rule of a
    shape pushed back as an action, the rest kept as custom rules. (section, {name: why custom})."""
    actions, custom = {}, {}
    for n, r in (hand_rules or {}).items():
        a, why = push_back(n, r)
        if a is None:
            custom[str(n)] = why
        else:
            actions[str(n)] = a
    section = {"version": 2, "title": app,
               "source": _clean({"written_by": "Wepwawet Veil", "from": version, "pushed_back": sorted(actions)}),
               "actions": actions}
    return section, custom


def same(rule_a, rule_b):
    """Do two rules do the same thing (their words, objects and steps, saved names aside)?"""
    def norm(r):
        return {"words": list((r or {}).get("words") or []), "objects": list((r or {}).get("objects") or []),
                "steps": [(k, _clean(p)) for k, p in map(rules.kind_of, (r or {}).get("steps") or [])]}
    return norm(rule_a) == norm(rule_b)
