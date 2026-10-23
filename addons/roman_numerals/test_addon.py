"""The Roman numerals add-on's own tests (run by tools/test_addon.py roman_numerals)."""


def run(mod, check):
    d = lambda s: mod.dress(s, {})  # noqa: E731
    check("a king, a pope, a war", [d("Henry VIII had six wives."), d("Pope Leo XIV spoke."), d("World War II ended in 1945.")],
          ["Henry the Eighth had six wives.", "Pope Leo the Fourteenth spoke.", "World War Two ended in 1945."])
    check("one, after a name and before a stop or 'of'", [d("Charles I was king."), d("Elizabeth I of England"), d("Yes, I can.")],
          ["Charles I was king.", "Elizabeth the First of England", "Yes, I can."])
    check("twenties and a bowl", [d("Pope John XXIII, the good pope."), d("Super Bowl LVIII")],
          ["Pope John the Twenty-Third, the good pope.", "Super Bowl Fifty-Eight"])
    check("not a numeral: left alone", [d("The XL size"), d("Louis IIII"), d("CIVIL war")], ["The XL size", "Louis IIII", "CIVIL war"])
