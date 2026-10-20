#!/usr/bin/env python3
# tests/make_copy.py - a throwaway copy of the router for the tests, built the way a fresh
# install starts: the code, without the household's own files (anything with a starting copy in
# defaults/, and release.yaml's never: list: her personality, misses, data/...), then the starting copies put in place exactly as the
# router does at start-up, then the stand-in assistants from tests/fixtures/personality/ on top.
# So the tests never read or write your settings, your voice maps or her real personality.
#
#   python3 tests/make_copy.py /tmp/veil-copy      (then point ROUTER_ROOT at it)

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEVER = {".git", "data", "state", "captures", "personality", "__pycache__"}


def household(root):
    """The household's files: every path with a starting copy under defaults/."""
    out = set()
    base = os.path.join(root, "defaults")
    for d, _dirs, files in os.walk(base):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), base)
            out.add(rel.split(os.sep, 1)[1] if rel.split(os.sep)[0] == "examples" else rel)
    return out


def never_list(root):
    """release.yaml's never: list (what a public install never has), so the copy matches one."""
    import yaml
    try:
        with open(os.path.join(root, "release.yaml")) as f:
            return [str(p) for p in (yaml.safe_load(f) or {}).get("never") or []]
    except OSError:
        return []


ON = ("weather_brain", "donetick")


def switch_on(settings, names):
    """enabled: true for these services in the copy's settings.yaml, its comments kept."""
    import re
    with open(settings) as f:
        text = f.read()
    for name in names:
        text = re.sub(rf"(\n  {name}:\n    enabled: )false\b[^\n]*", r"\1true", text, count=1)
    with open(settings, "w") as f:
        f.write(text)


def make(dest, root=HERE):
    import fnmatch
    if os.path.exists(dest):
        shutil.rmtree(dest)
    skip = household(root)
    nevers = never_list(root)

    def left_out(p):
        p = p.replace(os.sep, "/")
        return any((n.endswith("/") and (p + "/").startswith(n)) or fnmatch.fnmatch(p, n) for n in nevers)

    def ignore(folder, names):
        rel = os.path.relpath(folder, root)
        out = set()
        for n in names:
            p = os.path.normpath(os.path.join(rel, n))
            if (rel == "." and n in NEVER) or n == "__pycache__" or p in skip or left_out(p):
                out.add(n)
        return out

    shutil.copytree(root, dest, ignore=ignore)
    # the starting copies, put in place by the router's own start-up step
    env = dict(os.environ, ROUTER_ROOT=dest, ROUTER_DATA=os.path.join(dest, "data"))
    subprocess.run([sys.executable, "-c", "from veil import config"], cwd=dest, env=env, check=True)
    # the apps the tests talk to, switched on (they ship off until a house has them installed)
    switch_on(os.path.join(dest, "settings.yaml"), ON)
    # the stand-in assistants (her personality is the household's own)
    fx = os.path.join(root, "tests", "fixtures", "personality")
    shutil.copytree(fx, os.path.join(dest, "personality"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("README.md"))
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 tests/make_copy.py <throwaway folder>")
    print(make(os.path.abspath(sys.argv[1])))
