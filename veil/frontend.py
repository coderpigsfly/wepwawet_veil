# veil/frontend.py - the router's own words for devices and what can be done to them, with the front
# end's names behind them (frontend/<integration>.yaml; Home Assistant's today). Anything a person
# sees or writes is in the router's words; the front end's names stay behind this map (Oct 15), so a
# different front end needs only its own file.

import os

from veil import config


def words(s=None):
    """{"kinds": [{label, value}], "actions": [{label, value}]} from every front end's map file
    whose integration is in settings.yaml (integrations: <name>:)."""
    s = s if s is not None else config.settings()
    out = {"kinds": [], "actions": []}
    for name in sorted(config.section(s, "integrations")):
        path = config.path("frontend", f"{name}.yaml")
        if not os.path.exists(path):
            continue
        spec = config.load_yaml(path) or {}
        for part in ("kinds", "actions"):
            for label, value in (spec.get(part) or {}).items():
                out[part].append({"label": str(label), "value": str(value), "frontend": name})
    return out
