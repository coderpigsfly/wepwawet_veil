# veil/doors.py - the router's doors that can ask for an API token (the Security page, API keys).
#
# A door is a few of the router's own addresses that one program calls: the chat door for
# LiteLLM, the tools door, the guard door for Veil Guard Service. Each is a setting, not code:
# settings.yaml security: doors: name: {description, who, paths, role, locked}. Add one when a
# new program calls the router; the router checks it on the next request.
#   description  what comes through it          who    who calls it (and so needs the token)
#   paths        the router's paths it covers (one ending in * covers everything under it)
#   role         the least role a token needs   locked true: a token is needed
#   program      the integration that calls it (its Integrations card shows the door)
# A door without locked: takes the older security: <name>_token_required switch, so a router
# set up before doors were settings keeps its locks.

ROLES = ("viewer", "reviewer", "administrator", "super")


def doors(sec):
    """{name: {description, who, paths, role, locked}} from the security settings."""
    out = {}
    for name, d in ((sec or {}).get("doors") or {}).items():
        d = dict(d or {})
        if d.get("locked") is None:
            d["locked"] = bool((sec or {}).get(f"{name}_token_required", False))
        d["paths"] = [str(p) for p in (d.get("paths") or [])]
        d["role"] = d.get("role") if d.get("role") in ROLES else "viewer"
        out[str(name)] = d
    return out


def door_for(sec, path):
    """(name, door) for a request path, or (None, None) when no door covers it."""
    for name, d in doors(sec).items():
        for p in d["paths"]:
            if path == p or (p.endswith("*") and path.startswith(p[:-1])):
                return name, d
    return None, None


def check_new(name, d, existing):
    """A door to add from the page: problems, as a message, or None."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", name or ""):
        return "A door's name is a short word: small letters, digits and _ (like chat or guard)"
    if name in existing:
        return f"There's already a door named {name}"
    paths = d.get("paths") or []
    if not paths or not all(isinstance(p, str) and p.startswith("/") for p in paths):
        return "A door needs the router's paths it covers, each starting with / (like /v1/chat/completions)"
    if d.get("role", "viewer") not in ROLES:
        return f"The role is one of {', '.join(ROLES)}"
    if not (d.get("description") or "").strip():
        return "Say what comes through the door (its description)"
    return None
