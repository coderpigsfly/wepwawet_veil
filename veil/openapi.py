# veil/openapi.py - an app's own commands, read from its OpenAPI (or Swagger 2) spec.
#
# Adding an app we didn't write, step 3 (Integrations, its Commands tab): the router reads the
# app's spec and keeps what it found in connectors/<name>.commands.json, so the voice map's
# Calls choices and the API requirement beside each come from the app's own document. Reading
# it again later compares the new spec with the saved list: each command is marked add,
# modified or deleted, and nothing changes until the changes are accepted.
#
#   commands(spec)        [{api: "POST /chores", summary, requires: [...]}] from a spec (a dict)
#   compare(saved, new)   the rows marked: same | add | modified | deleted
#   load(path) / save(path, spec_url, title, commands)

import json
import os
import time

from veil import phases

METHODS = ("get", "post", "put", "patch", "delete")


def _ref(spec, ref):
    """#/definitions/x or #/components/schemas/x -> the schema it points at; a part in another
    file (https://.../LitCal.json#/definitions/x) from the parts read beside the spec (x-parts)."""
    where, _, frag = str(ref).partition("#")
    node = (spec.get("x-parts") or {}).get(where) if where else spec
    for part in frag.lstrip("/").split("/") if frag.strip("/") else []:
        node = (node or {}).get(part) if isinstance(node, dict) else None
    return node or {}


def file_refs(doc, base, part=False):
    """Every $ref into another file, made absolute against base (the address the doc was read
    from), rewritten so in the doc; in a part (part=True) its own #/... refs point into it too."""
    from urllib.parse import urljoin
    found = set()

    def walk(x):
        if isinstance(x, dict):
            r = x.get("$ref")
            if isinstance(r, str):
                where, _, frag = r.partition("#")
                if where:
                    target = urljoin(base, where)
                    found.add(target)
                    x["$ref"] = f"{target}#{frag}"
                elif part:
                    x["$ref"] = f"{base}#{frag}"
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    return found


def _schema_required(spec, schema, depth=0):
    """A schema's required fields (following $ref, allOf)."""
    if not isinstance(schema, dict) or depth > 5:
        return []
    if "$ref" in schema:
        return _schema_required(spec, _ref(spec, schema["$ref"]), depth + 1)
    out = list(schema.get("required") or [])
    for part in schema.get("allOf") or []:
        out += [r for r in _schema_required(spec, part, depth + 1) if r not in out]
    return out


def _requires(spec, path_item, op):
    """What the app itself demands for one command: path and query parameters marked required,
    and the required fields of the body (Swagger 2: an in: body parameter; OpenAPI 3: requestBody)."""
    out = []
    params = list((path_item or {}).get("parameters") or []) + list(op.get("parameters") or [])
    for p in params:
        if "$ref" in p:
            p = _ref(spec, p["$ref"])
        where = p.get("in")
        if where == "body":
            if p.get("required"):
                out += [f"body: {f}" for f in _schema_required(spec, p.get("schema"))] or ["body"]
        elif p.get("required") or where == "path":
            out.append(f"{where}: {p.get('name')}")
    body = op.get("requestBody")
    if isinstance(body, dict):
        if "$ref" in body:
            body = _ref(spec, body["$ref"])
        content = body.get("content") or {}
        media = content.get("application/json") or next(iter(content.values()), {})
        fields = _schema_required(spec, (media or {}).get("schema"))
        if fields:
            out += [f"body: {f}" for f in fields]
        elif body.get("required"):
            out.append("body")
    return out


