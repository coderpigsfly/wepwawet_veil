# veil/apps.py - any app the router talks to, the same way: a service (services: <name>:, like
# Donetick and the weather brain) or an integration (integrations: <name>:, like Oread). Each can
# have an OpenAPI spec; read on its Commands tab, the router keeps its commands, how to call it
# (its address and how its key is sent) and its x-wepwawet section (the Wepwawet standard:
# github.com/coderpigsfly/wepwawet_standard).
#
#   node(s, name)            (where, its settings): ("services" | "integrations", {...})
#   info(s, name)            {name, where, title, spec, key, verify, timeout}
#   await read_spec(i)       the spec as a dict (its key sent the saved way, or as a bearer token)
#   await read_parts(i, spec)  the spec with its parts in other files read in beside it
#   described(spec, url)     {wepwawet, auth, base} from a spec: what's kept beside its commands
#   await call(s, name, method, path)   one of its commands, the way its spec says

from urllib.parse import urlparse

from veil import access, config
from veil.errors import VeilError

# The offers the router knows (the Wepwawet standard's offer names) and where it keeps each one's
# on and way in the app's settings: who_spoke is Oread's switch and its source, as it always was
# (the standard's way names, and the source each is in the router's settings).
OFFER_SETTINGS = {"who_spoke": {"on": "enabled", "way": "source",
                                "ways": {"wyoming": "wyoming", "api": "oread", "sensor": "home_assistant"}}}


def way_to_setting(key, way):
    return ((OFFER_SETTINGS.get(key) or {}).get("ways") or {}).get(way, way)


def way_from_setting(key, value):
    for w, v in ((OFFER_SETTINGS.get(key) or {}).get("ways") or {}).items():
        if v == value:
            return w
    return value


def node(s, name):
    if name in (s.get("services") or {}):
        return "services", dict((s.get("services") or {}).get(name) or {})
    if name in (s.get("integrations") or {}) and isinstance(s["integrations"][name], dict):
        return "integrations", dict(s["integrations"][name])
    return None, None


def commands_file(name):
    import re
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name or ""):
        return None
    return config.path("connectors", f"{name}.commands.json")


def saved(name):
    from veil import openapi
    return openapi.load(commands_file(name)) or {}


def info(s, name):
    where, n = node(s, name)
    if where is None:
        raise VeilError(f"No app named {name}", 404)
    w = saved(name).get("wepwawet") or {}
    return {"name": name, "where": where, "title": n.get("title") or w.get("title") or name.replace("_", " ").capitalize(),
            "spec": str(n.get("spec") or "").strip(), "key": n.get("secret") if where == "services" else n.get("token"),
            "verify": bool(n.get("verify_tls", True)), "timeout": float(n.get("spec_timeout") or n.get("timeout") or 8),
            "kind": n.get("kind"), "node": n}


def _headers(auth, key):
    if not key:
        return {}
    auth = auth or {"in": "header", "name": "Authorization", "prefix": "Bearer "}
    if auth.get("in") != "header":
        return {}
    return {auth["name"]: f"{auth.get('prefix') or ''}{key}"}


async def read_spec(i):
    """The app's spec. Its key goes the way the saved spec said, else as a bearer token (the HTTP
    standard), and only when it has one."""
    if not i["spec"]:
        raise VeilError(f"{i['title']} has no spec address (its URL / ports tab)", 409)
    key = config.secret(i["key"] or "") if i["key"] else ""
    headers = _headers(saved(i["name"]).get("auth"), key)
    from veil import phases
    async with access.client(max(i["timeout"], 3), i["verify"]) as c:
        r = await (access.capped(c, "GET", i["spec"], access.most_kb("spec_max_kb"), headers=headers) if phases.on("dump16")
                   else c.get(i["spec"], headers=headers))
        r.raise_for_status()
        return spec_doc(r, i["title"])


