"""Which app a sentence is for, when no topic word says so (python3 tools/test_which_app.py).

An app's action word plus one of its own things routes to that app; when more than one app claims
the sentence, she asks which, and the answer picks. A stand-in "Builder" app sits beside Donetick.
Calls nothing (the router's decision only)."""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="which-app-")
# a throwaway copy as a fresh install starts, so the household's own files are never read
sys.path.insert(0, os.path.join(REPO, "tests"))
import make_copy  # noqa: E402
ROOT = make_copy.make(os.path.join(TMP, "root"), REPO)
sys.path.insert(0, ROOT)
os.environ["ROUTER_ROOT"] = ROOT
os.environ["ROUTER_DATA"] = os.path.join(TMP, "data")
os.environ.setdefault("LITELLM_URL", "http://stand-in")
import router as r  # noqa: E402

FAILED = []


def case(name, got, want):
    print(("PASS  " if got == want else "FAIL  ") + name + ("" if got == want else f"\n      got {got!r}, want {want!r}"))
    if got != want:
        FAILED.append(name)


dt = r.CONNECTORS["donetick"]
dt.cache["items"] = [{"id": 1, "name": "Paint the back of the house"}, {"id": 2, "name": "House"}]
dt.cache["people"] = {}
msg = lambda t: [{"role": "system", "content": "Iris Personality"}, {"role": "user", "content": t}]  # noqa: E731

d = r.decide(msg("Move painting the house to Saturday"), pending={})
case("one app names the thing: it's that app's", (d["path"], d.get("topic"), d.get("action")), ("A", "chores", "move"))
d = r.decide(msg("Move the couch to Saturday"), pending={})
case("no app has such a thing: not ours", d["path"], "gemini")


class Builder:
    def __init__(self, base):
        self.base, self.map = base, base.map

    def pick_action(self, t, measured_only=False):
        return self.base.pick_action(t, measured_only)

    def names_thing(self, said):
        return "house" in said.lower()

    def refine(self, said, a):
        return a


r.CONNECTORS["builder"] = Builder(dt)
r.SCORER.topics["jobs"] = {"service": "builder", "items": []}
r.SERVICES["builder"] = {"title": "Builder"}
d = r.decide(msg("Move the house to Saturday"), pending={})
case("two apps name it: she asks which", (d["path"], [x["title"] for x in d.get("apps", [])]), ("which", ["Donetick", "Builder"]))
p = {"kind": "which_app", "said": "Move the house to Saturday", "apps": d.get("apps") or []}
d = r.decide(msg("The builder one"), pending=p)
case("the answer picks the app, and the request runs there", (d["path"], d.get("topic"), d.get("said")), ("A", "jobs", "Move the house to Saturday"))
d = r.decide(msg("Donetick"), pending=p)
case("or the other", (d["path"], d.get("topic")), ("A", "chores"))
case("her question names them", r.or_list(["Donetick", "Builder"]), "Donetick or Builder")

# a request in its tree stays home (settings tree_stays_home, Oct 17)
r.STAYS_HOME = True
d = r.decide(msg("Delete the chore paint the back of the house"), pending={})
case("in the tree, a verb none of its actions has: it stays home", (d["path"], d.get("topic")), ("home", "chores"))
d = r.decide(msg("I need you to hide the chore"), pending={})
case("only strip_away words looked like an add: the real verb decides, and it stays home", d["path"], "home")
d = r.decide(msg("I need you to find the chore"), pending={})
case("the real verb is the find rule's: it's a find (Oct 17, evening)", (d["path"], d.get("action")), ("A", "find"))
d = r.decide(msg("I need to add a chore to paint the fence"), pending={})
case("an add is still an add", (d["path"], d.get("action")), ("A", "add"))
line = r.stay_home_line("chores", "iris")
case("her stay-home line names the tree as it's spoken", "chore list" in line and "{tree}" not in line, True)
r.STAYS_HOME = False
d = r.decide(msg("Delete the chore paint the back of the house"), pending={})
case("tree_stays_home off: as before", d["path"], "A")

