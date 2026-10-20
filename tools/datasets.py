#!/usr/bin/env python3
# tools/datasets.py - reads the labeled datasets described in tools/sources.yaml into one
# shape, for every tool (build_scores, test_scores, shape_test, word_shares, perplexity_test).
# No dataset, model or label is named in the code: they're all in tools/sources.yaml.
#
# Each source says its format:. The formats this reader knows:
#   massive_jsonl  one JSON object per line; text_field, label_field, slot_field (MASSIVE's
#                  "[date : tomorrow]" annotations) and intent_field
#   clinc_json     {section: [[text, intent], ...]}; sections, out_of_scope_sections
#   snips_json     {intent: [{data: [{text, entity?}, ...]}, ...]}
#   jsonl          one JSON object per line; text_field and label_field (no slots)
#   csv            a header row; text_field and label_field name the columns
#   lines          a plain text file, one sentence per line, all with label: (from the source)
# A new dataset in one of these shapes needs only an entry in sources.yaml; a new shape needs
# a reader below.
#
# Usage (a quick look):  python3 tools/datasets.py            every source: sentences, labels
#                        python3 tools/datasets.py <source>   that source's labels and counts

import csv
import json
import os
import random
import re
import sys
from collections import Counter

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FILE = os.path.join(ROOT, "tools", "sources.yaml")
if not os.path.exists(SOURCES_FILE):      # a fresh clone before the first start: the starting copy
    SOURCES_FILE = os.path.join(ROOT, "defaults", "tools", "sources.yaml")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


SPEC = load_yaml(SOURCES_FILE)
SOURCES = SPEC.get("sources") or {}
GATE = SPEC.get("gate_test") or {}


def local_path(src):
    return os.path.expanduser(src.get("local") or "")


def read_source(name, src, quiet=False):
    """[{text, label, parts, intent}] for one source; [] (with a note) if its file is missing."""
    path = local_path(src)
    if not path or not os.path.exists(path):
        if not quiet:
            print(f"  ! {name}: {path or '(no local: path)'} not found (try: build_scores.py refresh {name}) - skipped")
        return []
    fmt, rows = src.get("format", ""), []
    if fmt == "massive_jsonl":
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                parts = []
                if src.get("slot_field"):
                    parts = [(lab, val.strip().lower())
                             for lab, val in re.findall(r"\[(\w+) : ([^\]]+)\]", r[src["slot_field"]])]
                rows.append({"text": r[src["text_field"]].lower(),
                             "label": r[src["label_field"]], "parts": parts,
                             "intent": r.get(src.get("intent_field") or "", "")})
    elif fmt == "clinc_json":
        with open(path) as f:
            d = json.load(f)
        for sec in src.get("sections", []):
            for text, intent in d[sec]:
                rows.append({"text": text.lower(), "label": intent, "parts": []})
        for sec in src.get("out_of_scope_sections", []):
            for text, _ in d[sec]:
                rows.append({"text": text.lower(), "label": "out_of_scope", "parts": []})
    elif fmt == "snips_json":
        with open(path, encoding="utf-8", errors="replace") as f:
            d = json.load(f)
        for label, items in d.items():
            for it in items:
                rows.append({
                    "text": "".join(p["text"] for p in it["data"]).lower(),
                    "label": label,
                    "parts": [(p["entity"], p["text"].strip().lower())
                              for p in it["data"] if "entity" in p]})
    elif fmt == "jsonl":
        with open(path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    rows.append({"text": str(r[src["text_field"]]).lower(),
                                 "label": r.get(src.get("label_field") or "", src.get("label", "")),
                                 "parts": [], "intent": r.get(src.get("intent_field") or "", "")})
    elif fmt == "csv":
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                rows.append({"text": str(r[src["text_field"]]).lower(),
                             "label": r.get(src.get("label_field") or "", src.get("label", "")),
                             "parts": [], "intent": ""})
    elif fmt == "lines":
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    rows.append({"text": line.strip().lower(), "label": src.get("label", name),
                                 "parts": [], "intent": ""})
    else:
        sys.exit(f"{name}: unknown format '{fmt}' (tools/datasets.py knows massive_jsonl, clinc_json, "
                 f"snips_json, jsonl, csv, lines)")
    return rows


def load_all_sources(quiet=False):
    data = {}
    for name, src in SOURCES.items():
        if src.get("enabled", True) is False:
            continue
        data[name] = read_source(name, src, quiet)
        if not quiet:
            print(f"  {name}: {len(data[name])} sentences ({', '.join(src.get('use') or [])})")
    return data


# ---------- the Gemini gate's test set (tools/shape_test.py, tools/perplexity_test.py) ----------

def gate_real_requests(seed=7):
    """Real requests the house can't answer (so they rightly go straight to Gemini): from the
    sources and labels in sources.yaml gate_test: real_requests, plus its extra_real lines."""
    rnd = random.Random(seed)
    per = int(GATE.get("per_source", 250))
    out = []
    for pick in GATE.get("real_requests") or []:
        name = pick.get("source")
        src = SOURCES.get(name)
        if not src:
            print(f"  (gate_test: no source named {name} in sources.yaml)")
            continue
        labels = set(pick.get("labels") or [])
        field = pick.get("by", "label")              # label (the source's label_field) or intent
        rows = read_source(name, src, quiet=True)
        if not rows:
            print(f"  ({name} not found at {local_path(src)})")
            continue
        pool = [r["text"] for r in rows if not labels or r.get(field) in labels]
        out += rnd.sample(pool, min(per, len(pool)))
    return out + list(GATE.get("extra_real") or [])


def gate_known_nonsense():
    return list(GATE.get("known_nonsense") or [])


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, src in SOURCES.items():
        if only and name != only:
            continue
        rows = read_source(name, src)
        labels = Counter(r["label"] for r in rows)
        print(f"{name}: {len(rows)} sentences, {len(labels)} labels, format {src.get('format')}, "
              f"use {', '.join(src.get('use') or [])}")
        if only:
            for lab, n in labels.most_common():
                print(f"  {n:6}  {lab}")


if __name__ == "__main__":
    main()
