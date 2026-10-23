"""addons/brain_fleas: the household's small true facts found by their key words (issue #25, step 4). The
router makes the house (make: the app a flea's rule runs on, with its phrases) and runs the rule; this finds
which flea was asked, after the integrations' own key words found nothing."""
import fleas

FLEAS = None


def make(filler, say, which):
    """The house a flea's rule runs on (fleas.House), its fleas read from learn/fleas.yaml."""
    global FLEAS
    FLEAS = fleas.Fleas(filler=filler)
    return fleas.House(FLEAS, say, which)


def closest(said, drop=()):
    """(flea, its way as written, words shared) that fits what was said by enough words with a meaning (drop: the
    words that have none), else None (#28)."""
    return FLEAS.closest(said, drop) if FLEAS is not None else None


def names():
    """The fleas' names, for the names taken."""
    return [str(n) for n in (fleas.load().get("fleas") or {})]


def add(name, flea):
    """A flea added to learn/fleas.yaml (the Bank's "answer at home")."""
    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        if doc.get("fleas") is None:
            doc["fleas"] = CommentedMap()
        doc["fleas"][name] = flea
    fleas.edit(change)


def key_word(said, ctx):
    """{action, score, how} for the flea asked, else None. ctx: step (the request's why), telling (a
    sentence that tells a fact rather than asking)."""
    step, telling = ctx.get("step") or (lambda text: None), ctx.get("telling") or (lambda s: False)
    if FLEAS is None:
        return None
    flea, fs, how = FLEAS.find(said)
    if flea and how == "all its key words heard" and telling(said):
        step(f"{flea}'s key words are heard, but the sentence tells a fact rather than asking: not the flea")
        flea = None
    if not flea:
        step(f"none fits (best {fs:.0%}, they answer at {float(FLEAS.doc.get('match_at', 0.8)):.0%})")
        return None
    step(f"{flea} {fs:.0%} ({how})")
    return {"action": flea, "score": round(fs, 3), "how": how}
