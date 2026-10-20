#!/usr/bin/env python3
# tools/test_veil.py - Wepwawet Veil's own parts, tested on their own (no router, nothing
# running, nothing on myserver touched: everything works in a throwaway folder).
#   saying names (who is sure enough, the deck, where the name goes), the firewall,
#   permitted addresses, comment-keeping writes, the activity log and answer bank,
#   accounts, sessions and tokens, the vault, the Wyoming audio path (with the wyoming library,
#   when it's installed, as a stand-in Oread and a stand-in Home Assistant).
# Run from ~/docker/house-router:  python3 tools/test_veil.py

import os
import random
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="veil-test-")
# a throwaway copy as a fresh install starts (starting copies and stand-in assistants), so the
# tests never read or write the household's own files or her real personality
sys.path.insert(0, os.path.join(REPO, "tests"))
import make_copy  # noqa: E402
ROOT = make_copy.make(os.path.join(TMP, "root"), REPO)
sys.path.insert(0, ROOT)
os.environ["ROUTER_ROOT"] = ROOT
os.environ["ROUTER_DATA"] = os.path.join(TMP, "data")

from veil import access, activity, config, firewall, mishearings, security, speakers  # noqa: E402
from veil import phases as _ph  # noqa: E402
if os.environ.get("VEIL_PHASES_OFF"):        # tier 1 both ways: every staged dump switched off (the old paths)
    _ph.PHASES = {k: False for k in _ph.PHASES}

from veil.errors import VeilError  # noqa: E402

PASSED, FAILED = [], []


def case(name, got, want):
    (PASSED if got == want else FAILED).append(name)
    if got != want:
        print(f"FAIL  {name}\n        got:  {got!r}\n        want: {want!r}")


def raises(name, fn, kind=VeilError):
    try:
        fn()
    except kind:
        PASSED.append(name)
        return
    except Exception as e:
        FAILED.append(name)
        print(f"FAIL  {name}: raised {type(e).__name__} {e}")
        return
    FAILED.append(name)
    print(f"FAIL  {name}: didn't raise")


# ---------- names ----------

PEOPLE = {}
case("Who spoke is the voice ID's own name, exactly as sent (Oct 15)", (speakers.person_for("Sam"), speakers.person_for(" Beth "), speakers.person_for("")), ("Sam", "Beth", None))
nl = speakers.Names({"names_in_replies": {}}, {"e": {"names": {"rate": 1.0}}})
case("a voice with no names on Name Sparkle hears none", nl.dress("e", "You have 2 chores.", {"person": "beth", "speaker": "Beth", "label": "known", "score": 0.95}, "A")[0],
     "You have 2 chores.")
case("word overlap", round(speakers.overlap("what's the weather tomorrow", "What's the weather tomorrow?"), 2), 1.0)
case("no overlap", speakers.overlap("open the garage", "tell me a joke"), 0.0)
# echoes (Oct 17, from the log): her words back keep their order; a real request borrows a few
_ans = "It looks like you have Buy single whole faucet on your list. Should I mark that one complete for you?"
case("echo: her own words back, misheard in the middle, keep their order",
     speakers.in_order("It looks like you have my signal from the faucet on your list. Should I mark that one?", _ans) >= 0.6, True)
case("echo: a real request that borrows her words isn't one",
     [speakers.in_order(h, a) < 0.6 for h, a in [("Mark bisingle hole faucet complete.", _ans),
      ("Add a new chore.", "Added I for you, in Voice Tech. Is there anything else for this chore? I can add a due date, or repeat."),
      ("Did you mark it complete?", 'Oh, I see! You want to mark "Buy single whole faucet" as complete, don\'t you?')]], [True, True, True])
# Oct 17, evening: her answer back misheard, with room talk on the end, still brings most of her words
_gem = ("I'm still a bit puzzled, but I'm ready to sprinkle some magic on whatever you need! Are we looking for a recipe, "
        "or perhaps something else on your mind?")
_back = ("Puzzle, but I'm ready to spring on some magic of whatever you need. I mean, for us he or perhaps something else "
         "on my mind. We were talking about marriage.")
case("echo: misheard, room talk on the end: her answer's words come back", speakers.covered(_gem, _back) >= 0.6, True)
case("echo: a request borrowing a few of her words brings back few of them",
     [speakers.covered(a, h) < 0.6 for h, a in [("Mark bisingle hole faucet complete.", _ans),
      ("Add a new chore.", "Added I for you, in Voice Tech. Is there anything else for this chore? I can add a due date, or repeat."),
      ("Did you mark it complete?", 'Oh, I see! You want to mark "Buy single whole faucet" as complete, don\'t you?')]], [True, True, True])

rng = random.Random(1)
case("name in front lowers the first word", speakers.place("You have 3 chores.", "Owner", random.Random(5)),
     "Owner, you have 3 chores.")
case("never after a question", speakers.place("Want to hear the rest?", "Beth", random.Random(0)),
     "Beth, want to hear the rest?")
case("I stays capital", speakers.place("I added it.", "Beth", random.Random(5)), "Beth, I added it.")
case("an abbreviation stays capital", speakers.place("NWS says rain.", "Beth", random.Random(5)), "Beth, NWS says rain.")
ends = {speakers.place("It will rain tomorrow.", "Owner", random.Random(i)) for i in range(40)}
case("sometimes at the end", "It will rain tomorrow, Owner." in ends and "Owner, it will rain tomorrow." in ends, True)

S = {"names_in_replies": {"min_score": 0.8, "labels": ["known"], "paths": ["A", "B", "C"],
                                            "calls": {"Owner": ["Owner"]}}}
n = speakers.Names(S, {"iris": {"names": {"rate": 1.0}}, "felix": {"names": {"rate": 0}}}, seed=3)
sure = {"person": "owner", "speaker": "Owner", "label": "known", "score": 0.9}
line, why = n.dress("iris", "You have 3 chores.", sure, "A")
case("rate 1: the name every time", "Owner" in line, True)
line, why = n.dress("iris", "You have 3 chores.", dict(sure, label="maybe", score=0.95), "A")
case("maybe: no name", line, "You have 3 chores.")
line, why = n.dress("iris", "You have 3 chores.", dict(sure, score=0.4), "A")
case("a low score that the voice ID still calls known gets the name: the voice ID decides (Oct 15)", "Owner" in line, True)
_strict = speakers.Names(S, {"iris": {"names": {"rate": 1.0, "min_score": 0.8}}}, seed=3)
case("a persona's own least score holds a name back", _strict.dress("iris", "You have 3 chores.", dict(sure, score=0.7), "A")[0], "You have 3 chores.")
line, why = n.dress("iris", "Back to my nap.", sure, "0")
case("path 0: no name", line, "Back to my nap.")
line, why = n.dress("felix", "You have 3 chores.", sure, "A")
case("a device rate of 0 says no names", line, "You have 3 chores.")
line, why = n.dress("nobody", "You have 3 chores.", sure, "A")
case("a device with no rate says no names", line, "You have 3 chores.")
# Name Sparkle (Oct 14): one of the names she may call them, at random, by their voice ID name
SC = dict(S, names_in_replies=dict(S["names_in_replies"], calls={"Sam": ["Captain", "Boss"], "Elizabeth": []}))
nc = speakers.Names(SC, {"iris": {"names": {"rate": 1.0}}}, seed=5)
said = {nc.dress("iris", "You have 3 chores.", {"person": "owner", "speaker": "sam", "label": "known", "score": 0.9}, "A")[0] for _ in range(30)}
case("Name Sparkle: a random one of the names under them (voice ID name, any case)", said, {"Captain, you have 3 chores.", "Boss, you have 3 chores."} | {x for x in said if x.endswith(", Captain.") or x.endswith(", Boss.")})
_run = [nc.dress("iris", "You have 3 chores.", {"speaker": "Sam", "label": "known", "score": 0.9}, "A")[0] for _ in range(12)]
_nm = ["Captain" if "Captain" in x else "Boss" for x in _run]
case("Name Sparkle: never the same name twice running for a person (Oct 17)", any(a == b for a, b in zip(_nm, _nm[1:])), False)
case("Name Sparkle: nobody listed under them: no name", nc.dress("iris", "You have 3 chores.", {"person": "beth", "speaker": "Elizabeth", "label": "known", "score": 0.9}, "A")[0], "You have 3 chores.")
_l = nc.dress("iris", "You have 3 chores.", {"person": None, "speaker": "Sam", "label": "known", "score": 0.9}, "A")[0]
case("Name Sparkle: a voice with names needs no People entry", ("Captain" in _l) or ("Boss" in _l), True)
case("Name Sparkle: still only when the voice ID says known", nc.dress("iris", "You have 3 chores.", {"speaker": "Sam", "label": "maybe", "score": 0.9}, "A")[0], "You have 3 chores.")
_np = speakers.Names(SC, {"iris": {"names": {"rate": 1.0, "calls": {"sam": ["Sir"]}}}, "felix": {"names": {"rate": 1.0}}}, seed=5)
_said = {_np.dress("iris", "You have 3 chores.", {"speaker": "Sam", "label": "known", "score": 0.9}, "A")[0] for _ in range(20)}
case("A persona's own names come first", all("Sir" in x for x in _said), True)
_said = {_np.dress("felix", "You have 3 chores.", {"speaker": "Sam", "label": "known", "score": 0.9}, "A")[0] for _ in range(20)}
case("A persona with none of its own uses the shared names", all(("Captain" in x) or ("Boss" in x) for x in _said), True)
low = speakers.Names({"names_in_replies": {"rate": 0.5, "max_in_a_row": 2, "min_score": 0.8}},
                     {"e": {"names": {"rate": 0.2, "max_in_a_row": 3, "min_score": 0.7}}})
k = low.knobs("e")
case("the device's own rate rules (no house rate or house score)", (k["rate"], k["max_in_a_row"], k["min_score"], k["enabled"]), (0.2, 3, 0.7, True))
k = speakers.Names({"names_in_replies": {}}, {"e": {"names": {"rate": 0.6, "min_score": 0.9}}}).knobs("e")
case("a device can ask for a least score of its own", k["min_score"], 0.9)
case("rate 0 is off", speakers.Names({"names_in_replies": {}}, {"e": {"names": {"rate": 0}}}).knobs("e")["enabled"], False)
line, why = n.dress("iris", "Here you are [[name]], 3 chores.", sure, "A")
case("a placed [[name]] is used", line, "Here you are Owner, 3 chores.")
line, why = n.dress("iris", "Here you are [[name]], 3 chores.", {}, "A")
case("an unfilled [[name]] vanishes", line, "Here you are , 3 chores.".replace(" ,", ","))

d = speakers.Deck(0.3, 1, random.Random(4))
cards = [d.deal() for _ in range(200)]
case("deck: about 3 in 10", 45 <= sum(cards) <= 75, True)
case("deck: never two in a row", any(a and b for a, b in zip(cards, cards[1:])), False)

# ---------- the firewall ----------

fw = firewall.Firewall({"enabled": True, "rules": [
    {"name": "kids", "people": ["unknown"], "devices": ["garage door"], "commands": ["unlock the door"]},
    {"name": "beth off felix", "people": ["beth"], "voice_devices": ["felix"]},
    {"name": "no adds", "people": ["unknown"], "topics": ["chores.add"]},
    {"name": "off", "enabled": False, "people": ["anyone"], "gemini": True}]})
unknown = {"label": "unknown", "score": 0.3}
case("disabled rules are dropped", len(fw.rules), 3)
case("unknown voice, garage door", (fw.check(unknown, "iris", "open the garage door") or {}).get("why"),
     "may not work the garage door")
case("known voice, garage door", fw.check(sure, "iris", "open the garage door"), None)
case("a command phrase", bool(fw.check(unknown, "iris", "please unlock the door now")), True)
case("whole words only", fw.check(unknown, "iris", "the garage doorbell rang"), None)
case("voice device", bool(fw.check({"speaker": "Beth", "label": "known", "score": 0.9}, "felix", "hi there")), True)
case("other voice device", fw.check({"speaker": "Beth", "label": "known", "score": 0.9}, "iris", "hi there"), None)
case("the firewall matches the voice ID's own name only, no nickname or key in between",
     fw.check({"speaker": "Elizabeth", "person": "beth", "label": "known", "score": 0.9}, "felix", "hi there"), None)
# the people grid (Oct 17): a name in the same row is the same person (Oread's other profile, say)
from veil import people as _pp  # noqa: E402


def _grid(g):
    config.edit_yaml(config.SETTINGS_FILE, lambda doc: doc.__setitem__("people", g))
    _pp._CACHE["mtime"] = None


_grid({"apps": ["oread", "donetick"], "rows": [{"wepwawet": "Beth", "called": ["Liz"], "oread": ["Elizabeth"], "donetick": ["beth"]},
                                                {"wepwawet": "Owner", "called": [], "oread": ["Owner", "Sam"], "donetick": ["Owner"]},
                                                {"wepwawet": "", "called": [], "oread": ["Alexandra"], "donetick": []}]})
case("people grid: the firewall matches any name in the person's row",
     bool(fw.check({"speaker": "Elizabeth", "label": "known", "score": 0.9}, "felix", "hi there")), True)
case("people grid: every name a person goes by", sorted(_pp.names("sam")), ["owner", "sam"])
case("people grid: a name in no row is only itself", _pp.names("Visitor"), {"visitor"})
case("people grid: an app gets its own column only, beside the router's name",
     _pp.column("oread"), [{"person": "Beth", "names": ["Elizabeth"]}, {"person": "Owner", "names": ["Owner", "Sam"]},
                           {"person": None, "names": ["Alexandra"]}])
from veil import fleas as _flm  # noqa: E402
_fl_b = _flm.Fleas()
_fl_b.doc = {"changers": ["Sam"]}
case("people grid: Sam may change fleas, so Oread's Owner may too (one row)", (_fl_b.may_change("Owner"), _fl_b.may_change("Beth")), (True, False))
_grid({"apps": [], "rows": []})
case("topic action", bool(fw.check(unknown, "iris", "add milk", topic="chores", action="add")), True)
case("other action of the topic", fw.check(unknown, "iris", "list", topic="chores", action="list"), None)
case("watches tools for unknown", fw.watches_tools(unknown, "iris"), True)
case("doesn't watch a known voice", fw.watches_tools(sure, "iris"), False)
calls = [{"name": "HassTurnOn", "arguments": '{"name": "garage door"}'}]
case("a Gemini tool call is caught", bool(fw.check_tools(unknown, "iris", calls)), True)
case("another tool call isn't", fw.check_tools(unknown, "iris", [{"name": "HassTurnOn", "arguments": '{"name": "kitchen light"}'}]), None)
down = firewall.Firewall({"enabled": True, "when_oread_down": "allow", "rules": [{"people": ["unknown"], "gemini": True}]})
case("Oread down, allow: nobody blocked", down.check({"error": "timeout"}, "iris", "joke", going_to_gemini=True), None)
down2 = firewall.Firewall({"enabled": True, "rules": [{"people": ["unknown"], "gemini": True}]})
case("Oread down, default: unknown", bool(down2.check({"error": "timeout"}, "iris", "joke", going_to_gemini=True)), True)
case("firewall off", firewall.Firewall({"rules": [{"people": ["anyone"], "gemini": True}]}).check(unknown, "x", "y", going_to_gemini=True), None)

# Home Assistant's own commands (veil_guard_service asks /firewall/check)
hc = firewall.Firewall({"enabled": True, "rules": [
    {"people": ["unknown"], "domains": ["lock"]},
    {"people": ["unknown"], "intents": ["HassTurnOn:cover", "HassSetPosition"]},
    {"people": ["beth"], "devices": ["garage door"]}]})
beth = {"person": "beth", "label": "known", "score": 0.9}
case("a lock, any command", bool(hc.check_command(unknown, "iris", "HassTurnOff", ["front door", "lock.front_door"], ["lock"])), True)
case("a light is fine", hc.check_command(unknown, "iris", "HassTurnOn", ["kitchen light"], ["light"]), None)
case("a command on one kind of device", bool(hc.check_command(unknown, "x", "HassTurnOn", ["garage"], ["cover"])), True)
case("the same command elsewhere", hc.check_command(unknown, "x", "HassTurnOn", ["fan"], ["fan"]), None)
case("a command on any device", bool(hc.check_command(unknown, "x", "HassSetPosition", ["blinds"], ["cover"])), True)
case("a device by its name", bool(hc.check_command(beth, "x", "HassTurnOn", ["Garage door", "cover.garage_door"], ["cover"])), True)
case("a device in the words", bool(hc.check_command(beth, "x", "HassTurnOn", [], [], "open the garage door")), True)
case("a known voice passes", hc.check_command(sure, "x", "HassTurnOff", ["front door"], ["lock"]), None)
case("nothing to ask about when off", firewall.Firewall({"rules": [{"people": ["anyone"]}]}).has_command_rules(), False)

# ---------- permitted addresses ----------

a = access.Access({"inbound_allowed": [], "admin_allowed": ["192.168.1.0/24"], "outbound_allowed": ["192.168.1.20"]})
case("empty list: local network", a.allowed("inbound_allowed", "192.168.1.5"), True)
case("empty list: never the internet", a.allowed("inbound_allowed", "8.8.8.8"), False)
case("range", a.allowed("admin_allowed", "192.168.1.21"), True)
case("outside the range", a.allowed("admin_allowed", "192.168.2.20"), False)
case("ipv4 inside ipv6", a.allowed("admin_allowed", "::ffff:192.168.1.21"), True)
raises("outbound refused", lambda: a.check_outbound("http://192.168.1.65:2021/api"))
a.check_outbound("http://192.168.1.20:4000/chat")
PASSED.append("outbound permitted")
raises("a bad entry", lambda: access.parse(["not-an-address"]))
# Oct 20: "local" keeps the local network in a list that also names an app on the internet
c = access.Access({"outbound_allowed": ["local", "37.187.213.137"]})
case("local in a list: the local network still permitted", c.allowed("outbound_allowed", "192.168.1.20"), True)
case("...and the address beside it", c.allowed("outbound_allowed", "37.187.213.137"), True)
case("...and the rest of the internet still not", c.allowed("outbound_allowed", "8.8.8.8"), False)
# ...and an app on the internet permitted by its name, whatever its addresses (going out only)
c = access.Access({"outbound_allowed": ["local", "litcal.johnromanodorazio.com"]})
c.check_outbound("https://litcal.johnromanodorazio.com/api/v5/calendar")
PASSED.append("a name in the going-out list: calls to it permitted")
raises("...another name isn't", lambda: c.check_outbound("https://example.com/x"))
raises("a name in the coming-in list is refused when saved", lambda: access.parse(["litcal.johnromanodorazio.com"]))
# Oct 20: folders the router makes are handed back like its files (FILE_OWNER), not left to root
_handed = []
_was_hand_back, config.hand_back = config.hand_back, _handed.append
config.make_dirs(os.path.join(TMP, "made", "personality", "approved"))
config.make_dirs(os.path.join(TMP, "made", "personality"))
config.hand_back = _was_hand_back
case("new folders handed back, each one made, none twice",
     sorted(os.path.relpath(d, TMP) for d in _handed), ["made", "made/personality", "made/personality/approved"])
# Oct 18, after the power cut: a program at a new address, refused, is warned of with who used that door before
b = access.Access({"inbound_allowed": ["192.168.1.50"]})
b.allowed("inbound_allowed", "192.168.1.50", "Wyoming port for iris")
for _ in range(3):
    if not b.allowed("inbound_allowed", "192.168.1.65", "Wyoming port for iris"):
        b.note("inbound_allowed", "192.168.1.65", "Wyoming port for iris")
_late = b.lately(60)
case("refusals of the last hour, counted per address and door", [(x["address"], x["n"]) for x in _late], [("192.168.1.65", 3)])
case("...naming the address that used the same door before", _late[0]["before"], "192.168.1.50")
case("older ones aren't warned of", b.lately(0), [])