# Oct 17, late (Owner's test): delete is never by voice; no to her name question stops; an answer
# that's a request isn't a name; "check my list" reads it; an add with a date for a chore there moves it
r.STAYS_HOME = True
d = r.decide(msg("Delete the chore that you just added."), pending={})
case("delete: never by voice, said so (not 'staying home')", (d["path"], d.get("kind"), d.get("verb")), ("home", "never_by_voice", "delete"))
r.STAYS_HOME = False
case("never_by_voice speech names the app", "Donetick" in r.phrase("router", "never_by_voice", "iris").format(verb="delete", app="Donetick"), True)
ask = {"kind": "add_name", "topic": "chores", "action": "add", "said": "add a chore"}
d = r.decide(msg("No, cancel, idiot."), pending=ask)
case("no to 'what should I call it?': it stops", (d["path"], d["kind"]), ("C", "no"))
d = r.decide(msg("can you mark the chore paint the back of the house complete"), pending=ask)
case("an answer that's a request of its own isn't the name", (d["path"] == "C", d.get("action")), (False, "complete"))
d = r.decide(msg("Clean out the garage"), pending=ask)
case("a plain answer still is", (d["path"], d["kind"]), ("C", "add_name"))
# Oct 17, last Donetick round: "add a due date to that" while "anything else?" waits answers it
_ser = {"kind": "series", "topic": "chores", "service": "donetick", "name": "Root history diagram", "id": 9,
        "fields": dict((k, v) for k, v in dt.add_fields().items() if v.get("kind") == "extra"), "offered": ["due_date", "repeat"]}
case("'add a due date to that' answers 'anything else?' (not a new request)",
     r.opens_new_request(_ser, "Can you add a due date to that of tomorrow at three P. M.?"), False)
case("'remind me to call the plumber' is still a new one", r.opens_new_request(_ser, "Remind me to call the plumber tomorrow"), True)
d = r.decide(msg("Check my list of chores."), pending={})
case("check my list reads it", (d["path"], d.get("action")), ("A", "list"))
d = r.decide(msg("Can you add tomorrow as the date for the paint the back of the house chore?"), pending={})
case("an add with a date for a chore that's there moves it", d.get("action"), "move")

# Oct 17, evening, Felix: her answer came back misheard with room talk on the end, and was added as a chore
import time  # noqa: E402
gem = ("I'm still a bit puzzled, but I'm ready to sprinkle some magic on whatever you need! Are we looking for a recipe, "
       "or perhaps something else on your mind?")
back = ("Puzzle, but I'm ready to spring on some magic of whatever you need. I mean, for us he or perhaps something else "
        "on my mind. We were talking about marriage.")
case("her answer back, misheard, room talk on the end: an echo", bool(r.echo_of(back, [{"answer": gem, "time": time.time()}])), True)
case("a real request after a long answer isn't one", r.echo_of("Add a new chore.", [{"answer": "Added Call the vet for you, in House. "
     "Is there anything else for this chore? I can add a due date, or repeat.", "time": time.time()}]), None)
# Oct 17, last: another device's answer is an echo too; a yes or no after her words is kept
esm = "I think I heard \"out of brain cleave\". I'm not sure I can answer that. Shall I consult the bigger spell book?"
case("another device's answer heard here is an echo (every device's last answers are tried)",
     bool(r.echo_of("Not sure I can answer that, shall I consult the bigger spell book", [{"answer": "Okay.", "time": time.time()},
                                                                                       {"answer": esm, "time": time.time() - 5}])), True)
case("the person's own no after her words is the answer", r.answer_after_echo(
     "I think I heard how the brain flea that we only buy pizza. That's not something I know here at home. Want me to ask around? No.",
     "I think I heard \"had a brain flea\". That's not something I know here at home. Want me to ask around?"), "No")
_aa = "I think I heard \"had a brain flea that we only buy pizza at sales\". That's not something I know here at home. Want me to ask around?"
d = r.decide(msg("I think I heard had a brain flea that we only buy pizza at sales. That's not something I know here at home. "
                 "Want me to ask around? No."), pending={"kind": "ask_around", "said": "had a brain flea"},
             turns=[{"answer": _aa, "time": time.time()}])
case("so 'ask around? No.' coming back with her words answers her question", (d["path"], d.get("kind")), ("C", "no"))
# Oct 18: the same request again while the first is being answered gets the first one's answer,
# never decided or sent out a second time (LiteLLM's retry after its timeout)
import asyncio  # noqa: E402


async def _twice(make):
    k = "same-request"
    f = r.IN_FLIGHT[k] = {"done": r.asyncio.Event()}
    again = asyncio.ensure_future(r.answer_again(k))
    await asyncio.sleep(0)
    sent = r.kept(make(), k, f)
    if isinstance(sent, r.StreamingResponse):
        async for _ in sent.body_iterator:
            pass
    got = await again
    if isinstance(got, r.StreamingResponse):
        return "".join([p if isinstance(p, str) else p.decode() async for p in got.body_iterator])
    return got.body.decode() if got is not None else None


