# veil/people_map.py - an app's people, and which voice each is. Any app, not one.
#
# The people in the house are the voices the voice ID knows by name (Oread's names, saved on Name
# Sparkle: names_in_replies: calls). An app keeps its own people (Donetick's circle members); its
# people card (veil/lists.py, the app's Defaults tab) says which command lists them, which fields
# are a person's id and name, which voice each is (map:), the other names each voice is heard by
# in what's said to this app (names: {voice: [sam, me]}), and who "me" is (default:, me:).
# services: <name>: lists: people: {from: "GET /circles/members", id: userId, name: displayName,
#   house: people, map: {"<the app's id>": <voice>}, names: {<voice>: [other names]}, default: <voice>}
# A person mapped to "" is nobody in the house. Until the map is saved, people are suggested by
# name (the app's name is a voice or one of its other names). Oct 15: People and names retired.


def voices(s):
    """The voices the voice ID knows by name (saved on Name Sparkle), in their own spelling."""
    return [str(v) for v in (((s or {}).get("names_in_replies") or {}).get("calls") or {})]


def household(s, card=None):
    """{voice: {every name it goes by in this app, lowercased}}: each saved voice, plus the other
    names the app's people card gives it."""
    names = (card or {}).get("names") or {}
    out = {v: {v.lower()} for v in voices(s)}
    from veil import phases
    if phases.on("dump15"):            # and every name of the voice's row in the people grid (the People page)
        from veil import people
        for v in out:
            out[v] |= {str(n).lower() for n in people.names(v)}
    for v, ns in names.items():
        out.setdefault(str(v), {str(v).lower()}).update(str(n).lower() for n in ns or [])
    return out


async def members(call, conf):
    """[(id, name)] of the app's people, by its people card (veil/lists.py)."""
    from veil import lists
    return await lists.items(call, conf)


def suggest(found, house):
    """{the app's id (as text): voice} by name, for a map not saved yet."""
    out = {}
    for pid, name in found:
        hits = [k for k, ns in house.items() if name.lower() in ns]
        if len(hits) == 1:
            out[str(pid)] = hits[0]
    return out


def mapping(found, conf, house):
    """The saved map, or the suggestions while none is saved."""
    saved = (conf or {}).get("map")
    return {str(k): (v or "") for k, v in saved.items()} if isinstance(saved, dict) else suggest(found, house)


def spoken(found, conf, house):
    """{a spoken name: (the app's id, its name)} for the app's helper: every name of the voice each
    app person is, then an app person not in the map yet by their own name, when no voice already
    goes by it."""
    m = mapping(found, conf, house)
    out = {}
    for pid, name in found:
        key = m.get(str(pid))
        if key:
            for n in house.get(key, {key.lower()}):
                out[n] = (pid, name)
    taken = {n for ns in house.values() for n in ns}
    for pid, name in found:
        if str(pid) not in m and name.lower() not in out and name.lower() not in taken:
            out[name.lower()] = (pid, name)
    return out
