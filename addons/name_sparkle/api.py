"""addons/name_sparkle/api.py - Name Sparkle's doors: what she calls each person, how often.
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

    # ---------- Name Sparkle: saying people's names (Oct 14) ----------
    # The house rule (names_in_replies: on, how sure the voice ID must be, how often, most in a row),
    # where the names come from (voice_id_from: an integration with a people list, Oread here), each
    # device's own switch and rate (personality/<who>.yaml names:), and what she calls each person the
    # voice ID knows (names_in_replies: calls: {their voice ID name: [what she may call them]}).

    def voice_id_sources(s):
        """Integrations and apps that can name people: those offering who spoke first, then any with a
        people list. [{name, title, who_spoke, people}]"""
        out = []
        names = [n for n, v in (s.get("integrations") or {}).items() if isinstance(v, dict)] + list(s.get("services") or {})
        for name in names:
            w = apps.wepwawet(name) or {}
            node = apps.node(s, name)[1] or {}
            card = lists.people_card(node, (w.get("lists") or {}))
            who = "who_spoke" in (w.get("offers") or {})
            if who or card:
                try:
                    title = apps.info(s, name)["title"]
                except VeilError:
                    title = name
                out.append({"name": name, "title": title, "who_spoke": who, "people": bool(card)})
        out.sort(key=lambda x: (not x["who_spoke"], x["title"].lower()))
        return out


    async def voice_id_people(s, name):
        """The names the chosen integration knows, from its people list (x-wepwawet lists:), or why not."""
        if not name:
            return [], "Pick where the names come from (Voice ID from)."
        w = apps.wepwawet(name) or {}
        node = apps.node(s, name)[1] or {}
        card = lists.people_card(node, (w.get("lists") or {}))
        if not card:
            return [], f"{name} has no people list (read its spec on Integrations)."
        try:
            got = await lists.items(lambda m, p: apps.call(s, name, m, p), card)
        except Exception as e:
            return [], f"Couldn't ask {name}: {e}"
        seen, out = set(), []
        for _, n in got:
            if n and n.lower() not in seen:
                seen.add(n.lower())
                out.append(n)
        return out, None


    def device_names():
        r = router()
        return sorted(set(r.PERSONAS) | set(choices("assistants")))


    @app.get("/api/sparkle")
    async def sparkle_get(request: Request):
        need(request, "viewer")
        s = config.settings()
        n = config.plain(s.get("names_in_replies") or {})
        sources = voice_id_sources(s)
        src = n.get("voice_id_from") or (sources[0]["name"] if sources and sources[0]["who_spoke"] else "")
        calls = n.get("calls") or {}
        devices = []
        for who in device_names():
            try:
                spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
            except FileNotFoundError:
                spec = {}
            devices.append({"name": who, "names": spec.get("names") or {}, "has_file": bool(spec)})
        return {"settings": {k: n.get(k) for k in ("labels",)},
                "voice_id_from": src, "saved_from": n.get("voice_id_from"), "sources": sources,
                "people": list(calls), "calls": calls, "devices": devices}


    @app.post("/api/sparkle/pull")
    async def sparkle_pull(request: Request):
        """Pull the names from the voice ID integration now: anyone not saved yet is added (with no
        names under them yet); saved people stay until you delete them, whether or not it still knows them."""
        need(request, "administrator")
        s = config.settings()
        n = config.plain(s.get("names_in_replies") or {})
        sources = voice_id_sources(s)
        src = n.get("voice_id_from") or (sources[0]["name"] if sources and sources[0]["who_spoke"] else "")
        if not src:
            raise VeilError("Pick where the names come from (Voice ID from) and save first")
        people, why = await voice_id_people(s, src)
        if why:
            raise VeilError(why, 502)
        have = {str(k).lower() for k in (n.get("calls") or {})}
        new = [p for p in people if p.lower() not in have]

        def change(doc):
            node = config.map_in(doc, "names_in_replies")
            calls = config.map_in(node, "calls", block=True)      # one to a line
            for p in new:
                seq = config.flow_list()
                calls[p] = seq
        if new:
            config.edit_yaml(config.SETTINGS_FILE, change)
        audit(request, "voice names pulled", detail={"from": src, "added": new})
        return {"from": src, "known": people, "added": new}


    @app.put("/api/sparkle")
    async def sparkle_set(request: Request):
        """Where the names come from (how often, how sure and each persona's own names are the
        persona's: /api/sparkle/device)."""
        need(request, "administrator")
        b = await body_of(request)
        s = config.settings()
        vals = {}
        if "voice_id_from" in b:
            v = str(b.get("voice_id_from") or "")
            if v and v not in {x["name"] for x in voice_id_sources(s)}:
                raise VeilError(f"{v} can't name people (it has no people list)")
            vals["voice_id_from"] = v

        def change(doc):
            for k, v in vals.items():
                config.set_in(doc, ["names_in_replies", k], v)
        config.edit_yaml(config.SETTINGS_FILE, change)
        audit(request, "user sparkle saved", detail=vals)
        restart_note("names")
        return {"saved": vals}


    def call_names(raw):
        """The names to call someone, tidied: no blanks, no duplicates, no questions, 40 characters each."""
        names, seen = [], set()
        for x in raw or []:
            x = " ".join(str(x or "").split())
            if not x:
                continue
            if len(x) > 40:
                raise VeilError(f'"{x[:20]}...": a name is 40 characters at most')
            if x.endswith("?"):
                raise VeilError(f'"{x}": a name, not a question')
            if x.lower() not in seen:
                seen.add(x.lower())
                names.append(x)
        return names


    @app.put("/api/sparkle/calls")
    async def sparkle_calls(request: Request):
        """What she calls one person the voice ID knows: {person, names: [...]}; {person, remove: true}
        deletes the person (a saved voice stays until then, even with no names under it)."""
        need(request, "administrator")
        b = await body_of(request)
        person = " ".join(str(b.get("person") or "").split())
        if not person or len(person) > 40:
            raise VeilError("Whose names? (the voice ID's name for them, 40 characters at most)")
        names = call_names(b.get("names"))

        def change(doc):
            n = config.map_in(doc, "names_in_replies")
            calls = config.map_in(n, "calls", block=True)      # one to a line
            if b.get("remove"):
                if person in calls:
                    del calls[person]
            else:
                seq = config.flow_list(names)
                calls[person] = seq
        config.edit_yaml(config.SETTINGS_FILE, change)
        audit(request, "voice person deleted" if b.get("remove") else "names the persona calls someone", target=person, detail=names)
        restart_note("names")
        return {"person": person, "names": names, "removed": bool(b.get("remove"))}


    @app.put("/api/sparkle/device/{who}/calls")
    async def sparkle_device_calls(request: Request, who: str):
        """One persona's own names for one voice: {person, names: [...]} (personality/<who>.yaml
        names: calls:). The persona uses these first, and the shared ones when it has none for them."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        person = " ".join(str(b.get("person") or "").split())
        if not person or len(person) > 40:
            raise VeilError("Whose names? (the voice ID's name for them, 40 characters at most)")
        names = call_names(b.get("names"))
        file = os.path.join(PERS, f"{who}.yaml")

        def change(doc):
            n = config.map_in(doc, "names")
            calls = config.map_in(n, "calls", block=True)
            if names:
                calls[person] = config.flow_list(names)
            elif person in calls:
                del calls[person]
            if not calls:
                del n["calls"]
        config.edit_yaml(file, change)
        audit(request, "persona's own names", target=f"{who}: {person}", detail=names)
        restart_note(f"names: {who}")
        return {"name": who, "person": person, "names": names}


    @app.put("/api/sparkle/device/{who}")
    async def sparkle_device(request: Request, who: str):
        """One persona's own names rate, most in a row and optional least score (personality/<who>.yaml
        names:). A rate above 0 is the switch; an empty min_score leaves it to the voice ID's "known"."""
        need(request, "administrator")
        assistant_ok(who)
        b = await body_of(request)
        names = {}
        if "min_score" in b and b["min_score"] not in (None, ""):
            try:
                ms = float(b["min_score"])
            except (TypeError, ValueError):
                raise VeilError("min_score is a number from 0 to 1, or empty")
            if not 0 <= ms <= 1:
                raise VeilError("min_score is from 0 to 1, or empty")
            names["min_score"] = ms
        for k, lo, hi in (("rate", 0, 1), ("max_in_a_row", 0, 10)):
            v = b.get(k)
            if v in (None, ""):
                continue
            try:
                v = float(v) if k == "rate" else int(v)
            except (TypeError, ValueError):
                raise VeilError(f"{k} is a number")
            if not lo <= v <= hi:
                raise VeilError(f"{k} is from {lo} to {hi}")
            names[k] = v
        file = os.path.join(PERS, f"{who}.yaml")
        header = (f"# personality/{who}.yaml - {who.title()}'s flair. Read by flair.py; edited on the Persona Flair page.\n"
                  "# (See defaults/examples/personality/assistant.yaml for what each knob means.)")

        def change(doc):
            from ruamel.yaml.comments import CommentedMap
            doc.setdefault("rate", 0)
            doc.setdefault("max_in_a_row", 1)
            was = doc.get("names") if isinstance(doc.get("names"), dict) else {}
            keep = {k: v for k, v in was.items() if k not in ("enabled", "rate", "max_in_a_row", "min_score")}
            doc["names"] = CommentedMap({**names, **keep})
        config.edit_yaml(file, change, header=header)
        audit(request, "device names saved", target=who, detail=names)
        restart_note(f"names: {who}")
        return {"name": who, "names": names}