_one = asyncio.run(_twice(lambda: r.local_reply("Added milk.", False)))
case("a repeat waits and gets the same answer", '"Added milk."' in (_one or ""), True)
_two = asyncio.run(_twice(lambda: r.local_reply("Added milk.", True)))
case("a streamed answer is sent again whole", "Added milk." in (_two or ""), True)
case("nothing is left waiting", r.IN_FLIGHT, {})

# Oct 18, from the log: only her flair came back, misheard; each sentence of her answer is tried
_fl = "Three wishes await thee, mortal! I'll remember: We only take our cars to Joe's garage. Right?"
case("her flair alone coming back is an echo", bool(r.echo_of("Three wishes of weak bee, mortal, all remember.",
                                                              [{"answer": _fl, "time": time.time()}])), True)
case("a request borrowing two words of her flair isn't one", r.echo_of("Add three wishes to my list.",
                                                                       [{"answer": _fl, "time": time.time()}]), None)
d = r.decide(msg("I think I heard had a brain flea. That's not something I know here at home. Want me to ask around?"),
             pending={"kind": "ask_around"}, turns=[{"answer": _aa, "time": time.time()}])
case("her words alone are still an echo", (d["path"], d.get("kind")), ("0", "echo"))
d = r.decide(msg(back), pending={})
case("a long sentence whose only topic word is one door: not sure of the topic (lone_door_max_words)",
     (d.get("topic"), d["path"] != "A", d["ranked"][0]["reason"]), ("chores", True, "guard"))
d = r.decide(msg("Add a chore to start putting the cameras up and get them running"), pending={})
case("a long add whose one topic word is a seed (chore) still is", (d["path"], d.get("action")), ("A", "add"))
case("a name longer than add_name_max_words is no name: she asks for it",
     (dt.spoken_value("Add " + back, "add"), dt.spoken_value("Add a chore to call the vet", "add")), ("", "Call the vet"))

# Oct 18, the chores test: the follow-up step after "Shall I read the rest?"
_lr = {"kind": "list_rest", "topic": "chores", "items": ["Mow the lawn", "Spray weeds", "Take the trash out"]}
_read = [{"answer": "Next: Put windows out trash, and Start putting the cameras up. Plus 3 more. Shall I read the rest?",
          "time": time.time()}]
d = r.decide(msg("Read the rest."), pending=_lr, turns=_read)
case("'Read the rest.' answers her question, though all its words are in it (not an echo)", (d["path"], d.get("kind")), ("C", "yes"))
d = r.decide(msg("Shall I read the rest of it now"), pending={}, turns=_read)
case("with no question waiting, her words coming back are still an echo", d.get("kind"), "echo")
d = r.decide(msg("Continue."), pending=_lr, turns=[])
case("'Continue.' is a yes to 'read the rest?'", (d["path"], d.get("kind")), ("C", "yes"))
_conf = {"kind": "thing", "mode": "confirm", "topic": "chores", "action": "complete", "said": "Mark rotisserie diagram complete",
         "choices": [{"id": 7, "name": "Rotisserie diagram"}]}
d = r.decide(msg("Yes. I don't think you're not sure."), pending=_conf, turns=[])
case("a yes, then room talk asking for nothing: the yes answers 'Rotisserie diagram?'",
     (d["path"], d.get("chosen"), d.get("thing_answered")), ("A", 7, True))
case("...and the log, who spoke and the audio path go by the words said, not the request it confirms",
     (d.get("spoken"), d["said"]), ("Yes. I don't think you're not sure.", "Mark rotisserie diagram complete"))
case("a yes, then a request of its own, isn't taken as the yes", r.leading_answer("Yes. Add a chore to call the vet."), None)
case("a yes, then an app's own thing, isn't either", r.leading_answer("Yes. Paint the back of the house."), None)
case("one sentence alone is no leading answer", r.leading_answer("Yes"), None)
d = r.decide(msg("Yes. I don't think you're not sure."), pending={"kind": "add_name", "topic": "chores", "action": "add",
                                                                 "said": "add a chore"}, turns=[])
case("to 'what should I call it?' a leading yes isn't cut out (only yes-or-no questions)", d.get("kind") != "add_name"
     or "sure" in " ".join(r.without_filler(d["said"])), True)
