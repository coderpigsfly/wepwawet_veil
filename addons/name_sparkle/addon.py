"""addons/name_sparkle: the person's name in her answer (issue #25, step 2; the code is names.py beside it)."""

import logging

log = logging.getLogger("router")
NAMES = None


def setup(folder):
    global NAMES
    import names
    from veil import config, personas
    NAMES = names.Names(config.settings(), personas.files(config.path("personality")))


def dress(text, ctx):
    """Her answer with the person's name placed (a [[name]] where the phrase put it, else in front or at the
    end), when the voice ID is sure; a brain flea already says who it's about, so never there."""
    if NAMES is None or ctx.get("plain") or ctx.get("path") == "flea":
        return text
    out, why = NAMES.dress(ctx.get("assistant"), text, ctx.get("who") or {}, ctx.get("path"))
    if ctx.get("who"):
        log.info("  %s", why)
    return out


def aliases(who, assistant):
    """What this persona may call them (its own names for them, else the shared ones)."""
    return NAMES.aliases(who, assistant) if NAMES else []
