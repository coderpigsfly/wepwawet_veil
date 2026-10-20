#!/usr/bin/env python3
# tools/misses.py - learn level piece 3: review the misses you recorded by voice.
# For each miss: what happened then, what the router would do today, and your
# "should have been" note if you gave one. Nothing is judged for you and, unless you
# say fix or drop, nothing is changed.
# Run from ~/docker/house-router (the router must be running):
#   python3 tools/misses.py            list every miss: then -> now (a mishearing with what you
#                                      really said: heard -> today against said -> today)
#   python3 tools/misses.py 3 -v       miss 3 in full: the turn before, every reason then and now
#   python3 tools/misses.py fix 3      make miss 3 a test case expecting what she does today
#                                      (shows the case and asks first), then take it out of the log
#   python3 tools/misses.py drop 3     just take miss 3 out of the log (asks first)
#   add --yes to fix or drop to skip the question (the Tools page does)
# fix and drop change files you can see in git: git diff shows them, git restore undoes them.

import json
import os
import re
import sys
import urllib.request

import yaml

ROUTER = os.environ.get("ROUTER_URL", "http://localhost:8770").rstrip("/")
TOKEN = os.environ.get("ROUTER_TOKEN", "")   # when security: tools_token_required is on
MISSES = "learn/misses.yaml"
CASES_DIR = "tests/cases"
SETTINGS = "settings.yaml"

# what the words in a "should have been" note mean, and how speech-to-text tends to hear a
# topic's name in one ("chores" heard as "short"): vocab/learn.yaml note_paths and note_heard_as
# (moved out of the code Oct 13, so they grow with your misses)
_LEARN = (yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           "vocab", "learn.yaml"))) or {})
NOTE_PATHS = {str(k): str(v) for k, v in (_LEARN.get("note_paths") or {}).items()}
NOTE_HEARD_AS = {str(k): [str(x) for x in (v or [])] for k, v in (_LEARN.get("note_heard_as") or {}).items()}


def load():
    try:
        return (yaml.safe_load(open(MISSES)) or {}).get("misses") or []
    except FileNotFoundError:
        return []


