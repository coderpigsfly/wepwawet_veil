"""addons/roman_numerals: a Roman numeral after a name said as words (issue #7; the first add-on, #25).
"John V" -> "John the Fifth", "Pope Leo XIV" -> "Pope Leo the Fourteenth", "World War II" -> "World War Two".
Only a numeral right after a capitalized word, so "I" in a sentence ("Yes, I can") stays a word."""

import os
import re

import yaml

ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
       "twelve": "twelfth"}
VALUE = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
SET = {"plain_after": [], "highest": 100, "not_names": []}
NUMERAL = re.compile(r"\b([A-Z][a-z]+)( )([IVXLC]+)\b(?=(\s*[.,;:!?)]|\s+of\b|\s+[a-z]|$))")


def setup(folder):
    """Its own settings (settings.yaml beside it)."""
    path = os.path.join(folder, "settings.yaml")
    if os.path.exists(path):
        with open(path) as f:
            SET.update(yaml.safe_load(f) or {})


def value(numeral):
    """The number a Roman numeral writes, or None when it isn't one written properly ("IIII", "VX")."""
    total, last = 0, 0
    for ch in reversed(numeral):
        v = VALUE[ch]
        total += -v if v < last else v
        last = max(last, v)
    return total if 0 < total <= int(SET.get("highest") or 100) and roman(total) == numeral else None


def roman(n):
    out = ""
    for v, s in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    return "one hundred"


def ordinal(n):
    w = words(n)
    head, _, last = w.rpartition("-")
    last = ORD.get(last, (last[:-1] + "ieth") if last.endswith("y") else last + "th")
    return (head + "-" if head else "") + last


def dress(text, ctx):
    """Her answer with each Roman numeral after a name said as words."""
    plain = {str(w).lower() for w in SET.get("plain_after") or []}
    not_names = {str(w).lower() for w in SET.get("not_names") or []}

    def say(m):
        name, gap, num, after = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        n = value(num)
        if n is None or name.lower() in not_names:
            return m.group(0)
        if num == "I" and not (after == "" or after[:1] in ".,;:!?)" or after == "of"):
            return m.group(0)        # "Charles I was": a word, not a numeral, unless a stop or "of" follows
        if name.lower() in plain:
            return f"{name}{gap}{words(n).title()}"
        return f"{name}{gap}the {ordinal(n).title()}"
    return NUMERAL.sub(say, text)