# ---------- the word lists: a bare on, off, yes or no is read as true or false (Oct 18) ----------

import glob  # noqa: E402
import yaml  # noqa: E402


def _bools(x, where):
    if isinstance(x, dict):
        return [b for k, v in x.items() for b in ([f"{where} key {k}"] if isinstance(k, bool) else []) + _bools(v, f"{where}.{k}")]
    if isinstance(x, list):
        return [b for v in x for b in ([f"{where}: {v}"] if isinstance(v, bool) else []) + _bools(v, where)]
    return []


_found = [b for f in sorted(glob.glob(os.path.join(REPO, "vocab", "*.yaml")) + glob.glob(os.path.join(REPO, "phrases", "*.yaml")))
          for b in _bools(yaml.safe_load(open(f)) or {}, os.path.basename(f))]
case("no word in vocab/ or phrases/ is a bare on, off, yes or no (YAML would make it true or false)", _found, [])

# ---------- a page saved from an old copy (Oct 18) ----------

_sf = os.path.join(TMP, "stamped.yaml")
open(_sf, "w").write("rules:\n  one: {words: [a]}\nactions:\n  list: {api: GET /x}\n")
_st = config.stamp(_sf, "rules")
open(_sf, "w").write("rules:\n  one: {words: [a]}\nactions:\n  list: {api: GET /y}\n")
config.check_stamp(_sf, "rules", _st)
PASSED.append("another part of the file changing doesn't make the page's rules old")
open(_sf, "w").write("rules:\n  one: {words: [a, b]}\nactions:\n  list: {api: GET /y}\n")
raises("the rules changed since the page opened: the save is refused", lambda: config.check_stamp(_sf, "rules", _st))
config.check_stamp(_sf, "rules", None)
PASSED.append("no stamp sent (a tool): not checked")
case("a missing file has a stamp of its own", config.stamp(os.path.join(TMP, "none.yaml"), "rules") == _st, False)

# ---------- firewall device names against the front end's devices (Oct 18) ----------

case("a rule's device no device has is listed; one that's there isn't",
     firewall.unknown_devices([{"name": "kids", "devices": ["gaurd test", "garage door"]}], ["Garage Door Opener", "front porch"]),
     [{"rule": 1, "name": "kids", "device": "gaurd test"}])

# ---------- comment-keeping writes ----------

f = os.path.join(TMP, "s.yaml")
with open(f, "w") as fh:
    fh.write("# top comment\nrate: 0.3   # how often\nnested:\n  # inner\n  knob: 1\n")
config.edit_yaml(f, lambda doc: config.set_in(doc, ["nested", "knob"], 2))
config.edit_yaml(f, lambda doc: config.set_in(doc, ["new", "deep", "value"], True))
text = open(f).read()
case("comments survive", "# top comment" in text and "# how often" in text and "# inner" in text, True)
case("value changed", config.load_yaml(f)["nested"]["knob"], 2)
case("new path made", config.load_yaml(f)["new"]["deep"]["value"], True)
case("ends with blank lines", text.endswith("\n\n\n"), True)
from ruamel.yaml.comments import CommentedSeq  # noqa: E402


def risky(doc):
    seq = CommentedSeq(["kill*", "good-?bye", "yes", "3", "a: b", "plain"])
    seq.fa.set_flow_style()
    doc["never"] = seq


config.edit_yaml(f, risky)
case("risky words are quoted and read back", config.load_yaml(f)["never"], ["kill*", "good-?bye", "yes", "3", "a: b", "plain"])
case("defaults fill gaps", config.merged({"a": {"b": 1, "c": 2}}, {"a": {"b": 5}}), {"a": {"b": 5, "c": 2}})

# ---------- the activity log and the answer bank ----------

act = activity.Activity(os.path.join(TMP, "data", "veil.db"))
rid = act.add(assistant="iris", heard="tell me a joke", path="gemini", engine="gemini", why=["shaped like a request"])
act.finish(rid, answer="Why did the broom...", ms=900)
act.add(assistant="iris", heard="weather", path="A", engine="weather_brain", answer="Sunny.")
rows = act.recent(10)
case("activity newest first", [r["heard"] for r in rows], ["weather", "tell me a joke"])
case("why kept as a list", rows[1]["why"], ["shaped like a request"])
case("left the house only", [r["heard"] for r in act.recent(10, direction="out")], ["weather", "tell me a joke"])
c = act.counts(0)
case("counts", (c["total"], c["gemini"], c["home"]), (2, 1, 1))
b1 = act.bank_add(activity.key_of(["tell", "me", "a", "joke"]), "Tell me a joke", "command", "", None, None, "iris")
b2 = act.bank_add(activity.key_of("Tell me a joke!"), "tell me a joke", "command", "", None, None, "iris")
case("same words, same bank row", b1, b2)
bg = act.bank_add(activity.key_of("Tell me a joke!"), "tell me a joke", "command", "", None, None, "felix")
case("each personality has its own bank", bg != b1, True)
act.answers_kept = 5
for i in range(7):
    act.bank_trip(b1)
    act.bank_answer(b1, f"joke {i}", "gemini-lite", 800)
row = act.bank(personality="iris")["rows"][0]
case("bank counts heard and trips apart", (row["count"], row["trips"]), (2, 7))
case("answers kept: the newest T", [x["answer"] for x in row["answers"]], [f"joke {i}" for i in (6, 5, 4, 3, 2)])
act.bank_review(b1, "promote", "answer jokes at home")
case("review saved", act.bank(review="promote")["rows"][0]["note"], "answer jokes at home")
raises("a bad review", lambda: act.bank_review(b1, "maybe"), ValueError)

# the formula: N = trips - 1, T = answers kept, Q = N / T (at most 1), used when Q >= U, Q of the time
act.answers_kept = 10
case("formula: N and Q", act.quota(6), (5, 10, 0.5))
case("formula: Q at most 100%", act.quota(40)[2], 1.0)
case("formula: nothing before a second trip", act.quota(1), (0, 10, 0.0))
case("formula: no trips", act.quota(0), (0, 10, 0.0))


class Draw:
    """A stand-in for random: draws the numbers given, then picks the first choice."""
    def __init__(self, *draws):
        self.draws = list(draws)

    def random(self):
        return self.draws.pop(0)

    def choice(self, xs):
        return xs[0]


fresh = activity.Activity(os.path.join(TMP, "data", "formula.db"), answers_kept=10, use_from=0.2, rng=Draw(0.3, 0.7))
jk = fresh.bank_add("tell me a joke", "tell me a joke", "command", "", None, None, "iris")
for i in range(6):                            # 6 trips: N 5, T 10 -> Q 50%
    fresh.bank_trip(jk)
    fresh.bank_answer(jk, f"joke {i}", "gemini-lite", 800)
hit, why = fresh.bank_choose("iris", "tell me a joke")
case("formula: not added -> not used", (hit, why), (None, "in the bank's counts, but not added"))
fresh.bank_set_added(jk, True)
hit, why = fresh.bank_choose("iris", "tell me a joke")
case("formula: Q 50% >= U 20%, drew 0.30 -> the bank answers", (hit or {}).get("kind"), "answer")
case("formula: one of the kept answers", (hit or {}).get("text"), "joke 5")
case("formula: the why shows it", "N 5 (trips 6 - 1) / T 10 = Q 50%, U 20%" in why, True)
hit, why = fresh.bank_choose("iris", "tell me a joke")
case("formula: drew 0.70 >= Q 50% -> Off-Platform this time", (hit, "this time Off-Platform" in why), (None, True))
case("formula: another personality's bank is its own", fresh.bank_choose("felix", "tell me a joke")[0], None)
fresh.use_from = 0.6
fresh.rng = Draw(0.1)
hit, why = fresh.bank_choose("iris", "tell me a joke")
case("formula: Q 50% below U 60% -> never", (hit, "Q below U" in why), (None, True))
fresh.use_from = 0.2
for i in range(10):                           # N 15, T 10 -> Q 100%: always the bank
    fresh.bank_trip(jk)
fresh.rng = Draw(0.99)
case("formula: Q 100% -> always the bank", (fresh.bank_choose("iris", "tell me a joke")[0] or {}).get("kind"), "answer")
r0 = [r for r in fresh.bank(personality="iris")["rows"] if r["id"] == jk][0]
case("bank page: N, T, Q, usable", (r0["n"], r0["t"], r0["q"], r0["usable"]), (15, 10, 1.0, True))

# generic (Oct 14): another personality may use a saying marked generic; her own comes first
fresh.rng = Draw(0.5)
case("generic: off -> the joke stays with iris", fresh.bank_choose("felix", "tell me a joke")[0], None)
fresh.bank_set_generic(jk, True)
fresh.rng = Draw(0.5)
hit, why = fresh.bank_choose("felix", "tell me a joke")
case("generic: on -> felix may answer from iris's saying, marked as such",
     ((hit or {}).get("kind"), (hit or {}).get("generic_from"), why.startswith("generic, iris's")), ("answer", "iris", True))
gj = fresh.bank_add("tell me a joke", "tell me a joke", "command", "", None, None, "felix", personality="felix")
for i in range(16):
    fresh.bank_trip(gj)
fresh.bank_answer(gj, "felix's own joke", "gemini-lite", 800)
fresh.bank_set_added(gj, True)
fresh.rng = Draw(0.5)
hit, why = fresh.bank_choose("felix", "tell me a joke")
case("generic: her own saying, when usable, comes first", ((hit or {}).get("text"), (hit or {}).get("generic_from")), ("felix's own joke", None))
fresh.bank_set_added(gj, False)
fresh.rng = Draw(0.5)
case("generic: her own not added -> the generic one answers", (fresh.bank_choose("felix", "tell me a joke")[0] or {}).get("generic_from"), "iris")
fresh.bank_set_generic(jk, False)
case("generic: export says which are generic", [x["generic"] for x in fresh.bank_export() if x["heard"] == "tell me a joke" and x["personality"] == "iris"], [False])

# device commands: reused only when every kept answer is the same command
gd = fresh.bank_add("open the garage door", "Open the garage door", "command", "", None, None, "iris")
call = [{"name": "HassTurnOn", "arguments": '{"name": "Garage Door"}'}]
for i in range(6):
    fresh.bank_trip(gd)
    fresh.bank_answer(gd, "", "gemini-lite", 900, call)
    fresh.bank_answer(gd, "The garage door is opening.", "gemini-lite", 700)    # her words after it
fresh.bank_set_added(gd, True)
both = fresh.bank_add("lights on and say hi", "lights on and say hi", "command", "", None, None, "iris")
fresh.bank_answer(both, "Sure!", "gemini-lite", 900, call)                               # words and a command at once
fresh.bank_answer(both, "Done.", "gemini-lite", 700, after_command=True)                 # her words after it
kb = [r for r in fresh.bank(added=None)["rows"] if r["id"] == both][0]["answers"]
case("device commands aren't kept (Oct 14): words and a command at once, and the words after, keep nothing", kb, [])
kept = [r for r in fresh.bank()["rows"] if r["id"] == gd][0]["answers"]
case("device commands aren't kept: the garage door saying keeps no answers", kept, [])
fresh.rng = Draw(0.1)
hit, why = fresh.bank_choose("iris", "open the garage door")
case("device commands aren't kept: so the bank never hands one to Home Assistant", (hit, "no Off-Platform answers kept yet" in why), (None, True))
fresh.bank_answer(gd, "The garage door is closing.", "gemini-lite", 700, after_command=True)    # after a restart: no memory of the command
case("words after a command are never kept, even when the command was before a restart",
     [r for r in fresh.bank()["rows"] if r["id"] == gd][0]["answers"], [])
fresh.bank_answer(gd, "I can't find a garage door.", "gemini-lite", 700, after_command=False)   # words, no command: kept
case("words with no command are kept as usual", [a["answer"] for a in [r for r in fresh.bank()["rows"] if r["id"] == gd][0]["answers"]],
     ["I can't find a garage door."])
_old = os.path.join(TMP, "data", "old-tools.db")
_o = activity.Activity(_old)
_ob = _o.bank_add("lights off", "lights off", "command", "", None, None, "iris")
with _o._db() as _db:
    _db.execute("INSERT INTO bank_answers (bank_id, time, answer, model, ms, tool_calls, kind) VALUES (?, 0, 'ok', 'm', 1, '[]', 'tool')", (_ob,))
case("device commands kept before Oct 14 are cleared at start", [r for r in activity.Activity(_old).bank(added=None)["rows"] if r["id"] == _ob][0]["answers"], [])
gd2 = fresh.bank_add("open the garage store", "Open the garage store", "command", "", None, None, "iris")
fresh.bank_answer(gd2, "", "gemini-lite", 900, call)
res = fresh.by_result(10)["results"]
top = next(r for r in res if r["sig"].startswith("HassTurnOn"))
case("bank: one result, every wording that led there", (top["count"], sorted(v["heard"] for v in top["variants"])),
     (8, ["Open the garage door", "Open the garage store", "lights on and say hi"]))

# transactions: the bank link, Add, Delete, Misheard's mark, the filters
rid = act.add(heard="Open the garage door", engine="gemini", path="gemini", bank_id=b1, sent_to="gemini-lite")
home_rid = act.add(heard="what's the weather", engine="weather_brain", path="A", t_decide=12.5, t_engine=310.0, ms=330.0)
case("transactions: not in the bank yet", [r for r in act.recent(5) if r["id"] == rid][0]["in_bank"], False)
raises("bank: only an Off-Platform request can be added", lambda: act.bank_add_from(home_rid), ValueError)
case("bank: Add adds it", act.bank_add_from(rid)["added"] is not None, True)
case("transactions: shows it's in the bank", [r for r in act.recent(5) if r["id"] == rid][0]["in_bank"], True)
case("transactions: went Off-Platform", [r["heard"] for r in act.recent(5, direction="gemini")],
     ["Open the garage door", "tell me a joke"])
case("transactions: answered at home", [r["id"] for r in act.recent(5, direction="home")][0], home_rid)
case("bank: the added list", [r["id"] for r in act.bank(added=True)["rows"]], [b1])
act.mark(home_rid, "misheard")
case("transactions: Misheard is marked", act.get(home_rid)["marked"], "misheard")
tr = {x["route"]: x for x in act.time_routes(0)}
case("Time Routes: by route and hop", (tr["app:weather_brain"]["hops"]["t_engine"]["median"], tr["app:weather_brain"]["hops"]["ms"]["median"]),
     (310.0, 330.0))
case("Time Routes: Off-Platform is its own route", "off_platform" in tr, True)
# Oct 18: LiteLLM's own time is a hop of its own; the same request sent again is counted on its row
_lt = act.add(heard="tell me a riddle", engine="gemini", path="gemini", t_engine=9000.0, t_litellm=650.0, ms=9100.0)
act.repeated(_lt)
act.repeated(_lt)
tr = {x["route"]: x for x in act.time_routes(0)}
case("Time Routes: LiteLLM itself, and Sent again", (tr["off_platform"]["hops"]["t_litellm"]["median"], tr["off_platform"]["repeats"]),
     (650.0, 2))
act.delete(_lt)
act.delete(home_rid)
case("transactions: Delete takes it out", act.get(home_rid), None)
raises("transactions: deleting twice", lambda: act.delete(home_rid), ValueError)
old_one = act.bank_add("a one off", "A one off", "question", "", None, None, "iris")
import sqlite3  # noqa: E402
with sqlite3.connect(act.path) as db:
    db.execute("UPDATE bank SET last = 0 WHERE id = ?", (old_one,))
act.bank_set_added(old_one, True)
case("bank: an added one-off is never trimmed", act.trim(30), 0)
act.bank_set_added(old_one, False)
case("bank: one-offs are trimmed", act.trim(30), 1)

# an older veil.db (one bank for everyone, answers without a kind) is rebuilt in place
olddb = os.path.join(TMP, "data", "old.db")
with sqlite3.connect(olddb) as db:
    db.executescript("""
CREATE TABLE bank (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, heard TEXT, class TEXT,
  qword TEXT, topic_guess TEXT, topic_score REAL, assistant TEXT, count INTEGER DEFAULT 1, first REAL, last REAL,
  review TEXT DEFAULT 'new', note TEXT DEFAULT '');
CREATE TABLE bank_answers (id INTEGER PRIMARY KEY AUTOINCREMENT, bank_id INTEGER NOT NULL, time REAL, answer TEXT,
  model TEXT, ms REAL, tool_calls TEXT);
INSERT INTO bank (id, key, heard, class, assistant, count, first, last) VALUES (7, 'open the garage', 'open the garage', 'command', 'iris', 3, 1, 2);
INSERT INTO bank_answers (bank_id, time, answer, tool_calls) VALUES (7, 100, '', '[{"name": "HassTurnOn", "arguments": {}}]');
INSERT INTO bank_answers (bank_id, time, answer, tool_calls) VALUES (7, 101, 'Opening it.', NULL);
INSERT INTO bank_answers (bank_id, time, answer, tool_calls) VALUES (7, 500, 'Done before.', NULL);
""")
up = activity.Activity(olddb)
ur = up.bank(added=None)["rows"]
case("an older bank: rebuilt per personality, ids kept", [(r["id"], r["personality"], r["count"], r["trips"]) for r in ur],
     [(7, "iris", 3, 3)])
case("an older bank: the words after a tool call join it, and go with it (device commands aren't kept, Oct 14)",
     [(a["kind"], a["answer"]) for a in ur[0]["answers"]], [("answer", "Done before.")])
case("an older bank: opens again unchanged", len(activity.Activity(olddb).bank(added=None)["rows"]), 1)
_cr = up.add(assistant="iris", heard="at a chore", path="A", clip="20261017-090000-001-iris", device="iris")
case("an older log gets Oread's clip and device columns, and a row keeps them (Oct 17)",
     (up.get(_cr)["clip"], up.get(_cr)["device"]), ("20261017-090000-001-iris", "iris"))
sv = activity.Activity(os.path.join(TMP, "data", "save.db"))
sv.add(engine="weather_brain", path="A", est_tokens=4000)
sv.add(engine="router", path="0", est_tokens=3800)
sv.add(engine="gemini", path="gemini", est_tokens=4200)
sv.add(engine="home_assistant", path="ha")
sv.add(engine="gemini", path="tool", est_tokens=4500)
sav = sv.savings(0, 3000)
case("savings: trips kept and out", (sav["trips_saved"], sav["trips_out"]), (2, 2))
case("savings: tokens, by the default and measured", (sav["tokens_saved"], sav["tokens_saved_measured"]), (6000, 7800))

