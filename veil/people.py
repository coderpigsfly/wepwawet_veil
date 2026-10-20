# veil/people.py - the people grid: one row per person, one column per attached app. Any app.
#
# Who a person is differs by app: Oread names its voice profiles one way (Owner, Sam), Donetick
# its members another, and the people around them call them something else again. The grid
# (settings.yaml people:, the People page) puts each person's names side by side:
#   people:
#     apps: [oread, donetick]       # the app columns, after Wepwawet and Called (any integration)
#     rows:
#       - {wepwawet: Owner, called: [], oread: [Owner, Sam], donetick: [Owner]}
# wepwawet: the router's own name for them (optional: a name only one app knows still gets a row).
# Inside the router any name in a row is the same person: the firewall, the brain fleas' changers
# and the apps' people cards match on all of them (names()). Outside, each app asks through its own
# door (GET /people/<app>) and gets its own column only. Read again whenever settings.yaml changes.

import os

from veil import config

_CACHE = {"mtime": None, "grid": {"apps": [], "rows": []}}


def _names(v):
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def grid():
    """{apps: [app column names], rows: [{wepwawet: str, called: [..], <app>: [..]}]}."""
    try:
        mtime = os.path.getmtime(config.SETTINGS_FILE)
    except OSError:
        mtime = None
    if mtime != _CACHE["mtime"]:
        p = config.settings().get("people") or {}
        apps = [str(a) for a in (p.get("apps") or [])]
        rows = []
        for r in p.get("rows") or []:
            if isinstance(r, dict):
                row = {"wepwawet": str(r.get("wepwawet") or "").strip(), "called": _names(r.get("called"))}
                row.update({a: _names(r.get(a)) for a in apps})
                rows.append(row)
        _CACHE.update(mtime=mtime, grid={"apps": apps, "rows": rows})
    return _CACHE["grid"]


def row_names(row):
    """Every name in a row, lowercased."""
    out = {row["wepwawet"].lower()} if row.get("wepwawet") else set()
    for k, v in row.items():
        if k != "wepwawet":
            out.update(n.lower() for n in v)
    return out


def names(name):
    """Every name the person called name goes by (lowercased; itself when no row has it)."""
    low = str(name or "").strip().lower()
    for row in grid()["rows"]:
        every = row_names(row)
        if low in every:
            return every
    return {low} if low else set()


def change(app, action, name, was=None):
    """An app's own names kept in step with it (POST /people/<app>): add a name (to the row that already
    goes by it, else a new row with the name as the router's too), rename one (its row's router name
    follows when it was the same), remove one (from the app's column only: the row stays, with its other
    apps' names, for you to decide on the People page). Returns what was done, in words."""
    name, was = " ".join(str(name or "").split()), " ".join(str(was or "").split())
    if not name or len(name) > 40:
        raise ValueError("a name of 1 to 40 characters")
    said = []

    def edit(doc):
        from ruamel.yaml.comments import CommentedMap
        people = doc.get("people")
        if people is None:
            doc["people"] = people = CommentedMap([("apps", config.flow_list([])), ("rows", [])])
        apps = [str(a) for a in people.get("apps") or []]
        if app not in apps:
            people["apps"] = config.flow_list(apps + [app])
        rows = people.get("rows")
        if rows is None:
            rows = people["rows"] = []

        def names_of(r):
            return {str(r.get("wepwawet") or "").lower()} | {str(n).lower() for k, v in r.items()
                                                             if k != "wepwawet" for n in (v or [])} - {""}
        low = name.lower()
        if action == "add":
            row = next((r for r in rows if low in names_of(r)), None)
            if row is None:
                row = CommentedMap([("wepwawet", name), ("called", config.flow_list([])), (app, config.flow_list([name]))])
                row.fa.set_flow_style()
                rows.append(row)
                said.append(f"{name} added to the people grid")
            elif low not in {str(n).lower() for n in row.get(app) or []}:
                row[app] = config.flow_list([str(n) for n in row.get(app) or []] + [name])
                said.append(f"{name} joined {row.get('wepwawet') or 'a row'} in the people grid")
            else:
                said.append(f"{name} is already in the people grid")
        elif action == "rename":
            row = next((r for r in rows if was.lower() in {str(n).lower() for n in r.get(app) or []}), None)
            if any(low in names_of(r) for r in rows if r is not row):
                raise ValueError(f"{name} is already someone else's name in the people grid")
            if row is None:
                raise ValueError(f"{was} isn't in the people grid's {app} column")
            row[app] = config.flow_list([name if str(n).lower() == was.lower() else str(n) for n in row.get(app) or []])
            if str(row.get("wepwawet") or "").lower() == was.lower():
                row["wepwawet"] = name
            said.append(f"{was} is {name} in the people grid too")
        elif action == "remove":
            row = next((r for r in rows if low in {str(n).lower() for n in r.get(app) or []}), None)
            if row is not None:
                row[app] = config.flow_list([str(n) for n in row.get(app) or [] if str(n).lower() != low])
                said.append(f"{name} taken out of the {app} column; the row stays for you (People)")
            else:
                said.append(f"{name} wasn't in the people grid")
        else:
            raise ValueError("action is add, rename or remove")
    config.edit_yaml(config.SETTINGS_FILE, edit)
    _CACHE["mtime"] = None
    return "; ".join(said)


def column(app):
    """What one app may know: [{person: the router's name, names: its own names}] for the rows
    where it has names (GET /people/<app>)."""
    return [{"person": r["wepwawet"] or None, "names": r.get(app) or []}
            for r in grid()["rows"] if r.get(app)]
