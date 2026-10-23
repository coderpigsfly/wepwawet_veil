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
case("the person's own no after her words is the answer", r.after_echo(
     "I think I heard how the brain flea that we only buy pizza. That's not something I know here at home. Want me to ask around? No.",
     "I think I heard \"had a brain flea\". That's not something I know here at home. Want me to ask around?"), ("No", None))
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
# Oct 21, issue #25 step 5: weather(another app(the words)): the other app supplies the date (the Time add-on), the
# weather claims it (the starting copy has no calendar: the chores app's thing stands in for a feast)
_had_items = _lc.cache.get("items")
_lc.cache["items"] = [{"id": 8, "name": "Easter Sunday", "nextDueDate": "2027-03-28T00:00:00Z"}]
_e = r.thing_dated("Will it rain Easter Sunday", "weather")
case("Time: Easter Sunday is put as its date for the weather", (_e[0].startswith("Will it rain Sunday, March 28"), _e[2]), (True, "donetick"))
_had_time = r.ADDONS.services.pop("time.dated")
case("Time off: the words go as said", r.thing_dated("Will it rain Easter Sunday", "weather"), None)
r.ADDONS.services["time.dated"] = _had_time
# the chaining protocol (#25 step 6): the claimer names its blank, the add-ons with their flag on fill it or ask
import asyncio as _aio6  # noqa: E402
_asked6 = []


async def _again6(s):
    _asked6.append(s)
    return {"status": "answered", "speech": "Rain likely on Wednesday."} if "Wednesday" in s else {"status": "need", "need": "when", "about": "the picnic"}
_need6 = {"status": "need", "need": "when", "about": "the picnic"}
_had6 = list(r.ADDONS.slots.get("fill") or [])
r.ADDONS.slots["fill"] = [("asker", lambda b, c: {"ask": "You mean the picnic on Wednesday?", "choices": [{"name": "Picnic", "say": "Wednesday"}]}, {}),
                          ("filler", lambda b, c: {"words": c["said"] + " on Wednesday"}, {})]
_got6 = _aio6.run(r.chain("weather", "Is it going to rain for the picnic", dict(_need6), _again6))
case("chain: a module fills the blank, its flag goes off, and the claimer is asked again", (_got6["speech"], _asked6),
     ("Rain likely on Wednesday.", ["Is it going to rain for the picnic on Wednesday"]))
r.ADDONS.slots["fill"] = [("asker", lambda b, c: {"ask": "You mean the picnic on Wednesday?", "choices": [{"name": "Picnic", "say": "Wednesday"}]}, {})]
_got6 = _aio6.run(r.chain("weather", "Is it going to rain for the picnic", dict(_need6), _again6))
case("chain: nobody can fill it: she asks (held), and her question is saved as a clarification",
     (_got6["speech"], _got6["ask"]["kind"], _got6["ask"]["choices"][0]["name"]), (r.util.HOLD + "You mean the picnic on Wednesday?", "clarify", "Picnic"))
r.ADDONS.slots["fill"] = []
_got6 = _aio6.run(r.chain("weather", "Is it going to rain for the picnic", dict(_need6), _again6))
case("chain: no module at all: she asks when it is", r.util.unslot(_got6["speech"]), "When is the picnic?")
r.ADDONS.slots["fill"] = _had6
_p6 = {"kind": "clarify", "said": "Is it going to rain for the picnic", "about": "the picnic", "need": "when",
       "choices": [{"name": "Picnic", "say": "Wednesday"}]}
case("clarified: yes to the one offered puts its day in after the thing", r.clarified(_p6, "yes"), "Is it going to rain for the picnic on Wednesday")
import datetime as _d6  # noqa: E402
case("clarified: a day said instead is taken", r.clarified(dict(_p6, choices=[]), "it's on Saturday"),     # said as today or tomorrow near a Saturday
     "Is it going to rain for the picnic " + {0: "today", 1: "tomorrow"}.get((5 - _d6.date.today().weekday()) % 7, "on Saturday"))
case("clarified: tomorrow takes no 'on'", r.clarified(dict(_p6, choices=[]), "tomorrow"), "Is it going to rain for the picnic tomorrow")
_p6s = {"kind": "clarify", "said": "Will it snow on the Feast of Steven when I am at the picnic", "about": "the feast of steven",
        "choices": [{"name": "Saint Stephen, The First Martyr", "say": "Saturday, December 26", "replace": "the Feast of Steven"},
                    {"name": "Saint Stephen of Hungary", "say": "Monday, August 16, 2027", "replace": "the Feast of Steven"}]}
case("clarified: 'the martyr' picks one of the two; its day takes the feast's name's place",
     (r.clarified(_p6s, "the martyr"), r.clarified(_p6s, "the second one")),
     ("Will it snow on Saturday, December 26 when I am at the picnic", "Will it snow on Monday, August 16, 2027 when I am at the picnic"))
