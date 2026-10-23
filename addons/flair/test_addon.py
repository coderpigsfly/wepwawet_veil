"""Persona Flair's own tests: its test_flair.py beside it (run by tools/test_addon.py flair)."""
import os
import subprocess
import sys


def run(mod, check):
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "test_flair.py")], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["(nothing)"])[-1]
    check(f"test_flair.py: {last}", r.returncode, 0)
    out, = [mod.dress("[[name]] you have 3 chores.", {"assistant": "nobody", "path": "A"})]
    check("a [[name]] is left for Name Sparkle", "[[name]]" in out, True)
