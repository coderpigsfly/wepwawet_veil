"""addons/mishearings: the words corrected before anything is decided (issue #25, step 4). The swaps marked
Use it (learn/swaps.yaml) are made here; what was heard is kept (learn/mishearings.yaml) through add."""
import mishearings

swap, add, load, from_misses = mishearings.swap, mishearings.add, mishearings.load, mishearings.from_misses


def understand(said, ctx):
    """The words with the swaps made; each one made is added to ctx swapped [(heard, meant)], for the trace."""
    fixed, done = mishearings.swap(said)
    if isinstance(ctx.get("swapped"), list):
        ctx["swapped"].extend(done)
    return fixed