case("clarified: not an answer: none (a new request)", r.clarified(_p6, "turn on the lights"), None)
_d6 = r.decide([{"role": "user", "content": "yes"}], pending=dict(_p6, topic="weather"))
case("path C: yes to her clarification asks the weather again with the day", (_d6["path"], _d6["topic"], _d6["said"]),
     ("A", "weather", "Is it going to rain for the picnic on Wednesday"))
_dw = r.decide([{"role": "user", "content": "what's the weather tomorrow"}])
_dc = r.decide([{"role": "user", "content": "what's on my chores list"}])
case("Only the app a request involves is read live first (the chores list isn't read for the weather)",
     (r.involves(_dw), r.involves(_dc)), ({r.SCORER.topics["weather"]["service"]}, {r.SCORER.topics["chores"]["service"]}))
# Oct 21, the walkie-talkie conversation: (a) the person's words after her echo, (b) her offered thing is "that",
# (c) a thing found by the words only it has, the day or time said kept out of its name
_her = "I believe I heard you say Leave the walkie-talkie at school. Is that right?"
case("after an echo: her yes, then the person's own request",
     r.after_echo("My Chief, I believe I heard you sign Liva Walki Talking at school. Is that right? Yes. Could you change the time on that to three forty five PM?", _her),
     ("Yes", "Could you change the time on that to three forty five PM?"))
case("after an echo: a yes alone; nothing after it", (r.after_echo("Is that right? No.", _her), r.after_echo("Is that right?", _her)), (("No", None), (None, None)))
_pw = {"kind": "rule", "mode": "confirm", "topic": "chores", "action": "find", "said": "find Mara's walkie-talkie chore",
       "state": {"item": {"id": 42, "name": "Leave the walkie-talkie at school"}}, "question": _her}
_dw = r.decide([{"role": "user", "content": "My Chief, I believe I heard you sign Liva Walki Talking at school. Is that right? Yes. Could you change the time on that to three forty five PM?"}],
               pending=_pw, turns=[{"time": r.time.time(), "answer": _her}])
case("the request after her echo is decided, not dropped as her echo", (_dw["path"] != "0", _dw["said"].startswith("Could you change the time")), (True, True))
_dd = r.decide([{"role": "user", "content": "Did you change the time on that task?"}], pending=_pw)
case("her question left unanswered: the thing she offered is 'that'", _dd.get("offered"), {"topic": "chores", "id": 42, "name": "Leave the walkie-talkie at school"})
_dy = r.decide([{"role": "user", "content": "Yes, could you change the time on that to 3:45 p.m."}], pending=_pw)
case("'Yes, could you change the time on that to 3:45' to her question: the yes takes her offered chore as 'that'",
     (_dy.get("offered", {}).get("id"), _dy["said"]), (42, "could you change the time on that to 3:45 p.m."))
_dn = r.decide([{"role": "user", "content": "No, could you change the time on the mow the lawn chore to 3:45 p.m."}], pending=_pw)
case("a no first: her offered chore isn't 'that'", (_dn.get("offered"), _dn["said"].startswith("could you change")), (None, True))
case("a yes alone is not a request opening with yes", r.leading_yes("Yes please"), (None, "Yes please"))
_items = [{"id": 1, "name": "Leave the walkie-talkie at school"}, {"id": 2, "name": "Mow the lawn"}, {"id": 3, "name": "Check the pool filter"}]
case("only one thing has walkie and talkie: asked about, though half its name is under the bar",
     (dt.only_one("change the time on the walkie talkie tour", _items, dt.stop) or {}).get("id"), 1)
case("one shared word is never enough", dt.only_one("mow the field", _items, dt.stop), None)
case("the day or time said is kept out of the thing's name", dt.without_when("change the time on that to three forty five pm"), "change the time on that to")
_pq = {"kind": "offer", "topic": "chores", "action": "add", "said": "remind me to buy palms on Sunday", "offer": {"which": {"say": "Sunday"}},
       "chosen": {}, "question": "Is Sunday the day I should remind you, or the day it's due?"}
_dq = r.decide([{"role": "user", "content": "That's when I'll buy them."}], pending=_pq)
case("her which-day question takes any words as its answer (Loose language reads them): 'That's when I'll buy them'",
     (_dq["path"], (_dq.get("resume") or {}).get("answer")), ("A", "That's when I'll buy them."))
_ag = r.answer_pending(dict(_pq, offer={"time": {}}), "again", "wren")[0]
case("an answer she can't use: she asks for it another way, then her question", (_ag.endswith(_pq["question"]), len(_ag) > len(_pq["question"])), (True, True))
_mw = r.decide([{"role": "user", "content": "Mow the lawn Saturday."}], memory={"topic": "chores", "said": "add a chore", "time": time.time() - 11})
case("no seed word, no claim: 'Mow the lawn Saturday.' right after chores isn't chores' for its Saturday", (_mw["path"] != "home", _mw.get("topic")), (True, None))
_aw = r.decide([{"role": "user", "content": "Add a task to mow the lawn for Saturday."}], memory={"topic": "chores", "said": "add a chore", "time": time.time() - 11})
case("...an add said with its own word still is", (_aw["topic"], _aw.get("action")), ("chores", "add"))
# Off-Platform answers read right (#25): the reading add-ons on the stream, a sentence at a time
import json as _js  # noqa: E402
_had_slots = list(r.ADDONS.slots.get("dress") or [])
_rn = lambda text, ctx: text.replace("Henry VIII", "Henry the Eighth").replace("Louis XIV", "Louis the Fourteenth")  # noqa: E731
r.ADDONS.slots["dress"] = [("roman_numerals", _rn, {"positions": ["replace"]}),
                           ("flair", lambda text, ctx: text if ctx.get("plain") else "Behold! " + text, {"positions": ["beginning"]})]