def _accepts(spec, path_item, op):
    """Every field a command's body may hold (its schema's properties; Swagger 2: an in: body parameter):
    what's sent to an app that refuses fields it doesn't take (services: <app>: send_only_accepted)."""
    schema = None
    for p in list((path_item or {}).get("parameters") or []) + list(op.get("parameters") or []):
        if isinstance(p, dict) and "$ref" in p:
            p = _ref(spec, p["$ref"])
        if isinstance(p, dict) and p.get("in") == "body":
            schema = p.get("schema")
    body = op.get("requestBody")
    if isinstance(body, dict):
        if "$ref" in body:
            body = _ref(spec, body["$ref"])
        content = body.get("content") or {}
        schema = ((content.get("application/json") or next(iter(content.values()), {})) or {}).get("schema") or schema

    def props(s, depth=0):
        if not isinstance(s, dict) or depth > 6:
            return []
        if "$ref" in s:
            return props(_ref(spec, s["$ref"]), depth + 1)
        out = list((s.get("properties") or {}).keys())
        for k in ("allOf", "anyOf", "oneOf"):
            for part in s.get(k) or []:
                out += [f for f in props(part, depth + 1) if f not in out]
        return out
    return props(schema)


def _params(spec, path_item, op):
    """Every path and query parameter a command takes, required or not ("query: year_type"): the
    ones the router fills from the app's options (connector.py)."""
    out = []
    for p in list((path_item or {}).get("parameters") or []) + list(op.get("parameters") or []):
        if isinstance(p, dict) and "$ref" in p:
            p = _ref(spec, p["$ref"])
        if isinstance(p, dict) and p.get("in") in ("path", "query") and p.get("name"):
            out.append(f"{p['in']}: {p['name']}")
    return list(dict.fromkeys(out))


def _types(spec, path_item, op):
    """Each path parameter's type as the spec gives it ({"month": "string", "day": "integer"}): how
    the router writes a date part into the address (a month as a word, or its number)."""
    out = {}
    for p in list((path_item or {}).get("parameters") or []) + list(op.get("parameters") or []):
        if isinstance(p, dict) and "$ref" in p:
            p = _ref(spec, p["$ref"])
        if isinstance(p, dict) and p.get("in") == "path" and p.get("name"):
            t = (p.get("schema") or {}).get("type") or p.get("type")
            if t:
                out[p["name"]] = str(t)
    return out


def _path_params(spec, path_item, op):
    """Each path parameter as the spec gives it, its $ref followed."""
    for p in list((path_item or {}).get("parameters") or []) + list(op.get("parameters") or []):
        if isinstance(p, dict) and "$ref" in p:
            p = _ref(spec, p["$ref"])
        if isinstance(p, dict) and p.get("in") == "path" and p.get("name"):
            yield p


def _patterns(spec, path_item, op):
    """Each path parameter's pattern, when the spec gives one ({"month": "^(0[1-9]|1[012])$"}): how the
    app writes it (Wikipedia's two-digit month), which the router follows (dump7)."""
    return {p["name"]: str(p.get("pattern") or (p.get("schema") or {}).get("pattern"))
            for p in _path_params(spec, path_item, op) if p.get("pattern") or (p.get("schema") or {}).get("pattern")}


def _enums(spec, path_item, op):
    """Each path parameter's few allowed values ({"type": ["selected", "births", ...]}): each is offered
    as a command of its own, the value written in its path (dump8)."""
    out = {}
    for p in _path_params(spec, path_item, op):
        vals = p.get("enum") or (p.get("schema") or {}).get("enum")
        if isinstance(vals, list) and vals and all(isinstance(v, (str, int)) for v in vals):
            out[p["name"]] = [str(v) for v in vals]
    return out


def expanded(cmds, most=50):
    """The commands with each one whose path parameter has a few allowed values (enums) also listed
    once per value, written in its path ("GET /feed/onthisday/births/{month}/{day}"), each keeping
    what the router reads beside it: a rule or the voice map can call one as it is (dump8)."""
    out = list(cmds or [])
    if not phases.on("dump8"):
        return out
    seen = {c["api"].upper() for c in out}
    for c in cmds or []:
        for name, vals in (c.get("enums") or {}).items():
            if "{" + name + "}" not in c["api"] or len(vals) > most:
                continue
            for v in vals:
                api = c["api"].replace("{" + name + "}", v)
                if api.upper() not in seen:
                    seen.add(api.upper())
                    out.append(dict(c, api=api, summary=f"{c.get('summary') or ''} ({name}: {v})".strip(),
                                    requires=[r for r in c.get("requires") or [] if r != f"path: {name}"], of=c["api"]))
    return out


