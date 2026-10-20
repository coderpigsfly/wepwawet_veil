#!/usr/bin/env python3
# tools/perplexity_test.py - EXPERIMENT, not part of the router.
# Does a small local GPT-style model's "surprise" score (perplexity) separate
#   real questions that should go straight to Gemini   (should score LOW)
# from
#   nonsense, mishearings and overheard speech          (should score HIGH)?
# Prints how the two groups score and, for a range of thresholds, how many real questions
# would wrongly get "Want me to ask around?" and how much nonsense would be caught.
#
# Run on myserver in a throwaway container (nothing installed on myserver or in the router):
#   cd ~/docker/house-router
#   docker run --rm -v "$PWD":/w -v ~/datasets:/root/datasets python:3.12-slim bash -c \
#     "pip install -q torch --index-url https://download.pytorch.org/whl/cpu && \
#      pip install -q transformers pyyaml && python /w/tools/perplexity_test.py"
# The datasets, labels and model come from tools/sources.yaml (gate_test:).

import math
import os
import random
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datasets as D  # noqa: E402  (sources, labels and the model: tools/sources.yaml)

random.seed(7)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = D.GATE.get("perplexity_model", "distilgpt2")
MISSES = os.path.join(ROOT, "learn", "misses.yaml")
KNOWN_NONSENSE = D.gate_known_nonsense()


def real_requests():
    return D.gate_real_requests()


def nonsense(real):
    out = list(KNOWN_NONSENSE)
    try:
        out += [m["heard"] for m in (yaml.safe_load(open(MISSES)) or {}).get("misses") or []]
    except FileNotFoundError:
        pass
    # garbled versions of real requests: words shuffled, as a mishearing might jumble them
    for s in random.sample(real, min(120, len(real))):
        w = s.split()
        if len(w) >= 4:
            random.shuffle(w)
            out.append(" ".join(w))
    # word salad from the real requests' vocabulary
    vocab = [w for s in real for w in re.findall(r"[a-z']+", s.lower())]
    for _ in range(60):
        out.append(" ".join(random.choice(vocab) for _ in range(random.randint(3, 8))))
    return list(dict.fromkeys(out))


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL).eval()

    def ppl(text):
        ids = tok(tok.bos_token + text, return_tensors="pt").input_ids
        with torch.no_grad():
            loss = model(ids, labels=ids).loss.item()
        return math.exp(loss)

    real = real_requests()
    junk = nonsense(real)
    print(f"\nScoring {len(real)} real requests and {len(junk)} nonsense sentences with {MODEL}...")
    rs = sorted((ppl(s), s) for s in real)
    js = sorted((ppl(s), s) for s in junk)

    def pct(vals, p):
        return vals[min(len(vals) - 1, int(p / 100 * len(vals)))][0]

    print("\nSurprise score (perplexity)   median   75%     90%     95%")
    for name, v in (("real (should be LOW) ", rs), ("nonsense (HIGH)      ", js)):
        print(f"  {name}        {pct(v,50):7.0f} {pct(v,75):7.0f} {pct(v,90):7.0f} {pct(v,95):7.0f}")

    print("\nThreshold  real wrongly asked  nonsense caught")
    for t in (100, 200, 300, 500, 750, 1000, 1500, 2000, 3000):
        fa = sum(s >= t for s, _ in rs) / len(rs)
        ca = sum(s >= t for s, _ in js) / len(js)
        print(f"  {t:6}        {fa:6.1%}           {ca:6.1%}")

    print("\nThe real misses and known nonsense:")
    for s, t in sorted((ppl(t), t) for t in KNOWN_NONSENSE):
        print(f"  {s:8.0f}  {t}")
    print("\nReal requests that scored highest (these would wrongly be asked):")
    for s, t in rs[-12:]:
        print(f"  {s:8.0f}  {t}")
    print("\nNonsense that scored lowest (these would slip through to Gemini):")
    for s, t in js[:12]:
        print(f"  {s:8.0f}  {t}")


if __name__ == "__main__":
    main()
