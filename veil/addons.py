# veil/addons.py - add-ons: what isn't the router's own job, kept outside its core (issue #25).
#
# Wepwawet's function is to keep a request on platform, using what is made available to it. The
# core does that and nothing more; everything else is an add-on, asked the same question as any
# app: does it improve the function? (serves: on_platform, or comfort, said honestly).
#
# An add-on is a folder, addons/<name>/:
#   addon.yaml   what it is, as a Wepwawet section is (the standard applies to it):
#     name, title, version, about
#     serves:    on_platform (it keeps requests at home: how, in serves_how) | comfort (it doesn't, and costs nothing)
#     data:      {kind: record} | {kind: transient, pace: slow | fast}     (its data life)
#     slots:     the places on the path it works at (SLOTS below)
#     provides:  services other add-ons may call (functions of its module)
#     needs:     the add-ons it needs (one way only; no cycles)
#     may:       what it may touch: read (the words, who spoke), answer (change the answer), block, apps
#     pages:     [{id, label, group, role}]: its menu items; its page script is page.js beside it
#     on_error:  skip (the default: the core goes on without it) | block (a security add-on)
#     budget_ms: the most each slot call may take (the gate measures it)
#     path:      inbound (Home Assistant -> Wepwawet -> ... -> Oread: check, understand, before_off_platform)
#                | outbound (Oread -> Wepwawet -> ... -> Home Assistant or the device: dress, learn)
#                Inbound chains: the words from speech-to-text go to a key word, an integration's first, else an
#                action add-on's (key_word: Brain fleas), then before going out (Bank), then Off-Platform. Each
#                that has no key word in them hands them back at once. What claims them may be handed words another
#                integration supplied first (supply: Time puts Easter Sunday as its date for the weather):
#                weather(litcal(the words)). When the claimer can't answer, it names its blank (need: when,
#                about: the picnic) and each module with its flag still on is asked to fill it (fill); one that
#                answers turns its flag off, and the claimer is asked again; when no one can fill it, she asks
#                (clarification). Every module contributes once: nothing loops.
#     kind:      action (it performs a function: answers or corrects: the Bank, Brain fleas, Mishearings; its
#                answer is the line the dress add-ons start from, the base of what's spoken) |
#                dress (it adds to her answer: Flair, Name Sparkle, Roman numerals) | guard (the Firewall)
#     positions: outbound, where it touches the line for text-to-speech: beginning, end (before or after the
#                result: Flair, Name Sparkle), or replace (inside it: Roman numerals)
# Precedence on the outbound path: a replace add-on first (it changes the result itself), then the ones at the
# beginning or end in the household's order (settings.yaml addons: order:, set on the Add-ons page), each
# getting the line the one before it left: the start of chaining. An integration's own answer is the result
# itself (the action): add-ons only dress it, never come before it. An add-on that says last: true (the
# Firewall, a security add-on that may block) runs after every other, whatever comes before it.
#     tools:     its tools, on the Tools page while it's on (the same shape as tools/tools.yaml)
#   addon.py     one function per slot, and its services
#   settings.yaml, test_addon.py   its own settings and tests (never in the core's settings)
#
# The core calls whatever is registered in a slot, in order; it never imports an add-on by name.
# Which add-ons are on: settings.yaml addons: enabled: [...]. An add-on's needs come on with it.

import importlib.util
import inspect
import logging
import os
import sys
import time

import yaml

log = logging.getLogger("router")

# the places on the path, each with the shape of its function and what it may do there
PATH_OF = {"check": "inbound", "understand": "inbound", "key_word": "inbound", "supply": "inbound", "fill": "inbound",
           "before_off_platform": "inbound", "dress": "outbound", "learn": "outbound"}
