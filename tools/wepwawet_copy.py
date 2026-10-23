"""Write the compliant copy of an app that has no Wepwawet section of its own (issue #24).

    python3 tools/wepwawet_copy.py <app> [--root DIR] [--check]

The copy is connectors/<app>.wepwawet.yaml: the app's own file is never changed. Its x-wepwawet section
(version 2) has the app's spoken name (settings topics: spoken), its data life (cache_refresh_seconds:
0 is a record read live, else transient held that long), its lists (settings lists:), and each user rule
of one of the standard's shapes pushed back as an action (veil/wepwawet.py). A rule of no shape stays a
user rule. --check writes nothing: it prints how many rules the copy replaces.
--from-spec also takes the actions the app's own spec declares (its x-wepwawet actions:, as last read on
its Commands tab): an app's own actions are used only once they're here, and every one that changes
something asks first, always (#15: an app can't hand itself a delete that asks nothing).
Each pushed-back action is compiled again and compared with the rule it came from: only an exact match
counts."""
import argparse
import json
import os
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--root", default=os.environ.get("ROUTER_ROOT", REPO))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--from-spec", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, a.root)
    from veil import wepwawet as W
    cdir = os.path.join(a.root, "connectors")
    with open(os.path.join(cdir, f"{a.app}.yaml")) as f:
        hand = yaml.safe_load(f) or {}
    with open(os.path.join(a.root, "settings.yaml")) as f:
        settings = yaml.safe_load(f) or {}
    svc = (settings.get("services") or {}).get(a.app) or {}
    version, declared = None, {}
    try:
        with open(os.path.join(cdir, f"{a.app}.commands.json")) as f:
            saved = json.load(f)
        version, declared = saved.get("version"), ((saved.get("wepwawet") or {}).get("actions") or {})
    except (OSError, ValueError):
        pass
    own = hand.get("rules") or {}
    section, custom = W.copy_of(svc.get("title") or a.app, own, f"{svc.get('title') or a.app} {version or ''}".strip())
    back = W.compile(section)
    exact = [n for n in back if W.same(back[n], own[n])]
    for n in list(section["actions"]):
        if n not in exact:
            custom[n] = "it doesn't come back the same"
            section["actions"].pop(n)
    section["source"]["pushed_back"] = sorted(section["actions"])
    if a.from_spec and declared:
        for n, act in declared.items():
            act = dict(act or {})
            if act.get("command"):         # it changes something: asked first, always
                act["confirm"] = dict(act.get("confirm") or {}, always=True)
            section["actions"].setdefault(str(n), act)
        section["source"]["from_spec"] = sorted(str(n) for n in declared)
    spoken = next((t.get("spoken") for t in (settings.get("topics") or {}).values() if (t or {}).get("service") == a.app), None)
    if spoken:
        section["spoken"] = spoken
    keep = svc.get("cache_refresh_seconds")
    section["data"] = {"kind": "record"} if keep in (0, "0") else \
        {"kind": "transient", "pace": "slow" if float(keep or 60) >= 3600 else "fast", "hold_seconds": float(keep or 60)}
    if svc.get("lists"):
        section["lists"] = {k: {f: v[f] for f in ("from", "id", "name", "house") if f in v} for k, v in svc["lists"].items()}
    order = ["version", "title", "spoken", "source", "data", "lists", "actions"]
    section = {k: section[k] for k in order if k in section}
    n, done = len(own), len(section["actions"])
    print(f"{a.app}: {done} of {n} user rules are actions in the copy" + (f" ({done / n:.0%})" if n else "")
          + "".join(f"\n  custom: {k} ({why})" for k, why in custom.items()))
    if not a.check:
        path = os.path.join(cdir, f"{a.app}.wepwawet.yaml")
        with open(path, "w") as f:
            f.write(f"# The compliant copy of {section['title']} (issue #24), written by tools/wepwawet_copy.py: the app's own\n"
                    "# file is never changed. Its user rules of a standard shape are actions here; one the household\n"
                    "# keeps by hand under the same name (connectors/<app>.yaml rules:) is used instead.\n")
            yaml.safe_dump({"x-wepwawet": section}, f, sort_keys=False, allow_unicode=True, width=120)
        print(f"  written: {os.path.relpath(path, a.root)}")


if __name__ == "__main__":
    main()