_ask = {"kind": "ask_around", "said": "market complete"}
d = r.decide(msg("No. It doesn't matter really."), pending=_ask, turns=[])
case("'No.' then room talk to 'ask around?': no", (d["path"], d.get("kind")), ("C", "no"))


async def _echo_keeps(keep):
    who = "iris"
    os.makedirs(os.path.dirname(r.PENDING_FILE), exist_ok=True)      # the copy's own state/
    r.SETTINGS["echo_keeps_question"] = keep
    r.ask_later(who, dict(_lr))
    r.record_turn(who, {"said": "what's on my list", "path": "A"}, msg("what's on my list"), "donetick", _read[0]["answer"])
    await r.answer_chat({"messages": msg("Put windows out trash, and start putting the cameras up.")}, time.monotonic(), None, None)
    left = r.pending_for(who)
    r.clear_pending(who)
    return (left or {}).get("kind")


case("an echo keeps her waiting question (echo_keeps_question)", asyncio.run(_echo_keeps(True)), "list_rest")
case("echo_keeps_question false: an echo drops it, as before", asyncio.run(_echo_keeps(False)), None)
r.SETTINGS["echo_keeps_question"] = True
case("'Who answered that?' after the bank has its own line, naming the Off-Platform model",
     "bank" in r.phrase("router", "learn_bank", "iris").format(model="Gemini"), True)

# Oct 18: a greeting with a name for her is a greeting; the stay-home line names the verb; a due date gone by says so
d = r.decide(msg("Good morning, sweetheart."), pending={}, turns=[])
case("'Good morning, sweetheart.' is polite words (a greeting back), not a fragment", (d["path"], d.get("kind")), ("0", "polite"))
d = r.decide(msg("I love you"), pending={}, turns=[])
case("...but 'I love you' isn't cut down to nothing (her names count only beside a polite phrase)", d.get("kind") != "polite", True)
r.STAYS_HOME = True
d = r.decide(msg("I need you to hide the chore"), pending={})
case("the stay-home line names what she couldn't do", (d["path"], "hide" in r.home_line(d)), ("home", True))
r.STAYS_HOME = False
from veil import rules as _rules  # noqa: E402
case("a date already gone is past; one to come isn't", (_rules._gone("2020-01-01T10:00:00Z"), _rules._gone("2999-01-01T10:00:00Z"), _rules._gone("soon")),
     (True, False, False))
case("Response has past lines, said for a date gone by", "past_lines" in [x["name"] for x in _rules.STEPS["response"]["params"]], True)

# Oct 18, evening: a request borrowing most of a short answer isn't its echo; a value for "anything else?"
# is its answer before the echo guard; a sentence telling a fact isn't a flea's question
_short = [{"answer": "We only buy pizza at sales.", "time": time.time()}]
case("a longer request borrowing four of a short answer's six words isn't its echo (echo_cover_longest)",
     r.echo_of("Here's a brain flea to remember. We only buy Chinese food at Jade House in Douglasville.", _short), None)
case("...her short answer coming back, misheard, still is", bool(r.echo_of("We only buy pizza at sails.", _short)), True)
_ser2 = dict(_ser, offered=["due_date", "repeat"], filled={})
_asked = [{"answer": "Added Root history diagram for you. Is there anything else for this chore? I can add a due date, or repeat.", "time": time.time()}]
d = r.decide(msg("Add a due date of Friday for this chore."), pending=_ser2, turns=_asked)
case("'Add a due date of Friday for this chore.' answers her 'anything else?', though it borrows her word order",
     (d["path"], d.get("kind")), ("C", "series"))
case("a sentence telling a fact isn't asking (no flea by its key word)",
     (r.telling_a_fact("Brainfully, we only get our pizza at Jade House in Douglasville."), r.telling_a_fact("Where do we get our pizza?"),
      r.telling_a_fact("Tell me the wifi name")), (True, False, False))

# Oct 19, dump9: nodes of the same nature (a topic's apps in order; the next when one is busy)
import asyncio as _aio  # noqa: E402
from veil import phases as _ph  # noqa: E402


class _Node:
    def __init__(self, name, reply):
        self.name, self.reply, self.got = name, reply, []

    async def handle(self, said, context=(), **kw):
        self.got.append(kw.get("action"))
        return dict(self.reply) if self.reply is not None else None

    def answers(self):
        return False


_busy = _Node("first", {"status": "answered", "speech": "wait", "node_down": "busy"})
_ok = _Node("second", {"status": "answered", "speech": "1781: Yorktown"})
_had = dict(r.APPS), dict(r.NODES), r.SCORER.topics["chores"]["service"]
r.APPS.update(first=_busy, second=_ok, third=_Node("third", {"status": "answered", "speech": "also busy", "node_down": "busy"}))
for _n in ("first", "second", "third"):
    r.SERVICES.setdefault(_n, {"kind": "stand-in"})
