#!/usr/bin/env python3
# addons/flair/tools/build_flair.py (the Flair add-on's tool) - her flourishes from public-domain books, picked by you.
# Run on myserver from ~/docker/house-router:
#   python3 addons/flair/tools/build_flair.py refresh [assistant]   download the books in personality/sources.yaml
#   python3 addons/flair/tools/build_flair.py mine iris        propose lines -> personality/candidates/iris.yaml
#   python3 addons/flair/tools/build_flair.py approve iris     your keep: yes lines move into her lines bank (personality/iris.yaml)
#   (or Accept them one by one on the Persona Flair page)
# Then: docker compose restart
#
# The review: open personality/candidates/<assistant>.yaml in your editor, change keep: no to
# keep: yes for lines you like (fix slot, topics or mood if the guess is wrong; you can even
# reword one a little). Mining again keeps your choices. Approving writes only kept lines, and
# once she has approved lines, the placeholder lines in her personality file are ignored.

import json
import os
import re
import sys
import urllib.request

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the Flair add-on (addons/flair)
ROOT = os.path.dirname(os.path.dirname(HERE))                             # the router's folder
PERSONALITY = os.path.join(os.environ.get("ROUTER_ROOT", ROOT), "personality")
os.environ.setdefault("ROUTER_ROOT", ROOT)        # flairlines finds the router's files
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import flairlines  # noqa: E402
SOURCES = os.path.join(PERSONALITY, "sources.yaml")

COMBING = os.path.join(PERSONALITY, "combing.yaml")


def words_rx(entries, anchored=False):
    """A whole-word pattern for a combing.yaml list: * = any ending, -? = optional hyphen."""
    parts = []
    for e in entries or []:
        e = str(e).strip()
        if not e:
            continue
        p = re.escape(e).replace(r"\-\?", "-?").replace(r"\*", r"\w*").replace(r"\ ", " ")
        parts.append(p)
    if not parts:
        return re.compile(r"(?!x)x")           # matches nothing
    body = "|".join(parts)
    return re.compile((r"^(" if anchored else r"\b(") + body + r")\b", re.I)


def load_combing(who=None):
    """personality/combing.yaml, with the assistant's own combing: (sources.yaml) laid on top."""
    spec = yaml.safe_load(open(COMBING)) or {} if os.path.exists(COMBING) else {}
    if who:
        own = ((load_sources().get(who) or {}).get("combing")) or {}
        for k, v in own.items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k] = dict(spec[k], **v)
            else:
                spec[k] = v
    return spec


def comb(who=None):
    """The compiled patterns and knobs for one assistant (or the shared ones)."""
    c = load_combing(who)
    return {
        "UNKIND": words_rx(c.get("never")),
        "STORY": words_rx(c.get("story_words")),
        "INTERJECTION": words_rx(c.get("interjections"), anchored=True),
        "CLOSER": words_rx(c.get("closer_words")),
        "SORRY": words_rx((c.get("moods") or {}).get("sorry")),
        "WARNING": words_rx((c.get("moods") or {}).get("warning")),
        "TOPICS": {t: words_rx(ws) for t, ws in (c.get("topics") or {}).items()},
        "SAY": "(?:" + "|".join(re.escape(w) for w in (c.get("said_words") or ["said"])) + ")",
        "ADJ": [str(a) for a in (c.get("speaker_adjectives") or [])],
        "MAX_WORDS": int(c.get("max_words", 9)),
        "CAPS": set(c.get("allowed_capitals") or ["I"]),
        "SCORE": dict({"said_by_her_kind": 3, "nearby": 1, "interjection": 2, "short": 1,
                       "short_words": 4}, **(c.get("score") or {})),
    }


C = None          # set by mine() for the assistant being mined


def load_sources():
    return yaml.safe_load(open(SOURCES)) or {}


def local(path):
    return os.path.expanduser(path)


