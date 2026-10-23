"""addons/bank/api.py - the Off-Platform Bank page's doors: its sayings, their answers, what they became.
Moved out of the core's pages server (veil/web.py) with the add-on (issue #25): registered only when the
Bank is on. The counting itself (each saying that went out, its trips) is the core's activity log, kept
for Stats and Savings whether or not the Bank is on."""
import os  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401

from fastapi import Request  # noqa: F401


def register(app):
    import yaml  # noqa: F401
    from veil import activity as activity_mod, config, phases, security  # noqa: F401
    from veil.errors import VeilError  # noqa: F401
    from veil.web import audit, body_of, choices, names_taken, need, restart_note, router  # noqa: F401

    @app.get("/api/bank")
    def bank(request: Request, review: str = "", klass: str = "", search: str = "", order: str = "last",
             limit: int = 200, added: str = "yes", personality: str = ""):
        """added: yes (the replacement answers you added, the default), no (only counted), all.
        personality: one personality's bank (each has its own)."""
        need(request, "reviewer")
        r = router()
        if not r.ACTIVITY:
            return {"rows": [], "classes": [], "off": True}
        out = r.ACTIVITY.bank(review or None, klass or None, search or None, order, limit,
                              {"yes": True, "no": False}.get(added), personality or None)
        out["answer_from_bank"] = r.ACTIVITY.answer_from_bank
        out["bank_keeps"] = r.BANK_KEEPS
        return out


    @app.post("/api/bank/add")
    async def bank_add(request: Request):
        """The + on the Transactions page: that request becomes a replacement answer in the bank."""
        need(request, "reviewer")
        b = await body_of(request)
        try:
            row = router().ACTIVITY.bank_add_from(int(b.get("activity_id") or 0))
        except (TypeError, ValueError) as e:
            raise VeilError(str(e))
        audit(request, "added to the bank", target=str(row["id"]), detail=row.get("heard"))
        return row


    @app.post("/api/bank/upload")
    async def bank_upload(request: Request):
        """The generic upload (dump19): {personality, generic, sayings: [{said, answers: [...]}]} or {yaml: the
        same list as YAML text}: each saying put in the bank, added, with the ways it may be answered, so it's
        answered at home with no Off-Platform trip."""
        need(request, "reviewer")
        if not phases.on("dump19"):
            raise VeilError("Not here yet", 404)
        b = await body_of(request)
        rows = b.get("sayings")
        if isinstance(b.get("yaml"), str):
            try:
                rows = yaml.safe_load(b["yaml"])
            except yaml.YAMLError as e:
                raise VeilError(f"That isn't YAML that can be read: {str(e)[:120]}")
        if not isinstance(rows, list) or not rows:
            raise VeilError("sayings is a list of {said, answers}")
        r = router()
        pers = str(b.get("personality") or (r.PERSONAS or [""])[0]).strip().lower()
        done = []
        for i, x in enumerate(rows[:500]):
            said = " ".join(str((x or {}).get("said") or "").split())[:300]
            answers = [" ".join(str(a).split())[:600] for a in ((x or {}).get("answers") or []) if str(a).strip()]
            words = r.without_polite(said)
            if not words or not answers:
                raise VeilError(f"saying {i + 1}: it needs its words (said) and at least one answer")
            done.append(r.ACTIVITY.bank_upload(pers, activity_mod.key_of(words), said, answers, b.get("generic", True) is not False))
        audit(request, "bank upload", detail=f"{len(done)} sayings for {pers}")
        return {"added": len(done), "personality": pers}


    @app.post("/api/bank/{bank_id}/flea")
    async def bank_to_flea(request: Request, bank_id: int):
        """Answer at home: a saying in the bank becomes a brain flea (its words the way it's asked, the answers
        kept for it her lines), answered at home before anything goes Off-Platform (dump19)."""
        need(request, "reviewer")
        if not phases.on("dump19"):
            raise VeilError("Not here yet", 404)
        add = router().ADDONS.services.get("brain_fleas.add")      # the Brain fleas add-on, when it's on
        if not add:
            raise VeilError("Brain fleas is off (the Add-ons page)", 409)
        row = router().ACTIVITY.bank_row(bank_id)
        if not row:
            raise VeilError("No such bank row", 404)
        if not row["answers"]:
            raise VeilError("It has no answers kept yet to say")
        taken = names_taken()
        base = re.sub(r"[^a-z0-9]+", "_", str(row["key"]))[:30].strip("_") or "saying"
        name, n = base, 2
        while name in taken:
            name, n = f"{base}_{n}", n + 1
        add(name, {"title": str(row["heard"])[:60], "words": [str(row["key"])], "steps": [{"response": {"lines": row["answers"][:5]}}]})
        audit(request, "bank saying made a flea", target=name, detail=row["heard"])
        return {"flea": name}


    @app.patch("/api/bank/{bank_id}")
    async def bank_review(request: Request, bank_id: int):
        need(request, "reviewer")
        b = await body_of(request)
        try:
            row = router().ACTIVITY.bank_review(bank_id, b.get("review"), b.get("note"))
            if "added" in b:
                row = router().ACTIVITY.bank_set_added(bank_id, bool(b["added"]))
            if "generic" in b:
                row = router().ACTIVITY.bank_set_generic(bank_id, bool(b["generic"]))
        except ValueError as e:
            raise VeilError(str(e))
        if not row:
            raise VeilError("No such bank row", 404)
        audit(request, "bank reviewed", target=str(bank_id), detail={k: b.get(k) for k in ("review", "note", "added", "generic")})
        return row


    @app.get("/api/bank/results")
    def bank_results(request: Request, limit: int = 0, personality: str = ""):
        """The top things the Off-Platform model turned requests into, with every wording that led there."""
        need(request, "reviewer")
        r = router()
        if not r.ACTIVITY:
            return {"results": [], "off": True}
        out = r.ACTIVITY.by_result(limit or getattr(r.ACTIVITY, "bank_top", 25), personality or None)
        out["knobs"] = {k: getattr(r.ACTIVITY, k, None) for k in
                        ("answer_from_bank", "answers_kept", "use_from", "bank_top", "trim_days")}
        return out


    BANK_EXPORT_HEADER = """# learn/bank.yaml - the Off-Platform Bank, written out for git (Export on the Off-Platform Bank page).
    # The bank itself lives in the database (data/veil.db), which never goes into git; this is a copy
    # to read and commit. Nothing reads it back: changing it changes nothing.
    # Each saying: how often heard, its Off-Platform trips, how often the bank answered it, whether
    # you added it, your review and note, the answers kept for it, and what Gemini turned it into.

    """


    @app.post("/api/bank/export")
    def bank_export(request: Request):
        """Export on the bank page: the bank written to learn/bank.yaml, to commit and push."""
        need(request, "reviewer")
        r = router()
        if not r.ACTIVITY:
            raise VeilError("The activity log is off, so there's no bank")
        rows = r.ACTIVITY.bank_export()
        file = config.path("learn", "bank.yaml")
        config.make_dirs(os.path.dirname(file))
        tmp = file + ".tmp"
        with open(tmp, "w") as f:
            f.write(BANK_EXPORT_HEADER + f"# Exported {time.strftime('%Y-%m-%d %H:%M')}: {len(rows)} sayings.\n\n")
            yaml.safe_dump({"bank": rows}, f, sort_keys=False, allow_unicode=True, width=120)
        os.replace(tmp, file)
        config.hand_back(file)
        audit(request, "bank exported", detail=f"{len(rows)} sayings")
        return {"file": "learn/bank.yaml", "sayings": len(rows), "added": sum(1 for x in rows if x["added"])}


    @app.post("/api/bank/trim")
    def bank_trim(request: Request):
        need(request, "administrator")
        r = router()
        n = r.ACTIVITY.trim(getattr(r.ACTIVITY, "trim_days", 30) or 30) if r.ACTIVITY else 0
        audit(request, "bank trimmed", detail=f"{n} one-offs")
        return {"trimmed": n}


    @app.delete("/api/bank/{bank_id}")
    def bank_delete(request: Request, bank_id: int):
        need(request, "administrator")
        router().ACTIVITY.bank_delete(bank_id)
        audit(request, "bank row deleted", target=str(bank_id))
        return {"deleted": bank_id}


