"""addons/firewall: the Firewall (issue #25, step 3; the rules are firewall.py beside it)."""

import logging

log = logging.getLogger("router")
FW = None


def setup(folder):
    from veil import config
    import firewall
    try:
        spec = config.load_yaml(config.FIREWALL_FILE)
    except FileNotFoundError:
        spec = {}
    set_spec(spec)
    log.info("  firewall: %s (%d rules)", "on" if FW.enabled else "off", len(FW.rules))
    return firewall


def set_spec(spec):
    """Its rules, now (the page's save takes effect at once)."""
    global FW
    import firewall
    FW = firewall.Firewall(spec or {})


def check(said, ctx):
    """The first rule this request breaks ({rule, why}), or None: who spoke, the voice device, the words,
    the topic and action, and whether it's going Off-Platform."""
    if FW is None or not FW.enabled:
        return None
    return FW.check(ctx.get("who") or {}, ctx.get("assistant"), said, topic=ctx.get("topic"), action=ctx.get("action"),
                    going_to_gemini=bool(ctx.get("going_to_gemini")))


def current():
    """The rules in force (for the core's checks of a model's tool calls and Home Assistant's commands)."""
    return FW


def make(spec):
    """Rules from a firewall.yaml given (the test door tries one without saving it)."""
    import firewall
    return firewall.Firewall(spec or {})