def refresh(only=None):
    """Download each book to its local path. Says plainly what went wrong for any that didn't
    (Oct 14: Download her books seemed to do nothing), and fails if none came down."""
    got, failed = 0, []
    for who, spec in load_sources().items():
        if only and who != only:
            continue
        for b in spec.get("books") or []:
            dest = local(b["local"])
            print(f"  {b['title']}\n    <- {b['url']}")
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                req = urllib.request.Request(b["url"], headers={"User-Agent": "Mozilla/5.0 (house-router book download)",
                                                                "Accept": "text/plain, */*"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                    kind = r.headers.get("Content-Type", "")
                head = body[:400].lower()
                if b"<html" in head or b"<!doctype" in head or "html" in kind:
                    raise ValueError(f"got a web page, not the book ({kind or 'html'}): the address may be wrong, or the site is refusing")
                if len(body) < 10000:
                    raise ValueError(f"only {len(body)} bytes came back: not a whole book")
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    f.write(body)
                os.replace(tmp, dest)
                got += 1
                print(f"    -> {dest} ({len(body) // 1024} KB)")
            except Exception as e:
                failed.append(b["title"])
                print(f"    ! couldn't download: {type(e).__name__}: {e}")
    if not got and not failed:
        sys.exit(f"No books listed{' for ' + only if only else ''} in personality/sources.yaml.")
    print(f"\n{got} downloaded, {len(failed)} not" + (f" ({', '.join(failed)})" if failed else "") +
          f". Saved under {os.path.dirname(local('~/datasets/books/x'))} (in the container, ~ is /root; "
          "docker-compose.yml mounts your ~/datasets there).")
    if not got:
        sys.exit(1)


def book_text(path):
    t = open(path, encoding="utf-8", errors="ignore").read()
    for start in ("*** START OF", "***START OF"):
        if start in t:
            t = t.split(start, 1)[1].split("\n", 1)[-1]
    for end in ("*** END OF", "***END OF", "End of the Project Gutenberg", "End of Project Gutenberg"):
        if end in t:
            t = t.split(end, 1)[0]
    return t.replace("’", "'").replace("‘", "'").replace("_", "")


def speaker_pattern(speakers):
    names = "|".join(re.escape(s) for s in sorted(speakers or [], key=len, reverse=True))
    adj = "".join(f"{re.escape(a)}\\s+|" for a in C["ADJ"]).rstrip("|")
    who = rf"(?:the\s+)?(?:{adj})?(?:{names})" if adj else rf"(?:the\s+)?(?:{names})"
    return re.compile(rf"{C['SAY']}\s+{who}\b|\b{who}\s+{C['SAY']}", re.I)


def sentences(quote):
    for s in re.split(r"(?<=[.!?])\s+", quote.strip()):
        yield s.strip(" ,;:-—")


def usable(s):
    """A short, whole, kind sentence that makes sense on its own."""
    w = s.split()
    if not (1 <= len(w) <= C["MAX_WORDS"]) or not s or not s[0].isupper() or s[-1] not in ".!":
        return False
    if len(w) == 1 and not s.endswith("!"):
        return False
    if C["UNKIND"].search(s) or C["STORY"].search(s) or re.search(r"\d", s):
        return False
    # no names of story people or places ("Dorothy", "Kansas"); "I" and "Oz"-free
    if any(x[:1].isupper() for x in (y.strip("!.,'\"") for y in w[1:]) if x not in C["CAPS"]):
        return False
    return True


def guess(s):
    """slot, topics and mood, guessed from the words (you can change them in review)."""
    slot = "closer" if C["CLOSER"].search(s) else "opener"
    mood = ["sorry"] if C["SORRY"].search(s) else ["warning"] if C["WARNING"].search(s) else ["plain"]
    topics = [t for t, rx in C["TOPICS"].items() if rx.search(s)] or ["any"]
    return slot, topics, mood


def mine(who):
    global C
    spec = load_sources().get(who)
    if not spec:
        sys.exit(f"no '{who}' in personality/sources.yaml")
    C = comb(who)
    said_by = speaker_pattern(spec.get("speakers"))
    near = re.compile(r"\b(" + "|".join(re.escape(n) for n in spec.get("near") or []) + r")\b", re.I)
    found = {}
    read, missing = 0, []
    for b in spec.get("books") or []:
        path = local(b["local"])
        if not os.path.exists(path):
            missing.append(b["local"])
            print(f"  ! missing {b['local']}: run refresh first")
            continue
        read += 1
        paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", book_text(path))]
        for i, p in enumerate(paras):
            hers = bool(said_by.search(p))
            close = bool(near.search(" ".join(paras[max(0, i - 1):i + 1])))
            if not (hers or close):
                continue
            for q in re.findall(r'["“]([^"”]{2,240})["”]', p):
                for s in sentences(q):
                    if not usable(s):
                        continue
                    k = s.lower()
                    e = found.setdefault(k, {"text": s, "hers": 0, "near": 0, "books": set()})
                    e["hers" if hers else "near"] += 1
                    e["books"].add(b["title"].split(" (")[0])
    if not read:
        # none of her books on disk where this ran: say so and leave her list alone (Oct 14: combing
        # with no books used to leave only the few lines kept from before, which looked like a result)
        sys.exit(f"None of {who}'s {len(missing)} books are on disk here ({os.path.dirname(local(missing[0])) if missing else 'no books listed'}). "
                 f"Run Download her books (python3 addons/flair/tools/build_flair.py refresh {who}) first. Her list was left as it was.")
    # rank: said by her kind most, then interjections (they suit any answer), then how often seen
    k = C["SCORE"]

    def score(e):
        return k["said_by_her_kind"] * e["hers"] + k["nearby"] * e["near"] \
            + (k["interjection"] if C["INTERJECTION"].search(e["text"]) else 0) \
            + (k["short"] if len(e["text"].split()) <= k["short_words"] else 0)
    ranked = sorted(found.values(), key=lambda e: (-score(e), e["text"]))

    os.makedirs(os.path.join(PERSONALITY, "candidates"), exist_ok=True)
    out = os.path.join(PERSONALITY, "candidates", f"{who}.yaml")
    old = {}
    if os.path.exists(out):
        for c in (yaml.safe_load(open(out)) or {}).get("candidates") or []:
            old[c.get("found", c.get("text", "")).lower()] = c
    cands = []
    gone = flairlines.taken(who)       # accepted, in her lines bank, or dropped: never offered again
    for e in ranked:
        if flairlines.key(e["text"]) in gone:
            continue
        slot, topics, mood = guess(e["text"])
        c = {"keep": "no", "text": e["text"], "slot": slot, "topics": topics, "mood": mood,
             "from": ", ".join(sorted(e["books"])),
             "seen": f"seen {e['hers']}x said by her kind, {e['near']}x nearby"}
        prev = old.pop(e["text"].lower(), None)
        if prev:        # your choices and edits survive a re-mine
            for key in ("keep", "text", "slot", "topics", "mood"):
                c[key] = prev.get(key, c[key])
        c["found"] = e["text"]
        cands.append(c)
    for prev in old.values():      # lines you kept that the books no longer give (e.g. a book removed)
        if str(prev.get("keep")).lower() in ("yes", "true") and flairlines.key(prev.get("found", prev.get("text"))) not in gone \
                and flairlines.key(prev.get("text")) not in gone:
            cands.append(prev)
    with open(out, "w") as f:
        f.write(f"# personality/candidates/{who}.yaml - GENERATED by addons/flair/tools/build_flair.py mine {who}\n"
                "# Review: change keep: no to keep: yes for lines she should say. You may fix slot\n"
                "# (opener / closer), topics ([any] or weather, chores, router), mood ([plain], sorry,\n"
                "# warning) or reword the text a little; 'found' is the book's wording, used to keep\n"
                "# your choices when mining again. Best guesses are at the top.\n"
                f"# Then: python3 addons/flair/tools/build_flair.py approve {who}   and   docker compose restart\n\n")
        f.write("candidates:\n")
        for c in cands:
            keep = "yes" if str(c.get("keep")).lower() in ("yes", "true") else "no"
            f.write(f"- keep: {keep}\n"
                    f"  text: {json.dumps(c['text'], ensure_ascii=False)}\n"
                    f"  slot: {c['slot']}\n"
                    f"  topics: [{', '.join(c['topics'])}]\n"
                    f"  mood: [{', '.join(c['mood'])}]\n"
                    f"  from: {json.dumps(c.get('from', ''), ensure_ascii=False)}   # {c.get('seen', '')}\n"
                    f"  found: {json.dumps(c.get('found', c['text']), ensure_ascii=False)}\n")
        f.write("\n\n")
    print(f"{len(cands)} candidate lines for {who} -> personality/candidates/{who}.yaml")
    for c in cands[:25]:
        print(f"  {c['slot']:7} {'/'.join(c['topics']):14} {'/'.join(c['mood']):8} {c['text']}")


def approve(who):
    """Every keep: yes line moves into her lines bank, as Accept on the Persona Flair page does."""
    if not os.path.exists(os.path.join(PERSONALITY, "candidates", f"{who}.yaml")):
        sys.exit(f"nothing to approve: run  python3 addons/flair/tools/build_flair.py mine {who}  first")
    n = flairlines.accept_kept(who)
    print(f"{n} kept lines moved into {who}'s lines bank ({len(flairlines.bank(who))} there) -> personality/{who}.yaml")
    print("Then: docker compose restart")


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("refresh", "mine", "approve"):
        sys.exit(__doc__ or "usage: build_flair.py refresh [assistant] | mine <assistant> | approve <assistant>")
    if args[0] == "refresh":
        refresh(args[1] if len(args) > 1 else None)
    elif len(args) < 2:
        sys.exit(f"which assistant?  python3 addons/flair/tools/build_flair.py {args[0]} iris")
    elif args[0] == "mine":
        mine(args[1])
    else:
        approve(args[1])


if __name__ == "__main__":
    main()
