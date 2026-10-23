"""Mishearings' own tests (run by tools/test_addon.py mishearings)."""


def run(mod, check):
    real = mod.mishearings.swaps
    mod.mishearings.swaps = lambda: [{"heard": "grain flea", "meant": "brain flea"}, {"heard": "watcher", "meant": "washer"}]
    try:
        ctx = {"swapped": []}
        check("a swap marked Use it is made, whole words only", mod.understand("add a grain flea to the watchers", ctx),
              "add a brain flea to the watchers")
        check("each swap made is told, for the trace", ctx["swapped"], [("grain flea", "brain flea")])
        check("words with nothing to swap pass as heard", mod.understand("turn on the light", {}), "turn on the light")
    finally:
        mod.mishearings.swaps = real
