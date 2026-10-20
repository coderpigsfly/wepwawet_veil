# veil/lists.py - an app's own lists the router uses, each a card you name on the app's Defaults
# tab: people, project, or whatever else its commands list. Any app, not one.
#
# services: <name>: lists: <word>: {from: "GET /projects", id: id, name: name, default: House,
#   house: people (each item is someone in the house; then map: and me: too)}
# The app's voice map says which list a field fills (connectors/<name>.yaml, fields: list:).
# A list without a default and nothing said is left out (she may ask, later: the standard).

def cards(svc, declared=None):
    """{word: card} for an app (an older people: entry counts as its people card). declared: the
    lists its x-wepwawet section names; one not saved yet is offered as it says (a compliant app
    fills in its own cards; you check them and save)."""
    out = {str(k): dict(v or {}) for k, v in ((svc or {}).get("lists") or {}).items()}
    for k, v in (declared or {}).items():
        if str(k) not in out and isinstance(v, dict):
            out[str(k)] = dict(v, declared=True)
    legacy = (svc or {}).get("people")
    if isinstance(legacy, dict) and not any(c.get("house") == "people" for c in out.values()):
        out["people"] = dict(legacy, house="people")
    return out


def card(svc, word, declared=None):
    return cards(svc, declared).get(str(word or "")) or {}


def people_card(svc, declared=None):
    """The card whose items are people in the house, or {}."""
    return next((c for c in cards(svc, declared).values() if c.get("house") == "people"), {})


async def items(call, conf):
    """[(id, name)] from the app, by the card's command and fields. call(method, path) is the
    app's helper's own API call (it knows the address and the key)."""
    src = str((conf or {}).get("from") or "").strip()
    if not src or " " not in src:
        return []
    method, path = src.split(" ", 1)
    data = await call(method.upper(), path)
    if isinstance(data, dict):        # a wrapper around the list ({"res": [...]}): the list of things in it
        from veil import rules
        data = rules._as_list(data) or []
    idf, namef = conf.get("id"), conf.get("name")
    out = []
    for m in data or []:
        if isinstance(m, dict) and m.get(idf) is not None:
            out.append((m.get(idf), str(m.get(namef) or m.get(idf)).strip()))
    return out
