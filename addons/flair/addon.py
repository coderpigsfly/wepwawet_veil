"""addons/flair: her flair on answers given at home (issue #25, step 2; the code is flair.py beside it)."""

import logging
import re

import yaml

log = logging.getLogger("router")
FLAIR = None
NAME = re.compile(r"\[\[\s*name\s*\]\]", re.I)
KEEP = "⁣name⁣"        # a [[name]] kept for Name Sparkle while she dresses the line


def setup(folder):
    """Her personalities and moods; once, lines approved before Oct 14 move into her lines bank."""
    global FLAIR
    import flair
    import flairlines
    from veil import config
    try:
        with open(config.path("vocab", "moods.yaml")) as f:
            moods = yaml.safe_load(f) or {}
    except OSError:
        moods = {}
    FLAIR = flair.Flair(config.path("personality"), moods=moods)
    log.info("  flair on for %s", ", ".join(FLAIR.flaired()) or "none (every rate is 0)")
    for who in FLAIR.names():
        try:
            n = flairlines.approved_into_bank(who)
            if n:
                log.info("flair: %d approved lines moved into %s's lines bank", n, who)
        except Exception as e:
            log.info("  ! moving %s's approved lines: %s", who, e)


def dress(text, ctx):
    """Her answer with a flourish, by her rate: on answers at home (paths A, B, C) and a brain flea's; never
    her own questions or the learn level's plain answers."""
    if FLAIR is None or ctx.get("plain") or ctx.get("path") not in ("A", "B", "C", "flea"):
        return text
    out, why = FLAIR.dress(ctx.get("assistant"), NAME.sub(KEEP, text), None if ctx.get("path") == "flea" else ctx.get("topic"))
    log.info("  %s", why)
    return out.replace(KEEP, "[[name]]")


def flaired():
    """The personas with flair on (a rate above 0)."""
    return FLAIR.flaired() if FLAIR else []
