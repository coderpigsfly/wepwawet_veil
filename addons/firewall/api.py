"""addons/firewall/api.py - the Firewall page's doors: its rules, the devices it may name.
Moved out of the core's pages server (veil/web.py) with the add-on (issue #25): registered only when the
Firewall is on, so with it off none of these doors exist."""
import os  # noqa: F401
import re  # noqa: F401

from fastapi import Request  # noqa: F401


def register(app):
    import sys
    from veil import access, config, frontend, people_map  # noqa: F401
    from veil.errors import VeilError  # noqa: F401
    from veil.web import audit, body_of, choices, need, router, word_list  # noqa: F401
    import firewall  # noqa: E402  (beside it)
    addon = sys.modules.get("addon_firewall")

    @app.get("/api/firewall")
    def firewall_get(request: Request):
        need(request, "viewer")
        try:
            spec = config.plain(config.load_yaml(config.FIREWALL_FILE))
        except FileNotFoundError:
            spec = {"enabled": False, "rules": []}
        s = config.settings()
        return {"firewall": spec, "oread_on": bool(config.section(config.section(s, "integrations"), "oread").get("enabled")),
                "people": people_map.voices(s),      # the voice ID's own names (saved on Name Sparkle)
                "assistants": sorted(set(router().PERSONAS) | set(choices("assistants"))),
                "words": frontend.words(s),
                "topics": sorted((s.get("topics") or {}).keys())}


    @app.get("/api/firewall/devices")
    async def firewall_devices(request: Request):
        """The rules' device names checked against Home Assistant's own devices (their names and entity
        ids, read with its token): {devices: how many it has, unknown: [{rule, name, device}]}, or
        {error} when it can't be read. Only the saved rules."""
        need(request, "viewer")
        s = config.settings()
        ha = dict(config.section(config.section(s, "integrations"), "home_assistant"))
        url, token = (ha.get("url") or "").rstrip("/"), config.secret(ha.get("token") or "HA_TOKEN")
        if not url or not token:
            return {"error": "Home Assistant's address or token isn't set (Integrations, Home Assistant)"}
        try:
            async with access.client(8) as c:
                resp = await c.get(url + "/api/states", headers={"Authorization": f"Bearer {token}"})
            if resp.status_code >= 300:
                return {"error": f"Home Assistant answered {resp.status_code}" + (" (the token was refused)" if resp.status_code == 401 else "")}
            states = resp.json()
        except Exception as e:
            return {"error": f"Couldn't reach Home Assistant: {e}"}
        names = []
        for st in states if isinstance(states, list) else []:
            names.append(str((st.get("attributes") or {}).get("friendly_name") or ""))
            names.append(str(st.get("entity_id") or "").split(".", 1)[-1].replace("_", " "))
        try:
            spec = config.plain(config.load_yaml(config.FIREWALL_FILE))
        except FileNotFoundError:
            spec = {}
        return {"devices": len(states) if isinstance(states, list) else 0,
                "unknown": firewall.unknown_devices(spec.get("rules"), [n for n in names if n])}


    @app.put("/api/firewall")
    async def firewall_set(request: Request):
        need(request, "administrator")
        b = (await body_of(request)).get("firewall")
        if not isinstance(b, dict):
            raise VeilError("firewall is a set of rules")
        rules = []
        for i, r in enumerate(b.get("rules") or []):
            if not isinstance(r, dict):
                raise VeilError(f"rule {i + 1} isn't a rule")
            rule = {"name": " ".join(str(r.get("name") or "").split())[:80], "enabled": r.get("enabled", True) is not False}
            for k in ("people", "assistants", "voice_devices", "devices", "commands", "topics", "domains"):
                rule[k] = word_list([str(x) for x in (r.get(k) or [])], f"rule {i + 1} {k}") \
                    if k not in ("topics", "domains") else [str(x).lower().strip() for x in (r.get(k) or []) if str(x).strip()]
            rule["intents"] = []
            for it in r.get("intents") or []:
                it = str(it).strip()
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,40}(:[a-z_]{1,40})?", it):
                    raise VeilError(f"rule {i + 1}: '{it}' isn't a Home Assistant command (HassTurnOn, or HassTurnOn:lock)")
                rule["intents"].append(it)
            for dm in rule["domains"]:
                if not re.fullmatch(r"[a-z_]{1,40}", dm):
                    raise VeilError(f"rule {i + 1}: '{dm}' isn't a kind of device (lock, cover, light...)")
            if not rule["people"]:
                raise VeilError(f"rule {i + 1} needs people (a name, unknown, or anyone)")
            rule["gemini"] = bool(r.get("gemini"))
            rule["message"] = " ".join(str(r.get("message") or "").split())[:200]
            if not (rule["gemini"] or any(rule[k] for k in ("voice_devices", "devices", "commands", "topics",
                                                             "domains", "intents"))):
                raise VeilError(f"rule {i + 1} ({rule['name'] or 'unnamed'}) stops nothing: give it devices, commands, "
                                "topics, kinds of device, Home Assistant commands, voice devices, or Off-Platform")
            rules.append(rule)
        spec = {"enabled": bool(b.get("enabled")), "sure_score": float(b.get("sure_score", 0.8)),
                "sure_labels": [str(x) for x in (b.get("sure_labels") or ["known"])],
                "when_oread_down": "allow" if b.get("when_oread_down") == "allow" else "unknown", "rules": rules,
                "off_platform_never": [str(x) for x in b.get("off_platform_never", router().fw().off_platform_never) or []]}
        firewall.Firewall(spec)          # it must load

        def change(doc):
            from ruamel.yaml.comments import CommentedMap, CommentedSeq
            for k in ("enabled", "sure_score", "when_oread_down"):
                doc[k] = spec[k]
            sl = config.flow_list(spec["sure_labels"])
            doc["sure_labels"] = sl
            seq = CommentedSeq()
            for r in rules:
                m = CommentedMap()
                for k, v in r.items():
                    if isinstance(v, list):
                        s_ = config.flow_list(v)
                        m[k] = s_
                    else:
                        m[k] = v
                seq.append(m)
            doc["rules"] = seq
        config.edit_yaml(config.FIREWALL_FILE, change)
        addon.set_spec(spec)                         # takes effect at once
        audit(request, "firewall saved", detail=f"{'on' if spec['enabled'] else 'off'}, {len(rules)} rules")
        return {"saved": True, "active": spec["enabled"]}


