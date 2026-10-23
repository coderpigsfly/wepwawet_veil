"""addons/flair/api.py - Persona Flair's doors: her flair knobs, her lines bank, the books she combs.
Moved out of the core's pages server (veil/web.py) with the add-on (issue #25): registered only when the
add-on is on, so with it off none of these doors exist."""
import os  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401

from fastapi import Request  # noqa: F401


def register(app):
    from veil import apps, config, lists, security  # noqa: F401
    from veil.errors import VeilError  # noqa: F401
    from veil.web import PERS, assistant_ok, audit, body_of, choices, need, restart_note, router  # noqa: F401
    import flairlines  # noqa: E402  (beside it: the add-on's folder is on the path when it's loaded)
    SLOTS = ("any", "opener", "closer", "aside")
    MOODS = ("plain", "warning", "sorry")

    def clean_flourish(f):
        text = " ".join(str(f.get("text") or "").split())
        if not text or len(text) > 200:
            raise VeilError("Each flourish needs text (200 characters at most)")
        if text.endswith("?"):
            raise VeilError(f"\"{text}\": a flourish is never a question (the persona must end on its own question)")
        slot = str(f.get("slot") or "opener").lower()
        if slot not in SLOTS:
            raise VeilError(f"slot is one of {', '.join(SLOTS)}")
        topics_ = [str(t).lower() for t in (f.get("topics") or ["any"])] or ["any"]
        mood = [str(m).lower() for m in (f.get("mood") or ["plain"])] or ["plain"]
        if any(m not in MOODS for m in mood):
            raise VeilError(f"mood is one or more of {', '.join(MOODS)}")
        out = {"text": text, "slot": slot, "topics": topics_, "mood": mood}
        if f.get("placeholder"):
            out["placeholder"] = True
        return out


    @app.get("/api/flair")
    def flair_all(request: Request):
        need(request, "viewer")
        r = router()
        names = sorted(set(r.PERSONAS) | set(choices("assistants")))
        out = []
        for who in names:
            try:
                spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
            except FileNotFoundError:
                spec = {}
            try:
                approved = len(config.load_yaml(os.path.join(PERS, "approved", f"{who}.yaml")).get("flourishes") or [])
            except FileNotFoundError:
                approved = 0
            try:
                cands = config.load_yaml(os.path.join(PERS, "candidates", f"{who}.yaml")).get("candidates") or []
            except FileNotFoundError:
                cands = []
            out.append({"name": who, "rate": spec.get("rate"), "max_in_a_row": spec.get("max_in_a_row"),
                        "flourishes": len(spec.get("flourishes") or []), "approved": approved,
                        "candidates": len(cands), "kept": sum(str(c.get("keep")).lower() in ("yes", "true") for c in cands),
                        "has_file": bool(spec), "names": spec.get("names") or {}})
        return {"personalities": out, "names_in_replies": config.settings().get("names_in_replies")}


    @app.get("/api/flair/{who}")
    def flair_one(request: Request, who: str):
        need(request, "viewer")
        assistant_ok(who)
        try:
            spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
        except FileNotFoundError:
            spec = {"rate": 0, "max_in_a_row": 1, "flourishes": []}
        try:
            approved = config.plain(config.load_yaml(os.path.join(PERS, "approved", f"{who}.yaml")).get("flourishes") or [])
        except FileNotFoundError:
            approved = []
        try:
            src = config.plain((config.load_yaml(os.path.join(PERS, "sources.yaml")) or {}).get(who) or {})
        except FileNotFoundError:
            src = {}
        return {"name": who, "personality": spec, "approved": approved, "sources": src}


    @app.put("/api/flair/{who}")
    async def flair_save(request: Request, who: str):
        """Her personality file: rate, max_in_a_row, names (rate, max_in_a_row, enabled), flourishes."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        try:
            rate = float(b.get("rate", 0))
            streak = int(b.get("max_in_a_row", 1))
        except (TypeError, ValueError):
            raise VeilError("rate is a number from 0 to 1; max_in_a_row a whole number")
        if not 0 <= rate <= 1 or not 0 <= streak <= 10:
            raise VeilError("rate is 0 to 1; max_in_a_row 0 to 10")
        # her lines bank is edited line by line now (PATCH /lines); a whole list only if one is sent
        flourishes = [clean_flourish(f) for f in (b.get("flourishes") or [])] if "flourishes" in b else None
        names = b.get("names")
        if names is not None:
            if not isinstance(names, dict):
                raise VeilError("names is a set of knobs (rate, max_in_a_row, min_score)")
            names = {k: names[k] for k in ("rate", "max_in_a_row", "min_score") if k in names}
        file = os.path.join(PERS, f"{who}.yaml")
        header = (f"# personality/{who}.yaml - {who.title()}'s flair. Read by flair.py; edited on the Flair page.\n"
                  "# (See defaults/examples/personality/assistant.yaml for what each knob means.)")

        def change(doc):
            from ruamel.yaml.comments import CommentedMap
            doc["rate"] = rate
            doc["max_in_a_row"] = streak
            if names is not None:
                if names:
                    doc["names"] = CommentedMap(names)
                elif "names" in doc:
                    del doc["names"]
            if flourishes is not None:
                doc["flourishes"] = flairlines.lines_seq(flourishes)
        config.edit_yaml(file, change, header=header)
        audit(request, "flair saved", target=who, detail=f"rate {rate}" + (f", {len(flourishes)} flourishes" if flourishes is not None else ""))
        restart_note("flair")
        return {"saved": who}


    @app.get("/api/flair/{who}/candidates")
    def candidates(request: Request, who: str):
        need(request, "viewer")
        assistant_ok(who)
        try:
            cands = config.plain(config.load_yaml(os.path.join(PERS, "candidates", f"{who}.yaml")).get("candidates") or [])
        except FileNotFoundError:
            cands = []
        for i, c in enumerate(cands):
            c["index"] = i
            c["keep"] = str(c.get("keep")).lower() in ("yes", "true")
        return {"candidates": cands}


    @app.post("/api/flair/{who}/candidates/accept")
    async def candidates_accept(request: Request, who: str):
        """Accept on Lines from her books: {found, slot?, mood?, topics?} moves that line into her lines bank."""
        need(request, "reviewer")
        assistant_ok(who)
        b = await body_of(request)
        changes = {k: b[k] for k in ("slot", "topics", "mood") if b.get(k)}
        if "slot" in changes and changes["slot"] not in SLOTS:
            raise VeilError(f"slot is one of {', '.join(SLOTS)}")
        if any(m not in MOODS for m in changes.get("mood") or []):
            raise VeilError(f"mood is one or more of {', '.join(MOODS)}")
        line = flairlines.accept(who, str(b.get("found") or ""), changes)
        if not line:
            raise VeilError("That line isn't in the persona's books list any more (reload the page)", 404)
        audit(request, "book line accepted into the lines bank", target=who, detail=line["text"])
        restart_note(f"flair: {who}")
        return {"banked": line}


    @app.post("/api/flair/{who}/candidates/clear")
    def candidates_clear(request: Request, who: str):
        """Empty Lines from her books; combing the books again fills it (leaving out what's taken)."""
        need(request, "reviewer")
        assistant_ok(who)
        n = flairlines.clear_candidates(who)
        audit(request, "book lines cleared", target=who, detail=f"{n} lines")
        return {"cleared": n}


    @app.patch("/api/flair/{who}/lines")
    async def lines_edit(request: Request, who: str):
        """One line of her lines bank: {index, text_was, text, slot, topics, mood} saves it;
        {index, text_was, delete: true} deletes it."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        try:
            i = int(b.get("index"))
        except (TypeError, ValueError):
            raise VeilError("Which line? (reload the page)")
        line = None if b.get("delete") else clean_flourish({"text": b.get("text"), "slot": b.get("slot"),
                                                            "topics": b.get("topics"), "mood": b.get("mood")})
        try:
            lines = flairlines.edit_bank(who, i, b.get("text_was"), line)
        except LookupError as e:
            raise VeilError(str(e), 409)
        audit(request, "lines bank: line deleted" if line is None else "lines bank: line saved", target=who,
              detail={"was": b.get("text_was"), "now": line and line["text"]})
        restart_note(f"flair: {who}")
        return {"lines": lines}


    @app.post("/api/flair/{who}/lines")
    async def lines_add(request: Request, who: str):
        """Lines typed on the page into her lines bank: {lines: [{text, slot?, topics?, mood?}]}."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        new = [clean_flourish(f) for f in (b.get("lines") or [])]
        if not new:
            raise VeilError("Type a line (or many, separated by |)")
        n = flairlines.add_to_bank(who, new)
        audit(request, "lines bank: lines added", target=who, detail=f"{n} added")
        restart_note(f"flair: {who}")
        return {"added": n, "already": len(new) - n}


    @app.get("/api/combing")
    def combing_get(request: Request):
        need(request, "viewer")
        try:
            return {"combing": config.plain(config.load_yaml(os.path.join(PERS, "combing.yaml")))}
        except FileNotFoundError:
            return {"combing": {}}


    @app.put("/api/combing")
    async def combing_set(request: Request):
        """The whole combing.yaml, as JSON: each list a list of words or phrases."""
        need(request, "administrator")
        b = (await body_of(request)).get("combing")
        if not isinstance(b, dict):
            raise VeilError("combing is a set of word lists")
        lists = ("said_words", "speaker_adjectives", "never", "story_words", "allowed_capitals",
                 "closer_words", "interjections")

        def words(v, what):
            if not isinstance(v, list) or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in v):
                raise VeilError(f"{what} is a list of words or short phrases")
            return [" ".join(x.split()) for x in v]
        clean = {k: words(b[k], k) for k in lists if k in b}
        if "max_words" in b:
            clean["max_words"] = int(b["max_words"])
        for group in ("moods", "topics"):
            if group in b:
                if not isinstance(b[group], dict):
                    raise VeilError(f"{group} is a set of word lists")
                clean[group] = {str(k): words(v, f"{group}.{k}") for k, v in b[group].items()}
        if "score" in b:
            clean["score"] = {k: int(v) for k, v in (b["score"] or {}).items()}

        def change(doc):
            for k, v in clean.items():
                if isinstance(v, list):
                    s_ = config.flow_list(v)
                    doc[k] = s_
                elif isinstance(v, dict):
                    node = config.map_in(doc, k)
                    for kk in list(node):
                        if kk not in v:
                            del node[kk]
                    for kk, vv in v.items():
                        if isinstance(vv, list):
                            s_ = config.flow_list(vv)
                            node[kk] = s_
                        else:
                            node[kk] = vv
                else:
                    doc[k] = v
        config.edit_yaml(os.path.join(PERS, "combing.yaml"), change)
        audit(request, "combing saved")
        return {"saved": True}


    @app.put("/api/flair/{who}/sources")
    async def flair_sources(request: Request, who: str):
        """Her books, speakers and near words (personality/sources.yaml)."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        speakers_ = [str(x).strip().lower() for x in (b.get("speakers") or []) if str(x).strip()]
        near = [str(x).strip().lower() for x in (b.get("near") or []) if str(x).strip()]
        books = []
        for bk in b.get("books") or []:
            title, url, local = (str(bk.get(k) or "").strip() for k in ("title", "url", "local"))
            if not (title and url.startswith(("https://", "http://")) and local):
                raise VeilError("Each book needs a title, an http(s) address and a local path")
            books.append({"title": title, "url": url, "local": local})

        def change(doc):
            from ruamel.yaml.comments import CommentedMap, CommentedSeq
            node = config.map_in(doc, who)
            for k, v in (("speakers", speakers_), ("near", near)):
                s_ = config.flow_list(v)
                node[k] = s_
            node["books"] = CommentedSeq([CommentedMap(x) for x in books])
        config.edit_yaml(os.path.join(PERS, "sources.yaml"), change)
        audit(request, "flair sources saved", target=who, detail=f"{len(books)} books")
        return {"saved": who}