def _fields(spec, schema, depth=0):
    """The field names of what a command answers with: the properties of the object, or of each
    item when it's a list (through $ref, allOf / anyOf / oneOf, and through a wrapper object holding
    the list: one with no id of its own, its first list of things)."""
    if not isinstance(schema, dict) or depth > 8:
        return []
    if "$ref" in schema:
        return _fields(spec, _ref(spec, schema["$ref"]), depth + 1)
    if schema.get("type") == "array" or "items" in schema:
        return _fields(spec, schema.get("items"), depth + 1)
    props = schema.get("properties") or {}
    for k in ("allOf", "anyOf", "oneOf"):
        if isinstance(schema.get(k), list) and not props:
            return list(dict.fromkeys(f for s in schema[k] for f in _fields(spec, s, depth + 1)))
    if props:
        out = list(props)
        if "id" not in props:
            seen = [_ref(spec, v["$ref"]) if isinstance(v, dict) and "$ref" in v and phases.on("dump11") else v
                    for v in props.values()]
            lst = next((v for v in seen if isinstance(v, dict)
                        and (v.get("type") == "array" or "items" in v)), None)
            if lst is not None:
                out += [f for f in _fields(spec, lst, depth + 1) if f not in out]
        return out
    extra = schema.get("additionalProperties")
    return _fields(spec, extra, depth + 1) if isinstance(extra, dict) else []


def _returns(spec, op):
    res = op.get("responses") or {}
    # a YAML spec may write the codes as numbers (200:, Wikipedia's feed service), JSON always as text
    ok = res.get("200") or res.get("201") or (res.get(200) or res.get(201) if phases.on("dump11") else None) or {}
    if "$ref" in ok:
        ok = _ref(spec, ok["$ref"])
    schema = ok.get("schema")
    if schema is None:
        content = ok.get("content") or {}
        schema = (content.get("application/json") or next(iter(content.values()), {}) or {}).get("schema")
    return _fields(spec, schema)


def commands(spec):
    """Every command in the spec: {api, summary, requires, returns}, in the spec's order.
    returns: the fields of what it answers with (a person's id and name, for an app's people)."""
    out = []
    for path, item in (spec.get("paths") or {}).items():
        for m, op in (item or {}).items():
            if m.lower() not in METHODS or not isinstance(op, dict):
                continue
            out.append({"api": f"{m.upper()} {path}",
                        "summary": op.get("summary") or (op.get("description") or "").split("\n")[0],
                        "requires": _requires(spec, item, op), "returns": _returns(spec, op),
                        "params": _params(spec, item, op), "types": _types(spec, item, op),
                        "patterns": _patterns(spec, item, op), "enums": _enums(spec, item, op),
                        "accepts": _accepts(spec, item, op)})
    return out


def compare(saved, new):
    """Rows for the Commands tab: every command in either list, marked
    same, add (new in the spec), modified (its summary or requirements changed) or deleted."""
    old = {c["api"]: c for c in saved or []}
    seen, rows = set(), []
    for c in new:
        was = old.get(c["api"])
        if was is None:
            mark = "add"
        elif was.get("summary") != c.get("summary") or list(was.get("requires") or []) != list(c.get("requires") or []) \
                or ("returns" in was and list(was.get("returns") or []) != list(c.get("returns") or [])):
            mark = "modified"
        else:
            mark = "same"
        rows.append(dict(c, mark=mark, was=was if mark == "modified" else None))
        seen.add(c["api"])
    rows += [dict(c, mark="deleted") for a, c in old.items() if a not in seen]
    return rows


def load(path):
    """The saved commands file, or None when the spec hasn't been read yet."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save(path, spec_url, title, cmds, extra=None):
    """extra: what else is kept beside the commands (its x-wepwawet section, how to call it)."""
    data = {"read_from": spec_url, "title": title, "accepted": time.strftime("%Y-%m-%d %H:%M"),
            "commands": cmds}
    data.update(extra or {})
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    return data