r.NODES["chores"] = ["first", "second"]
_got = _aio.run(r.call_service("chores", "what happened today", action="today_events"))
case("dump9: the first app at its limit passes the request to the next of the same nature, which picks its own action",
     (_got["speech"], _got["service"], _busy.got, _ok.got), ("1781: Yorktown", "second", ["today_events"], [None]))
r.NODES["chores"] = ["first", "third"]
case("dump9: every one busy: the last one's answer (she says to wait)", _aio.run(r.call_service("chores", "x"))["speech"], "also busy")
case("dump9: her question goes back to the app it came from (node)", _aio.run(r.call_service("chores", "yes", node="second"))["service"], "second")
_ph.PHASES["dump9"] = False
r.SCORER.topics["chores"]["service"] = "first"
case("dump9 off: the topic's one app, busy or not (the old path)", _aio.run(r.call_service("chores", "x"))["speech"], "wait")
_ph.PHASES["dump9"] = True
r.APPS.clear(); r.APPS.update(_had[0]); r.NODES.clear(); r.NODES.update(_had[1]); r.SCORER.topics["chores"]["service"] = _had[2]

# Oct 19, dump13: the Off-Platform model says how it heard the request first
case("dump13: its HEARD: line found (markdown and quotes off), the rest is the answer; waits for the line; none without it",
     (r.heard_split("**HEARD:** \"mark it complete\"\nSure, done!"), r.heard_split("HEAR")[0], r.heard_split("HEARD: mark it")[0],
      r.heard_split("HEARD: mark it", end=True)[:2], r.heard_split("Sure, I can help")[0], r.heard_split("Hi")[0]),
     (("found", "mark it complete", "Sure, done!"), "wait", "wait", ("found", "mark it"), "none", "none"))
_body = {"messages": msg("Mark the pain the back of the hose shore done"), "stream": False}
_d = {"said": "Mark the pain the back of the hose shore done", "assistant": "iris", "why": [], "path": "gemini"}
_res = _aio.run(r.heard_at_home(_d, "Mark the paint the back of the house chore done", None, 0, _body, 0, None, False))
import json as _js  # noqa: E402
case("dump13: it heard a change answered at home: she asks first, and waits on it (heard_as)",
     (_js.loads(_res.body)["choices"][0]["message"]["content"].startswith("I think you meant"), r.pending_for("iris").get("kind")),
     (True, "heard_as"))
d = r.decide(msg("Yes."), pending={"kind": "heard_as", "said": "Mark the pain the back of the hose shore done", "meant": "Mark the paint the back of the house chore done"})
case("dump13: yes is that request, decided afresh (and the mishearing kept)", (d["path"], d.get("topic"), d.get("action"), d.get("heard_as_yes")),
     ("A", "chores", "complete", "Mark the paint the back of the house chore done"))
d = r.decide(msg("No."), pending={"kind": "heard_as", "said": "x", "meant": "y"})
case("dump13: no ends it", (d["path"], d.get("kind")), ("C", "no"))
r.clear_pending("iris", "test")
case("dump13: what it heard isn't answered at home, or is what was said: its answer goes on",
     (_aio.run(r.heard_at_home(_d, "Tell me a joke about painters", None, 0, _body, 0, None, False)),
      _aio.run(r.heard_at_home(_d, "mark the pain the back of the hose shore done", None, 0, _body, 0, None, False))), (None, None))

# Oct 19, dumps 14 to 19 (the parking lot's Wepwawet column), the router's side
case("dump14: a rule's own read length; numbers as she reads, counted across 'the rest?'",
     (r.read_list("{items}.", ["a", "b", "c", "d"], "iris", 2)[1], r.READ_LIST_NUMBERS), (["c", "d"], False))
r.READ_LIST_NUMBERS = True
case("dump14: read_list_numbers on: each with its place", r.read_list("{items}.", ["c", "d"], "iris", 2, 2)[0], "3, c and 4, d.")
r.READ_LIST_NUMBERS = False
_d17 = {"said": "what's the weather", "assistant": "iris"}
r.twin_of(_d17)
case("dump17: the same words from another device within twin_seconds: left to the first; the same device again isn't a twin",
     (r.twin_of({"said": "what's the weather", "assistant": "felix"})[0], r.twin_of({"said": "what's the weather", "assistant": "felix"})),
     ("iris", None))