POSITIONS = {"beginning", "end", "replace"}
SLOTS = {
    "check": {"args": ["said", "ctx"], "may": "block", "about": "before anything is done: None, or {block: what she says}"},
    "understand": {"args": ["said", "ctx"], "may": "read", "about": "the words, before deciding: the words to decide on"},
    "key_word": {"args": ["said", "ctx"], "may": "answer", "about": "after the integrations' own key words found nothing: None, or {action, score, how}: an action add-on's own"},
    "supply": {"args": ["said", "ctx"], "may": "read", "about": "after the claim, before the claiming app is asked: the words it gets, with what other integrations supply (a feast day's date)"},
    "fill": {"args": ["blank", "ctx"], "may": "answer", "about": "the claiming app can't answer without a blank ({need: when, about: the picnic}): None, {words: what's asked now, with it filled}, or {ask: her question, choices: [...]}"},
    "before_off_platform": {"args": ["said", "ctx"], "may": "answer", "about": "before going out: None, an answer from home, or {kind: ask, meant}: her did-you-mean first (the window)"},
    "dress": {"args": ["text", "ctx"], "may": "answer", "about": "her answer, before it's spoken: the answer to speak"},
    "learn": {"args": ["said", "text", "ctx"], "may": "read", "about": "after the answer: nothing back"},
}
MAY = {"read", "answer", "block", "apps"}
PASS_ON = ("dress", "understand", "supply")      # the slots whose words go on from one add-on to the next
HOLD = "\u2063"     # a held line's mark (util.HOLD): the dress add-ons leave it alone; taken out before it's spoken
SERVES = {"on_platform", "comfort"}
REQUIRED = ("name", "title", "version", "about", "serves", "data", "may", "path")


class AddonError(Exception):
    pass


def manifest_problems(m, name=None):
    """What's wrong with an addon.yaml against the standard, as sentences ([] when nothing)."""
    out = []
    for k in REQUIRED:
        if m.get(k) in (None, "", [], {}):
            out.append(f"it doesn't say its {k}")
    if name and m.get("name") and m["name"] != name:
        out.append(f"its name ({m['name']}) isn't its folder's ({name})")
    if m.get("serves") and m["serves"] not in SERVES:
        out.append(f"serves: is {m['serves']}, not on_platform or comfort")
    if m.get("serves") == "on_platform" and not m.get("serves_how"):
        out.append("it serves the function but doesn't say how (serves_how)")
    data = m.get("data") or {}
    if data and data.get("kind") not in ("record", "transient"):
        out.append("its data life isn't record or transient")
    if data.get("kind") == "transient" and data.get("pace") not in ("slow", "fast"):
        out.append("its transient data doesn't say slow or fast")
    may = set(m.get("may") or [])
    if may - MAY:
        out.append(f"it asks for what no add-on may have: {', '.join(sorted(may - MAY))}")
    if m.get("kind") and m["kind"] not in ("action", "dress", "guard"):
        out.append(f"kind: is {m['kind']}, not action, dress or guard")
    if m.get("path") and m["path"] not in ("inbound", "outbound"):
        out.append(f"path: is {m['path']}, not inbound or outbound")
    pos = set(m.get("positions") or [])
    if m.get("path") == "outbound" and "dress" in (m.get("slots") or []) and not pos:
        out.append("an outbound add-on that dresses her answer says where (positions: beginning, end, replace)")
    if pos - POSITIONS:
        out.append(f"positions are beginning, end or replace, not {', '.join(sorted(pos - POSITIONS))}")
    for s in m.get("slots") or []:
        if s in PATH_OF and m.get("path") and PATH_OF[s] != m["path"]:
            out.append(f"the {s} slot is on the {PATH_OF[s]} path, not {m['path']}")
        if s not in SLOTS:
            out.append(f"{s} isn't a slot on the path")
        elif SLOTS[s]["may"] not in may and SLOTS[s]["may"] != "read":
            out.append(f"the {s} slot needs may: {SLOTS[s]['may']}")
    if m.get("serves") == "comfort" and may & {"block", "apps"}:
        out.append("a comfort add-on may not block or call apps")
    if m.get("last") and "block" not in may:
        out.append("only an add-on that may block runs last (last: true, the Firewall)")
    if m.get("on_error", "skip") not in ("skip", "block"):
        out.append("on_error is skip or block")
    if m.get("on_error") == "block" and "block" not in may:
        out.append("on_error: block needs may: block")
    for p in m.get("pages") or []:
        if not (isinstance(p, dict) and p.get("id") and p.get("label")):
            out.append("a page needs an id and a label")
    return out


