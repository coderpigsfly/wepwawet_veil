"""addons/brain_fleas/api.py - the Brain fleas page's doors: the fleas, the steps they use, who may change them.
Moved out of the core's pages server (veil/web.py) with the add-on (issue #25): registered only when Brain fleas is on."""
import os  # noqa: F401
import re  # noqa: F401

from fastapi import Request  # noqa: F401


def register(app):
    from veil import config, people_map, rules as rulebook  # noqa: F401
    from veil.errors import VeilError  # noqa: F401
    from veil.web import audit, body_of, choices, clean_rules, names_taken, need, router, rules_node, rules_rows  # noqa: F401
    import fleas as fleas_mod  # noqa: E402  (beside it)
    @app.get("/api/fleas")
    def fleas_list(request: Request):
        """The fleas as the Brain fleas page edits them, the steps they can use, the router's own commands
        for fleas, its settings (match_at, changers) and the voices that can be named as changers."""
        need(request, "reviewer")
        s = config.settings()
        book = fleas_mod.Fleas().fresh()
        doc = book.doc
        return {"rules": rules_rows(doc.get("fleas") or {}, book.broken), "rule_steps": rulebook.STEPS,
                "commands": list(fleas_mod.COMMANDS.values()), "file": os.path.relpath(fleas_mod.FILE, config.path()),
                "match_at": doc.get("match_at", 0.8), "changers": doc.get("changers") or [],
                "never_count": doc.get("never_count") or [], "voices": people_map.voices(s),
                "stamp": config.stamp(fleas_mod.FILE, "fleas")}


    @app.put("/api/fleas")
    async def fleas_save(request: Request):
        """Save the fleas from the page: {rules: [...]}, the same rows as an app's User rules. Used at once."""
        need(request, "administrator")
        b = await body_of(request)
        clean = clean_rules(b.get("rules"), set(fleas_mod.COMMANDS), names_taken(skip_fleas=True))
        old = fleas_mod.load().get("fleas") or {}
        keep = {n: {k: old[n][k] for k in ("title", "system") if k in (old.get(n) or {})} for n, _ in clean if n in old}
        for r in b.get("rules") or []:          # a title typed on the page
            n = str((r or {}).get("name") or "").strip().lower()
            if str(r.get("title") or "").strip():
                keep.setdefault(n, {})["title"] = " ".join(str(r["title"]).split())

        def write(doc):
            doc["fleas"] = rules_node(clean, keep)
        config.check_stamp(fleas_mod.FILE, "fleas", b.get("stamp"))
        config.edit_yaml(fleas_mod.FILE, write, width=4096)
        config.hand_back(fleas_mod.FILE)
        audit(request, "brain fleas saved", target="fleas", detail=", ".join(n for n, _ in clean))
        return {"saved": [n for n, _ in clean], "stamp": config.stamp(fleas_mod.FILE, "fleas")}


    @app.patch("/api/fleas/settings")
    async def fleas_settings(request: Request):
        """{match_at: 0..1, changers: [voice names]}: how closely a sentence must fit, and who may change fleas by voice."""
        need(request, "administrator")
        b = await body_of(request)
        m = b.get("match_at")
        if m is not None and (isinstance(m, bool) or not isinstance(m, (int, float)) or not 0 < m <= 1):
            raise VeilError("match at is a share from 0 to 1 (like 0.75)")
        voices = {v.lower(): v for v in people_map.voices(config.settings())}
        who = b.get("changers")
        if who is not None and (not isinstance(who, list) or any(str(x).lower() not in voices for x in who)):
            raise VeilError("changers are voices the voice ID knows (Name Sparkle)")

        def write(doc):
            if m is not None:
                doc["match_at"] = m
            if who is not None:
                doc["changers"] = config.flow_list([voices[str(x).lower()] for x in who])
        config.edit_yaml(fleas_mod.FILE, write, width=4096)
        config.hand_back(fleas_mod.FILE)
        audit(request, "brain flea settings", target="fleas", detail=str(b))
        return {"match_at": m, "changers": who}


