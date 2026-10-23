"""The Firewall's own tests (run by tools/test_addon.py firewall)."""


def run(mod, check):
    mod.set_spec({"enabled": True, "rules": [{"name": "no garage", "people": ["anyone"], "devices": ["garage"], "message": "No."}]})
    anyone = {"speaker": "x", "label": "known", "score": 0.99}
    hit = mod.check("open the garage door", {"who": anyone, "assistant": "iris"})
    check("a rule stops what it names", bool(hit) and hit["why"].startswith("may not work"), True)
    check("what it doesn't name goes on", mod.check("what's the weather", {"who": anyone, "assistant": "iris"}), None)
    check("by default no model works a lock, by its kind", bool(mod.current().check_model_command("HassTurnOff", ["Front Door"], ["lock"])), True)
    mod.set_spec({"enabled": False, "rules": []})
    check("off: nothing stopped by a rule", mod.check("open the garage door", {"who": anyone, "assistant": "iris"}), None)