class Addons:
    """The add-ons found, which are on, and their slots and services, in the order they run."""

    def __init__(self, folder, enabled=(), order=()):
        self.folder = folder
        self.found, self.broken, self.on = {}, {}, []
        self.slots = {s: [] for s in SLOTS}
        self.services = {}
        self.timing = {}            # name.slot -> [calls, ms in all, errors]
        if not os.path.isdir(folder):
            return
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name, "addon.yaml")
            if not os.path.isfile(path):
                continue
            try:
                with open(path) as f:
                    m = yaml.safe_load(f) or {}
            except Exception as e:
                self.broken[name] = f"its addon.yaml can't be read: {e}"
                continue
            wrong = manifest_problems(m, name)
            if wrong:
                self.broken[name] = "; ".join(wrong)
                continue
            self.found[name] = m
        for name in self.order(enabled):
            try:
                self._load(name)
            except Exception as e:
                self.broken[name] = str(e)
                log.info("  ! add-on %s not loaded: %s", name, e)
        self.ranked = self.precedence(order)
        for s in self.slots:            # each slot in precedence: replace first, then the household's order
            self.slots[s].sort(key=lambda x: self.ranked.index(x[0]) if x[0] in self.ranked else len(self.ranked))

    def precedence(self, order=()):
        """The add-ons that are on, in the order they run: any that replace inside the result first, then
        the household's order (addons: order:), then any not placed yet, as they were turned on."""
        on = list(self.on)
        mine = [n for n in order or [] if n in on] + [n for n in on if n not in (order or [])]
        last = [n for n in mine if self.found[n].get("last")]          # the Firewall: always after every other
        mine = [n for n in mine if n not in last]
        replace = [n for n in mine if "replace" in (self.found[n].get("positions") or [])]
        return replace + [n for n in mine if n not in replace] + last

    def order(self, enabled):
        """The add-ons to turn on, each after what it needs (its needs come on with it); a cycle or a need
        that isn't there is refused."""
        out, seen = [], set()

        def visit(n, path):
            if n in path:
                raise AddonError(f"{' -> '.join(path + [n])}: a cycle")
            if n in seen:
                return
            if n not in self.found:
                raise AddonError(f"{n} is needed{' by ' + path[-1] if path else ''} but isn't there or is broken")
            for d in self.found[n].get("needs") or []:
                visit(str(d), path + [n])
            seen.add(n)
            out.append(n)
        for n in enabled or []:
            try:
                visit(str(n), [])
            except AddonError as e:
                self.broken[str(n)] = str(e)
                log.info("  ! add-on %s not turned on: %s", n, e)
        return out

    def _load(self, name):
        m = self.found[name]
        here = os.path.join(self.folder, name)
        if here not in sys.path:
            sys.path.insert(0, here)      # its own modules beside it (flair.py, flairlines.py)
        spec = importlib.util.spec_from_file_location(f"addon_{name}", os.path.join(self.folder, name, "addon.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"addon_{name}"] = mod      # its doors (api.py) reach it by this name
        spec.loader.exec_module(mod)
        problems = shape_problems(m, mod)
        if problems:
            raise AddonError("; ".join(problems))
        mod.SERVICES = self          # what it needs, called through here: services("time").read_day(...)
        if hasattr(mod, "setup"):
            mod.setup(os.path.join(self.folder, name))
        for s in m.get("slots") or []:
            self.slots[s].append((name, getattr(mod, s), m))
        for svc in m.get("provides") or []:
            self.services[f"{name}.{svc}"] = getattr(mod, svc)
        self.on.append(name)
        log.info("loaded add-on: %s %s (%s)", name, m.get("version"), ", ".join(m.get("slots") or []) or "services")

    def register_api(self, app):
        """Each add-on that's on with its own doors (api.py: register(app)) adds them to the pages server:
        an add-on that's off has none."""
        for name in self.on:
            path = os.path.join(self.folder, name, "api.py")
            if not os.path.exists(path):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"addon_{name}_api", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.register(app)
                log.info("  add-on %s: its pages' doors added", name)
            except Exception as e:
                log.info("  ! add-on %s: its doors weren't added: %s", name, e)

    def service(self, name, caller=None):
        """A service of an add-on that's on ("time.read_day"), for an add-on that declared it needs it."""
        owner = name.split(".", 1)[0]
        if caller and owner not in (self.found.get(caller, {}).get("needs") or []) and owner != caller:
            raise AddonError(f"{caller} calls {name} but doesn't say it needs {owner}")
        if name not in self.services:
            raise AddonError(f"no add-on that's on provides {name}")
        return self.services[name]

    def run(self, slot, *args):
        """Each add-on in the slot, in order: dress, understand and supply pass their result on; check, key_word
        and before_off_platform stop at the first that answers. A line marked held (util.HOLD: Loose language's,
        until it has closed out its text) is never dressed. An error is logged and skipped, unless the
        add-on says on_error: block (then check blocks). Returns the result (or the input unchanged)."""
        value = args[0] if slot in PASS_ON else None
        if slot == "dress" and HOLD in str(value or ""):
            return value
        for name, fn, m in self.slots.get(slot) or []:
            key = f"{name}.{slot}"
            t0 = time.monotonic()
            try:
                call = (value,) + args[1:] if slot in PASS_ON else args
                got = fn(*call)
            except Exception as e:
                self._time(key, t0, True)
                log.info("  ! add-on %s failed in %s: %s", name, slot, e)
                if slot == "check" and m.get("on_error") == "block":
                    return {"block": "", "why": f"the add-on {name} failed, and it fails closed"}
                continue
            self._time(key, t0)
            if slot in PASS_ON:
                value = got if isinstance(got, str) else value
            elif got:
                return got
        return value

    def _time(self, key, t0, failed=False):
        t = self.timing.setdefault(key, [0, 0.0, 0])
        t[0] += 1
        t[1] += (time.monotonic() - t0) * 1000
        t[2] += 1 if failed else 0

    def listing(self, enabled=()):
        """Every add-on found, for the Add-ons page: its manifest, on or off, why it's broken, its timing."""
        out = []
        for name in sorted(set(self.found) | set(self.broken)):
            m = self.found.get(name) or {}
            out.append({"name": name, "title": m.get("title") or name, "version": m.get("version"), "about": m.get("about"),
                        "serves": m.get("serves"), "serves_how": m.get("serves_how"), "data": m.get("data"),
                        "slots": m.get("slots") or [], "needs": m.get("needs") or [], "may": m.get("may") or [],
                        "path": m.get("path"), "positions": m.get("positions") or [], "kind": m.get("kind"),
                        "rank": self.ranked.index(name) if name in getattr(self, "ranked", []) else None,
                        "pages": m.get("pages") or [], "on": name in self.on, "chosen": name in (enabled or []),
                        "needed_by": sorted(n for n, x in self.found.items() if name in (x.get("needs") or []) and n in self.on),
                        "broken": self.broken.get(name),
                        "timing": {k.split(".", 1)[1]: {"calls": v[0], "avg_ms": round(v[1] / v[0], 2) if v[0] else 0, "errors": v[2]}
                                   for k, v in self.timing.items() if k.startswith(name + ".")}})
        return out

    def pages(self):
        """The menu items of the add-ons that are on: [{addon, id, label, group, role}]."""
        return [dict(p, addon=name, group=p.get("group") or "Add-ons", role=p.get("role") or "administrator")
                for name in self.on for p in self.found[name].get("pages") or []]


def shape_problems(m, mod):
    """Each slot it declares has a function of that slot's shape; each service it provides exists."""
    out = []
    for s in m.get("slots") or []:
        fn = getattr(mod, s, None)
        if not callable(fn):
            out.append(f"it declares the {s} slot but has no {s}()")
            continue
        args = [p for p in inspect.signature(fn).parameters]
        if args != SLOTS[s]["args"]:
            out.append(f"its {s}() takes ({', '.join(args)}), not ({', '.join(SLOTS[s]['args'])})")
    for svc in m.get("provides") or []:
        if not callable(getattr(mod, svc, None)):
            out.append(f"it provides {svc} but has no {svc}()")
    return out