def post(path, body):
    req = urllib.request.Request(ROUTER + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    return json.load(urllib.request.urlopen(req, timeout=30))


def history(m):
    b = m.get("before") or {}
    return [b["you"], b["her"]] if b.get("you") and b.get("her") else []


def replay(m):
    """What the router decides today for this miss (asks /explain; changes nothing)."""
    msgs = [{"role": "system", "content": "replay"}]
    for i, t in enumerate(history(m)):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": t})
    msgs.append({"role": "user", "content": m.get("heard", "")})
    return post("/explain", {"messages": msgs, "fresh_context": bool(history(m))})


def where(path, topic=None, action=None):
    return " ".join(x for x in (str(path), topic or "", f"({action})" if action else "") if x)


def note_means(note, topics):
    """(path, topic) the note points at, or (None, None) if it names nothing she knows."""
    n = (note or "").lower()
    for t in topics:
        for w in [t] + NOTE_HEARD_AS.get(t, []):
            if re.search(r"\b" + re.escape(w) + r"\b", n):
                return ("A", t)
    for words, path in NOTE_PATHS.items():
        if words in n:
            return (path, None)
    return (None, None)


def verdict(m, now, topics):
    then = (str(m.get("path")), m.get("topic"))
    nowp = (str(now.get("path")), now.get("topic"))
    want = note_means(m.get("should_be"), topics)
    if want[0]:
        hit = (nowp[0] in ("A", "B") and want[0] == "A" and nowp[1] == want[1]) or \
              (want[0] != "A" and nowp[0] == want[0])
        if hit:
            return "LOOKS FIXED"
    return "same" if then == nowp else "CHANGED"


def waiting(m):
    """She may have been waiting on an answer then; the replay can't know that."""
    why = " ".join(m.get("why") or []).lower()
    return str(m.get("path")) == "C" or "pending" in why or "answer to" in why


def show(misses, topics, verbose=None):
    if not misses:
        print("\nNo misses recorded.")
        return
    print(f"\nMisses recorded: {len(misses)}   (then -> today)")
    for i, m in enumerate(misses, 1):
        if verbose and i != verbose:
            continue
        try:
            now = replay(m)
        except Exception as e:
            print(f"  router not reachable: {e}")
            return
        v = verdict(m, now, topics)
        then = where(m.get("path"), m.get("topic"))
        today = where(now.get("path"), now.get("topic"), now.get("action"))
        count = f" x{m['count']}" if int(m.get("count", 1)) > 1 else ""
        print(f"{i:3}  {m.get('kind', '?'):8} \"{m.get('heard', '')[:48]}\"{count}")
        print(f"       then: {then:20} now: {today:24} {v}")
        if m.get("should_be"):
            meant = note_means(m["should_be"], topics)[1]
            heard_as = f" (read as {meant})" if meant and meant not in m["should_be"].lower() else ""
            print(f"       you said: should have been {m['should_be']}{heard_as}")
        if waiting(m):
            print("       note: she was waiting on an answer then; today's replay can't know that")
        if verbose:
            b = m.get("before") or {}
            print(f"       turn before: you \"{b.get('you', '')}\"  her \"{b.get('her', '')[:90]}\"")
            print(f"       she answered: {m.get('answer', '')[:200]}")
            for w in m.get("why") or []:
                print(f"       why then: {w}")
            for w in now.get("why") or []:
                print(f"       why now:  {w}")


def case_for(m, now):
    exp = {"path": str(now.get("path"))}
    for k in ("topic", "action", "kind"):
        if now.get(k) and not (k == "kind" and exp["path"] in ("A", "B")):
            exp[k] = now[k]
    case = {"name": f"miss: {m.get('heard', '')[:50]}", "say": m.get("heard", "")}
    if history(m):
        case["history"] = history(m)
    case["expect"] = exp
    what = "an engine miss" if m.get("kind") == "engine" else "a miss"
    note = f"recorded by voice {m.get('first', '')} as {what}"
    if m.get("should_be"):
        note += f"; you said it should have been {m['should_be']}"
    return case, note


def target_file(now):
    """chores.yaml for a chores case (it needs Donetick), weather.yaml for weather, else core.yaml."""
    t = now.get("topic")
    if t and os.path.exists(os.path.join(CASES_DIR, f"{t}.yaml")):
        return os.path.join(CASES_DIR, f"{t}.yaml")
    return os.path.join(CASES_DIR, "core.yaml")


def as_text(case, note):
    body = yaml.safe_dump([case], sort_keys=False, allow_unicode=True, width=110)
    return f"# {note}\n{body}"


def confirm(q):
    if "--yes" in sys.argv:               # the Tools page answers for you (you pressed the button)
        print(q + " yes")
        return True
    try:
        return input(q + " (y/n) ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def drop(m):
    r = post("/learn/drop", {"kind": m.get("kind"), "heard": m.get("heard", "")})
    print("Taken out of the miss log." if r.get("dropped") else "It wasn't in the miss log any more.")


def main():
    args = [a for a in sys.argv[1:] if a != "--yes"]
    topics = list(((yaml.safe_load(open(SETTINGS)) or {}).get("topics") or {}).keys())
    misses = load()
    if args and args[0] in ("fix", "drop"):
        if len(args) < 2 or not args[1].isdigit() or not 1 <= int(args[1]) <= len(misses):
            print(f"Which miss? Give its number (1 to {len(misses)}): python3 tools/misses.py {args[0]} 3")
            return
        m = misses[int(args[1]) - 1]
        show([m], topics)
        if args[0] == "drop":
            if confirm("Take this miss out of the log?"):
                drop(m)
            else:
                print("Nothing changed.")
            return
        now = replay(m)
        case, note = case_for(m, now)
        path = target_file(now)
        text = as_text(case, note)
        print(f"\nThis test case goes at the end of {path}, expecting what she does today:\n")
        print("  " + text.replace("\n", "\n  "))
        if not confirm("Write it and take the miss out of the log?"):
            print("Nothing changed.")
            return
        with open(path) as f:
            old = f.read()
        with open(path, "w") as f:
            f.write(old.rstrip() + "\n\n" + text + "\n\n")
        print(f"Written to {path}.")
        drop(m)
        print("Run python3 tools/regress.py to see it pass; git diff shows both changes.")
        return
    verbose = int(args[0]) if args and args[0].isdigit() else None
    show(misses, topics, verbose)


if __name__ == "__main__":
    main()