def spec_doc(r, title):
    """A spec (or a part of one) as a dict: JSON, or YAML (OpenAPI allows either: Day in History's is
    YAML, application/vnd.oai.openapi), whichever it is; else an error that says so."""
    import json
    import yaml
    text = r.text
    kind = r.headers.get("content-type", "")
    tries = (yaml.safe_load, json.loads) if "yaml" in kind or "openapi" in kind and "json" not in kind else (json.loads, yaml.safe_load)
    for load in tries:
        try:
            doc = load(text)
        except Exception:
            continue
        if isinstance(doc, dict):
            return doc
    raise VeilError(f"{title}'s spec isn't JSON or YAML that can be read (it sent {kind or 'no type'})", 502)


async def read_parts(i, spec, most=40):
    """The spec with its parts in other files ($ref: ./LitCal.json) read in beside it (x-parts), so
    what its commands answer with is known; each part's own parts too, up to most files."""
    from veil import openapi
    key = config.secret(i["key"] or "") if i["key"] else ""
    headers = _headers(saved(i["name"]).get("auth"), key)
    parts, todo = {}, set(openapi.file_refs(spec, i["spec"]))
    async with access.client(max(i["timeout"], 3), i["verify"]) as c:
        while todo and len(parts) < most:
            url = todo.pop()
            if url in parts:
                continue
            from veil import phases
            r = await (access.capped(c, "GET", url, access.most_kb("spec_max_kb"), headers=headers) if phases.on("dump16")
                       else c.get(url, headers=headers))
            r.raise_for_status()
            parts[url] = spec_doc(r, i["title"])
            todo |= set(openapi.file_refs(parts[url], url, part=True)) - set(parts)
    if parts:
        spec["x-parts"] = parts
    return spec


def auth_of(spec):
    """How a program sends its key: x-wepwawet: auth:, else the spec's first header key scheme."""
    w = spec.get("x-wepwawet") or {}
    if isinstance(w.get("auth"), dict):
        return w["auth"]
    schemes = (spec.get("components") or {}).get("securitySchemes") or spec.get("securityDefinitions") or {}
    for sch in schemes.values():
        if sch.get("type") == "apiKey" and sch.get("in") == "header":
            return {"in": "header", "name": sch["name"], "prefix": ""}
        if sch.get("type") == "http" and str(sch.get("scheme")).lower() == "bearer":
            return {"in": "header", "name": "Authorization", "prefix": "Bearer "}
    return None


def base_of(spec_url, spec, url=None):
    """Where its commands' paths start: the spec's own server (OpenAPI 3 servers:, Swagger 2
    basePath:), on the address the spec was read from; of several servers, the one at the address
    you gave the app (url), else the first."""
    u = urlparse(spec_url)
    origin = f"{u.scheme}://{u.netloc}"
    servers = [x for x in spec.get("servers") or [] if isinstance(x, dict) and x.get("url")]
    mine = str(url or "").rstrip("/")
    servers = [x for x in servers if str(x["url"]).rstrip("/") == mine] + [x for x in servers if str(x["url"]).rstrip("/") != mine]
    if servers and isinstance(servers[0], dict) and servers[0].get("url"):
        su = servers[0]["url"]
        return su.rstrip("/") if su.startswith("http") else origin + "/" + su.strip("/") if su.strip("/") else origin
    bp = str(spec.get("basePath") or "").strip("/")
    return origin + ("/" + bp if bp else "")


def described(spec, spec_url, url=None):
    w = spec.get("x-wepwawet")
    return {"wepwawet": w if isinstance(w, dict) else None, "auth": auth_of(spec), "base": base_of(spec_url, spec, url)}


async def call(s, name, method, path, **kw):
    """One of the app's commands, sent to the base and with the key its spec said."""
    i = info(s, name)
    sv = saved(name)
    if not sv.get("base"):
        raise VeilError(f"{i['title']}'s spec hasn't been read (its Commands tab)", 409)
    url = sv["base"].rstrip("/") + path
    key = config.secret(i["key"] or "") if i["key"] else ""
    async with access.client(max(i["timeout"], 3), i["verify"]) as c:
        r = await c.request(method, url, headers=_headers(sv.get("auth"), key), **kw)
    if r.status_code >= 300:
        raise VeilError(f"{i['title']} said {r.status_code}: {r.text[:160]}", 502)
    return r.json() if r.content else {}


def wepwawet(name):
    """The app's x-wepwawet section, as last read from its spec (None: not compliant, or not read)."""
    return saved(name).get("wepwawet")