# Donetick's "me": the default person, or whoever Oread is sure spoke
import connector as _cnx  # noqa: E402
dtk = _cnx.make("donetick", {"options": {}, "lists": {"people": {"house": "people", "me": "default", "default": "owner"}}},
                {"people": {"default": "owner"}}, lambda *a, **k: "",
                actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"))
case("donetick: its own class, on the generic connector", (type(dtk).__name__, isinstance(dtk, _cnx.Connector)), ("Donetick", True))
NAMES_DT = {"owner": (1, "Owner"), "sam": (1, "Owner"), "me": (1, "Owner"), "beth": (2, "Beth")}
case("donetick: me is the default", dtk.who_in("what's on my list", NAMES_DT), (1, "Owner"))
tok = dtk.SPEAKER.set("beth")
case("donetick: the speaker only when me: speaker", dtk.who_in("what's on my list", NAMES_DT), (1, "Owner"))
dtk.svc["lists"]["people"]["me"] = "speaker"
case("donetick: me is whoever spoke", dtk.who_in("what's on my list", NAMES_DT), (2, "Beth"))
case("donetick: a name said outright still wins", dtk.who_in("what does sam have", NAMES_DT), (1, "Owner"))
case("donetick: she says 'you' to the speaker", dtk.spoken_name((2, "Beth"), NAMES_DT), "you")
dtk.SPEAKER.reset(tok)
case("donetick: nobody known: the default", dtk.who_in("what's on my list", NAMES_DT), (1, "Owner"))
dtk.svc["lists"]["people"].update(me="default", default="beth")
case("donetick: no one named: the people card's own default person", dtk.default_person(NAMES_DT), (2, "Beth"))
dtk.svc["lists"]["people"]["default"] = "owner"
case("donetick: match_min comes from its voice map", dtk.match_min, float(__import__("yaml").safe_load(open(os.path.join(ROOT, "connectors", "donetick.yaml")))["match_min"]))
dtk.match_min = None
case("donetick: no match_min, no spoken chore matches", dtk.find_item("skip the trash", [{"id": 1, "name": "trash"}])[0], None)
dtk.match_min = 0.6

# ---------- accounts, sessions, tokens ----------

data = os.path.join(TMP, "data")
events = []
users = security.Users(data, lambda **e: events.append(e))
case("needs setup", users.needs_setup(), True)
code = users.setup_code()
raises("wrong setup code", lambda: users.setup("0000-0000-0000", "sam", "a long password", "1.2.3.4"))
users.setup(code, "sam", "a long password", "1.2.3.4")
case("set up", users.needs_setup(), False)
raises("wrong password", lambda: users.sign_in("sam", "wrong one!!", "1.2.3.4"))
session, me = users.sign_in("SAM", "a long password", "1.2.3.4")
case("names ignore case; first user is super", me["role"], "super")
case("session works", users.session_user(session)["name"], "sam")
actor = {"name": "sam", "role": "super"}
users.create(actor, "beth", "another password", "reviewer")
raises("a reviewer can't make an administrator", lambda: users.create({"name": "beth", "role": "reviewer"}, "kid", "kids password", "administrator"))
raises("short password", lambda: users.create(actor, "kid", "short", "viewer"))
raises("the last super can't be demoted", lambda: users.update({"name": "x", "role": "super"}, "sam", "viewer"))
for _ in range(5):
    try:
        users.sign_in("beth", "not it at all", "1.2.3.4")
    except VeilError:
        pass
raises("locked after five", lambda: users.sign_in("beth", "another password", "1.2.3.4"))
users.sign_out(session)
case("signed out", users.session_user(session), None)
toks = security.Tokens(data)
t = toks.create("tools", "reviewer")
case("token checks", toks.check(t), {"name": "tools", "role": "reviewer"})
case("a wrong token", toks.check(t + "x"), None)
case("the internal token", toks.check(security.INTERNAL)["role"], "administrator")
case("tokens stored as fingerprints", t in open(os.path.join(data, "tokens.json")).read(), False)
case("audit noted refusals", any(e.get("action") == "sign-in refused" for e in events), True)

# ---------- the vault ----------

try:
    from veil import vault
    v = vault.Vault(os.path.join(data, "vault.json"), os.path.join(data, "keys"))
    v.set("DONETICK_TOKEN", "abcdefghijklmnop", "donetick")
    case("vault reads back", v.get("donetick_token"), "abcdefghijklmnop")
    case("vault never stores plain text", "abcdefghijklmnop" in open(os.path.join(data, "vault.json")).read(), False)
    case("vault shows only the end", v.list()["keys"][0]["ends_with"], "…mnop")
    config._vault = v
    case("secrets: the vault first", config.secret("DONETICK_TOKEN"), "abcdefghijklmnop")
    os.environ["ONLY_ENV"] = "from env"
    case("secrets: then .env", config.secret("ONLY_ENV"), "from env")
    case("secret source", (config.secret_source("DONETICK_TOKEN"), config.secret_source("ONLY_ENV"), config.secret_source("NOPE")),
         ("vault", ".env", None))
except ImportError:
    print("  (vault skipped: no cryptography package)")

# ---------- the audio path (Wyoming, in front of Oread) ----------

try:
    import asyncio
    from wyoming.asr import Transcribe, Transcript
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.client import AsyncTcpClient
    from wyoming.event import async_read_event, async_write_event
    from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
    from veil import wyoming as wy

    unclaimed, results = [], {}

    async def audio_path():
        got_audio = []

        async def fake_oread(reader, writer):          # answers like Oread: info, then a transcript with who spoke
            while True:
                ev = await async_read_event(reader)
                if ev is None:
                    break
                if Describe.is_type(ev.type):
                    att = Attribution(name="x", url="")
                    await async_write_event(Info(asr=[AsrProgram(name="oread", description="", attribution=att, installed=True,
                        version="1", models=[AsrModel(name="whisper", description="", attribution=att, installed=True,
                                                      languages=["en"], version="1")])]).event(), writer)
                elif AudioChunk.is_type(ev.type):
                    got_audio.append(AudioChunk.from_event(ev).audio)
                elif AudioStop.is_type(ev.type):
                    await async_write_event(Transcript(text="what are my chores", context={
                        "speaker": "Sam", "label": "known", "score": 0.93, "by": "voice", "clip": "c1", "device": "iris"}).event(), writer)
            writer.close()

        oread = await asyncio.start_server(fake_oread, "127.0.0.1", 0)
        oport = oread.sockets[0].getsockname()[1]
        s = {"integrations": {"oread": {"enabled": True, "source": "wyoming", "max_age_seconds": 20, "min_word_overlap": 0.5,
             "wyoming": {"host": "127.0.0.1", "connect_timeout": 2, "devices": {"Iris": {"listen": 0, "oread": oport}},
                         "home_assistant_answered_after": 0.3}}},
             }
        wy.ON_UNCLAIMED = lambda assistant, h: unclaimed.append((assistant, h["text"]))
        await wy.start(s)
        port = wy.listening()[0]
        test = await wy.test(s)
        sound = bytes(range(256)) * 8
        async with AsyncTcpClient("127.0.0.1", port) as c:      # Home Assistant's side
            await c.write_event(Transcribe(language="en").event())
            await c.write_event(AudioStart(rate=16000, width=2, channels=1).event())
            await c.write_event(AudioChunk(rate=16000, width=2, channels=1, audio=sound).event())
            await c.write_event(AudioStop().event())
            ev = await asyncio.wait_for(c.read_event(), 3)
        heard = Transcript.from_event(ev)
        hops = wy.claim("iris", "What are my chores?")      # the request reached the router
        await asyncio.sleep(0.5)
        claimed_logged = list(unclaimed)
        async with AsyncTcpClient("127.0.0.1", port) as c:      # the same words again, never reaching the router
            await c.write_event(AudioStart(rate=16000, width=2, channels=1).event())
            await c.write_event(AudioStop().event())
            await asyncio.wait_for(c.read_event(), 3)
        await asyncio.sleep(0.5)
        results["hops"], results["claimed_logged"], results["unclaimed"] = hops, claimed_logged, list(unclaimed)
        # Oct 18: a mishearing marked Use it is fixed before Home Assistant gets the words
        wy.SWAP = lambda t: (t.replace("chores", "jobs"), [("chores", "jobs")])
        async with AsyncTcpClient("127.0.0.1", port) as c:
            await c.write_event(AudioStart(rate=16000, width=2, channels=1).event())
            await c.write_event(AudioStop().event())
            fixed_ev = await asyncio.wait_for(c.read_event(), 3)
        wy.SWAP = None
        results["fixed"] = Transcript.from_event(fixed_ev)
        results["fixed_hops"] = wy.claim("iris", "what are my jobs")
        who = await speakers.lookup("iris", "What are my chores?", s)
        other = await speakers.lookup("iris", "open the garage door", s)
        nobody = await speakers.lookup("felix", "what are my chores", s)
        await wy.stop()
        oread.close()
        return test, heard, got_audio, who, other, nobody

    test, heard, got_audio, who, other, nobody = asyncio.run(audio_path())
    case("Wyoming test: Oread answers", (test["ok"], "whisper" in test["detail"]), (True, True))
    case("Wyoming: Home Assistant gets Oread's words untouched", (heard.text, heard.context.get("speaker")), ("what are my chores", "Sam"))
    case("Wyoming: the audio reaches Oread byte for byte", b"".join(got_audio), bytes(range(256)) * 8)
    case("Wyoming: who spoke, for the request that follows (the voice ID's own name)", (who.get("person"), who.get("source"), who.get("score")),
         ("Sam", "wyoming", 0.93))
    case("Wyoming: other words aren't that request", other, {"mismatch": True})
    case("Wyoming: a request that reached the router gets its hops, the router's own hand-off among them (Oct 18)",
         sorted(k for k, v in results["hops"].items() if v is not None),
         ["audio_swaps", "clip", "device", "ha_text", "oread_heard", "t_ha_in", "t_relay", "t_speech", "t_stt"])
    case("Wyoming: the hand-off is the router's own few milliseconds", 0 <= results["hops"]["t_relay"] < 200, True)
    case("Wyoming: a mishearing marked Use it is fixed before Home Assistant gets it, who spoke kept (Oct 18)",
         (results["fixed"].text, results["fixed"].context.get("speaker")), ("what are my jobs", "Sam"))
    case("Wyoming: and the router knows what Oread really heard",
         (results["fixed_hops"]["oread_heard"], results["fixed_hops"]["audio_swaps"]), ("what are my chores", [("chores", "jobs")]))
    case("Wyoming: an event rebuilt keeps its type and payload", wy.rebuilt(b'{"type": "x", "data_length": 2, "payload_length": 3}\n{}abc', {"text": "hi"}),
         b'{"type": "x", "data_length": 14, "payload_length": 3}\n{"text": "hi"}abc')
    case("Wyoming: and Oread's clip and device, for the activity row (Oct 17)",
         (results["hops"]["clip"], results["hops"]["device"]), ("c1", "iris"))
    case("Wyoming: words that reached the router aren't logged as Home Assistant's", results["claimed_logged"], [])
    case("Wyoming: words that never reached the router were answered by Home Assistant itself",
         results["unclaimed"], [("iris", "what are my chores")])
    wy.ON_UNCLAIMED = None
    case("Wyoming: another device knows nobody", nobody, {})
    wy.HEARD["iris"]["time"] -= 60
    case("Wyoming: an old answer is stale", asyncio.run(speakers.lookup("iris", "what are my chores",
         {"integrations": {"oread": {"enabled": True, "source": "wyoming", "max_age_seconds": 20}}})), {"stale": True})
    case("Wyoming: off unless the source is wyoming",
         wy.wanted({"integrations": {"oread": {"enabled": True, "source": "oread"}}}), None)
    wy.HEARD["felix"] = {"text": "what's on my list", "speaker": "Owner", "time": __import__("time").time()}
    wy.noted("felix", {"text": "", "context": {"speaker": None, "label": "unknown"}})
    case("Wyoming: nothing heard (a reopened mic) keeps the last words and speaker (Oct 18)",
         (wy.HEARD["felix"]["text"], wy.HEARD["felix"]["speaker"]), ("what's on my list", "Owner"))
except ImportError:
    print("  (Wyoming skipped: pip install wyoming==1.10.2 to test the audio path)")

# ---------- Stats: is anything slow, CPU, the router's cost ----------
import time  # noqa: E402
from veil import activity as _act, resources as _res  # noqa: E402
st = _act.Activity(os.path.join(TMP, "stats.db"))
# noon UTC today, so rows "a minute ago" are today's whatever the hour (they were yesterday's just after midnight UTC)
now = (time.time() // 86400) * 86400 + 43200
for i in range(20):                                      # a month of ordinary weather answers
    st.add(time=now - (i + 1) * 86400, assistant="iris", heard="what's the weather", engine="weather_brain", ms=400, cpu_ms=5)
for i in range(3):                                       # today it's slow
    st.add(time=now - 60 - i, assistant="iris", heard="what's the weather", engine="weather_brain", ms=1500, cpu_ms=40)
st.add(time=now - 30, assistant="iris", heard="tell me a story", engine="gemini", ms=900, cpu_ms=80)
st.add(time=now - 20, assistant="iris", heard="tell me a story", engine="gemini", path="tool", ms=700, cpu_ms=10)
tr = st.route_trend(now, 0, 30, 1.5, 3)
wb = next(r for r in tr["routes"] if r["route"] == "app:weather_brain")
case("Stats: a route slower than usual today is flagged", (wb["slow"], wb["today"]["median"], wb["month"]["n"]), (True, 1500.0, 23))
case("Stats: her words after a device command are one Off-Platform route",
     [(r["route"], r["requests"]) for r in st.time_routes(now - 86400) if r["route"].startswith("off")], [("off_platform", 2)])
case("Stats: a day for each of the 30 days", (len(tr["days"]) in (30, 31), wb["by_day"][-1]), (True, 1500.0))
top = st.top_cpu(now - 7 * 86400, 10)
case("Stats: the most CPU first, one line per saying", [(x["heard"], x["count"], x["cpu_max"]) for x in top],
     [("tell me a story", 2, 80.0), ("what's the weather", 10, 40.0)])
st.add(time=now - 10, assistant="felix", heard="what's the weather", engine="weather_brain", ms=2500, cpu_ms=9)
case("Stats: one assistant's requests only", ([(r["route"], r["requests"]) for r in st.time_routes(now - 86400, assistant="felix")],
     sum(st.shares(now - 86400, 0, "iris")["where"].values())), ([("app:weather_brain", 1)], 6))
st.note_resources(now, 20.0, 50.0)
st.note_resources(now + 1, 60.0, 70.0)
r = st.resources(now + 2)["periods"]["last_hour"]
case("Stats: CPU and memory folded into the hour", (r["cpu_average"], r["cpu_busiest"], r["memory_highest"]), (40.0, 60.0, 70))
smp = _res.Sampler(None, 60)
smp._last = (time.time() - 10, _res.cpu_seconds() - 5)
case("Stats: CPU as a share of one core", round(smp.sample()[0]), 50)
# Oct 18: the 30-day usual from one summary per route per day, outlasting the log's own keep_days
_real = time.time()
sm = _act.Activity(os.path.join(TMP, "summary.db"), keep_days=2)
for i in range(10):                                      # ten days of weather answers, one a day, 400 ms
    sm.add(time=_real - (i + 3) * 86400, assistant="felix", heard="weather", engine="weather_brain", ms=400)
sm.add(time=_real - 31 * 86400, assistant="felix", heard="weather", engine="weather_brain", ms=9000)   # older than 30 days
for _ in range(3):                                       # today it's slow
    sm.add(time=_real - 5, assistant="felix", heard="weather", engine="weather_brain", ms=1500)
with sm._lock, sm._db() as _db:
    sm._prune(_db)                                       # the log trims itself (every 50 writes)
    _left = _db.execute("SELECT COUNT(*) FROM activity WHERE time < ?", (_real - 2 * 86400,)).fetchone()[0]
_t = next(r for r in sm.route_trend(_real, 0, 30, 1.5, 3)["routes"] if r["route"] == "app:weather_brain")
case("Stats: the log's own old rows are gone, but the usual still has their days (30 days, not older)",
     (_left, _t["month"]["n"], _t["today"]["n"], _t["slow"]), (0, 13, 3, True))
case("Stats: the usual reaches back to its first summarized day", sm.usual_since() is not None and sm.usual_since() < _real - 11 * 86400, True)
from veil import hadebug  # noqa: E402
from datetime import datetime as _dt, timezone as _tz  # noqa: E402
_iso = lambda t: _dt.fromtimestamp(t, _tz.utc).isoformat()   # noqa: E731
_runs = [{"pipeline": "Felix", "events": [{"type": "stt-end", "timestamp": _iso(_real - 3), "data": {"stt_output": {"text": "What's on my list?"}}},
                                          {"type": "intent-end", "timestamp": _iso(_real + 0.35)}]},
         {"pipeline": "Felix", "events": [{"type": "stt-end", "timestamp": _iso(_real - 90), "data": {"stt_output": {"text": "What's on my list?"}}},
                                          {"type": "intent-end", "timestamp": _iso(_real - 88)}]}]
case("The way back: from the answer leaving to Home Assistant done, for the run with the same words just after",
     (hadebug.back_ms(_runs, "what's on my list", _real), hadebug.back_ms(_runs, "something else", _real)), (350, None))
case("Stats: brain fleas are their own route, Wepwawet Musings",
     _act.Activity.route_of({"path": "flea", "engine": "router"}), "musings")

# ---------- Oct 15: which leg was slow (the router, the machine, the outside hop, the internet) ----------
import asyncio  # noqa: E402
from veil import netcheck  # noqa: E402
case("Which leg: the machine's load is a share of its cores", isinstance(_res.machine_load(), float), True)
_was_access = access.ACCESS
access.ACCESS = access.Access({"outbound_allowed": ["192.168.1.20"]})
_pings = []
nc = netcheck.Checker({"servers": ["1.1.1.1", "8.8.8.8"], "routes": ["off_platform"], "cooldown_minutes": 5},
                      pinger=lambda s, t: _pings.append(s) or {"1.1.1.1": 40.0, "8.8.8.8": 25.0}[s], looker=lambda s, n, t: 90.0)
case("Internet check: servers not in outbound_allowed aren't called", (nc.measure()["method"], _pings), ("not permitted", []))
access.ACCESS = access.Access({"outbound_allowed": ["1.1.1.1", "8.8.8.8"]})
got = nc.measure()
case("Internet check: the fastest server's ping", (got["ms"], got["method"], got["server"]), (25.0, "ping", "8.8.8.8"))
case("Internet check: only on the routes named", (nc.wanted("off_platform"), nc.wanted("app:donetick")), (True, False))
case("Internet check: not after an app that answered from its own memory (under min_outside_ms)",
     (nc.wanted("off_platform", 60), nc.wanted("off_platform", 450), nc.wanted("off_platform", None)), (False, True, True))


def _no_ping(s, t):
    raise PermissionError("no ping socket")


nd = netcheck.Checker({"servers": ["1.1.1.1"], "routes": ["off_platform"]}, pinger=_no_ping, looker=lambda s, n, t: 90.0)
got = nd.measure()
case("Internet check: no ping in the container, a DNS lookup to the same server", (got["ms"], got["method"], nd.can_ping), (90.0, "dns", False))
lg = _act.Activity(os.path.join(TMP, "legs.db"))
_r1 = lg.add(time=now - 5, heard="one", engine="gemini", ms=1500)
_pings.clear()
asyncio.run(nc.after("off_platform", _r1, lg))
_r2 = lg.add(time=now - 4, heard="two", engine="gemini", ms=1500)
asyncio.run(nc.after("off_platform", _r2, lg))
case("Internet check: once per cool-down; the next request carries the last check",
     (len(_pings), lg.get(_r2)["net_ms"], lg.get(_r2)["net_at"] == lg.get(_r1)["net_at"]), (2, 25.0, True))
access.ACCESS = _was_access
lg = _act.Activity(os.path.join(TMP, "legs2.db"))
for i in range(6):                                       # usual: Off-Platform 1.2 s outside, 200 ms of the router's own, the internet 30 ms
    _ri = lg.add(time=now - (i + 1) * 86400, heard="usual", engine="gemini", ms=1400, t_engine=1200, cpu_ms=100, load=20)
    lg.finish(_ri, net_ms=30.0, net_method="ping", net_at=now - (i + 1) * 86400 + 2)
for i in range(3):                                       # today: the outside hop 10 s, the internet 120 ms, the router and machine as usual
    _ri = lg.add(time=now - 60 - i, heard="tell me a story", engine="gemini", ms=10200, t_engine=10000, cpu_ms=110, load=22)
    lg.finish(_ri, net_ms=120.0, net_method="ping", net_at=now - 58 - i)
L = lg.legs(now, 0, 1.5, 3, 2.0)
off = next(r for r in L["routes"] if r["route"] == "off_platform")
case("Which leg: the outside hop is slow, the router's own work and the machine are not",
     (off["legs"]["t_engine"]["slow"], off["legs"]["own_ms"]["slow"], off["legs"]["load"]["slow"], off["legs"]["own_ms"]["today"]["median"]),
     (True, False, False, 200.0))
case("Which leg: the internet today against usual", (L["internet"]["slow"], L["internet"]["times"], L["internet"]["method"]), (True, 4.0, "ping"))
case("Which leg: the slow requests carry their check", [(x["heard"], x["net_ms"], x["net_usual"], x["net_slow"]) for x in L["slow_requests"]][:1],
     [("tell me a story", 120.0, 30.0, True)])
tr = {x["route"]: x for x in lg.time_routes(0)}
case("Where the time goes: average and all together", (tr["off_platform"]["hops"]["ms"]["mean"], tr["off_platform"]["hops"]["t_engine"]["total"]),
     (round((6 * 1400 + 3 * 10200) / 9, 1), 6 * 1200 + 3 * 10000.0))
lg.add(time=now - 1, heard="hi", engine="router", ms=40, t_speech=2000, t_stt=600)
case("Where the time goes: Oread per second of speech", {x["route"]: x for x in lg.time_routes(0)}["router"]["hops"]["stt_per_s"]["median"], 300.0)
case("The log's real span", (lg.span(0)["n"], lg.span(0)["first"] == now - 6 * 86400), (10, True))

# ---------- Oct 15: "remind me", and the reminder at a chore's due time (issue #5) ----------
import datetime as _dt  # noqa: E402
import connector as _cnd  # noqa: E402
import fields as _fl  # noqa: E402
_dsvc = dict(config.section(config.section(config.settings(), "services"), "donetick"))
_dmake = lambda: _cnd.make("donetick", _dsvc, config.settings(), lambda *a, **k: "", actions_dir=os.path.join(ROOT, "actions"),  # noqa: E731
                           connectors_dir=os.path.join(ROOT, "connectors"))
_dk = _dmake()
_at = _dt.datetime(2026, 10, 14, 11, 56)


def _chore(said):
    """What a chore said this way is added with: its reminder at the due time, and Donetick's notification."""
    flds = _dk.add_fields()
    filled = _dk.opening_extras(_fl.parse_answer(said, flds, _at), _at)
    body = _dk.body_fields(filled, _at.date())
    return ((filled.get("remind_at_due") or {}).get("value"), body.get("notification", False),
            (body.get("notificationMetadata") or {}).get("dueDate", False), sorted(filled))


case("Remind me to call the plumber at three: reminded at the due time",
     _chore("Remind me to call the plumber tomorrow at three.")[:3], (True, True, True))
case("A chore given a time is reminded at that time (remind_when_timed)",
     _chore("call the plumber tomorrow at three")[:3], (True, True, True))
case("Don't remind me keeps it off", _chore("call the plumber tomorrow at three and don't remind me")[:3],
     (False, False, False))
case("Remind me 10 minutes before: before, and at the due time",
     _chore("call the plumber tomorrow at three and remind me 10 minutes before")[3],
     ["due_date", "due_time", "remind_at_due", "remind_before"])
case("A day with no time gets no reminder of its own", _chore("call the plumber tomorrow")[:2], (None, False))
_said = "Sam is home late tonight. Remind me at 4.30 and nag me every half hour."
_f = _dk.opening_extras(_fl.parse_answer(_said, _dk.add_fields(), _at), _at)
case("A time alone means today: the time, the reminder and the nags are kept (Oct 15)",
     {k: v.get("say") for k, v in _f.items()},
     {"due_date": "today", "due_time": "4:30 pm", "remind_at_due": "remind at due", "nag": "half an hour after"})
_f = _dk.opening_extras(_fl.parse_answer("call the plumber at 9 in the morning", _dk.add_fields(), _at), _at)
case("A time already past today means tomorrow", (_f["due_date"]["say"], _f["due_time"]["say"]), ("tomorrow", "9 am"))
_f = _dk.opening_extras(_fl.parse_answer("call the plumber and nag me", _dk.add_fields(), _at), _at)
case("No day and no time: nags and reminders wait (only_if due_date)", sorted(_f), [])
_dsvc["options"] = dict(_dsvc.get("options") or {}, remind_when_timed=False)
_dk = _dmake()
case("remind_when_timed off: only when asked", (_chore("call the plumber tomorrow at three")[:2],
     _chore("Remind me to call the plumber tomorrow at three.")[:2]), ((None, False), (True, True)))

# ---------- an app's commands from its spec, and the spoken needs the router asks for ----------
from veil import openapi as _oa
_spec = {"swagger": "2.0", "paths": {
    "/chores": {"post": {"summary": "Create", "parameters": [{"in": "body", "name": "c", "required": True, "schema": {"$ref": "#/definitions/Req"}}]}},
    "/chores/{id}/do": {"post": {"summary": "Complete", "parameters": [{"in": "path", "name": "id", "required": True}]}}},
    "definitions": {"Req": {"required": ["name", "frequencyType"]}}}
_c = _oa.commands(_spec)
case("Spec: each command with what the app requires", [(c["api"], c["requires"]) for c in _c],
     [("POST /chores", ["body: name", "body: frequencyType"]), ("POST /chores/{id}/do", ["path: id"])])
_new = [_c[0], {"api": "GET /chores", "summary": "List", "requires": []}]
_new[0] = dict(_new[0], summary="Create a chore")
case("Spec: read again, each change marked", sorted((r["api"], r["mark"]) for r in _oa.compare(_c, _new)),
     [("GET /chores", "add"), ("POST /chores", "modified"), ("POST /chores/{id}/do", "deleted")])

import connector as _conn
_k = _conn.Connector.__new__(_conn.Connector)
_k.needs = {"move": {"chore": "required", "when": "required"}, "nudge": {"who": "required"}, "list": {"who": "optional"}}
_k.people = _conn.people_words({"names_in_replies": {"calls": {"Owner": [], "Beth": []}},
                                "services": {"x": {"lists": {"people": {"house": "people", "names": {"Owner": ["sam"]}}}}}})
_old = _conn.HEARD_NEEDS
_conn.HEARD_NEEDS = {"who": "person", "when": "date"}
case("Spoken needs: a required when that wasn't heard", _k.missing_need("move the gutters", "move"), "when")
case("Spoken needs: heard (a day)", _k.missing_need("move the gutters to saturday", "move"), None)
case("Spoken needs: heard (tomorrow)", _k.missing_need("move the gutters tomorrow", "move"), None)
case("Spoken needs: a required who that wasn't heard", _k.missing_need("nudge about the trash", "nudge"), "who")
case("Spoken needs: heard (a person)", _k.missing_need("nudge beth about the trash", "nudge"), None)
case("Spoken needs: optional ones never ask, and the helper's own (chore) are left to it", _k.missing_need("what's on the list", "list"), None)
_k.has_line = lambda sec: sec == "need_when"
_k.say = lambda sec, **v: f"[{sec}]"
_q = _k.ask_for("when", "move the gutters", "move")
case("Spoken needs: her question, kept to be answered", (_q["speech"], _q["ask"]), ("[need_when]", {"kind": "need", "need": "when", "said": "move the gutters", "action": "move"}))
case("Spoken needs: a need without its own line uses the shared one", _k.ask_for("recipe", "x", "toss")["speech"], "[need]")
_conn.HEARD_NEEDS = _old

# ---------- an app's people, and who each is in the house ----------
import asyncio as _aio
from veil import people_map as _pm
_spec2 = {"swagger": "2.0", "paths": {"/circles/members": {"get": {"responses": {"200": {"schema": {"type": "object",
          "additionalProperties": {"type": "array", "items": {"$ref": "#/definitions/M"}}}}}}}},
          "definitions": {"M": {"properties": {"userId": {}, "displayName": {}}}}}
case("Spec: the fields a command answers with (through a wrapper and a list)", _oa.commands(_spec2)[0]["returns"], ["userId", "displayName"])
_ppl = _pm.household({"names_in_replies": {"calls": {"owner": [], "beth": [], "son": []}}},
                     {"names": {"owner": ["sam", "me"], "son": ["sam jr"]}})
async def _call(method, path):
    return {"res": [{"userId": 1, "displayName": "Sam"}, {"userId": 2, "displayName": "Beth"}, {"userId": 3, "displayName": "Sam"}, {"userId": 4, "displayName": "Ann"}]}
_conf = {"from": "GET /circles/members", "id": "userId", "name": "displayName"}
_found = _aio.run(_pm.members(_call, _conf))
case("People: listed by the command and fields chosen", _found, [(1, "Sam"), (2, "Beth"), (3, "Sam"), (4, "Ann")])
case("People: matched by name until a map is saved", _pm.mapping(_found, _conf, _ppl), {"1": "owner", "2": "beth", "3": "owner"})
_sp = _pm.spoken(_found, dict(_conf, map={"1": "owner", "2": "beth", "3": "son", "4": ""}), _ppl)
case("People: two people named Sam, told apart by the map", (_sp["sam"], _sp["owner"], _sp["sam jr"], _sp["son"]), ((1, "Sam"), (1, "Sam"), (3, "Sam"), (3, "Sam")))
case("People: someone mapped to nobody isn't sayable", "ann" in _sp, False)
_sp2 = _pm.spoken(_found, dict(_conf, map={"1": "owner"}), _ppl)
case("People: a new app person not in the map yet goes by their own name, unless a house name", ("ann" in _sp2, _sp2.get("sam")), (True, (1, "Sam")))
case("People: no command chosen, no people", _aio.run(_pm.members(_call, {})), [])

# ---------- the Wepwawet standard: how an app is called, from its spec ----------
from veil import apps as _apps
case("Apps: Swagger 2's base path and its header key", (_apps.base_of("http://h:2021/swagger/doc.json", {"basePath": "/api/v1"}),
     _apps.auth_of({"securityDefinitions": {"K": {"type": "apiKey", "in": "header", "name": "secretkey"}}})),
     ("http://h:2021/api/v1", {"in": "header", "name": "secretkey", "prefix": ""}))
case("Apps: OpenAPI 3's server, and the Wepwawet section's auth first", (_apps.base_of("https://h:10311/openapi.json", {"servers": [{"url": "/v2"}]}),
     _apps.auth_of({"x-wepwawet": {"auth": {"in": "header", "name": "Authorization", "prefix": "Bearer "}}, "components": {"securitySchemes": {}}})["prefix"]),
     ("https://h:10311/v2", "Bearer "))
case("Apps: no server or base path: the spec's own address", _apps.base_of("http://h:8765/openapi.json", {}), "http://h:8765")
case("Apps: the standard's way names and the router's own", (_apps.way_to_setting("who_spoke", "api"), _apps.way_from_setting("who_spoke", "home_assistant")), ("oread", "sensor"))
case("People: the voices are the household, with each app's other names", sorted(_ppl), ["beth", "owner", "son"])
case("Spoken names: a voice and the other names an app's card gives it", (_k.people.get("sam"), _k.people.get("beth")), ("Owner", "Beth"))

# ---------- the shared connector: names said, the verb before the noun, actions with no app code ----------
import asyncio as _aio2
import connector as _cn
_s = config.settings()
_k2 = _cn.make("donetick", _s["services"]["donetick"], _s, lambda sec, **v: f"[{sec}] " + " ".join(f"{a}={b}" for a, b in v.items()),
                    actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"),
                    has_line=lambda sec: False)
for said, want in [("Add a chore, paint the back of the house on Thursday.", "Paint the back of the house"),
                   ("add a chore paint the back of the house on thursday", "Paint the back of the house"),
                   ("Um, add a chore for Beth, clean the gutters, uh, by Friday.", "Clean the gutters"),
                   ("Can you add a chore? Mow the lawn this Saturday morning.", "Mow the lawn"),
                   ("Remind me to call the plumber tomorrow at 3.", "Call the plumber"),
                   ("add a chore pick up beth from school friday", "Pick up beth from school"),
                   ("Add paint the back of the house to the house project on Thursday at 3.", "Paint the back of the house"),
                   ("Add a chore, take the trash out every Tuesday.", "Take the trash out"),
                   ("put milk on my list", "Milk"),
                   # Oct 17, from the log: the speaker's own words before the action aren't the name
                   ("I need to add a chore.", ""),
                   ("I need to add the chore to get Newton's Medicine at Tractor Supply.", "Get Newton's Medicine at Tractor Supply"),
                   ("Can you add to the chore list to get Newton's?", "Get Newton's"),
                   ("Iris, I need you to find the chore.", ""),
                   ("I want to add mow the lawn", "Mow the lawn")]:
    case(f"Names said: {said}", _k2.spoken_value(said, "add"), want)
# the voice map has a create_project too: "create" and the noun "project"
_k2.map["actions"]["create_project"] = {"api": "POST /projects", "verbs": {"create": {"share": 0.9, "basis": "yours"},
                                        "new project": {"share": 0.9, "basis": "yours"}}, "objects": []}
_k2.hand.setdefault("actions", {})["create_project"] = {"api": "POST /projects", "needs": {"name": "required"}}
_k2.needs["create_project"] = {"name": "required"}
case("The verb decides between actions that name the same noun", _k2.pick_action("Create a project called Voice Test")[0], "create_project")
case("The noun alone still lists", _k2.pick_action("What projects do I have")[0], "projects")
case("Names said: a project called", _k2.spoken_value("Create a project called Voice Test.", "create_project"), "Voice Test")
_sent = []
async def _fake_api(method, path, **kw):
    _sent.append((method, path, kw.get("json")))
    return {"res": 9}
async def _nothing():
    return None
_k2.api = _fake_api
_k2.refresh = _nothing
_r = _aio2.run(_k2.run_generic("Create a project called Voice Test.", "create_project"))
case("No app code: the router sends the command, the spec's required name filled from what was said",
     (_sent[-1], _r["speech"]), (("POST", "/projects", {"name": "Voice Test"}), "[generic_done] name=Voice Test action=create project"))
_k2.hand["actions"]["create_project"]["needs"] = {}
_k2.needs["create_project"] = {}
_r = _aio2.run(_k2.run_generic("Create a project called Voice Test.", "create_project"))
case("No app code: a field the spec requires that no spoken need fills is said, not sent", (len(_sent), _r["speech"].split()[0]), (1, "[generic_missing]"))

# ---------- an app that takes the words as said: the plain connector, its one door (piece 2) ----------
from veil import access as _acc
# Oct 20: a failed question isn't told "I didn't change anything" when the app has a reading line
_k3 = _cn.make("donetick", _s["services"]["donetick"], _s, lambda sec, **v: sec,
               actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"),
               has_line=lambda sec: sec == "service_error_read")
case("a failed read: its own line; a failed change: the changed-nothing line",
     (_k3.error_line(_k3.changes("list")), _k3.error_line(_k3.changes("add"))), ("service_error_read", "service_error"))
case("...and an app without a reading line keeps the one line", _k2.error_line(False), "service_error")
_wb = _cn.make("weather_brain", {"kind": "contract", "url": "http://brain/ask", "timeout": 3}, _s, lambda *a, **k: "",
               actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"))
_asked = []
class _Resp:
    def raise_for_status(self):
        return None
    def json(self):
        return {"status": "answered", "speech": "Sunny."}
class _Client:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url, params=None, headers=None):
        _asked.append((url, params, headers))
        return _Resp()
_had_client = _acc.client
_acc.client = lambda timeout: _Client()
_wb.wepwawet = {"role": "answers", "answers": {"door": "GET /ask", "said": "q", "context": "before"}}
_r = _aio2.run(_wb.handle("What about Sunday?", ["What's the weather Saturday?"]))
_acc.client = _had_client
case("The weather brain on the plain connector: it takes the words as said, through its door's own names",
     (type(_wb).__name__, _wb.answers(), _r["speech"], _asked[-1]),
     ("Connector", True, "Sunny.", ("http://brain/ask", [("q", "What about Sunday?"), ("before", "What's the weather Saturday?")], {})))
case("An app that takes the words as said has no actions to decide with", (_wb.pick_action("what's the weather")[0], _wb.names_thing("rain")), (None, False))

# ---------- an app we didn't write, reached as its spec says (Oct 18: Liturgical calendar) ----------
import datetime as _dtl
from veil import openapi as _oa2, apps as _ap
_part = {"type": "object", "properties": {"litcal": {"type": "array", "items": {"anyOf": [{"$ref": "#/definitions/E"}, {"$ref": "#/definitions/V"}]}},
                                          "messages": {"type": "array", "items": {"type": "string"}}},
         "definitions": {"E": {"properties": {"event_key": {}, "name": {}, "date": {}, "holy_day_of_obligation": {}}},
                         "V": {"properties": {"event_key": {}, "is_vigil_mass": {}}}}}
_sp3 = {"servers": [{"url": "https://cal/api/dev"}, {"url": "https://cal/api/v5"}],
        "paths": {"/calendar/nation/{calendar_id}/{year}": {"get": {"parameters": [
            {"in": "path", "name": "calendar_id", "required": True}, {"in": "path", "name": "year", "required": True},
            {"in": "query", "name": "year_type"}], "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "./LitCal.json"}}}}}}}}}
_found = _oa2.file_refs(_sp3, "https://cal/api/v5/schemas/openapi.json")
_oa2.file_refs(_part, "https://cal/api/v5/schemas/LitCal.json", part=True)
_sp3["x-parts"] = {"https://cal/api/v5/schemas/LitCal.json": _part}
_c3 = _oa2.commands(_sp3)[0]
case("A spec in several files: the part it points at is read, so the fields of each thing in its list are known",
     (sorted(_found), _c3["returns"][:2], {"name", "date", "holy_day_of_obligation", "is_vigil_mass"} <= set(_c3["returns"])),
     (["https://cal/api/v5/schemas/LitCal.json"], ["litcal", "messages"], True))
class _R:
    def __init__(self, text, kind):
        self.text, self.headers = text, {"content-type": kind}
case("A spec as JSON or YAML, and a plain error for neither",
     (_ap.spec_doc(_R("openapi: 3.0.3\npaths: {}", "application/vnd.oai.openapi; charset=utf-8"), "X")["openapi"],
      _ap.spec_doc(_R('{"openapi": "3.1.0"}', "application/json"), "X")["openapi"],
      _ap.spec_doc(_R("swagger: '2.0'", "text/plain"), "X")["swagger"]),
     ("3.0.3", "3.1.0", "2.0"))
raises("A spec that's neither", lambda: _ap.spec_doc(_R("<html>nope</html>", "text/html"), "X"))
case("Every parameter a command takes, required or not", _c3["params"], ["path: calendar_id", "path: year", "query: year_type"])
case("Of several servers, the one at the address you gave the app", (_ap.base_of("https://cal/api/v5/schemas/openapi.json", _sp3, "https://cal/api/v5"),
     _ap.base_of("https://cal/api/v5/schemas/openapi.json", _sp3)), ("https://cal/api/v5", "https://cal/api/dev"))
_wb.commands = {"GET /CALENDAR/NATION/{CALENDAR_ID}/{YEAR}": _c3}
_wb.svc["options"] = {"calendar_id": "US", "year_type": "CIVIL", "loud": True}
case("A command's address filled from its options and today's year, and the query it takes added",
     _wb.filled("GET", "/calendar/nation/{calendar_id}/{year}"), (f"/calendar/nation/US/{_dtl.date.today().year}", {"year_type": "CIVIL"}))
case("A path filled elsewhere still gets its command's query", _wb.filled("GET", "/calendar/nation/US/2027", "/calendar/nation/{calendar_id}/{year}"),
     ("/calendar/nation/US/2027", {"year_type": "CIVIL"}))
_wb.svc["options"] = {}
case("A wrapper with two lists: the list of things (litcal), not its messages",
     __import__("veil.rules", fromlist=["_as_list"])._as_list({"litcal": [{"name": "All Saints"}], "messages": ["a", "b", "c"]}),
     [{"name": "All Saints"}])

# ---------- user rules: an app's commands chained with the router's steps (veil/rules.py) ----------
from veil import rules as _ru
_chores = [{"id": 1, "name": "Mow Lawn", "assignStrategy": "", "updatedAt": "t1"},
           {"id": 2, "name": "Go to the store"}, {"id": 3, "name": "Clean the gutters"},
           {"id": 4, "name": "Wash the car"}, {"id": 5, "name": "Wash the dog"}]
_sent = []
_projects = [{"id": 6, "name": "House", "color": "red"}, {"id": 7, "name": "Voice Tech", "color": "blue"}]
async def _rule_api(method, path, **kw):
    _sent.append((method, path, kw.get("json")))
    if path == "/chores":
        return _chores
    if path == "/projects":
        return _projects
    if path.startswith("/chores/"):
        return dict(next(c for c in _chores if str(c["id"]) == path.rsplit("/", 1)[1]))
    return {}
_k2.api = _rule_api
_k2.say = lambda sec, **v: f"[{sec}] " + " ".join(f"{a}={b}" for a, b in v.items())
case("User rules: a rule is spoken like an action, and changes something", (_k2.pick_action("rename mow lawn to cut the grass")[0],
     _k2.changes("rename")), ("rename", True))
_r = _aio2.run(_k2.run_rule("rename mow lawn to cut the grass", "rename"))
case("User rules: a sure match runs every step (fresh copy, the new name, an empty field filled)",
     (_sent[-1], _r["speech"]), (("PUT", "/chores", {"id": 1, "name": "Cut the grass", "assignStrategy": "keep_last_assigned", "updatedAt": "t1"}),
                                 "Mow Lawn is now Cut the grass."))
_sent.clear()
_r = _aio2.run(_k2.run_rule("rename go to the store to rename the shop", "rename"))
case("User rules: Search tries each Until word; the cut that matches best wins (the rule's word only once)", (_sent[-1][2]["name"], _r["speech"]), ("Rename the shop", "Go to the store is now Rename the shop."))
_sent.clear()
_r = _aio2.run(_k2.run_rule("rename mow lawns pest to cut the grass", "rename"))
case("User rules: a word said that the item lacks: Confirm asks, nothing sent",
     (_r["ask"]["mode"], _r["speech"], [m for m, *_ in _sent]), ("confirm", "[rule_confirm] item=Mow Lawn", ["GET"]))
_st, _stop = _ru.resume(dict(_r["ask"]), "yes", lambda w: "yes" if w == "yes" else "no" if w == "no" else None, None, ["yes"], 8)
_r2 = _aio2.run(_k2.run_rule("rename mow lawns pest to cut the grass", "rename", _st))
case("User rules: yes goes on from the step after Confirm", (_sent[-1][0], _r2["speech"]), ("PUT", "Mow Lawn is now Cut the grass."))
case("User rules: no stops it", _ru.resume(dict(_r["ask"]), "no", lambda w: "no", None, ["no"], 8), (None, "no"))
_sent.clear()
_r = _aio2.run(_k2.run_rule("rename wash", "rename"))
case("User rules: two fit equally: she asks which", (_r["ask"]["mode"], [c["name"] for c in _r["ask"]["choices"]], _r["speech"][:13]),
     ("which", ["Wash the car", "Wash the dog"], "[thing_which]"))
_st, _ = _ru.resume(dict(_r["ask"]), "the dog one", lambda w: None, lambda a, c: c[1], ["dog", "one"], 8)
_r2 = _aio2.run(_k2.run_rule("rename wash", "rename", _st))
case("User rules: the pick goes on; no new name said: Ask asks", (_r2["ask"]["mode"], _r2["speech"]), ("ask", "What should I call it?"))
_st, _ = _ru.resume(dict(_r2["ask"]), "bathe the dog", lambda w: None, None, ["bathe", "the", "dog"], 8)
_r3 = _aio2.run(_k2.run_rule("rename wash", "rename", _st))
case("User rules: the answer is the value", (_sent[-1][2]["id"], _sent[-1][2]["name"]), (5, "Bathe the dog"))
_r = _aio2.run(_k2.run_rule("rename paint the fence to x", "rename"))
case("User rules: below Match's Ask %: not found, nothing sent", (_r["speech"], _sent[-1][0]), ("[rule_not_found] action=rename", "GET"))
case("User rules: a rule checked before it's saved", (_ru.check({"steps": [{"call": "GET /chores"}, {"match": {"act": 40, "ask": 60}}]}),
     _ru.check({"steps": [{"call": "GET /nothing"}]}, {"GET /CHORES"}), _ru.check({"steps": [{"ask": {}}]})),
     ("step 2: Match's Ask % must be 0 to 100 and no more than its Act %", "step 1: GET /nothing isn't one of the app's commands (Commands tab)",
      "step 1: Ask needs the value's name, one word (new_name)"))
case("User rules: a rule's words heard by their stems (Oread heard renamed)", _k2.pick_action("Renamed mow lawn to cut the grass")[0], "rename")
case("User rules: a rule that needs a noun wins when it's said, and only then",
     (_k2.pick_action("rename the house project to home")[0], _k2.pick_action("rename mow lawn to the house")[0]), ("rename_project", "rename"))
_sent.clear()
_r = _aio2.run(_k2.run_rule("rename the house project to home", "rename_project"))
case("User rules: rename a project: its Ignore words, a copy picked out of the list, the command's {id}",
     (_sent[-1], _r["speech"], "chore" in _r), (("PUT", "/projects/6", {"id": 6, "name": "Home", "color": "red"}), "The project House is now Home.", False))
_r = _aio2.run(_k2.run_rule("rename that to bathe the dog", "rename", None, {"last_chore": {"id": 5, "name": "Wash the dog", "action": "add"}}))
case("User rules: \"rename that\" is the chore she last named, and it's remembered under its new name",
     (_sent[-1][1], _sent[-1][2]["id"], _sent[-1][2]["name"], _r["chore"]), ("/chores", 5, "Bathe the dog", {"id": 5, "name": "Bathe the dog", "action": "rename"}))
_r = _aio2.run(_k2.run_rule("rename it to bathe the dog", "rename"))
case("User rules: \"rename it\" with nothing named lately: she asks for its name", _r["speech"], "[rule_no_last] action=rename")
# Oct 18, piece 3: the chore just added, by any way of pointing back at it; a correction opening it
_wd = {"last_chore": {"id": 5, "name": "Wash the dog", "action": "add", "topic": "chores"}}
_got = []
for _said in ("Call it bathe the dog.", "It should be bathe the dog.", "No, rename it to bathe the dog.",
              "That's wrong. It should be bathe the dog.", "Rename the one you just added to bathe the dog.",
              "Change the name to bathe the dog."):
    _sent.clear()
    _r = _aio2.run(_k2.run_rule(_said, "rename", None, _wd))
    _got.append((_sent[-1][2]["id"], _sent[-1][2]["name"]) if _sent and _sent[-1][0] == "PUT" else _r.get("speech"))
case("User rules: call it, it should be, a correction, the one you just added, change the name to: the chore just added",
     _got, [(5, "Bathe the dog")] * 6)
case("User rules: those openings are the rule's, a correction's own words aside",
     [_k2.rule_opening(x) for x in ("No, rename it to bathe the dog.", "Call it bathe the dog.", "That's wrong. It should be X.", "No.")],
     ["rename", "rename", "rename", None])
case("User rules: about the chore she last named, or not",
     [_k2.about_last("rename", x) for x in ("rename that to x", "call it x", "rename the one you just added to x", "rename mow lawn to x")],
     [True, True, True, False])
_r = _aio2.run(_k2.run_rule("Call it bathe the dog.", "rename"))
case("User rules: call it, with nothing named lately: she asks for its name", _r["speech"], "[rule_no_last] action=rename")
_chores.append({"id": 11, "name": "Buy single whole faucet"})
_sent.clear()
_r = _aio2.run(_k2.run_rule("Rename by single hole faucet to install the faucet.", "rename"))
_chores.pop()
case("User rules: Search by sound too (the voice map's sound_alike): found, and she checks first",
     (_r.get("ask", {}).get("mode"), (_r.get("ask", {}).get("state", {}).get("item") or {}).get("id"), [x for x in _sent if x[0] != "GET"]),
     ("confirm", 11, []))
_had = _k2.has_line
_k2.has_line = lambda sec: sec == "series_offer_rule"
case("Her offer after an add names the user rules on the thing just added", _k2.rule_offers(), ["[series_offer_rule] word=rename"])
_k2.has_line = _had
import series as _ser  # noqa: E402
case("The series offers it last", _ser.start("Wash the dog", "chore", {"due_date": {"type": "date", "kind": "extra", "offer": "a due date"}}, {},
     lambda sec, **v: v.get("offers"), more=["rename it"])[0], "a due date, or rename it")
_ll = {"last_list": {"app": "donetick", "ids": [7, 8, 9, 10]}}
case("By its place in the list she read: number 3, #2, the third one, mark 4 done, number three; another app's list, or a name: no",
     [_k2.position(x, _ll) for x in ("mark number 3 done", "mark #2 done", "mark the third one done", "mark 4 done",
                                     "mark number three done", "mark mow lawn done")] + [_k2.position("mark number 3 done", {"last_list": {"app": "x", "ids": [1, 2, 3]}})],
     [9, 8, 9, 10, 9, None, None])
# Oct 17: find (Beth's "can you find the camera chore?"): a Response says the matched item's own fields
import datetime as _dtm
_due = (_dtm.datetime.now().astimezone() + _dtm.timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
_chores[2]["nextDueDate"] = _due.isoformat()
case("Find: the starting copy's find rule is spoken as itself", (_k2.pick_action("can you find the gutters chore")[0],
     _k2.pick_action("when is clean the gutters due")[0], _k2.changes("find")), ("find", "find", False))
_r = _aio2.run(_k2.run_rule("can you find the gutters chore", "find"))
case("Find: the chore and when it's due, said as a day and time", _r["speech"] in
     ("Clean the gutters is due tomorrow at 1 pm.", "Clean the gutters, due tomorrow at 1 pm."), True)
_r = _aio2.run(_k2.run_rule("find the mow lawn chore", "find"))
case("Find: a chore with no due date gets the empty line", _r["speech"], "Mow Lawn has no due date.")
_r = _aio2.run(_k2.run_rule("find the cure clean the gutters", "find"))
case("Find: the whole name with a misheard word beside it answers at once (extra words ignored)", "Clean the gutters" in _r["speech"] and "ask" not in _r, True)
_r = _aio2.run(_k2.run_rule("find wash the", "find"))
case("Find: two fit alike: which one", _r["ask"]["mode"], "which")
case("Find: 'what time is X due' is a find", _k2.pick_action("what time is clean the gutters due")[0], "find")
_r = _aio2.run(_k2.run_rule("what is the due date on that chore", "find", None, {"last_chore": {"id": 3, "name": "Clean the gutters", "action": "add"}}))
case("Find: 'that chore' is the one she last named", "Clean the gutters" in _r["speech"], True)
case("Find: a Response's fields and empty lines are settings the check knows",
     _ru.check({"steps": [{"call": "GET /chores"}, {"response": {"lines": ["{item} {due}"], "fields": {"due": "nextDueDate"}, "empty_lines": ["x"]}}]}), None)
case("Find: a date field said as a day, its time only when it has one",
     (_ru._spoken("2026-10-20T00:00:00", _dtm.datetime(2026, 10, 17).astimezone()), _ru._spoken("Voice Tech"), _ru._spoken(3)),
     ("Tuesday", "Voice Tech", "3"))
del _chores[2]["nextDueDate"]
_k2.api = _fake_api

# ---------- brain fleas: the household's small true facts (veil/fleas.py, learn/fleas.yaml) ----------
from veil import fleas as _fl
case("Fleas: ways of asking with choices", _fl.expand("who is {speaking | talking} {to you | }"),
     ["who is speaking to you", "who is speaking", "who is talking to you", "who is talking"])
_F = _fl.Fleas(filler=["um", "uh", "hey"]).fresh()
case("Fleas: the starting copy's fleas load", sorted(_F.rules), ["add_flea", "change_flea", "device_who_is_speaking_to_you", "forget_flea", "list_fleas"])
case("Fleas: found by how closely it fits, its words opening it, or its key words",
     [_F.find(x)[0] for x in ["Who is talking?", "hey, who's speaking to you", "Who am I?", "add a brain flea we only buy pizza from Sal's",
                              "change the pizza flea to we get it from Dominos", "forget the pizza flea", "What's the capital of France?",
                              "who am i supposed to call for a ride"]],
     ["device_who_is_speaking_to_you", "device_who_is_speaking_to_you", "device_who_is_speaking_to_you", "add_flea",
      "change_flea", "forget_flea", None, None])
# Oct 17, night: the ways people really ask (the starting copy's never_count and add_flea words)
case("Fleas: adding, said the way people say it",
     [_F.find(x)[0] for x in ["Can you add a brain flea? We only buy pizza from Sal's.", "I want to add a brain flea", "Create a brain flea",
                              "Make brain flea", "Remember that we only buy pizza from Sal's", "Do you remember that song?",
                              "Change the pizza flea to Dominos"]],
     ["add_flea", "add_flea", "add_flea", "add_flea", "add_flea", None, "change_flea"])
_H = _fl.House(_F, lambda sec, **v: f"[{sec}]" + "".join(f" {a}={b}" for a, b in v.items()), lambda ask: "[thing_which]")
def _who(score, label="known"):
    _H.speaker = {"own": "Alexandra", "nicknames": ["Dear pimple."], "score": score, "known": label == "known"}
    return _aio2.run(_ru.run(_H, "device_who_is_speaking_to_you", "who is talking", None, {}))["speech"]
case("Fleas: Who spoke at or above Sure: their own name, not a nickname", ("Alexandra" in _who(0.74), "pimple" in _who(0.74)), (True, False))
case("Fleas: between Hedge and Sure: she thinks so", _who(0.65), "[rule_who_hedge] speaker=Alexandra")
case("Fleas: below Hedge (Beth heard as Allie at 0.56), not known, or nobody: a polite way out, never a name",
     (_who(0.56), _who(0.9, "maybe"), _aio2.run(_ru.run(_H, "device_who_is_speaking_to_you", "who", None, {}))["speech"] if not setattr(_H, "speaker", None) else ""),
     ("[rule_who_unsure]", "[rule_who_unsure]", "[rule_who_unsure]"))
_H.rules["device_who_is_speaking_to_you"]["steps"][0] = {"who_spoke": {"name": "nickname", "unsure": "Not a clue."}}
case("Fleas: a nickname when the step asks, its period dropped; its own way-out line (one line from before still reads)",
     (any(x in _who(0.8) for x in ("pimple..", "pimple. t", "pimple.,")), "Dear pimple" in _who(0.8), _who(0.3)), (False, True, "Not a clue."))
_H.speaker = None
_said = "Add a brain flea, we only buy pizza from Sal's."
_r = _aio2.run(_ru.run(_H, "add_flea", _said, None, {}))
case("Fleas: a voice add is read back first, the fact as it was said", (_r["ask"]["mode"], _r["speech"]),
     ("confirm", "I'll remember: We only buy pizza from Sal's. Right?"))
case("Fleas: a fact after 'brain flea that' leaves the 'that' out (Oct 17)",
     _aio2.run(_ru.run(_H, "add_flea", "Add a brain flea that we only buy pizza at Sal's.", None, {}))["speech"],
     "I'll remember: We only buy pizza at Sal's. Right?")
_yes = lambda w: "yes" if w == "yes" else "no" if w == "no" else None
_st, _ = _ru.resume(dict(_r["ask"]), "yes", _yes, None, ["yes"], 8)
_r = _aio2.run(_ru.run(_H, "add_flea", _said, _st, {}))
_name, _score, _how = _F.find("Where do we get pizza?")
case("Fleas: added on yes; asking about its nouns finds it", (_r["speech"] in ("Got it.", "I'll remember that."), _name, _how),
     (True, "pizza_sal", "all its key words heard"))
_r = _aio2.run(_ru.run(_H, _name, "Where do we get pizza?", None, {}))
case("Fleas: she says the fact back", _r["speech"], "We only buy pizza from Sal's.")
case("Fleas: the built-in ones aren't listed for voice changes", [x["id"] for x in _F.items()], ["device_who_is_speaking_to_you", "pizza_sal"])
# Oct 18: "What brain fleas do you have?" reads them, a list the router reads out a few at a time
case("Fleas: asked what she remembers, the list flea", (_F.find("What brain fleas do you have?")[0], _F.find("What do you remember?")[0]),
     ("list_fleas", "list_fleas"))
_r = _aio2.run(_ru.run(_H, "list_fleas", "What brain fleas do you have?", None, {}))
case("Fleas: it answers with their names as a list (the built-in ones left out)", (_r["speech"], _r.get("items")),
     ("I remember {items}.", ["who is speaking", "pizza sal"]))
_said = "change the pizza flea to we get pizza from Dominos"
_r = _aio2.run(_ru.run(_H, "change_flea", _said, None, {}))
_st, _ = _ru.resume(dict(_r["ask"]), "yes", _yes, None, ["yes"], 8)
_r2 = _aio2.run(_ru.run(_H, "change_flea", _said, _st, {}))
case("Fleas: changed by voice after a check", (_r["speech"], _aio2.run(_ru.run(_H, "pizza_sal", "pizza?", None, {}))["speech"]),
     ("Change the flea about pizza sal?", "We get pizza from Dominos."))
_r = _aio2.run(_ru.run(_H, "forget_flea", "forget the pizza flea", None, {}))
_st, _ = _ru.resume(dict(_r["ask"]), "yes", _yes, None, ["yes"], 8)
_aio2.run(_ru.run(_H, "forget_flea", "forget the pizza flea", _st, {}))
case("Fleas: forgotten by voice after a check (its new title), the file's comments kept", (_r["speech"], _F.find("Where do we get pizza?")[0], open(_fl.FILE).read().startswith("# learn/fleas.yaml")),
     ("Forget the flea about pizza dominos?", None, True))
case("Fleas: who may change them: only the voices named, Oread sure", (_F.may_change(None), _F.may_change("Beth"), _F.changes("add_flea"),
     _F.changes("device_who_is_speaking_to_you")), (False, False, True, False))
case("Rules: Say is Response now; an older say: still reads", _ru.kind_of({"say": {"line": "Done."}}), ("response", {"lines": ["Done."]}))
_G = _fl.Fleas()
_G.fresh = lambda: _G          # this test's own fleas, not the file's
_G._build({"match_at": 0.8, "fleas": {"rude": {"words": ["{that is | that's} {so | very | } rude", "not nice", "that isn't very nice"],
                                                "steps": [{"response": {"lines": ["x"]}}]}}})
case("Fleas: yes and no must agree (a compliment never gets the that's-rude flea)",
     [_G.find(t)[0] for t in ["That isn't very nice", "That was not nice", "That is very nice", "That's so rude", "That is so nice"]],
     ["rude", "rude", None, "rude", None])
from veil import mishearings as _mh
case("Swaps: the starting copy's brain flea mishearings",
     [_mh.swap(x)[0] for x in ["Add a brain's lake, we only buy pizza", "add a Brainflea", "Add a frame layer", "add a brain fleet"]],
     ["Add a brain flea, we only buy pizza", "add a brain flea", "Add a brain flea", "add a brain flea"])
_mh.use("grainsplate", "brain flea")
case("Swaps: a difference marked Use it is swapped before deciding, whole words only",
     (_mh.swap("Add a grainsplate, we only buy pizza"), _mh.swap("the grain is wet")[1], _mh.swap("GRAINSPLATE please")[0]),
     (("Add a brain flea, we only buy pizza", [("grainsplate", "brain flea")]), [], "brain flea please"))
_mh.use("grainsplate", "brain flea", on=False)
case("Swaps: stopped, it's heard as said again", _mh.swap("Add a grainsplate")[1], [])
_mh.use("who taught you three", "who taught you that")
case("Swaps: a phrase fix swaps only the whole run, never the word alone",
     (_mh.swap("Who taught you three?")[0], _mh.swap("set a timer for three minutes")[1], _mh.swap("who taught you three languages")[0]),
     ("who taught you that?", [], "who taught you that languages"))
_mh.use("who taught you three", None, on=False)
case("Rules: a setting the step doesn't have is caught (the helper changed?)", _ru.check({"steps": [{"match": {"act": 85, "wobble": 1}}]}),
     "step 1: Match has no setting wobble (the helper changed?)")

from veil import spoken as _sp
case("A list item inside the chore's own name isn't that item (the House project)",
     (_sp.said_outside("Add a chore. Paint the back of the house on Thursday.", "Paint the back of the house", "House"),
      _sp.said_outside("Add paint the back of the house to the house project on Thursday", "Paint the back of the house", "House")), (False, True))

_k2.cache["items"] = [{"id": 1, "name": "Paint the back of the house"}, {"id": 2, "name": "Clean the gutters"}]
case("An app's own thing named (voice script line 9): painting the house is a chore it has; the couch isn't",
     (_k2.names_thing("Move painting the house to Saturday."), _k2.names_thing("move the couch to saturday")), (True, False))

_k2.match_min = 0.6
_k2.cache["items"] = [{"id": 3, "name": "Mow the lawn"}, {"id": 4, "name": "Take the trash out"},
                              {"id": 5, "name": "Put the trash out"}]
case("Voice script 10 and 11: finished mowing finds Mow the lawn; skip taking the trash finds Take the trash out",
     (_k2.find_item("I finished mowing the lawn.", _k2.cache["items"], {"finished"})[0]["id"],
      _k2.find_item("Skip taking the trash out.", _k2.cache["items"], {"skip"})[0]["id"]), (3, 4))
_sent.clear()
_r = _aio2.run(_k2.do_undo("Undo that.", [], {"last_chore": {"id": 4, "name": "Take the trash out", "action": "skip"}}))
case("Undo: a skip, which Donetick refuses to undo (voice script 12): she says so, nothing sent",
     (len(_sent), _r["speech"].split()[0]), (0, "[undo_unsupported]"))
_r = _aio2.run(_k2.do_undo("Undo that.", [], {"last_chore": {"id": 3, "name": "Mow the lawn", "action": "complete"}}))
case("Undo: a completion, which the voice map says the app's undo reverses, is sent",
     (_sent[-1][:2], _r["speech"].split()[0]), (("POST", "/chores/3/undo"), "[undone]"))
_r = _aio2.run(_k2.do_undo("Undo that.", [], {"last_chore": {"id": 4, "name": "Take the trash out", "action": "move"}}))
case("A move the app's undo doesn't reverse: she says so, nothing sent", (len(_sent), _r["speech"].split()[0]), (1, "[undo_unsupported]"))

# ---------- the voice map counts without a build ----------
_built = {"actions": {"list": {"api": "GET /chores", "verbs": {"what": {"share": 0.98, "basis": "measured"}, "old": {"share": None, "basis": "yours"}}},
                      "gone": {"api": "GET /gone", "verbs": {"x": {"basis": "measured"}}}}}
_hand = {"actions": {"list": {"api": "GET /chores", "words": ["what", "show me"]},
                     "create_project": {"api": "POST /projects", "words": ["new project"], "objects": ["project"]}}}
_vm = _cn.with_voice_map(_built, _hand)["actions"]
case("Voice map without a build: its new action counts, with your words and its objects",
     (_vm["create_project"]["api"], _vm["create_project"]["verbs"]["new project"]["basis"], _vm["create_project"]["objects"]), ("POST /projects", "yours", ["project"]))
case("Voice map without a build: measured words kept, your new word added, a word you removed gone",
     sorted((w, v["basis"]) for w, v in _vm["list"]["verbs"].items()), [("show me", "yours"), ("what", "measured")])
case("Voice map without a build: an action you took out of the voice map can't be spoken", "gone" in _vm, False)

# ---------- the verb the request hangs on (veil/spoken.py), Oct 17 ----------
_strip = _cn.STRIP_AWAY | _cn.FILLER
case("Main verb: past the speaker's own words, or none",
     [_sp.main_verb(x, _strip) for x in ("I need you to find the chore.", "I need to add milk.", "What's on my list?",
                                         "Delete the path.", "Can you add a chore? Mow the lawn this Saturday.")],
     ["find", "add", None, "delete", "add"])
case("Real verb: only strip_away words picked add, so the sentence's own verb decides (none of Donetick's)",
     _k2.real_verb("I need you to hide the chore.", "add", ["to", "need"]), (None, "its own verb 'hide' is none of donetick's actions"))
case("Real verb: a user rule's word counts as its action's (find, Oct 17 evening)",
     _k2.real_verb("I need you to find the chore.", "add", ["to", "need"]), ("find", "its own verb 'find' is find's"))
case("Real verb: a word of several (check off) needs all of it said ('check my list' isn't complete)",
     _k2.real_verb("Check the dishes.", "list", [])[0], None)
case("Never by voice: the voice map's words, she says it's the app's page", (_k2.never_by_voice("Delete the chore you just added."),
     _k2.never_by_voice("Add a chore to tidy up")), ("delete", None))
case("Asked of her: 'can you mark...' is a request, 'thank you' isn't",
     [_sp.asked_of_you(x) for x in ("can you mark the chore spray weeks complete", "Thank you.", "Paint the fence")], [True, False, False])
case("Real verb: an action's own word was heard, nothing changes", _k2.real_verb("I need to add milk.", "add", ["to", "add", "need"]), ("add", None))
case("Real verb: a verb of another action moves it there", _k2.real_verb("I need you to skip the trash.", "add", ["to", "need"])[0], "skip")

# ---------- which of an app's things was meant (veil/match.py), with her questions ----------
from veil import match as _m  # noqa: E402
_never = set(_k2.stop) | {"beth", "owner"}
_ch = [{"id": 1, "name": "Mow Lawn", "group": "House"}, {"id": 2, "name": "Mow the lawn test", "group": "Voice Tech"},
       {"id": 3, "name": "Take the trash out", "group": "Voice Tech"}, {"id": 4, "name": "Put the trash out", "group": "House"},
       {"id": 6, "name": "Paint the back of the house", "group": "Voice Tech"}, {"id": 7, "name": "Clean the gutters", "group": "Voice Tech"}]
_f = lambda said, things=_ch: _m.find(said, things, _never, 0.6, group_first="Voice Tech")  # noqa: E731
case("Match: a word you said that a chore lacks counts against it (the test chore, never Mow Lawn)",
     (_f("I finished mowing the lawn test.").how, _f("I finished mowing the lawn test.").thing["id"]), ("sure", 2))
case("Match: a word that's in no chore's name (a mishearing) means she checks first",
     (_f("I finished mowing a lawn pest.").how, _f("I finished mowing a lawn pest.").thing["id"]), ("confirm", 1))
case("Match: 'taking' and 'take' are cut down alike", (_f("Skip taking the trash out.").how, _f("Skip taking the trash out.").thing["id"]), ("sure", 3))
case("Match: a short name for a long one is sure (painting the house)", _f("Move painting the house to Saturday.").thing["id"], 6)
_tie = _f("I finished mowing the lawn.", [{"id": 1, "name": "Mow Lawn", "group": "House"}, {"id": 8, "name": "Mow the lawn", "group": "Voice Tech"}])
case("Match: two that fit equally: she asks which, the default project's first",
     (_tie.how, [c["group"] for c in _tie.choices]), ("tie", ["Voice Tech", "House"]))
_ord = {"first": 1, "second": 2, "one": 1, "two": 2}
case("Match: the answer to which one, by a word only one has, or by order",
     [(_m.pick(a, _tie.choices, _never, _ord) or {}).get("id") for a in ("Voice Tech", "the house one", "the first one", "two", "the lawn")],
     [8, 1, 8, 1, None])
# sound-alike (Oct 17: "by single hole faucet" for "Buy single whole faucet", 8 times in a morning)
case("Match: how a word sounds: by, bi and buy alike; hole and whole alike",
     [_m.sound(_m.stem(w)) for w in ("by", "bi", "buy", "hole", "whole", "faucets")], ["b", "b", "b", "hl", "hl", "fst"])
_fs = [{"id": 11, "name": "Buy single whole faucet", "group": "House"}, {"id": 12, "name": "Install faucet", "group": "House"},
       {"id": 13, "name": "Clean the gutters", "group": "House"}]
case("Match: sound-alike off, the words alone don't find it", _f("Mark by single hole faucet complete.", _fs).how, "weak")
_sa = lambda said: _m.find(said, _fs, _never, 0.6, sound_alike=True)  # noqa: E731
case("Match: sound-alike on, it's found, and she asks first (never at once)",
     [(_sa(s).how, (_sa(s).thing or {}).get("id")) for s in ("Mark by single hole faucet complete.",
      "Mark the bi single faucet completed.", "Mark the chore by single whole clauses complete.")],
     [("confirm", 11), ("confirm", 11), ("confirm", 11)])
case("Match: sound-alike never overrides what the words find, nor finds what isn't there",
     [(_sa(s).how, (_sa(s).thing or {}).get("id")) for s in ("Mark buy single whole faucet complete.", "Mark the path.")],
     [("sure", 11), ("none", None)])
case("Match: by sound, one word alone isn't enough ('path' sounds like 'put' in Put the trash out)",
     _m.find("Mark my path.", [{"id": 4, "name": "Put the trash out"}], _never, 0.6, sound_alike=True).how, "none")
# Oct 17, late: a weak match is asked about (the voice map's ask_min), not "couldn't find"
_wk = [{"id": 21, "name": "Spray weeds"}, {"id": 22, "name": "Start putting the cameras up and get them running."},
       {"id": 23, "name": "Start putting the cameras up and get them running."}, {"id": 24, "name": "Check pool filter"}]
_aw = lambda said, ask=0.4: _m.find(said, _wk, _never, 0.6, ask_min=ask)  # noqa: E731
case("Match: weak at or above ask_min: she asks about it ('spray the wheat' for Spray weeds)",
     (_aw("Mark my chore, spray the wheat.").how, _aw("Mark my chore, spray the wheat.").thing["id"]), ("confirm", 21))
case("Match: weak, every word said in its name: asked too; two alike: which one",
     (_aw("mark the camera chore done").how, [c["id"] for c in _aw("mark the camera chore done").choices]), ("tie", [22, 23]))
case("Match: ask_min off (none): weak stays weak", _aw("Mark my chore, spray the wheat.", None).how, "weak")
case("Match: nothing shared is still none", _aw("Mark my chores brave lease complete.").how, "none")
# Oct 18, the matching ladder ("When to ask"): same meaning, words that never decide alone, a whole fit
_al = {"our lady": "mary", "blessed virgin mary": "mary", "virgin mary": "mary", "mother of god": "mary"}
_nb = ["mary", "joseph"]
_fe = [{"id": "Assumption", "name": "The Assumption of the Blessed Virgin Mary"},
       {"id": "Assumption_vigil", "name": "The Assumption of the Blessed Virgin Mary Vigil Mass"},
       {"id": "StJoseph", "name": "Saint Joseph Husband of the Blessed Virgin Mary"},
       {"id": "JosephWorker", "name": "Saint Joseph the Worker"}, {"id": "Calasanz", "name": "Saint Joseph Calasanz, Priest"},
       {"id": "HolyFamily", "name": "Holy Family of Jesus, Mary and Joseph"}, {"id": "MotherOfGod", "name": "Mary, Mother of God"}]
case("Same meaning on both sides: Our Lady is the Blessed Virgin Mary",
     (_m.canon("the Assumption of Our Lady", _al).split(), _m.find("the assumption of our lady", _fe, (), 0.6, alike=_al, nearby=_nb).thing["id"]),
     (["the", "assumption", "of", "mary"], "Assumption"))
case("A word that never decides alone: Saint Joseph isn't the Holy Family; Mary alone is a choice of three, never sure",
     ([x[3]["id"] for x in _m.scores("saint joseph", _fe, (), alike=_al, nearby=_nb)], _m.find("mary", _fe, (), 0.6, alike=_al, nearby=_nb).how,
      len(_m.find("mary", _fe, (), 0.6, alike=_al, nearby=_nb).choices)),
     (["StJoseph", "JosephWorker", "Calasanz"], "nearby", 3))
# Oct 18, build C: a day is a day; "when" looks forward; a card's skips
import datetime as _dc
_ty = _dc.date.today().year
case("Midnight UTC is a plain day (a feast), not the evening before; any other time is a moment in the house's time",
     (_ru._when(f"{_ty}-08-15T00:00:00+00:00"), isinstance(_ru._when(f"{_ty}-08-15T13:00:00Z"), _dc.datetime), _ru._when("2026-13-01")),
     (_dc.date(_ty, 8, 15), True, None))
case("A day is said with no time", "at" in _ru._spoken(f"{_ty + 1}-08-15T00:00:00+00:00").split(), False)
_yr = [{"event_key": "Assumption", "name": "The Assumption", "date": f"{_ty}-01-01T00:00:00+00:00"},
       {"event_key": "Easter", "name": "Easter", "date": f"{_ty}-01-02T00:00:00+00:00"},
       {"event_key": "Assumption", "name": "The Assumption", "date": f"{_ty + 1}-01-01T00:00:00+00:00"},
       {"event_key": "Advent", "name": "Advent", "date": f"{_ty + 1}-12-01T00:00:00+00:00"}]
case("When looks forward: each thing once, at its next date; gone and not again, its last",
     [(x["event_key"], x["date"][:4]) for x in _ru.upcoming(_yr, "event_key")],
     [("Easter", str(_ty)), ("Assumption", str(_ty + 1)), ("Advent", str(_ty + 1))])
class _FeastApp:
    name, sound_alike, speaker, commands = "feasts", False, None, {}
    alike, nearby = _al, _nb
    rules = {"when": {"words": ["when is"], "steps": [{"call": "GET /events"}, {"search": {"ignore": ["the", "feast", "of", "day", "is"]}},
                                                      {"match": {"act": 60, "ask": 30, "extra_words": "ignore"}}, {"confirm": {}},
                                                      {"response": {"lines": ["{item}"]}}]}}
    def say(self, sec, **v):
        return f"[{sec}]" + (" " + v["item"] if "item" in v else "")
    def thing_question(self, ask):
        return "which: " + ", ".join(c["name"] for c in ask["choices"])
    async def api(self, method, path, **kw):
        return list(_fe)
    async def refresh(self):
        return None
    def drop_words(self):
        return set()
    def never_words(self):
        return set()
_fa = _FeastApp()
# Oct 18, weight: the main one first ("When to ask", 3 and 4)
_wb.svc["lists"] = {"feast": {"from": "GET /events", "id": "id", "name": "name", "weight": {"field": "grade", "higher": True, "words": "grade_lcl"}}}
_ch3 = [{"id": "W", "name": "Saint Joseph the Worker", "fields": {"grade": 2, "date": "2027-05-01T00:00:00+00:00", "grade_lcl": "optional memorial"}},
        {"id": "H", "name": "Saint Joseph Husband of the Blessed Virgin Mary", "fields": {"grade": 6, "date": "2027-03-19T00:00:00+00:00", "grade_lcl": "SOLEMNITY"}},
        {"id": "C", "name": "Saint Joseph Calasanz", "fields": {"grade": 2, "date": "2027-08-25T00:00:00+00:00", "grade_lcl": "optional memorial"}}]
_ord, _w = _wb.weigh("/events", _ch3)
_had_say, _had_line = _wb.say, _wb.has_line
_wb.say = lambda sec, **v: f"[{sec}] " + " ".join(f"{k}={v[k]}" for k in sorted(v))
_wb.has_line = lambda sec: sec == "thing_main"
case("Weight: the main one first (the card's grade, higher first), said with its own words and month, and how many",
     ([c["id"] for c in _ord], _wb.thing_question({"mode": "main", "choices": _ord, "weight": _w})),
     (["H", "W", "C"], "[thing_main] count=3 label=, solemnity name=Saint Joseph Husband of the Blessed Virgin Mary when=, in March"))
_wb.say, _wb.has_line = _had_say, _had_line
_wb.svc["lists"]["dated"] = {"from": "GET /events2", "id": "id", "name": "name", "weight": {"field": "date"}}
case("Weight by a date: soonest first (what's on my list), and enough weight to stay (from)",
     ([c["id"] for c in _wb.weigh("/events2", _ch3)[0]], _wb.heavy_enough({"grade": 2}, {"field": "grade", "from": 3}), _wb.heavy_enough({"grade": 6}, {"field": "grade", "from": 3})),
     (["H", "W", "C"], False, True))
_pm = {"mode": "main", "choices": _ord, "state": {"at": 3}}
_pick = lambda a, c: next((x for x in c if a.lower() in x["name"].lower()), None)  # noqa: E731
_kind = lambda a: {"yes": "yes", "no": "no"}.get(a.lower())  # noqa: E731
case("The main one's question: yes is it; a name picks another; no stops (she names the others)",
     [(_ru.resume(_pm, a, _kind, _pick, a.split(), 8)[0] or {}).get("item", {}).get("id") for a in ("yes", "the worker")] + [_ru.resume(_pm, "no", _kind, _pick, ["no"], 8)[1]],
     ["H", "W", "no"])
_wb.svc["lists"] = {}
# Oct 19: the copy on hand, for an app that writes nothing
_calls_wb = []
async def _api_wb(method, path, **kw):
    _calls_wb.append(path)
    return [{"id": 1, "name": "x"}]
_had_api, _wb.api = _wb.api, _api_wb
_wb.svc["cache_refresh_seconds"] = 3600
_aio2.run(_wb.listing("/events")); _aio2.run(_wb.listing("/events"))
_n1 = len(_calls_wb)
_aio2.run(_wb.listing("/events", fresh=True))
case("An app that writes nothing: read once, then from the copy on hand; fresh reads it again; one that writes reads live",
     (_n1, len(_calls_wb), _wb.writes(), _k2.writes()), (1, 2, False, True))
_wb.api = _had_api
# Oct 19, the staged dumps (veil/phases.py), each tried on and off
_was_ph = dict(_ph.PHASES)
_ph.PHASES.update(dump1=True, dump2=True, dump3=True, dump4=True)
_wb.commands = {"GET /V1/EVENTS/{MONTH}/{DAY}/": {"api": "GET /v1/events/{month}/{day}/", "types": {"month": "string", "day": "integer"}},
                "GET /V1/N/{MONTH}/{DAY}/": {"api": "GET /v1/n/{month}/{day}/", "types": {"month": "integer", "day": "integer"}}}
_dv = _wb.date_values("/v1/events/{month}/{day}/", "What happened on December 7th?")
case("dump1: the day said, each part as the app writes it (a string month is its name; an integer its number); no day, nothing",
     ((_dv["month"], _dv["day"], bool(_dv["day_said"])), _wb.date_values("/v1/n/{month}/{day}/", "what happened on december 7th")["month"],
      _wb.date_values("/v1/events/{month}/{day}/", "what happened")), (("december", 7, True), 12, {}))
_ev = [{"year": "1781", "title": "Surrender of Lord <b>Cornwallis</b>", "description": "x"}, {"year": "1987", "title": "Black Monday", "description": "y"}]
class _HistApp(_FeastApp):
    commands = {}
    def card_for(self, cmd):
        return {"name": "title"}
    async def api(self, method, path, **kw):
        _hist_paths.append(path)
        return {"count": 2, "results": list(_ev)}
    def date_values(self, command, said):
        return {"month": "december", "day": 7, "day_said": "December 7"} if "december" in said.lower() else {}
_hist_paths = []
_ha = _HistApp()
_ha.rules = {"on": {"words": ["what happened"], "steps": [{"call": "GET /v1/events/{month}/{day}/"},
                    {"response": {"list": True, "line": "{year}: {title}", "lines": ["{items}."]}}]},
             "one": {"words": ["tell me"], "steps": [{"call": "GET /v1/events/{month}/{day}/"},
                    {"response": {"one": "random", "lines": ["In {year}, {title}."]}}]}}
def _hsay(rule, said):
    return _aio2.run(_ru.run(_ha, rule, said))
_r = _hsay("on", "What happened on December 7th?")
case("dump1 and dump2 on: the address from the day said; each read as its line; dump4 strips its markup",
     (_hist_paths[-1], _r.get("items")), ("/v1/events/december/7/", ["1781: Surrender of Lord Cornwallis", "1987: Black Monday"]))
case("dump3 on: one at random, by its own fields", _hsay("one", "tell me something that happened on December 7th")["speech"] in
     ("In 1781, Surrender of Lord Cornwallis.", "In 1987, Black Monday."), True)
case("dump4: outside text as plain words (no markup, links, control characters; at most 300 characters)",
     (_ru._plain("<i>Hi</i> there\x07 see https://evil.example/x now"), len(_ru._plain("w " * 400)) <= 303), ("Hi there see now", True))
_ph.PHASES.update(dump1=False, dump2=False, dump3=False, dump4=False)
_r = _hsay("on", "What happened on December 7th?")
_ha.rules["today"] = {"words": ["today"], "steps": [{"call": "GET /v1/today/events/"}, {"response": {"list": True, "line": "{year}: {title}", "lines": ["{items}."]}}]}
case("Every dump off: no day said in the address (it can't be called), names as before, markup kept, no random pick (the old paths)",
     (_r["speech"], _hsay("today", "today")["items"], _ru._plain("<i>Hi</i>"), _hsay("one", "tell me")["speech"]),
     ("[generic_cannot]", ["Surrender of Lord <b>Cornwallis</b>", "Black Monday"], "<i>Hi</i>", "[generic_cannot]"))
_ph.PHASES = _was_ph
# Oct 19: the copy kept on disk (a restart spends no call) and an app's "too many calls" (429)
_wb._kept = None
_wb2 = _cn.make("weather_brain", dict(_wb.svc), _s, lambda *a, **k: "", actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"))
_calls_wb.clear()
async def _api_429(method, path, **kw):
    _calls_wb.append(path)
    raise _cn.AppError("Weather Brain said 429: slow down", 429, "120")
_wb2.api = _api_429
_got = _aio2.run(_wb2.listing("/events", fresh=True))
_aio2.run(_wb2.listing("/events", fresh=True))
case("A restart finds the copy on disk; a 429 answers from it and waits as long as the app said",
     (_got[1], len(_calls_wb), round(_wb2._waits.get("/events", 0) - __import__("time").time())), ([{"id": 1, "name": "x"}], 1, 120))
_wb3 = _cn.make("weather_brain", dict(_wb.svc), _s, lambda *a, **k: "", actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"))
_wb3.api, _wb3._kept = _api_429, {}
raises("No copy at all: the refusal is said", lambda: _aio2.run(_wb3.listing("/events")), _cn.AppError)
# Oct 19: abbreviations speech-to-text writes, spelled out only when what was heard matches nothing
_ab = {"st": ["saint", "street"], "dr": ["doctor", "drive"]}
case("Abbreviations: each meaning tried; none when there's no abbreviation",
     (_m.expansions("st joseph", _ab), _m.expansions("saint joseph", _ab)), (["saint joseph", "street joseph"], []))
case("Abbreviations as a fallback: St. Joseph the Worker finds Saint Joseph the Worker",
     _m.find("St. Joseph the Worker", _fe, (), 0.6, alike=_al, nearby=_nb, abbrev=_ab).thing["id"], "JosephWorker")
# Oct 19: next and the day said, for forward-looking records ("when" is a date action: in date order, the first)
import datetime as _dn
_t0 = _dn.date.today()
_cal = [{"name": "Past", "date": (_t0 - _dn.timedelta(days=3)).isoformat() + "T00:00:00+00:00", "holy": None},
        {"name": "Tomorrow A", "date": (_t0 + _dn.timedelta(days=1)).isoformat() + "T00:00:00+00:00", "holy": None},
        {"name": "Tomorrow B", "date": (_t0 + _dn.timedelta(days=1)).isoformat() + "T00:00:00+00:00", "holy": True},
        {"name": "Later", "date": (_t0 + _dn.timedelta(days=9)).isoformat() + "T00:00:00+00:00", "holy": True}]
case("By date: the next (the first from today on), the day said (several that day), the next of a Filter's",
     ([x["name"] for x in _ru.by_date(_cal, "next", "what's the next feast day")[0]],
      ([x["name"] for x in _ru.by_date(_cal, "day said", "whose feast day is tomorrow")[0]], _ru.by_date(_cal, "day said", "whose feast day is tomorrow")[1]),
      [x["name"] for x in _ru.by_date([x for x in _cal if _ru._is(x.get("holy"), "true")], "next", "")[0]]),
     (["Tomorrow A", "Tomorrow B"], (["Tomorrow A", "Tomorrow B"], "tomorrow"), ["Tomorrow B"]))
_cal2 = _cal + [{"name": "Tomorrow C", "date": (_t0 + _dn.timedelta(days=1)).isoformat() + "T00:00:00+00:00"}]
case("By date, next: every one on the next day (several feasts that day are read together); days until a date",
     ([x["name"] for x in _ru.by_date(_cal2, "next", "")[0]], _ru.days_until((_t0 + _dn.timedelta(days=160)).isoformat() + "T00:00:00+00:00"),
      _ru.days_until(_t0.isoformat()), _ru.days_until("not a date")),
     (["Tomorrow A", "Tomorrow B", "Tomorrow C"], 160, 0, None))
case("Filter's value: true, a word, a number", [_ru._is(True, "true"), _ru._is(None, "true"), _ru._is("US", "us"), _ru._is(6, "6")], [True, False, True, True])
case("The app's own find: a name holding every word said is a fit below match_min (one: asked about; several: which)",
     (_m.find("easter", [{"id": 1, "name": "Easter Sunday of the Resurrection of the Lord"}, {"id": 2, "name": "Ash Wednesday"}], (), 0.6).how,
      _m.find("trash", [{"id": 1, "name": "Take the trash out"}, {"id": 2, "name": "Put the trash out"}], (), 0.6).how), ("confirm", "tie"))
_said = lambda x: (lambda r: r["speech"])(_aio2.run(_ru.run(_fa, "when", x)))  # noqa: E731
_FeastApp.abbrev = _ab
case("Abbreviations in a rule's Search: St. Joseph the Worker", _said("When is St. Joseph the Worker?"), "Saint Joseph the Worker")
case("The ladder in a rule: a whole fit below Ask is the Assumption; Our Lady is sure; three Josephs: which; Mary alone: which",
     [_said("When is the Assumption?"), _said("When is the Assumption of Our Lady?"), _said("When is Saint Joseph's feast?"), _said("When is Mary's feast day?")],
     ["The Assumption of the Blessed Virgin Mary", "The Assumption of the Blessed Virgin Mary",
      "which: Saint Joseph the Worker, Saint Joseph Husband of the Blessed Virgin Mary, Saint Joseph Calasanz, Priest",
      "which: Mary, Mother of God, The Assumption of the Blessed Virgin Mary, The Assumption of the Blessed Virgin Mary Vigil Mass"])

_dt = _k2
_dt.match_min = 0.6
_dt.cache["groups"] = {"House": 10, "Voice Tech": 20}
_live = [{"id": 1, "name": "Mow Lawn", "projectId": 10}, {"id": 8, "name": "Mow the lawn", "projectId": 20},
         {"id": 4, "name": "Put the trash out", "projectId": 10}]
_calls = []


async def _refresh():
    _calls.append("read")
    _dt.cache["items"] = [dict(c) for c in _live]


_dt.refresh = _refresh
_dt.cache["items"] = [{"id": 1, "name": "Mow Lawn", "projectId": 10}]        # an out-of-date copy
_r = _aio2.run(_dt.target("I finished mowing the lawn.", "complete"))
case("Before a change: Donetick read live, so the newer chore is seen (a tie, not Mow Lawn)",
     (_calls[-1:], _r[0], (_r[1] or {}).get("ask", {}).get("mode")), (["read"], None, "which"))
_tok = _dt.CHOSEN.set(8)
_r = _aio2.run(_dt.target("I finished mowing the lawn.", "complete"))
_dt.CHOSEN.reset(_tok)
case("Her question's answer: the chosen chore is acted on, not matched again", (_r[0] or {}).get("id"), 8)
_r = _aio2.run(_dt.target("Mark number 2 done.", "complete", {"last_list": {"app": "donetick", "ids": [1, 8, 4]}}))
case("Mark number 2 done: the second of the list she read, the live copy's", (_r[0] or {}).get("id"), 8)
_q = _k2.thing_question({"mode": "which", "action": "complete", "choices": [{"name": "Mow the lawn", "group": "Voice Tech"}, {"name": "Mow Lawn", "group": "House"}]})
case("Her which-one question names each one's project", (_q.split()[0], "Mow the lawn" in _q and "group=House" in _q), ("[thing_which]", True))
_had = _k2.has_line
_k2.has_line = lambda section: section == "confirm_complete"
_q = _k2.thing_question({"mode": "confirm", "action": "complete", "choices": [{"name": "Mow Lawn", "group": "House"}]})
_q2 = _k2.thing_question({"mode": "confirm", "action": "skip", "choices": [{"name": "Mow Lawn", "group": "House"}]})
_k2.has_line = _had
case("Her check-first question says what she'd do (the app's line, else the shared one)",
     (_q.split()[0], "doing=[confirm_complete]" in _q, "doing=[confirm_any]" in _q2), ("[thing_confirm]", True, True))

# ---------- mishearings: what was heard, under what was meant ----------
import learn as _learn  # noqa: E402
import yaml  # noqa: E402
_mf = mishearings.FILE
if os.path.exists(_mf):
    os.remove(_mf)
_p, _c = mishearings.add("At a chore", "add a chore")
mishearings.add("at a chore.", "Add a chore")
mishearings.add("at the chore", "add a chore")
_p, _c = mishearings.add("Are the windows hold?")
case("Mishearings: the same heard words count up under one intention (capitals and punctuation aside)",
     [(p["meant"], [(c["said"], c["count"]) for c in p["heard"]]) for p in mishearings.load()],
     [("add a chore", [("At a chore", 2), ("at the chore", 1)]), (None, [("Are the windows hold?", 1)])])
case("Mishearings: the intention's total is all its heard lines together", mishearings.total(mishearings.load()[0]), 3)
mishearings.set_meant("are the windows hold", "Are the windows closed")
case("Mishearings: typing what was said files a not-given-yet one, and the empty group goes",
     [(p["meant"], mishearings.total(p)) for p in mishearings.load()], [("add a chore", 3), ("Are the windows closed", 1)])
mishearings.add("at the chore", "at the store")
case("Mishearings: recorded again under another intention, it moves there with its count",
     [(p["meant"], [(c["said"], c["count"]) for c in p["heard"]]) for p in mishearings.load() if p["meant"] == "at the store"],
     [("at the store", [("at the chore", 2)])])
mishearings.add("at a chore")
case("Mishearings: recorded again with nothing typed, it stays where it is",
     [mishearings.total(p) for p in mishearings.load() if p["meant"] == "add a chore"], [3])
case("Mishearings: taken into the words is a mark, not a removal",
     (mishearings.mark_taken("at a chore"), mishearings.find("at a chore")[1]["taken"]), (True, True))
for _i in range(30):
    mishearings.add(f"heard number {_i}", "meant")
case("Mishearings: never cut for size", sum(len(p["heard"]) for p in mishearings.load()), 33)
case("Mishearings: drop one, and twice says so", (mishearings.drop("Heard number 3"), mishearings.drop("heard number 3")), (True, False))
os.remove(_mf)
mishearings.add("at a chore", "add a chore", when="2026-10-17 09:00", clip="20261017-090000-001-iris", device="iris")
mishearings.add("At a chore.", None, when="2026-10-17 09:05", clip="20261017-090000-001-iris", device="iris")
mishearings.add("at a chore", None, when="2026-10-17 09:10", clip="20261017-091000-002-felix", device="felix")
mishearings.add("at a chore", None, when="2026-10-17 09:15")
case("Mishearings: each Oread clip it was heard in is kept once, with its device (Oct 17)",
     [(k["clip"], k["device"], k["when"]) for k in mishearings.find("at a chore")[1]["clips"]],
     [("20261017-090000-001-iris", "iris", "2026-10-17 09:00"), ("20261017-091000-002-felix", "felix", "2026-10-17 09:10")])
case("Mishearings: heard with no clip (typed, or before Oct 17) still counts", mishearings.find("at a chore")[1]["count"], 4)
mishearings.add("are the windows hold", "are the windows closed")
case("Mishearings: a line never heard through the audio path has no clips", "clips" in mishearings.find("are the windows hold")[1], False)
os.remove(_mf)
_r = _learn.add_miss("misheard", {"heard": "what's the feather", "clip": "c9", "device": "iris"}, "iris", None)
_r2 = _learn.add_miss("misheard", {"heard": "What's the feather?"}, "iris", None)
case("Voice: \"Record that as a misunderstanding\" after \"What did you hear?\" files a mishearing, counted",
     (_r["count"], _r2["count"], _r2["should_be"]), (1, 2, None))
_learn.add_note("whats the feather", "misheard", "what's the weather")
case("Voice: \"That should have been ...\" puts it under what was meant",
     [(p["meant"], mishearings.total(p)) for p in mishearings.load()], [("what's the weather", 2)])
case("Voice: the turn's clip goes with the mishearing (Oct 17)",
     [(k["clip"], k["device"]) for k in mishearings.find("whats the feather")[1]["clips"]], [("c9", "iris")])
case("Voice: the engine miss log is left alone", any(m.get("heard") == "what's the feather" for m in _learn.load()), False)
os.remove(_mf)
_old = os.path.join(TMP, "old-misses.yaml")
with open(_old, "w") as _f:
    yaml.safe_dump({"misses": [{"kind": "misheard", "heard": "Are the windows hold?", "should_be": "Are the windows closed", "count": 2,
                                "first": "2026-10-13 20:30", "last": "2026-10-13 21:00", "answer": "I believe you meant closed"},
                               {"kind": "engine", "heard": "tell me a joke", "count": 1}]}, _f)
case("Mishearings recorded before move over once, with their counts", (mishearings.from_misses(_old),
     [(p["meant"], [(c["said"], c["count"], c["first"]) for c in p["heard"]]) for p in mishearings.load()]),
     (1, [("Are the windows closed", [("Are the windows hold?", 2, "2026-10-13 20:30")])]))
os.remove(_mf)
config.seed_household()          # the starting copy back, as a fresh install has it

# ---------- the household's files: starting copies, and what's new in them ----------
case("Starting copies: a fresh install gets them (settings, the firewall, the keyword files, a voice map)",
     all(os.path.exists(os.path.join(ROOT, p)) for p in ("settings.yaml", "firewall.yaml", "topics/weather.yaml",
                                                          "scores/weather.yaml", "connectors/donetick.yaml", "learn/misses.yaml", "learn/mishearings.yaml")), True)
_set = os.path.join(ROOT, "settings.yaml")
with open(_set, "a") as _f:
    _f.write("# my own line\n")
config.seed_household()
case("Starting copies: never put over the household's own file", open(_set).read().rstrip().endswith("# my own line"), True)
_fresh = os.path.join(TMP, "fresh")
os.makedirs(os.path.join(_fresh, "personality"))
open(os.path.join(_fresh, "personality", "mine.yaml"), "w").write("rate: 0.1\n")
shutil.copytree(os.path.join(ROOT, "defaults"), os.path.join(_fresh, "defaults"))
import subprocess as _sub  # noqa: E402
_sub.run([sys.executable, "-c", "from veil import config"], cwd=ROOT, check=True,
         env=dict(os.environ, ROUTER_ROOT=_fresh, ROUTER_DATA=os.path.join(_fresh, "data")))
case("Starting copies: an example never lands beside your own (your assistant, no example assistant)",
     (os.path.exists(os.path.join(_fresh, "personality", "assistant.yaml")), os.path.exists(os.path.join(_fresh, "settings.yaml")),
      os.path.exists(os.path.join(_fresh, "topics", "weather.yaml"))), (False, True, True))

from veil import starting  # noqa: E402
starting.DISMISSED_FILE = os.path.join(TMP, "data", "starting-dismissed.json")
case("What's new: nothing, when the household's files match the starting copies", starting.new_items(), [])


def _drop_pinned(doc):
    doc["topics"]["weather"]["pinned"].remove("sun set")
    del doc["read_list_max"]


config.edit_yaml(_set, _drop_pinned)
_new = starting.new_items()
case("What's new: a word in a list and a whole setting yours don't have",
     sorted((i["kind"], tuple(i["path"]), i["value"]) for i in _new),
     sorted([("item", ("topics", "weather", "pinned"), "sun set"), ("key", ("read_list_max",), config.load_yaml(os.path.join(ROOT, "defaults", "settings.yaml"))["read_list_max"])]))
_word = next(i for i in _new if i["kind"] == "item")
starting.add(_word["id"])
case("What's new: Add puts the word back in your file, your comments kept",
     ("sun set" in config.load_yaml(_set)["topics"]["weather"]["pinned"], "# my own line" in open(_set).read()), (True, True))
_key = next(i for i in starting.new_items() if i["kind"] == "key")
starting.dismiss(_key["id"])
case("What's new: Not for us hides it for good, and changes nothing", (starting.new_items(), "read_list_max" in config.load_yaml(_set)), ([], False))
raises("What's new: an item already dealt with can't be added twice", lambda: starting.add(_word["id"]))

# ---------- Oct 15: moved settings, an older file still works; mishearings capped ----------
_was = open(_set).read()
_old = yaml.safe_load(_was)
for _k in ("followup_lookback", "heard_needs", "own_words_share", "verb_beats_object"):
    _old.pop(_k, None)
_old.setdefault("router", {})["followup_lookback"] = 7
_old["llm"] = {"fallback_model": "old-model", "timeout": 33}
(_old.get("integrations") or {}).pop("litellm", None)
open(_set, "w").write(yaml.safe_dump(_old))
case("An older settings.yaml: a key under router: is still read", config.knob(config.settings(), "followup_lookback"), 7)
case("An older settings.yaml: llm: is still read", (config.litellm()["fallback_model"], config.litellm()["timeout"]), ("old-model", 33))
_old["followup_lookback"] = 4
_old["integrations"]["litellm"] = {"fallback_model": "new-model"}
open(_set, "w").write(yaml.safe_dump(_old))
case("The newer place wins when both are there", (config.knob(config.settings(), "followup_lookback"), config.litellm()["fallback_model"]), (4, "new-model"))
_old["miss_log_max"] = 3
open(_set, "w").write(yaml.safe_dump(_old))
if os.path.exists(_mf):
    os.remove(_mf)
for _i, _w in enumerate(["one thing", "two thing", "three thing", "four thing"]):
    mishearings.add(_w, "meant", when=f"2026-10-1{_i} 10:00")
_heard = [c["said"] for p in mishearings.load() for c in p["heard"]]
case("Mishearings capped by miss_log_max, the least recently heard going first", _heard, ["two thing", "three thing", "four thing"])
open(_set, "w").write(_was)

# ---------- a topic no dataset knows (feast days): built from its own seed words (Oct 18) ----------
import importlib.util as _ilb  # noqa: E402
import scoring as _sc  # noqa: E402
_bspec = _ilb.spec_from_file_location("build_scores_t", os.path.join(REPO, "tools", "build_scores.py"))
_bs = _ilb.module_from_spec(_bspec)
_bspec.loader.exec_module(_bs)
_bs.TOPICS_DIR, _bs.SCORES_DIR = os.path.join(TMP, "own_topics"), os.path.join(TMP, "own_scores")
os.makedirs(_bs.TOPICS_DIR), os.makedirs(_bs.SCORES_DIR)
_bs.build_own("feasts", {"service": "litcal", "seed": ["feast", "holy day of obligation"], "always_tentative": ["obligation"]},
              [("massive", {"text": "set a reminder for the feast tonight"})])
_own = _sc.Scorer(_bs.TOPICS_DIR, _bs.SCORES_DIR)
_rk = {t: (round(sc, 2), why) for t, sc, m, why in _own.rank("Is the Assumption a holy day of obligation?")}
case("A topic no dataset knows: its seed words are its doors, counted as yours, the longest phrase first",
     (_own.topics["feasts"]["service"], _rk.get("feasts")), ("litcal", (0.9, "ok")))
case("Its tentative word alone isn't enough; how often a seed is in other topics' sentences is kept",
     ([why for t, sc, m, why in _own.rank("what's the obligation")], _bs.load_yaml(os.path.join(_bs.SCORES_DIR, "feasts.yaml"))["words"]["feast"]["seen"]),
     (["guard"], 1))

# ---------- Oct 19, Wikipedia's On this day: dumps 5 to 10 (veil/phases.py), each on and off ----------
import yaml as _y5  # noqa: E402
from veil import openapi as _oa5, web as _web5  # noqa: E402
_was5 = dict(_ph.PHASES)
_ph.PHASES.update(dump5=True, dump6=True, dump7=True, dump8=True, dump9=True, dump10=True, dump11=True)
_wf = _y5.safe_load("""
swagger: "2.0"
info: {title: Wikifeeds API, version: 1.0.0}
parameters:
  domain: {in: path, name: domain, required: true, type: string}
  month: {in: path, name: month, required: true, type: string, pattern: "^(0[1-9]|1[012])$"}
  day: {in: path, name: day, required: true, type: string, pattern: "^(0[1-9]|[12][0-9]|3[01])$"}
paths:
  /{domain}/v1/feed/onthisday/{type}/{month}/{day}:
    get:
      summary: Get events on a day in history
      parameters:
        - $ref: "#/parameters/domain"
        - {name: type, in: path, required: true, type: string, enum: [selected, births, deaths]}
        - $ref: "#/parameters/month"
        - $ref: "#/parameters/day"
      responses:
        200: {description: ok, schema: {$ref: "#/definitions/resp"}}
definitions:
  list: {type: array, items: {type: object, properties: {text: {type: string}, year: {type: integer}}}}
  resp: {type: object, properties: {births: {$ref: "#/definitions/list"}, selected: {$ref: "#/definitions/list"}}}
""")
_wc = _oa5.commands(_wf)
case("A Swagger 2 spec in YAML: its path parameters by $ref, their patterns and allowed values, what it answers with",
     (_wc[0]["api"], _wc[0]["patterns"]["month"], _wc[0]["enums"], _wc[0]["returns"]),
     ("GET /{domain}/v1/feed/onthisday/{type}/{month}/{day}", "^(0[1-9]|1[012])$", {"type": ["selected", "births", "deaths"]}, ["births", "selected", "text", "year"]))
_exp = [c["api"] for c in _oa5.expanded(_wc)]
case("dump8: a command per allowed value, written in its path; a rule may call one, the template too",
     (_exp[1:], _ru.check({"steps": [{"call": "GET /{domain}/v1/feed/onthisday/births/{month}/{day}"}]}, {a.upper() for a in _exp})),
     (["GET /{domain}/v1/feed/onthisday/selected/{month}/{day}", "GET /{domain}/v1/feed/onthisday/births/{month}/{day}",
       "GET /{domain}/v1/feed/onthisday/deaths/{month}/{day}"], None))
_wk = _cn.make("weather_brain", {"kind": "openapi", "url": "https://en.wikipedia.org/api/rest_v1", "timeout": 3,
                                 "spec_prefix": "/{domain}/v1"}, _s, lambda *a, **k: "",
               actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"))
_wk.commands = {c["api"].upper(): c for c in _oa5.expanded(_wc)}
_bth = "/{domain}/v1/feed/onthisday/births/{month}/{day}"
case("dump6: the start its spec gives every path but its address leaves out, taken off",
     (_wk.own_path(_bth), _wk.filled("GET", _bth, more={"month": "01", "day": "09"})[0]),
     ("/feed/onthisday/births/{month}/{day}", "/feed/onthisday/births/01/09"))
_dv7 = _wk.date_values(_bth, "Who was born on January 9th?")
import datetime as _d7  # noqa: E402
_t7 = _d7.date.today()
case("dump7: each part as its pattern says (01, 09), today's too when no day was said",
     ((_dv7["month"], _dv7["day"], _dv7["day_said"]), {k: str(v) for k, v in _wk.date_values(_bth, "who was born").items()}),
     (("01", "09", "January 9"), {"year": str(_t7.year), "month": f"{_t7.month:02d}", "day": f"{_t7.day:02d}"}))
import asyncio as _a5  # noqa: E402
async def _ua5():
    async with access.client(3) as c:
        return c.headers.get("user-agent")
case("dump5: every call out says who it is (router: user_agent)", _a5.run(_ua5()), "WepwawetVeil/1.0 (household voice router)")
_old_at = _d7.datetime.now().strftime("%Y-%m-%d %H:%M")
case("dump10: a spec read for the version check within the day isn't read again; an older one or none is",
     (_web5.recently_checked({"checked": {"at": _old_at}}, _s), _web5.recently_checked({"checked": {"at": "2026-01-01 08:00"}}, _s),
      _web5.recently_checked({}, _s)), (True, False, False))
class _BusyApp(_FeastApp):
    rules = {"today": {"words": ["today"], "steps": [{"call": "GET /today"}, {"response": {"list": True, "lines": ["{items}"]}}]},
             "rename": {"words": ["rename"], "steps": [{"call": "PUT /x"}]}}
    def has_line(self, sec):
        return True
    async def api(self, method, path, **kw):
        raise _cn.AppError("busy", 429)
_bz = _cn.Connector.__new__(_cn.Connector)
_bz.name, _bz.rules, _bz.say, _bz.has_line = "busy", _BusyApp.rules, (lambda sec, **v: f"[{sec}]"), (lambda sec: True)
_bz.api = _BusyApp().api
async def _bz_list(path, command=None):
    raise _cn.AppError("busy", 429)
_bz.listing = _bz_list
async def _bz_none():
    return None
_bz.svc, _bz.refresh = {}, _bz_none
_bzr = _a5.run(_bz.run_rule("today", "today"))
case("dump9: a rule that only reads, refused (429): her busy line, marked busy for the next of the same nature; one that changes isn't passed on",
     (_bzr["speech"], _bzr.get("node_down"), _a5.run(_bz.run_rule("rename", "rename x")).get("node_down")), ("[service_busy]", "busy", None))
_ph.PHASES.update(dump5=False, dump6=False, dump7=False, dump8=False, dump9=False, dump11=False)
async def _ua6():
    async with access.client(3) as c:
        return c.headers.get("user-agent", "").startswith("python-httpx")
case("Dumps 5 to 11 off: httpx's own name, the spec's whole path, no pattern, no command per value, no node marked, the spec's numbered answers unread (the old paths)",
     (_a5.run(_ua6()), _wk.own_path(_bth), _wk.date_values(_bth, "who was born"), len(_oa5.expanded(_wc)),
      _a5.run(_bz.run_rule("today", "today")).get("node_down"), _oa5.commands(_wf)[0]["returns"]), (True, _bth, {}, 1, None, []))
_ph.PHASES = _was5

# ---------- Oct 19, the parking lot's Wepwawet column: dumps 14 to 19, each on and off ----------
_was14 = dict(_ph.PHASES)
_ph.PHASES.update(dump14=True, dump15=True, dump16=True, dump17=True, dump18=True, dump19=True)
import datetime as _d14  # noqa: E402
import fields as _F14  # noqa: E402
_t14 = _d14.date(2026, 10, 19)
case("dump14: a date in another year says its year; this year's doesn't",
     (_F14.say_date(_d14.date(2027, 8, 15), _t14), _F14.say_date(_d14.date(2026, 12, 6), _t14)), ("Sunday, August 15, 2027", "Sunday, December 6"))
_k5 = _cn.make("donetick", _s["services"]["donetick"], _s, lambda sec, **v: f"[{sec}]" + (" " + " ".join(f"{a}={b}" for a, b in sorted(v.items())) if v else ""),
               actions_dir=os.path.join(ROOT, "actions"), connectors_dir=os.path.join(ROOT, "connectors"), has_line=lambda sec: True)
case("dump14: more fit than she names: \"several\"", _k5.thing_question({"mode": "main", "more": True, "weight": {},
     "choices": [{"name": "A", "fields": {}}, {"name": "B", "fields": {}}]}).split(" ")[1], "count=several")
_k5.map["actions"]["add"] = {"api": "POST /chores", "verbs": {"to": {"share": 0.67, "basis": "measured"}, "in": {"share": 0.62, "basis": "measured"},
                                                             "add": {"share": 0.97, "basis": "measured"}}}
case("dump15: little words the datasets counted pick no action alone; with the action's own word they still count",
     ([a for a, _, _ in _k5._verbs("task fixed rotisserie to in", False)], [a for a, _, _ in _k5._verbs("add milk to the list", False)]),
     ([], ["add"]))
case("dump15: \"... named do not save that\": nothing added, she says so",
     _aio2.run(_k5.do_add("Okay so named do not save that", []))["speech"], "[add_cancelled]")
_k5.map["actions"]["complete"] = {"api": "POST /chores/{id}/do", "verbs": {"mark": {"share": 0.9}, "complete": {"share": 0.9}, "done": {"share": 0.9}}}
case("dump15: \"mark it complete\" points at the one she last named; \"mark the gutters complete\" doesn't",
     (_k5.points_at_last("Mark it complete", "complete"), _k5.points_at_last("Mark the gutters complete", "complete")), (True, False))
case("dump15: \"rename the house project chore\": the project is in a chore's name",
     (_k5.noun_after("rename the house project chore", ["project"]), _k5.noun_after("rename the house project to home", ["project"])), (True, False))
_k5.people = dict(_k5.people, john="John")
case("dump15: a first name with its last name stays in the name (Call John Smith); a first name alone is who",
     (_k5.spoken_value("Add a chore, call John Smith tomorrow", "add"), _k5.spoken_value("Add a chore for John, clean the gutters", "add")),
     ("Call John Smith", "Clean the gutters"))
_fa2 = _FeastApp()
_fa2.rules = {"find": {"words": ["find"], "steps": [{"call": "GET /events"}, {"search": {"ignore": ["the", "task"]}},
                                                     {"match": {"act": 60, "ask": 30}}, {"response": {"lines": ["{item}"]}}]}}
_r15 = _aio2.run(_ru.run(_fa2, "find", "Find the task."))
case("dump15: a find with nothing to search by asks which one, and searches by the answer",
     (_r15["speech"], _r15["ask"]["need"], _aio2.run(_ru.run(_fa2, "find", "x", dict(_r15["ask"]["state"], values={"_name": "Saint Joseph the Worker"})))["speech"]),
     ("[rule_which_name]", "_name", "Saint Joseph the Worker"))
from veil import firewall as _fw16  # noqa: E402
_f16 = _fw16.Firewall({"enabled": False})
case("dump16: the Off-Platform model never works a lock, the alarm or the garage door, whoever spoke (the firewall off too)",
     (bool(_f16.check_off_platform([{"name": "HassTurnOn", "arguments": '{"name": "garage door"}'}])),
      bool(_f16.check_off_platform([{"name": "HassTurnOn", "arguments": '{"domain": ["lock"]}'}])),
      _f16.check_off_platform([{"name": "HassTurnOn", "arguments": '{"name": "kitchen light"}'}])), (True, True, None))
case("dump16: an address on the house's network isn't outside; one on the internet is",
     (access.outside("http://192.168.1.20:2021/api"), access.outside("http://127.0.0.1:1"), access.outside("https://1.1.1.1/x")), (False, False, True))
case("dump16: how its key is sent, changed, said plainly",
     _web5.key_said({"was": {"in": "header", "name": "secretkey", "prefix": ""}, "now": {"in": "header", "name": "Authorization", "prefix": "Bearer "}}),
     'How its key is sent changed: it was in the secretkey header, its spec now says in the Authorization header after "Bearer". Accept only if you expected this.')
import http.server as _hs, threading as _th  # noqa: E401,E402
class _Big(_hs.BaseHTTPRequestHandler):
    def do_GET(self):
        import gzip
        if self.path == "/gz":      # a gzipped answer (Wikipedia's, GitHub's): read as decoded, not decoded twice
            z = gzip.compress(b'{"ok": true}')
            self.send_response(200); self.send_header("Content-Encoding", "gzip"); self.send_header("Content-Length", str(len(z)))
            self.end_headers(); self.wfile.write(z)
            return
        self.send_response(200); self.end_headers(); self.wfile.write(b"x" * 300000)
    def log_message(self, *a):
        pass
_srv = _hs.HTTPServer(("127.0.0.1", 0), _Big)
_th.Thread(target=_srv.serve_forever, daemon=True).start()
async def _cap(kb):
    async with access.client(5) as c:
        return len((await access.capped(c, "GET", f"http://127.0.0.1:{_srv.server_port}/", kb)).content)
raises("dump16: an answer bigger than its cap is refused as it comes", lambda: _a5.run(_cap(100)))
case("dump16: one within its cap is read whole", _a5.run(_cap(1000)), 300000)
async def _gz():
    async with access.client(5) as c:
        return (await access.capped(c, "GET", f"http://127.0.0.1:{_srv.server_port}/gz", 100)).json()
case("dump16: a gzipped answer is read once, as decoded", _a5.run(_gz()), {"ok": True})
_srv.shutdown()
class _Paged(_FeastApp):
    pass
_k5.svc = dict(_k5.svc, pages_max=3, url="https://app.example/api")
_pages = {"/v1/x?page=2": {"next": "https://app.example/api/v1/x?page=3", "results": [{"n": 2}]}, "/v1/x?page=3": {"next": None, "results": [{"n": 3}]}}
async def _pg(method, path, **kw):
    return _pages[path]
_k5.api = _pg
case("dump18: an answer in pages: its following pages read, up to pages_max, on the app's own address only",
     (_a5.run(_k5.more_pages({"next": "https://app.example/api/v1/x?page=2", "results": [{"n": 1}]})),
      _a5.run(_k5.more_pages({"next": "https://evil.example/x"}))), ([{"n": 2}, {"n": 3}], []))
_y18 = _d14.date.today().year
_k5.svc["lists"] = {"feast": {"from": "GET /cal", "id": "event_key", "name": "name", "defined": {"from": "GET /defined", "month": "month", "day": "day"}}}
_k5._card_fields = {"id": "event_key", "name": "name"}
_t18 = _d14.date.today()
_soon = _t18 + _d14.timedelta(days=10)
_lists = {"/defined": [{"event_key": "Nick", "name": "Saint Nicholas", "month": _soon.month, "day": _soon.day},
                       {"event_key": "Gone", "name": "Saint Gone", "month": _soon.month, "day": _soon.day}],
          "/cal": [{"event_key": "Adv", "name": "Second Sunday of Advent", "date": _soon.isoformat()},
                   {"event_key": "Nick", "name": "Saint Nicholas", "date": (_soon.replace(year=_soon.year + 1)).isoformat()}]}
async def _lst(path, command=None, fresh=False):
    return {}, _lists[path]
_k5.listing = _lst
_k5.alike, _k5.nearby = {}, []
case("dump18: only in the list of what should be: superseded, said so",
     _a5.run(_k5.not_kept("/cal", "saint gone", "name", set())).startswith("[not_kept] item=Saint Gone"), True)
case("dump18: kept on another day than its usual one still to come: what takes its place",
     _a5.run(_k5.gives_way("/cal", {"id": "Nick", "fields": {"date": _soon.replace(year=_soon.year + 1).isoformat()}})),
     f" [gives_way] other=Second Sunday of Advent usual={_soon.strftime('%B')} {_soon.day}")
_ba = activity.Activity(os.path.join(TMP, "data", "bank19.db"), answers_kept=5, use_from=0.2)
_bid = _ba.bank_upload("iris", "what is the capital of pa", "What is the capital of PA?", ["Harrisburg."])
_row = _ba.bank_row(_bid)
case("dump19: an uploaded saying: added, generic, its answers kept, trips enough that the bank always answers it",
     (bool(_row["added"]), _row["generic"], _row["answers"], _row["trips"]), (True, 1, ["Harrisburg."], 6))
case("dump19: a similar saying finds it; a different one doesn't",
     (_ba.similar_key("iris", "what is the capital of pa please", {"is", "the", "of", "please", "what"}, 0.8),
      _ba.similar_key("iris", "what is the capital of ohio", {"is", "the", "of", "what"}, 0.8)), ("what is the capital of pa", None))
import scoring as _sc19  # noqa: E402
_it19 = _sc19.prepare({"words": {"five": {"share": 0.9, "where": ["doors"]}, "chore": {"share": 0.9, "where": ["doors"]}}})
case("dump19: numbers never count toward a topic",
     (_sc19.score("five hundred divided by three", _it19, 0, {"five", "hundred"})[2], _sc19.score("five chores", _it19)[2]), ("no door", "ok"))
_ph.PHASES.update(dump14=False, dump15=False, dump16=False, dump17=False, dump18=False, dump19=False)
case("Dumps 14 to 19 off: no year said, little words count, no cancel, the firewall's own rules only (the old paths)",
     (_F14.say_date(_d14.date(2027, 8, 15), _t14), [a for a, _, _ in _k5._verbs("task fixed rotisserie to in", False)],
      _a5.run(_k5.gives_way("/cal", {"id": "Nick", "fields": {}}))), ("Sunday, August 15", ["add"], ""))
_ph.PHASES = _was14

# Oct 19 night, dump21: a rule whose lines say the day asks which when none was said
_was21 = dict(_ph.PHASES)
_ph.PHASES.update(dump1=True, dump21=True)
_ha.rules["day"] = {"words": ["what happened on"], "steps": [{"call": "GET /v1/events/{month}/{day}/"},
                    {"response": {"list": True, "lines": ["On {day_said} in history: {items}."]}}]}
case("dump21: no day said for a rule that says the day: she asks which; a day said goes on",
     (_hsay("day", "What happened on Victory Day?")["speech"], _hsay("day", "What happened on December 7th?").get("items") is not None),
     ("[rule_which_day]", True))
_ph.PHASES["dump21"] = False
case("dump21 off: as before", _hsay("day", "What happened on Victory Day?")["speech"] != "[rule_which_day]", True)
_ph.PHASES = _was21

# Oct 19 evening, dump22: an app keeps its own names in the people grid
from veil import people as _pp22  # noqa: E402
_was22 = open(config.SETTINGS_FILE).read()
case("dump22: an app adds a name nobody has: a new row, the name the router's too; one a row goes by: joins it",
     (_pp22.change("oread", "add", "Rachel"), _pp22.change("oread", "add", "Rachel")),
     ("Rachel added to the people grid", "Rachel is already in the people grid"))
case("dump22: renamed there, renamed here (the router's name too, when it was the same); removed: out of its column, the row kept",
     (_pp22.change("oread", "rename", "Rach", "Rachel"), _pp22.column("oread")[-1], _pp22.change("oread", "remove", "Rach"),
      any(r["wepwawet"] == "Rach" for r in _pp22.grid()["rows"]), [r for r in _pp22.column("oread") if r["person"] == "Rach"]),
     ("Rachel is Rach in the people grid too", {"person": "Rach", "names": ["Rach"]},
      "Rach taken out of the oread column; the row stays for you (People)", True, []))
raises("dump22: a rename to someone else's name is refused", lambda: (_pp22.change("oread", "add", "Zed"), _pp22.change("oread", "add", "Ann"),
                                                                     _pp22.change("oread", "rename", "Ann", "Zed")), ValueError)
open(config.SETTINGS_FILE, "w").write(_was22)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{len(PASSED)} pass" + (f", {len(FAILED)} fail" if FAILED else ""))
sys.exit(1 if FAILED else 0)
