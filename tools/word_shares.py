#!/usr/bin/env python3
# tools/word_shares.py - how strongly each word in a topic file points to one dataset label,
# measured on any source in tools/sources.yaml (read through tools/datasets.py).
# Usage: python3 tools/word_shares.py topics/weather.yaml weather massive
#        (topic file, the label to measure against, the source's name in tools/sources.yaml)

import os
import re
import sys
from collections import Counter

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datasets as D  # noqa: E402

if len(sys.argv) != 4:
    sys.exit("usage: python3 tools/word_shares.py <topic file> <label> <source>")
topic_file, label, source = sys.argv[1], sys.argv[2], sys.argv[3]
if source not in D.SOURCES:
    sys.exit(f"no source '{source}' in tools/sources.yaml ({', '.join(D.SOURCES)})")
topic = yaml.safe_load(open(topic_file))
rows = D.read_source(source, D.SOURCES[source])
utts = [(r["label"], r["text"]) for r in rows]
in_label = sum(1 for s, _ in utts if s == label)


def words_in(node, path=""):
    """Every word or phrase in the file, with where it lives (doors.strong, when.today...)."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from words_in(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for item in node:
            yield from words_in(item, path)
    elif isinstance(node, str) and path.split(".")[0] in ("doors", "about", "when", "places"):
        if "{" not in node and path != "places.prepositions":
            yield path, node.lower()


print(f"{len(rows)} requests in {source}, {in_label} of them '{label}'\n")
print(f"{'where':20}{'word':22}{'seen':>6}{label[:9]:>9}{'share':>7}  also in")
last = None
for where, word in words_in(topic):
    if where != last:
        print()
        last = where
    pat = re.compile(r"\b" + re.escape(word) + r"\b")
    hits = Counter(s for s, u in utts if pat.search(u))
    seen = sum(hits.values())
    if not seen:
        print(f"{where:20}{word:22}{'-':>6}{'-':>9}{'-':>7}  never seen in {source}")
        continue
    share = hits[label] / seen
    others = ", ".join(f"{s} {n}" for s, n in hits.most_common() if s != label)[:40]
    print(f"{where:20}{word:22}{seen:>6}{hits[label]:>9}{share:>7.0%}  {others}")