def _ev(content=None, finish=None, tool=False):
    delta = {"content": content} if content is not None else ({"tool_calls": [{"index": 0, "function": {"name": "x"}}]} if tool else {})
    return ("data: " + _js.dumps({"id": "c1", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n").encode()
_ss = r.SpokenStream("wren")
_pieces = [_ev("King Henry "), _ev("V"), _ev("III was born"), _ev(" in 1491. Louis X"), _ev("IV came "), _ev("later."), _ev(None, "stop"), b"data: [DONE]\n\n"]
_raw = b"".join(_pieces)
_out = b"".join(b"".join(_ss.feed(_raw[i:i + 7])) for i in range(0, len(_raw), 7)) + b"".join(_ss.close())     # cut anywhere, mid-line too
_said = "".join((_js.loads(l[6:])["choices"][0]["delta"].get("content") or "") for l in _out.decode().split("\n")
                if l.startswith("data: {"))
case("an Off-Platform answer streamed in pieces is read right a sentence at a time (a numeral split across pieces too); no flair on it",
     (_said, _out.decode().rstrip().endswith("data: [DONE]")), ("King Henry the Eighth was born in 1491. Louis the Fourteenth came later.", True))
_ss2 = r.SpokenStream("wren")
_o2 = b"".join(_ss2.feed(_ev(None, tool=True))) + b"".join(_ss2.close())
case("a tool call in the stream passes as it came", _o2, _ev(None, tool=True))
case("the reading add-ons' spacing is kept: a sentence's own space and new line", r.read_right("Henry VIII.\n", "wren"), "Henry the Eighth.\n")
r.ADDONS.slots["dress"] = _had_slots
_feast_sup = {"name": "litcal", "items": [{"name": "Palm Sunday", "date": "2027-03-21T00:00:00Z"}], "name_of": lambda x: x["name"],
              "never": {"the", "of", "feast"}, "alike": {}, "anchors": set(), "weight": lambda x: 0}
case("loose language(time(...)): an add's feast day is put as its date, Loose language asking Time (it needs it)",
     r.ADDONS.services["loose_language.days"]("remind me to buy palms on Palm Sunday", dict(r.supply_ctx("x", "chores"), suppliers=[_feast_sup])),
     ("remind me to buy palms on Sunday, March 21, 2027", None))
_cake = r.ADDONS.services["loose_language.days"]("bake a cake for Palm Sunday", dict(r.supply_ctx("x", "chores"), suppliers=[_feast_sup]))
case("'for' a feast: its day put in, and the feast kept as the event the chore is done before",
     (_cake[0], {k: _cake[1][k] for k in ("name", "date", "lead")}), ("bake a cake for Sunday, March 21, 2027",
                                                                      {"name": "Palm Sunday", "date": "2027-03-21", "lead": "for"}))
_lc.cache["items"] = _had_items
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

# Oct 21, the chores study: her question to a user rule answered with a request of its own, a bare
# "okay" (the mic cut the rest off), or a name; the rule's word asked politely
_ask = {"kind": "rule", "mode": "ask", "action": "rename", "topic": "chores", "said": "rename the task me",
        "need": "_name", "question": "Which one?", "state": {"said": "rename the task me", "at": 1, "values": {}}}
d = r.decide(msg("What's on my list to do today?"), pending=_ask, turns=[])
case("to a rule's 'which one?': 'what's on my list to do today' is a request of its own",
     (d["path"], d.get("action"), d.get("pending_dropped")), ("A", "list", True))
d = r.decide(msg("Okay."), pending=_ask, turns=[])
case("to a rule's question: a bare 'okay' isn't the answer; she asks again and still waits",
     (d["path"], d.get("kind"), r.answer_pending(_ask, "again", "iris")[0].endswith("Which one?"), r.answer_pending(_ask, "again", "iris")[1]),
     ("C", "again", True, _ask))      # she asks for it another way first (Oct 21), then her question
d = r.decide(msg("Paint the back of the house"), pending=_ask, turns=[])
case("to a rule's question: a name is still the answer", (d["path"], bool(d.get("resume"))), ("A", True))
case("a rule's word asked politely is still the rule's (could you, I would like you to)",
     [dt.rule_opening(x) for x in ("could you rename paint the back of the house to x", "i would like you to rename number five",
                                   "what's on my list")], ["rename", "rename", None])

case("her own question asked back of her isn't an echo (Oct 21); her words coming back still are",
     (r.echo_of("Did you delete paint the house?", [{"answer": "It can't be undone. Delete Paint the house?", "time": time.time()}]),
      bool(r.echo_of("It can't be undone. Delete paint the house.", [{"answer": "It can't be undone. Delete Paint the house?", "time": time.time()}]))),
     (None, True))

# Oct 21, issue #19: the thing left unsaid ("What does Mara have?"): she asks in reference to what, and
# the answer goes after the verb
d = r.decide(msg("What does Mara have?"), pending={}, turns=[])
case("a question whose thing is left unsaid: she asks in reference to what", (d["path"], d.get("object_left")), ("object", ("what does mara have", "")))
d = r.decide(msg("What do I have tomorrow?"), pending={}, turns=[])
case("the day after the verb stays with it", d.get("object_left"), ("what do i have", "tomorrow"))
case("a thing said, or a request with its own object, isn't asked about",
     [r.missing_object(x) for x in ("What do I have to do today?", "What chores does Mara have?", "I have a cat.")], [None, None, None])
d = r.decide(msg("Chores."), pending={"kind": "object", "said": "What does Mara have?", "head": "what does mara have", "tail": ""}, turns=[])
case("the answer is the thing: the request decided afresh with it", (d["path"], d.get("topic"), d.get("action")), ("A", "chores", "list"))
d = r.decide(msg("No."), pending={"kind": "object", "said": "What does Mara have?", "head": "what does mara have", "tail": ""}, turns=[])
case("no to it: nothing more", (d["path"], d.get("kind")), ("C", "no"))
case("her question names the apps", r.object_question("iris").count(",") >= 1 or " or " in r.object_question("iris"), True)

d = r.decide(msg("That's very fun. Thank you."), pending={"kind": "add_name", "topic": "chores", "said": "remind you to wet me"}, turns=[])
case("to 'what should I call it?', words that aren't something to do aren't a name", d.get("pending_dropped"), True)

# Oct 21, the fifth test
case("'Could you remind me to tell ...' opens with remind: an add, not the list",
     dt.pick_action("could you remind me to tell claude this week what a good job he's doing")[0], "add")
_off = {"kind": "offer", "topic": "chores", "said": "remind me to call the vet this week", "offer": {"day": {"value": "2026-10-24"}},
        "question": "Would Saturday work for this week?"}
d = r.decide(msg("What was that? I'm sorry?"), pending=_off, turns=[])
case("a question back with no answer in it: she asks her question again, still waiting",
     (d["path"], d.get("kind"), r.answer_pending(_off, "again", "iris")[0].endswith("Would Saturday work for this week?"),
      r.answer_pending(_off, "again", "iris")[1]), ("C", "again", True, _off))
d = r.decide(msg("What are my other chores?"), pending={"kind": "list_rest", "topic": "chores", "items": ["a", "b"]}, turns=[])
case("'What are my other chores?' to 'Shall I read the rest?': the rest", (d["path"], d.get("kind")), ("C", "yes"))

# Oct 21, the seventh test
d = r.decide(msg("Remind me to tell Nora she's a squatter quatch at least six times before the weekends."), pending={}, turns=[])
case("a long sentence opening with the add's own word isn't held by the guard", (d["path"], d.get("action")), ("A", "add"))
_off2 = {"kind": "offer", "topic": "chores", "said": "remind me to wash the car", "offer": {"day": {"value": "2026-10-24"}},
         "chosen": {"day": "2026-10-27", "time": "09:00"}, "question": "Should I remind you by voice, by alert, or both?"}
d = r.decide(msg("Minded by Rock."), pending=_off2, turns=[])
case("words with no yes, no day, time or way to remind confirm nothing: she asks again", (d["path"], d.get("kind")), ("C", "again"))
d = r.decide(msg("Saturday's fine."), pending=_off2, turns=[])
case("'Saturday's fine' answers her offer", (d["path"], bool(d.get("resume"))), ("A", True))
d = r.decide(msg("Could you remind me to paint the fence this weekend?"), pending=_off2, turns=[])
case("a new request while she waits: the waiting add is finished first", (d.get("finish_offer") or {}).get("said"), "remind me to wash the car")

d = r.decide(msg("Oh, could you make it the 15th?"), pending=_off2, turns=[])
case("'Could you make it the 15th?' to her offer: an answer (a day), not a new request", (d["path"], bool(d.get("resume")), d.get("finish_offer")),
     ("A", True, None))

# Oct 22: the window (addons/window): a lost seed word, asked about before the words go out
_body = {"messages": msg("Mark the troll done")}
case("the corrected words are taken at home; words no app takes, or only by its topic word, aren't",
     (r.taken_at_home(_body, "Mark the chore done"), r.taken_at_home(_body, "I took a chore of Rome"),
      r.taken_at_home(_body, "I like the chore")), ("chores", None, None))
_win = {"kind": "heard_as", "said": "Add a chew to paint the back of the house", "meant": "Add a chore to paint the back of the house",
        "by": "window"}
d = r.decide(msg("Yes."), pending=_win, turns=[])
case("yes to the window's 'I think you meant ...': the corrected words, decided afresh, the mishearing kept",
     (d["path"], d.get("topic"), d.get("heard_as_yes"), d.get("heard_from"), (d.get("window_answer") or {}).get("answer")),
     ("A", "chores", _win["meant"], _win["said"], "yes"))
d = r.decide(msg("No."), pending=_win, turns=[])
case("no to the window's question: the words go out as heard", (d["path"], d.get("kind"), d.get("rewrite"), d["window_answer"]["answer"]),
     ("gemini", "ask_yes", _win["said"], "no"))
d = r.decide(msg("What's the weather tomorrow?"), pending=_win, turns=[])
case("a new request instead of an answer: recorded as such, handled as new", (d.get("topic"), d["window_answer"]["answer"]),
     ("weather", "new request"))
d = r.decide(msg("No."), pending=dict(_win, by=None), turns=[])
case("no to the Off-Platform model's own 'did you mean?' still does nothing, and isn't an add-on's answer",
     (d["path"], d.get("kind"), d.get("window_answer")), ("C", "no", None))
from veil import addons as _ad  # noqa: E402
_w = _ad.Addons(os.path.join(REPO, "addons"), enabled=["window"])
_ctx = {"assistant": "iris", "at_home": lambda words: r.taken_at_home(_body, words)}
case("the window with the real router: 'Add a chew to paint the back of the house' is asked about, the name apart",
     {k: v for k, v in (_w.run("before_off_platform", "Add a chew to paint the back of the house", _ctx) or {}).items()
      if k in ("meant", "head", "payload")},
     {"meant": "Add a chore to paint the back of the house", "head": "Add a chore", "payload": "paint the back of the house"})
case("the window's offer has its own words: the command, then the name in quotes, never 'I think I heard'",
     (r.phrase("router", "window_offer_split", "iris").format(head="Add a chore", payload="Pack for the shore"),
      r.phrase("router", "window_offer", "iris").format(meant="Mark the chore done")),
     ('Did you mean: Add a chore, "Pack for the shore"? Shall I?', 'Did you mean "Mark the chore done"? Shall I?'))

# #28: who can answer this? Nothing at home claimed it: each app whose find opens it is asked, read only
import asyncio as _aio28  # noqa: E402
_real_call = r.call_service
_asked = []


async def _fake_call(topic, said, context=(), action=None, **kw):
    _asked.append((topic, action))
    if "walkie" in said:
        return {"status": "answered", "speech": "Leave the walkie-talkie at school is due Friday."}
    return {"status": "answered", "speech": "I couldn't find that one.", "not_found": True}
r.call_service = _fake_call
_find = [("chores", "find", ["find"])]
_apps = r.apps_to_ask
r.apps_to_ask = lambda said: [(t, None, a, f) for t, a, f in _find] if said.lower().split()[2:3] == ["find"] or "find" in said.lower().split()[:3] else []


def _who(said, path="gemini", **more):
    d = dict({"said": said, "path": path, "why": []}, **more)
    return _aio28.run(r.who_answers(d)), d
got, d = _who("Can you find the walkie coffee tour?")
case("#28: nothing claimed it, the chores app's find is asked and finds it", ([(t, a) for t, a, _x in got], _asked[-1]),
     ([("chores", "find")], ("chores", "find")))
case("...and the why says so", d["why"][-1].endswith("chores (find): found it"), True)
got, d = _who("Can you find my car keys?")
case("#28: its find finds nothing: not the app's, on to Off-Platform", (got, d["why"][-1].endswith("not found")), ([], True))
_keep_fake = r.call_service


async def _which(topic, said, context=(), action=None, **kw):
    if "faucet" in said:
        return {"status": "answered", "speech": "Which one: Buy single hole faucet, or Fix the single hole faucet?",
                "looked_for": "single hole faucet", "ask": {"kind": "rule", "mode": "which", "choices": [
                    {"name": "Buy single hole faucet"}, {"name": "Fix the single hole faucet"}]}}
    return {"status": "answered", "speech": "Which one: Remember School Keys, or Bullet car inspection?", "looked_for": "car keys",
            "ask": {"kind": "rule", "mode": "which", "choices": [{"name": "Remember School Keys"}, {"name": "Bullet car inspection"}]}}
r.call_service = _which
got, d = _who("Can you find my car keys?")
case("#28: only parts fit two of its things (car keys: School Keys, car inspection): not claimed", got, [])
got, d = _who("Can you find the single hole faucet?")
case("#28: a tie between two of its things that both fit by enough words: claimed, she asks which",
     [x[2]["ask"]["mode"] for x in got], ["which"])


async def _one_word(topic, said, context=(), action=None, **kw):
    return {"status": "answered", "speech": "I believe I heard you say Leave the walkie-talkie at school. Is that right?",
            "ask": {"kind": "rule", "mode": "confirm"}, "looked_for": "walkie coffee tour", "found_item": "Leave the walkie-talkie at school"}
r.call_service = _one_word
got, d = _who("Can you find the walkie coffee tour?")
case("#28 (yours): one word of three fits the thing found (walkie): too few words, not claimed", (got, "too few words" in d["why"][-1]),
     ([], True))
case("#28: two words fit (Newton, medicine), or the one word said fits (Easter): claimed",
     (r.enough_words({"looked_for": "newton medicine attractive applied", "found_item": "Get Newton's Medicine at Tractor Supply"}, None),
      r.enough_words({"looked_for": "easter", "found_item": "Easter Sunday"}, None),
      r.enough_words({"looked_for": "car keys", "found_item": "Remember School Keys"}, None)), (True, True, False))
r.call_service = _keep_fake
r.call_service = _keep_fake
_asked.clear()
case("#28: words sent out by a yes or a no are never asked about again", (_who("Can you find the walkie coffee tour?", rewrite="x")[0], _asked),
     ([], []))
case("#28: only a request headed out is asked about", _who("Can you find the walkie coffee tour?", path="A")[0], [])
case("#28: a long ramble is conversation, never asked of the apps", _who("Can you find the walkie coffee tour " + "and so on " * 8)[0], [])
_find = [("chores", "find", ["find"]), ("feasts", "when_feast", ["find"])]
got, d = _who("Can you find the walkie coffee tour?")
case("#28: two apps find it: both are kept, for her which-app question", [t for t, _a, _x in got], ["chores", "feasts"])


async def _slow(*a, **k):
    await _aio28.sleep(5)
r.call_service, r.ASK_APPS_SECONDS = _slow, 0.1
_find = [("chores", "find", ["find"])]
got, d = _who("Can you find the walkie coffee tour?")
case("#28: an app that doesn't answer in time passes", (got, "no answer in" in d["why"][-1]), ([], True))
r.call_service, r.apps_to_ask, r.ASK_APPS_SECONDS = _real_call, _apps, 2.0
case("#28: the real list of apps to ask: a find rule opening the sentence; never a rule that changes something",
     ([(t, a) for t, _c, a, _f in r.apps_to_ask("Can you find the paint the back of the house chore?")],
      r.apps_to_ask("Rename the walkie coffee tour to lunch"), r.apps_to_ask("Tell me a joke")),
     ([("chores", "find")], [], []))

# #28, Oct 22 later: an app asked whether it's its own (the weather brain's claim), and a brain flea offered
class _Answers:
    def __init__(self, reply):
        self.reply, self.got = reply, None

    def claims(self):
        return True

    async def ask(self, said, context=(), claim=False):
        self.got = (said, claim)
        return self.reply


_wb = _Answers({"status": "not_mine", "reason": "not_weather"})
r.apps_to_ask = lambda said: [("weather", _wb, None, [])]
got, d = _who("Is it hot?", guarded="weather")
case("#28: a topic the guard held on purpose ('Is it hot?' alone): its app isn't asked to claim it", (got, _wb.got), ([], None))
got, d = _who("Tell me a joke")
case("#28: the weather brain is asked with claim, and says not its own", (got, _wb.got, d["why"][-1].endswith("weather: not its own")),
     ([], ("Tell me a joke", True), True))
_wb.reply = {"status": "answered", "speech": "Tomorrow will be sunny."}
got, d = _who("Will it be nice tomorrow for a walk?")
case("#28: ...and a weather question is its own, answered as it came", [(t, a, x["speech"]) for t, a, x in got],
     [("weather", None, "Tomorrow will be sunny.")])
r.apps_to_ask = _apps
_cl = r.ADDONS.services.get("brain_fleas.closest")
case("#28: a brain flea is offered only when words with a meaning fit: never by 'that', 'is', 'very' alone, or a system flea",
     (_cl("Is it going to be nice for a walk later", r.FUNCTION_WORDS), _cl("She's like well I don't know.", r.FUNCTION_WORDS),
      _cl("tell me lisas shoe size", r.FUNCTION_WORDS), _cl("delete flea", r.FUNCTION_WORDS)), (None, None, None, None))
case("#28: ...and one whose meaning words are all said is ('Talking?': who is talking to you)",
     (_cl("Talking?", r.FUNCTION_WORDS) or [""])[0], "device_who_is_speaking_to_you")

_fo = {"kind": "heard_as", "said": "tell me who is speaking right now", "meant": "who is speaking to you", "by": "brain_fleas",
       "keep": False}
d = r.decide(msg("Yes."), pending=_fo, turns=[])
case("#28: yes to a flea offered: the flea answers, and no mishearing is kept (it was never misheard)",
     (d["path"], d.get("heard_as_yes"), (d.get("window_answer") or {}).get("answer")), ("flea", None, "yes"))
d = r.decide(msg("No."), pending=_fo, turns=[])
case("#28: no to a flea offered: the words go out as heard", (d["path"], d.get("rewrite")), ("gemini", _fo["said"]))

import httpx as _hx  # noqa: E402
case("Oct 22: no answer in time is slow, a refused connection can't reach",
     (r.slow_not_down(_hx.ReadTimeout("x")), r.slow_not_down(_hx.ConnectError("x")), r.slow_not_down(_hx.ConnectTimeout("x")),
      r.phrase("router", "gemini_slow", "iris")), (True, False, False, "My helpers outside the house are slow right now."))

# Oct 22: the shoe size flea, lost twice: "Thank you." to her "Right?", and the question taken for her echo
case("a thanks to her confirmation is a yes; to anything else it isn't an answer; no thank you stays no",
     (r.confirm_kind("Thank you."), r.confirm_kind("Thanks so much, Iris."), r.answer_kind("Thank you."), r.confirm_kind("No, thank you.")),
     ("yes", "yes", None, "no"))
d = r.decide(msg("Thank you."), pending=_win, turns=[])
case("'Thank you.' to the window's 'Did you mean ...? Shall I?': yes", (d["path"], d.get("topic")), ("A", "chores"))
d = r.decide(msg("Thank you."), pending={"kind": "ask_around", "said": "tell me a joke"}, turns=[])
case("'Thank you.' to 'Want me to ask around?': not a yes", d.get("kind") == "ask_yes", False)
_her = [{"time": __import__("time").time() - 22, "answer": "I'll remember: Mara's shoe size is eight and a half. Right?"}]
case("'What's Mara's shoe size?' 22 s after her 'I'll remember: Mara's shoe size ...': a question, not her echo",
     r.echo_of("What's Mara's shoe size?", _her), None)
case("...while her own words coming back still are", bool(r.echo_of("Mara's shoe size is eight and a half right", _her)), True)

# #29: the trainer, per person (its services loaded as when it's on; a stand-in People grid)
import tempfile as _tf29  # noqa: E402
_tr = _ad.Addons(os.path.join(REPO, "addons"), enabled=["trainer"])
_trm = sys.modules["addon_trainer"]
_trm.DB = os.path.join(_tf29.mkdtemp(), "trainer.db")
r.ADDONS.services.update({k: v for k, v in _tr.services.items() if k.startswith("trainer.")})
_grid = r.people.grid
r.people.grid = lambda: {"apps": [], "rows": [{"wepwawet": "Owner", "called": []}, {"wepwawet": "Mara", "called": []},
                                               {"wepwawet": "Owen", "called": []}]}
case("#29: trainer mode said by voice: the long way, the short way, someone's, my own; never 'my trainer at the gym'",
     [r.trainer_command(x) for x in ("Trainer mode.", "Enter trainer mode", "Turn on trainer mode for Mara",
                                     "Turn on Mara's chore trainer", "Turn off my trainer mode", "My trainer at the gym said hi",
                                     "Start the dishwasher", "Training mode on for Mara.", "Training mode off.",
                                     "Turn Mara's training mode on", "Mara's training mode",
                                     "I went to the gym and my trainer mode of teaching was hard")],
     [(None, None), (None, None), ("on", "Mara"), ("on", "Mara"), ("off", "me"), None, None, ("on", "Mara"), ("off", None),
      ("on", "Mara"), (None, "Mara"), None])
d = r.decide(msg("Turn on trainer mode for Mara"), pending={}, turns=[])
case("#29: the switch is the trainer's, decided before anything else", (d["path"], d["kind"], d["turn"], d["target"]),
     ("trainer", "switch", "on", "Mara"))
case("#29: a chore said as a condition is split; a 'when' that asks isn't one",
     (r.condition_split("When Owen wakes up and asks for his chores, ask him to go to the post office again and mail my letter."),
      r.condition_split("When is the trash due?"), r.condition_split("When's the trash due?")),
     (("When Owen wakes up and asks for his chores", "ask him to go to the post office again and mail my letter."), None, None))
case("#29: her words offered as the name, the 'ask him to' taken off", r.trainer_name("ask him to go to the post office again and mail my letter."),
     "Go to the post office again and mail my letter")
_mara = {"person": "Mara", "speaker": "Mara", "label": "known"}
_d = {"said": "When Owen wakes up, ask him to go to the post office.", "path": "A", "topic": "chores", "why": []}
case("#29: trainer mode off: it never steps in", r.trainer_due(dict(_d), _mara), False)
_trm.set_on("Mara", True, "Owner")
_d1 = dict(_d, why=[])
case("#29: on for Mara, a chore said as a condition: she offers to walk it through, her words as the name",
     (r.trainer_due(_d1, _mara), _d1["trainer_offer"]["origin"], _d1["trainer_offer"]["suggest"]),
     (True, "condition", "Go to the post office"))
case("#29: ...not when the voice ID isn't sure it's her, or it's someone else",
     (r.trainer_due(dict(_d, why=[]), {"person": "Mara", "label": "maybe"}), r.trainer_due(dict(_d, why=[]), {"person": "Owen", "label": "known"})),
     (False, False))
case("#29: a request formed right: silent", r.trainer_due({"said": "Add a chore to call the plumber Friday at 9", "path": "A",
                                                           "topic": "chores", "action": "add", "why": []}, _mara), False)
case("#29: a statement nothing claims: offered; a question: silent",
     (r.trainer_due({"said": "I need the plumber called", "path": "gemini", "shape": "need", "why": []}, _mara),
      r.trainer_due({"said": "Who won the game?", "path": "gemini", "shape": "question", "why": []}, _mara)), (True, False))
_off = dict(_d1["trainer_offer"])
d = r.decide(msg("Yes."), pending=_off, turns=[])
case("#29: yes to her offer: what shall we call it, her words offered", (d["path"], d["kind"], d["trainer_next"]["mode"], d["trainer_q"]),
     ("trainer", "ask", "name", 'What shall we call it? Shall I call it "Go to the post office"?'))
d = r.decide(msg("Thank you."), pending=d["trainer_next"], turns=[])
case("#29: the name taken: what day", (d["trainer_next"]["name"], d["trainer_q"]), ("Go to the post office", "What day should it be due?"))
d = r.decide(msg("Friday."), pending=d["trainer_next"], turns=[])
case("#29: the day taken: what time", (bool(d["trainer_next"]["due_date"]), d["trainer_q"]), (True, "What time?"))
d = r.decide(msg("3 pm."), pending=d["trainer_next"], turns=[])
case("#29: the time taken: who's it for", (d["trainer_next"]["due_time"]["say"], d["trainer_q"]), ("3 pm", "Do you want to assign it to someone?"))
_last = d["trainer_next"]
d = r.decide(msg("Owen."), pending=_last, turns=[])
case("#29: who it's for: the app's own add runs with all of it", (d["path"], d.get("topic"), d.get("action"), d.get("trainer_done"),
     "go to the post office" in d["said"].lower() and " at 3 pm" in d["said"] and d["said"].endswith("for Owen")),
     ("A", "chores", "add", True, True))
d = r.decide(msg("Never mind."), pending=_last, turns=[])
case("#29: never mind ends it at any step (a dismissal: her question is dropped)", (d["path"], d["kind"]), ("0", "dismissed"))
d = r.decide(msg("Scratch that, forget it please"), pending=_last, turns=[])
case("#29: ...and a cancel inside an answer ends it too", (d["path"], d["kind"]), ("C", "no"))
d = r.decide(msg("No."), pending=dict(_off, origin="out", said="I need the plumber called"), turns=[])
case("#29: no to her offer for a statement: the words go out as heard", (d["path"], d.get("rewrite")), ("gemini", "I need the plumber called"))
d = r.decide(msg("Yes."), pending={"kind": "trainer", "mode": "toggle", "target": "Mara", "to": False}, turns=[])
case("#29: yes to 'Would you like to turn it off?': switched", (d["path"], d["kind"], d["target"], d["on"]), ("trainer", "set", "Mara", False))
case("#29: who may switch it: anyone their own; someone else's, only a changer",
     (r.trainer_may("Mara", "Mara"), r.trainer_may("Owen", "Mara")), (True, False))
r.people.grid = _grid

_trm.SET["changers"] = ["Owner"]
r.people.grid = lambda: {"apps": [], "rows": [{"wepwawet": "Owner", "called": []}, {"wepwawet": "Mara", "called": []},
                                               {"wepwawet": "Owen", "called": []}]}
_owner = {"person": "Owner", "speaker": "Owner", "label": "known"}


def _turn(who, **d):
    import json as _j
    resp = r.trainer_turn(dict({"assistant": "iris", "said": "x", "path": "trainer", "why": []}, **d), who, msg("x"),
                          __import__("time").monotonic(), False)
    return _j.loads(resp.body)["choices"][0]["message"]["content"], r.pending_for("iris")
_trm.set_on("Mara", False, "Owner")
line, p = _turn(_owner, kind="switch", turn=None, target=None)
case("#29: 'Trainer mode' from a changer: for who?", (line, p.get("mode")), ("Trainer mode for who?", "who"))
line, p = _turn(_owner, kind="switch", turn=None, target="Mara")
case("#29: ...Mara: its state, and the opposite offered", (line, p.get("mode"), p.get("to")),
     ("Trainer mode is off for Mara. Would you like to turn it on?", "toggle", True))
line, p = _turn(_owner, kind="set", target="Mara", on=True)
case("#29: ...yes: on for Mara from her next request, no restart", (line, r.ADDONS.services["trainer.is_on"]("Mara")),
     ("Trainer mode is on for Mara: chores.", True))
line, p = _turn(_owner, kind="switch", turn="on", target="Mara")
case("#29: 'Turn on trainer mode for Mara' when it's on already", line, "Trainer mode is already on for Mara.")
line, p = _turn({"person": "Owen", "label": "known"}, kind="switch", turn="off", target="Mara")
case("#29: someone who isn't a changer can't switch someone else's", line.startswith("Trainer mode for Mara can only be changed"), True)
line, p = _turn({"person": "Mara", "label": "known"}, kind="switch", turn="off", target="me")
case("#29: Mara may switch her own off: she asks first", line, "Turn off trainer mode for Mara? Say yes.")
line, p = _turn({"person": "Owner", "label": "maybe"}, kind="switch", turn="on", target="Mara")
case("#29: the voice ID not sure who's asking: left as it is", line, "I'm not sure who's asking, so I'll leave trainer mode as it is.")
r.people.grid = _grid

print(f"\n{'all pass' if not FAILED else str(len(FAILED)) + ' fail'}")
sys.exit(1 if FAILED else 0)