r.OREAD["her_voices"] = ["Iris Voice"]
case("dump17: her own voice, the voice ID sure of it, is an echo",
     (r.her_own_voice({"speaker": "Iris Voice", "label": "known"}), r.her_own_voice({"speaker": "Beth", "label": "known"}),
      r.her_own_voice({"speaker": "Iris Voice", "label": "unknown"})), (True, False, False))
r.OREAD.pop("her_voices")
_dc = {"cpu0": 1.0, "cpu_sent": 1.25}
case("dump17: a request that went Off-Platform counts the router's CPU to the hand-off", r.cpu_used(_dc), 250.0)
case("dump16: a change claimed with no tool call is said honestly; with a tool call, or none claimed, it goes on",
     (bool(r.claimed_change("I have updated your tasks list.", [])), r.claimed_change("I have updated your tasks list.", [{"name": "x"}]),
      r.claimed_change("Paris is the capital.", [])), (True, None, None))
case("dump16: a request with one of an app's change words is held whole; a question isn't",
     (r.changes_something("Mark the spray weeds chore done"), r.changes_something("What's the capital of France?")), (True, False))
_lc = r.CONNECTORS["donetick"]
_had_items, _had_mm = _lc.cache.get("items"), _lc.match_min
_lc.match_min = 0.6
_lc.cache["items"] = [{"id": 7, "name": "Paint the fence", "nextDueDate": "2026-10-24T13:00:00Z"}]
_got = r.thing_dated("Will it rain when I paint the fence?", "weather")
case("dump18: another app's thing put as its date for an app that takes the words as said",
     (_got[0].startswith("Will it rain when I ") and "the fence" not in _got[0], "Paint the fence" in _got[1]), (True, True))
_lc.cache["items"], _lc.match_min = _had_items, _had_mm
case("dump18: an app's spoken name, else its title", r.app_spoken("chores"), (r.SERVICES["donetick"].get("spoken_name") or r.app_title("chores")))

case("dump22: Oread's own-voice mark, sure of the voice, is her own voice (no name list needed)",
     (r.her_own_voice({"speaker": "Iris voice", "label": "known", "own_voice": True}),
      r.her_own_voice({"speaker": "Iris voice", "label": "maybe", "own_voice": True}), r.her_own_voice({"speaker": "Beth", "label": "known"})),
     (True, False, False))

# Oct 20, dump23: the echoes go to Oread with the mishearings (to learn her voice as the device hears it)
import tempfile as _tf23  # noqa: E402
from types import SimpleNamespace as _ns23  # noqa: E402
from veil import activity as _act23, doors as _doors23, phases as _ph23  # noqa: E402
_had23 = (r.ACTIVITY, _doors23.door_for)
r.ACTIVITY = _act23.Activity(os.path.join(_tf23.mkdtemp(), "veil.db"))
r.ACTIVITY.add(kind="echo", path="0", heard="Here is what happened", clip="c1-felix", device="felix",
               why=["an echo of her own answer 3 s ago (0.80 of the words): not answered"])
r.ACTIVITY.add(kind="echo", path="0", heard="Good morning", clip="c2-felix", device="felix",
               why=[f"{r.BY_VOICE} (hfc female): an echo"])
r.ACTIVITY.add(kind="echo", path="0", heard="No clip here", device="felix", why=["an echo"])
r.ACTIVITY.add(kind="answer", path="1", heard="What's the weather", clip="c3-felix", device="felix")
_doors23.door_for = lambda sec, path: ("oread", {"program": "oread"})
_got23 = r.learn_mishearings(_ns23(url=_ns23(path="/learn/mishearings")))["echoes"]
case("dump23: the pull carries each echo with a clip (not other requests), newest first, found by her words or her voice",
     [(e["clip"], e["device"], e["by"], "why" in e, e["when"][:2]) for e in _got23],
     [("c2-felix", "felix", "voice", False, "20"), ("c1-felix", "felix", "words", False, "20")])
_ph23.PHASES["dump23"] = False
case("dump23 off: no echoes in the pull", "echoes" in r.learn_mishearings(_ns23(url=_ns23(path="/learn/mishearings"))), False)
_ph23.PHASES["dump23"] = True
r.ACTIVITY, _doors23.door_for = _had23

print(f"\n{'all pass' if not FAILED else str(len(FAILED)) + ' fail'}")
sys.exit(1 if FAILED else 0)
