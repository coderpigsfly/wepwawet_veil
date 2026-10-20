#!/usr/bin/env python3
# tests/web_test.py - Wepwawet Veil's pages and doors, end to end, against a running copy.
# Never run it against the live router: it signs up, saves settings and runs tools.
# Start a throwaway copy first (a copy of the folder, with a stand-in for LiteLLM), then:
#   python3 tests/web_test.py https://127.0.0.1:8771 http://127.0.0.1:8770 <copy's folder>
# Checks: setup and sign-in, every page's API, the change header, roles, saving settings with
# comments kept, topics, flair, people, the firewall (also on a Gemini tool call), the chat door
# (streamed and not), the activity log and the answer bank, a tool run, and the lock-out guard.

import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

WEB, CHAT, ROOT = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/"), sys.argv[3]
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
PASSED, FAILED = [], []


def opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=CTX))


ME = opener()


def call(method, path, body=None, who=ME, header=True, base=None, raw=False, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request((base or WEB) + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if header:
        req.add_header("X-Requested-With", "veil")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with who.open(req, timeout=60) as r:
            text = r.read().decode()
            return r.status, (text if raw else (json.loads(text) if text.strip()[:1] in "[{" else text))
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text


def case(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    if not ok:
        print(f"FAIL  {name} {detail}")


# ---------- setup ----------
st, d = call("GET", "/api/setup")
case("setup is needed", st == 200 and d.get("needs_setup"), d)
st, d = call("GET", "/api/overview")
case("pages need a sign-in", st == 401, st)
code = open(os.path.join(ROOT, "data", "setup-code.txt")).read().strip()
st, d = call("POST", "/api/setup", {"code": "0000-0000-0000", "name": "sam", "password": "a long password"})
case("a wrong setup code is refused", st == 403, d)
st, d = call("POST", "/api/setup", {"code": code, "name": "sam", "password": "a long password"})
case("setup makes a super user and signs in", st == 200 and d["user"]["role"] == "super", d)
st, d = call("GET", "/api/session")
case("signed in", d.get("user", {}).get("name") == "sam" and "security" in d.get("can", []), d)

# ---------- the change header ----------
st, d = call("PATCH", "/api/settings", {"path": ["read_list_max"], "value": 6}, header=False)
case("a change without X-Requested-With is refused", st == 403, d)

# ---------- every page's data ----------
for path in ("/api/overview", "/api/savings", "/api/bank/results", "/api/activity", "/api/activity?direction=out", "/api/activity?direction=gemini", "/api/bank", "/api/topics",
             "/api/sources", "/api/tools", "/api/flair", "/api/flair/iris", "/api/flair/iris/candidates",
             "/api/combing", "/api/integrations", "/api/firewall", "/api/settings", "/api/users",
             "/api/tokens", "/api/vault", "/api/access", "/api/audit", "/api/misses", "/api/mishearings", "/api/sparkle", "/api/phrases", "/api/holding"):
    st, d = call("GET", path)
    case(f"GET {path}", st == 200, f"{st} {str(d)[:200]}")
st, page = call("GET", "/", raw=True)
case("the page itself", st == 200 and "app.js" in page)
for f in ("app.js", "style.css", "veil.css", "theme.js", "icon.svg"):
    st, _ = call("GET", "/" + f, raw=True)
    case(f"static {f}", st == 200)
st, _ = call("GET", "/../settings.yaml", raw=True)
case("no files outside the page folder", st == 404)

# ---------- settings keep comments ----------
st, d = call("PATCH", "/api/settings", {"path": ["read_list_max"], "value": 6})
text = open(os.path.join(ROOT, "settings.yaml")).read()
case("a setting is saved", st == 200 and "read_list_max: 6" in text, d)
case("its comment survives", "this many are read, then the question" in text)
st, d = call("PATCH", "/api/settings", {"path": ["read_list_max"], "value": "six"})
case("a wrong kind of value is refused", st == 400, d)
st, d = call("PATCH", "/api/settings", {"path": ["topics"], "value": {}})
case("topics aren't changed on the settings page", st == 400, d)

# ---------- topics ----------
st, d = call("PUT", "/api/topics/chores", {"service": "donetick", "seed": ["chore", "chores", "todo", "task", "tasks", "list"],
                                           "always_tentative": [], "pinned": ["honey do"]})
case("a topic is saved", st == 200 and "honey do" in open(os.path.join(ROOT, "settings.yaml")).read(), d)
st, d = call("PUT", "/api/topics/sensors", {"service": "nope"})
case("a topic needs a real service", st == 400)

# ---------- flair and people ----------
st, d = call("PUT", "/api/flair/iris", {"rate": 0.5, "max_in_a_row": 2, "names": {"rate": 0.2},
                                             "flourishes": [{"text": "Let me stir the cauldron.", "slot": "opener", "topics": ["any"], "mood": ["plain"]}]})
case("flair is saved", st == 200, d)
st, d = call("GET", "/api/flair/iris")
case("flair reads back", d["personality"]["rate"] == 0.5 and d["personality"]["names"]["rate"] == 0.2, d)
st, d = call("PUT", "/api/flair/iris", {"rate": 0.5, "max_in_a_row": 2, "flourishes": [{"text": "Is it?"}]})
case("a flourish is never a question", st == 400)
st, d = call("GET", "/api/people")
case("People: the grid (Oct 17; People and names stays retired), empty to start", st == 200 and d["rows"] == [] and d["apps"] == [], d)
st, d = call("GET", "/api/combing")
case("combing as JSON", "never" in d["combing"], d)
st, d = call("PUT", "/api/combing", {"combing": dict(d["combing"], max_words=8)})
case("combing is saved", st == 200 and "max_words: 8" in open(os.path.join(ROOT, "personality", "combing.yaml")).read(), d)
import yaml  # noqa: E402
try:
    back = yaml.safe_load(open(os.path.join(ROOT, "personality", "combing.yaml")))
    case("saved combing reads back the same", back["closer_words"][0] == "good-?bye", back["closer_words"][:2])
except yaml.YAMLError as e:
    case("saved combing reads back the same", False, e)

# ---------- try it and the firewall ----------
st, d = call("POST", "/api/try", {"say": "what's the weather tomorrow", "speaker": {"speaker": "Sam", "label": "known", "score": 0.9}})
case("try it", st == 200 and d["path"] == "A" and d.get("name_sure") is True, d)
fw = {"enabled": True, "rules": [{"name": "garage", "people": ["anyone"], "devices": ["garage door"], "commands": ["unlock everything"]}]}
st, d = call("PUT", "/api/firewall", {"firewall": fw})
case("the firewall is saved and on at once", st == 200 and d.get("active"), d)


def chat(said, stream):
    body = {"model": "house-router", "stream": stream,
            "messages": [{"role": "system", "content": "Iris Personality"}, {"role": "user", "content": said}]}
    req = urllib.request.Request(CHAT + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode()
    if not stream:
        return json.loads(text)["choices"][0]["message"].get("content") or ""
    out = []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            out.append((json.loads(line[6:])["choices"][0].get("delta") or {}).get("content") or "")
    return "".join(out)


said = chat("unlock everything please", True)
case("a blocked command never leaves", "can't" in said or "not something" in said, said)
said = chat("tell me a joke about brooms", True)
case("a streamed Gemini answer", "Gemini says" in said, said)
said = chat("tell me a joke about cats", False)
case("a Gemini answer, not streamed", "Gemini says" in said, said)
said = chat("could you check on the garage", True)
case("a watched voice's Gemini tool call is stopped", "can't" in said or "not something" in said, said)
said = chat("Never mind, Iris.", True)
case("a dismissal answered at home", said and "Gemini" not in said, said)
time.sleep(0.5)
st, d = call("GET", "/api/activity?limit=20")
heard = [r["heard"] for r in d["rows"]]
case("the activity log has them", "tell me a joke about brooms" in heard and "unlock everything please" in heard, heard)
blocked = [r for r in d["rows"] if r["heard"] == "unlock everything please"]
case("the block is logged", blocked and blocked[0]["blocked"], blocked)
answered = [r for r in d["rows"] if r["heard"] == "tell me a joke about brooms"]
case("Gemini's words are logged", answered and "Gemini says" in (answered[0]["answer"] or ""), answered)
st, d = call("GET", "/api/activity?direction=out")
case("left the house shows Gemini", any(r["engine"] == "gemini" for r in d["rows"]), d)
st, d = call("GET", "/api/activity?direction=blocked")
case("transactions: the firewall's stops", d["rows"] and all(r["blocked"] for r in d["rows"]), d)
st, d = call("GET", "/api/bank")
case("the bank shows only what you added, at first nothing", d["rows"] == [], d)
st, d = call("GET", "/api/bank?review=&added=all")
keys = [r["key"] for r in d["rows"]]
case("the answer bank has the jokes", "tell me a joke about brooms" in keys, keys)
row = next(r for r in d["rows"] if r["key"] == "tell me a joke about brooms")
case("bank classifies the sentence", row["class"] in ("command", "question", "need"), row)
case("bank keeps the answer", row["answers"] and "Gemini says" in row["answers"][0]["answer"], row)
st, d = call("PATCH", f"/api/bank/{row['id']}", {"review": "promote", "note": "jokes at home?"})
case("bank review", st == 200 and d["review"] == "promote", d)
st, d = call("PUT", "/api/firewall", {"firewall": {"enabled": True, "rules": [{"name": "guard test", "people": ["anyone"]}]}})
case("a rule that stops nothing is refused", st == 400 and "stops nothing" in d.get("detail", ""), d)
call("PUT", "/api/firewall", {"firewall": {"enabled": False, "rules": []}})

# ---------- Home Assistant's own commands (what veil_guard_service asks) ----------


def guard(path, body=None):
    req = urllib.request.Request(CHAT + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


case("guard: nothing to ask about with the firewall off", guard("/firewall/summary")["ask"] is False)
case("guard: off means allow", guard("/firewall/check", {"intent": "HassTurnOff", "domains": ["lock"]})["allow"] is True)
call("PUT", "/api/firewall", {"firewall": {"enabled": True, "rules": [
    {"name": "locks", "people": ["unknown"], "domains": ["lock"], "intents": ["HassTurnOn:cover"], "message": "Ask a grown-up."}]}})
case("guard: rules mean ask", guard("/firewall/summary")["ask"] is True)
d = guard("/firewall/check", {"intent": "HassTurnOff", "targets": ["front door", "lock.front_door"], "domains": ["lock"],
                              "text": "unlock the front door", "device_name": "Iris tablet", "platform": "conversation"})
case("guard: an unknown voice may not work a lock", d["allow"] is False and d["message"] == "Ask a grown-up.", d)
case("guard: the satellite is Iris", d.get("assistant") == "iris", d)
d = guard("/firewall/check", {"intent": "HassTurnOn", "targets": ["kitchen light"], "domains": ["light"], "text": "kitchen light on"})
case("guard: a light is fine", d["allow"] is True, d)
d = guard("/firewall/check", {"intent": "HassTurnOn", "targets": ["garage"], "domains": ["cover"], "text": None})
case("guard: a Gemini tool call on a cover", d["allow"] is False, d)
st, d = call("GET", "/api/activity?limit=10")
case("guard: Home Assistant's commands are in the activity log",
     any(r["engine"] == "home_assistant" and r["blocked"] for r in d["rows"]), [r["heard"] for r in d["rows"]][:5])
call("PUT", "/api/firewall", {"firewall": {"enabled": False, "rules": []}})

# ---------- the bank: what Gemini did, and answering from it ----------
TOOLS = [{"type": "function", "function": {"name": "HassTurnOn", "parameters": {}}},
         {"type": "function", "function": {"name": "HassTurnOff", "parameters": {}}}]


def raw_chat(messages, stream=True):
    body = {"model": "house-router", "stream": stream, "tools": TOOLS, "messages": messages}
    req = urllib.request.Request(CHAT + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode()
    words, calls = [], []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            delta = json.loads(line[6:])["choices"][0].get("delta") or {}
            words.append(delta.get("content") or "")
            for tc in delta.get("tool_calls") or []:
                if (tc.get("function") or {}).get("name"):
                    calls.append(tc)
    return "".join(words), calls


def garage_round():
    msgs = [{"role": "system", "content": "Iris Personality"}, {"role": "user", "content": "please open the garage"}]
    said, calls = raw_chat(msgs)
    if not calls:
        return said, calls, None
    msgs += [{"role": "assistant", "content": None, "tool_calls": calls},
             {"role": "tool", "tool_call_id": calls[0].get("id", "t1"),
              "content": json.dumps({"response_type": "action_done", "speech": {}})}]
    final, _ = raw_chat(msgs)
    return said, calls, final


_fw = call("GET", "/api/firewall")[1]["firewall"]
call("PUT", "/api/firewall", {"firewall": dict(_fw, off_platform_never=[])})      # the bank cases below: let it through
for _ in range(2):
    _, calls, final = garage_round()
case("bank: the Off-Platform tool call passes through", bool(calls) and "Gemini says" in (final or ""), (calls, final))
case("Tool rounds: at the cap (1) the cloud model's tools are taken away, words only", "(words only)" in (final or ""), final)
_msgs = [{"role": "system", "content": "Iris Personality"}, {"role": "user", "content": "please open the garage"}]
for _i in range(2):
    _msgs += [{"role": "assistant", "content": None, "tool_calls": calls},
              {"role": "tool", "tool_call_id": "t%d" % _i, "content": json.dumps({"response_type": "action_done", "speech": {}})}]
_said, _calls = raw_chat(_msgs)
case("Tool rounds: past the cap nothing more goes out; she asks to hear it again", not _calls and ("repeat" in _said or "say it again" in _said), (_said, _calls))
st, d = call("GET", "/api/bank/results")
top = (d.get("results") or [{}])[0]
case("bank: what Gemini did, counted, with the words", top.get("count") == 2 and "HassTurnOn" in top.get("sig", "")
     and any(v["heard"] == "please open the garage" for v in top.get("variants", [])), top)
case("bank: and what she said after it", "Gemini says" in (top.get("final") or ""), top)
st, d = call("PATCH", "/api/settings", {"path": ["activity", "bank_answers_kept"], "value": 0})
case("answers kept can be 0: the bank keeps none, and still counts (Oct 15)", st == 200, d)
st, d = call("PATCH", "/api/settings", {"path": ["activity", "bank_answers_kept"], "value": -1})
case("answers kept is never below 0", st == 400, d)
call("PATCH", "/api/settings", {"path": ["activity", "bank_answers_kept"], "value": 5})
st, d = call("PATCH", "/api/settings", {"path": ["activity", "bank_use_from"], "value": 1.5})
case("the formula: U is a share", st == 400, d)
call("PATCH", "/api/settings", {"path": ["activity", "bank_answers_kept"], "value": 2})     # T 2
call("PATCH", "/api/settings", {"path": ["activity", "bank_use_from"], "value": 0.2})       # U 20%
call("PATCH", "/api/settings", {"path": ["activity", "answer_from_bank"], "value": True})
said, calls, final = garage_round()                                                        # trip 3
st, d = call("GET", "/api/activity?limit=10")
case("bank: not added, so still Off-Platform", not any(r["engine"] == "bank" for r in d["rows"]), [(r["heard"], r["engine"]) for r in d["rows"]])
st, d = call("GET", "/api/activity?direction=gemini&search=garage")
g = next((r for r in d["rows"] if r["heard"] == "please open the garage"), None)
case("transactions: an Off-Platform request can be added", g and g["bank_id"] and not g["in_bank"] and g["sent_to"], g)
st, d = call("POST", "/api/bank/add", {"activity_id": g["id"]})
case("Add puts it in the bank", st == 200 and d.get("added"), d)
st, d = call("GET", "/api/activity?direction=gemini&search=garage")
case("transactions: it now shows in the bank", any(r["id"] == g["id"] and r["in_bank"] for r in d["rows"]), d)
st, d = call("GET", "/api/activity?direction=home&limit=1")
st2, d2 = call("POST", "/api/bank/add", {"activity_id": d["rows"][0]["id"]}) if d["rows"] else (400, {})
case("Add refuses a request answered at home", st2 == 400, d2)
st, d = call("GET", "/api/bank")
mine = [r for r in d["rows"] if r["heard"] == "please open the garage"]
case("the bank: heard, trips, N / T = Q; a device command is never kept, so not usable (Oct 14)",
     mine and (mine[0]["personality"], mine[0]["trips"], mine[0]["n"], mine[0]["t"], mine[0]["q"], mine[0]["usable"], mine[0]["answers"])
     == ("iris", 3, 2, 2, 1.0, False, []), mine)
said, calls, final = garage_round()                                                        # Q 100%, but no words kept
st, d = call("GET", "/api/activity?limit=5")
case("bank: a device command is never handed out from the bank: Off-Platform as usual", not any(r["engine"] == "bank" for r in d["rows"]),
     [(r["heard"], r["engine"]) for r in d["rows"]])
case("bank: Home Assistant still gets the device command (from Gemini)", bool(calls) and calls[0]["function"]["name"] == "HassTurnOn", calls)
st, d = call("GET", "/api/bank")
mine = [r for r in d["rows"] if r["heard"] == "please open the garage"]
case("bank: that was a trip, and the bank answered nothing", mine and (mine[0]["trips"], mine[0]["used"]) == (4, 0), mine)
# Oct 19, dump16: the Off-Platform model never works a lock, the alarm or the garage door, whoever spoke
call("PUT", "/api/firewall", {"firewall": dict(_fw, off_platform_never=["lock", "alarm", "garage door"])})
_said, _calls, _ = garage_round()
case("dump16: the Off-Platform model's garage door command is stopped (off_platform_never), said honestly",
     (_calls, "won't work that" in _said), ([], True))
# a spoken answer from the bank
for _ in range(2):
    chat("tell me a joke about cats", True)
st, d = call("GET", "/api/activity?direction=gemini&search=cats")
cats = d["rows"][0]
call("POST", "/api/bank/add", {"activity_id": cats["id"]})
said = chat("tell me a joke about cats", True)
st, d = call("GET", "/api/activity?limit=1")
case("bank: a spoken answer from the bank", d["rows"][0]["engine"] == "bank" and "joke about cats" in said, (said, d["rows"][0]))
st, d = call("GET", "/api/activity?limit=100&handled=hide&search=cats")
case("Transactions: once a saying is banked, none of its rows stay on the list to look at (Oct 14)",
     not any(r["in_bank"] for r in d["rows"]), [(r["id"], r["marked"], r["in_bank"]) for r in d["rows"]])
st, d = call("GET", "/api/activity?limit=100&handled=only&search=cats")
case("Transactions: they're under handled", any(r["id"] != cats["id"] and r["in_bank"] for r in d["rows"]) and any(r["id"] == cats["id"] for r in d["rows"]),
     [(r["id"], r["marked"], r["in_bank"]) for r in d["rows"]])
st, d = call("GET", "/api/activity?limit=500&handled=all&sort=heard&order=asc")
_h = [(r["heard"] or "").lower() for r in d["rows"] if r["heard"] is not None]
case("Transactions: sorted by a column (heard, A to Z)", st == 200 and _h == sorted(_h) and len(_h) > 3, _h[:8])
st, d = call("GET", "/api/activity?limit=500&handled=all&sort=heard&order=desc")
_h2 = [(r["heard"] or "").lower() for r in d["rows"] if r["heard"] is not None]
case("Transactions: and the other way", _h2 == sorted(_h2, reverse=True), _h2[:8])
st, d1 = call("GET", "/api/activity?limit=3&handled=all&sort=assistant&order=asc")
st, d2 = call("GET", "/api/activity?limit=3&handled=all&sort=assistant&order=asc&offset=3")
st, d3 = call("GET", "/api/activity?limit=6&handled=all&sort=assistant&order=asc")
case("Transactions: the next page of a sort follows on (offset)", [r["id"] for r in d1["rows"] + d2["rows"]] == [r["id"] for r in d3["rows"]],
     ([r["id"] for r in d1["rows"] + d2["rows"]], [r["id"] for r in d3["rows"]]))
for _k in ("speaker", "went", "said", "time"):
    st, d = call("GET", f"/api/activity?limit=5&sort={_k}&order=asc")
    case(f"Transactions: sorts by {_k}", st == 200, d)
st, d = call("GET", "/api/activity?limit=5&sort=nonsense")
case("Transactions: an unknown sort is newest first", st == 200 and [r["id"] for r in d["rows"]] == sorted([r["id"] for r in d["rows"]], reverse=True), d)
st, d = call("GET", "/api/bank?personality=felix")
case("bank: each personality's own", all(r["personality"] == "felix" for r in d["rows"]), d)
st, d = call("GET", "/api/savings?days=1")
case("savings: counted", st == 200 and d["trips_saved"] >= 1 and d["tokens_saved"] == d["trips_saved"] * d["tokens_per_request"], d)
call("PATCH", "/api/settings", {"path": ["activity", "answer_from_bank"], "value": False})
st, d = call("POST", "/api/bank/trim")
case("bank: trim runs", st == 200 and "trimmed" in d, d)
st, d = call("POST", "/api/bank/export")
_bk = (yaml.safe_load(open(os.path.join(ROOT, "learn", "bank.yaml"))) or {}).get("bank") or [] if st == 200 else []
case("bank: Export writes learn/bank.yaml, every saying with its answers", st == 200 and d["sayings"] == len(_bk) > 0
     and any(x["added"] and x["answers"] for x in _bk) and all("heard" in x and "trips" in x for x in _bk), (d, _bk[:1]))
_one = call("GET", "/api/bank?added=all")[1]["rows"][0]
st, d = call("PATCH", f"/api/bank/{_one['id']}", {"generic": True})
st2, d2 = call("GET", "/api/bank?added=all")
case("bank: Generic is set from the page and shown", st == 200 and any(r["id"] == _one["id"] and r["generic"] == 1 for r in d2["rows"]), d)
call("PATCH", f"/api/bank/{_one['id']}", {"generic": False})

# ---------- transactions: Delete, Misheard; Stats ----------
import yaml as _y  # noqa: E402
st, d = call("GET", "/api/activity?direction=home&limit=3")
right = d["rows"][0]
st, d = call("POST", f"/api/activity/{right['id']}/misheard", {"said": "the weather tomorrow"})
case("Misheard: filed under what was really said", st == 200 and d["recorded"]["meant"] == "the weather tomorrow"
     and d["recorded"]["heard"] == right["heard"] and d["recorded"]["count"] == 1, d)
mm = (_y.safe_load(open(os.path.join(ROOT, "learn", "mishearings.yaml"))) or {}).get("mishearings") or []
case("Misheard: in learn/mishearings.yaml, the heard line under the intention, no answer kept",
     any(p["meant"] == "the weather tomorrow" and any(c["said"] == right["heard"] and "answer" not in c for c in p["heard"]) for p in mm), mm)
mo = (_y.safe_load(open(os.path.join(ROOT, "learn", "misses.yaml"))) or {}).get("misses") or []
case("Misheard: not in the engine miss log", not any(m.get("heard") == right["heard"] for m in mo), mo[-1:])
st, d = call("GET", "/api/activity?limit=50")
case("Misheard: the row is marked", any(r["id"] == right["id"] and r["marked"] == "misheard" for r in d["rows"]), "")
st, d = call("GET", "/api/activity?limit=100&handled=hide")
case("Handled: hidden by default once misheard or banked", not any(r["id"] in (right["id"], g["id"]) for r in d["rows"]), "")
st, d = call("GET", "/api/activity?limit=100&handled=only")
case("Handled: shown on asking", {right["id"], g["id"]} <= {r["id"] for r in d["rows"]} and all(r["marked"] or r["in_bank"] for r in d["rows"]), "")
st, d = call("POST", f"/api/activity/{right['id']}/misheard", {"said": "The weather, tomorrow?"})
case("Misheard again, same intention in other capitals: counted up under it", st == 200 and d["recorded"]["count"] == 2
     and d["recorded"]["meant"] == "the weather tomorrow", d)
other = [r for r in call("GET", "/api/activity?limit=100&handled=all")[1]["rows"] if r.get("heard") and r["heard"] != right["heard"]]
st, d = call("POST", f"/api/activity/{other[0]['id']}/misheard", {})
case("Misheard with nothing typed: waits under not given yet", st == 200 and d["recorded"]["meant"] is None, d)
st, d = call("GET", "/api/mishearings")
first = d["mishearings"][0] if d["mishearings"] else {}
mine = next((p for p in d["mishearings"] if p["meant"] == "the weather tomorrow"), None)
case("Mishearings: not given yet comes first", first.get("meant") is None and any(c["said"] == other[0]["heard"] for c in first.get("heard", [])), first)
case("Mishearings: the intention with its total, each heard line with its count, the differing words and a verdict",
     mine and mine["total"] == 2 and mine["heard"][0]["count"] == 2 and mine["heard"][0].get("verdict")
     and any(x["op"] != "same" for x in mine["heard"][0]["diff"]), mine)
st, d = call("POST", "/api/mishearings/meant", {"heard": other[0]["heard"], "meant": "the weather tomorrow"})
case("Mishearings: typing what was said files it under that intention, adding to its total", st == 200 and d["total"] == 3, d)
st, d = call("GET", "/api/mishearings")
case("Mishearings: an intention with nothing left under it goes", not any(p["meant"] is None for p in d["mishearings"]), d)
st, d = call("POST", "/api/mishearings/meant", {"heard": right["heard"], "meant": "what is the weather tomorrow"})
case("Mishearings: Move takes it, count and all, to another intention", st == 200 and d["total"] == 2, d)
st, d = call("POST", "/api/mishearings/meant", {"heard": right["heard"], "meant": "  "})
case("Mishearings: an empty intention is refused", st == 400, d)
st, d = call("POST", "/api/mishearings/swap", {"heard": "who taught you four", "meant": "who taught you that", "line": "Who taught you three?"})
st2, d2 = call("POST", "/api/mishearings/swap", {"heard": "who taught you three", "meant": " ", "line": "Who taught you three?"})
st3, d3 = call("POST", "/api/mishearings/swap", {"heard": "taught you three", "meant": "taught you that", "line": "Who taught you three?"})
case("Mishearings: Use a phrase keeps a run of words found in what was heard; one not there, or nothing meant, refused",
     (st, st2, st3) == (400, 400, 200) and {"heard": "taught you three", "meant": "taught you that"} in [{k: x[k] for k in ("heard", "meant")} for x in d3["swaps"]]
     and all(x["added"] for x in d3["swaps"] if x["heard"] == "taught you three"), (d, d2, d3))
call("POST", "/api/mishearings/swap", {"heard": "taught you three", "meant": "taught you that", "on": False})
st, d = call("POST", "/api/mishearings/drop", {"heard": right["heard"]})
st2, d2 = call("GET", "/api/mishearings")
case("Mishearings: Drop takes out that one, not the others", st == 200
     and not any(c["said"] == right["heard"] for p in d2["mishearings"] for c in p["heard"])
     and any(c["said"] == other[0]["heard"] for p in d2["mishearings"] for c in p["heard"]), d2)
st, d = call("POST", "/api/mishearings/drop", {"heard": right["heard"]})
case("Mishearings: dropping it twice says so", st == 404, d)
call("POST", "/api/mishearings/drop", {"heard": other[0]["heard"]})
st, d = call("GET", "/api/misses")
case("Misses: the engine misses only", st == 200 and all(m["kind"] != "misheard" for m in d["misses"]), d)
st, d = call("DELETE", f"/api/activity/{right['id']}")
case("Delete takes a transaction out", st == 200, d)
st, d = call("GET", "/api/activity?limit=100")
case("Delete: it's gone", not any(r["id"] == right["id"] for r in d["rows"]), "")
st, d = call("DELETE", f"/api/activity/{right['id']}")
case("Delete: twice is a 404", st == 404, d)
st, d = call("GET", "/api/stats?days=1")
routes = {x["route"]: x for x in d.get("time_routes", [])}
case("Stats: counts and Time Routes", st == 200 and d["last_day"]["total"] > 0 and "off_platform" in routes
     and routes["off_platform"]["hops"].get("t_engine") and routes["off_platform"]["hops"].get("t_decide"), d)
sh = d.get("shares") or {}
case("Stats: where answered, by day, by assistant (for the charts)", sum(sh.get("where", {}).values()) > 0
     and sh.get("by_day") and set(sh["where"]) == {"home", "bank", "off_platform", "blocked"}
     and sum(x[1] for x in sh.get("by_assistant", [])) == sum(sh["where"].values()), sh)
tr = d.get("trend") or {}
case("Stats: is anything slow (each route today, 7 and 30 days)", tr.get("routes") and all("slow" in r and len(r["by_day"]) == len(tr["days"]) for r in tr["routes"])
     and any(r["route"] == "off_platform" and r["today"] for r in tr["routes"]), tr)
case("Stats: her words after a device command are Off-Platform too", not any(r["route"] == "off_platform_after_command" for r in d["time_routes"]), "")
case("Stats: the router's CPU for each request", routes["off_platform"]["hops"].get("cpu_ms") and d["top_cpu"] and d["top_cpu"][0]["cpu_max"] >= d["top_cpu"][-1]["cpu_max"], d.get("top_cpu"))
case("Stats: what the router costs to run", d["resources"]["now"]["memory_mb"] > 0 and d["resources"]["now"]["cores"] >= 1, d.get("resources"))
st, d2 = call("GET", "/api/stats?days=1&assistant=felix")
case("Stats: one assistant at a time", st == 200 and d2["assistant"] == "felix"
     and sum(d2["shares"]["where"].values()) < sum(d["shares"]["where"].values()), d2.get("shares"))
st, d = call("GET", "/api/stats?days=7&tz=-240")
case("Stats: days in the viewer's time zone", st == 200 and all(len(x["day"]) == 10 for x in d["shares"]["by_day"]), d.get("shares"))
st, d = call("GET", "/api/session")
case("Session: the password rule and the assistants come from the router", isinstance(d.get("password_min_length"), int)
     and "iris" in d.get("assistants", []), d)
st, d = call("GET", "/api/guide/users", raw=True)
case("Guides: the user's guide, with the routes", st == 200 and "The routes a request can take" in str(d), str(d)[:80])
st, d = call("GET", "/api/settings")
case("Settings: in sections, with what each setting does", st == 200 and len(d.get("sections") or []) >= 5 and len(d.get("comments") or {}) > 20,
     [x["title"] for x in d.get("sections") or []])

# ---------- people from Home Assistant ----------
call("PUT", "/api/vault/ha_token", {"value": "ha-long-lived-token-for-tests"})
st, d = call("GET", "/api/session")
case("Vault: a saved key shows the restart bar", "vault: ha_token" in d.get("restart_needed", []), d.get("restart_needed"))
st, d = call("GET", "/api/vault")
case("Vault: the LiteLLM key is one it asks for", any(w["name"] == "OFF_PLATFORM_KEY" and w["from"] == ".env" for w in d.get("wanted", [])), d.get("wanted"))
st, d = call("PATCH", "/api/integrations/home_assistant", {"url": "http://127.0.0.1:4999", "token": "HA_TOKEN"})
case("Home Assistant's address is saved", st == 200, d)
st, d = call("POST", "/api/integrations/home_assistant/test")
case("Home Assistant answers the test", d.get("ok") is True, d)
import yaml as _y  # noqa: E402
case("The starting settings carry an empty people grid (Oct 17), not the old people: section",
     (_y.safe_load(open(os.path.join(ROOT, "settings.yaml"))) or {}).get("people") == {"apps": [], "rows": []}, "")
st, d = call("GET", "/api/people/home_assistant")
case("Home Assistant's People are no longer read (nothing used the link)", st == 404, d)

# ---------- Oread in the audio path (Wyoming) ----------
st, d = call("PATCH", "/api/integrations/oread", {"source": "wyoming", "wyoming": {"host": "192.168.1.20", "connect_timeout": 2,
             "devices": {"iris": {"listen": 10413, "oread": 10313}, "felix": {"listen": 10412, "oread": 10312}}}})
case("Wyoming ports are saved", st == 200, d)
w = (_y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["integrations"]["oread"]).get("wyoming") or {}
case("Wyoming ports in settings.yaml", w.get("devices", {}).get("felix") == {"listen": 10412, "oread": 10312} and w.get("connect_timeout") == 2, w)
case("Wyoming: the comments stay", "Oread's address" in open(os.path.join(ROOT, "settings.yaml")).read(), "")
st, d = call("PATCH", "/api/integrations/oread", {"wyoming": {"devices": {"iris": {"listen": 8771, "oread": 10313}}}})
case("Wyoming: a port already taken is refused", st == 400, d)
st, d = call("PATCH", "/api/integrations/oread", {"wyoming": {"host": "http://x"}})
case("Wyoming: the host is an address, not a URL", st == 400, d)
st, d = call("PATCH", "/api/integrations/oread", {"source": "telepathy"})
case("Wyoming: unknown sources are refused", st == 400, d)
st, d = call("GET", "/api/integrations")
case("integrations show the open Wyoming ports", d["oread"].get("listening") == [] and d["oread"]["source"] == "wyoming", d["oread"])
case("integrations: titles come from the settings, not the code", d["services"]["donetick"]["title"] and d["services"]["donetick"]["connector"], d["services"]["donetick"])

# ---------- integrations: the same tabs for every app ----------
st, d = call("GET", "/api/integrations/donetick/details")
case("Donetick's tabs: options, clean-up words, voice map", st == 200 and "nag_max" in d["options"] and "never_in_names" in d["language"]
     and any(a["name"] == "list" for a in d["actions"]) and d["language_notes"]["never_in_names"], {k: d.get(k) for k in ("connector", "doors")})
words = d["language"]["me_words"] + ["us"]
st, d = call("PUT", "/api/integrations/donetick/language", {"key": "me_words", "value": words})
hand = _y.safe_load(open(os.path.join(ROOT, "connectors", "donetick.yaml")))
case("Clean-up words are saved to the connector file, comments kept", st == 200 and hand["language"]["me_words"][-1] == "us"
     and "# words that mean the person speaking" in open(os.path.join(ROOT, "connectors", "donetick.yaml")).read(), d)
st, d = call("PUT", "/api/integrations/donetick/language", {"key": "undo_names", "value": ["a list"]})
case("Clean-up words keep their shape", st == 400, d)
st, d = call("PATCH", "/api/integrations/donetick", {"spec_prefix": "/{domain}/v1"})
st2, d2 = call("PATCH", "/api/integrations/donetick", {"spec_prefix": "no slash"})
case("An app's spec prefix is saved (the start its spec's paths have but its address doesn't); a wrong one refused",
     (st, _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["services"]["donetick"].get("spec_prefix"), st2), (200, "/{domain}/v1", 400))
call("PATCH", "/api/integrations/donetick", {"spec_prefix": ""})
st, d = call("PATCH", "/api/integrations/donetick/options", {"key": "nag_max", "value": 4})
st2, d2 = call("PATCH", "/api/integrations/donetick/options", {"key": "nag_max", "value": "lots"})
case("Options save, and keep their kind", st == 200 and st2 == 400 and _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["services"]["donetick"]["options"]["nag_max"] == 4, (d, d2))
st, d = call("GET", "/api/integrations/home_assistant/details")
case("Home Assistant asks the router like any app: its door", st == 200 and [x["name"] for x in d["doors"]] == ["guard"], d)
st, d = call("GET", "/api/integrations/litellm/details")
case("LiteLLM asks through the chat door", [x["name"] for x in d["doors"]] == ["chat"], d)
st, d = call("GET", "/api/integrations/oread/details")
case("Oread asks the router through its own door: the mishearings (Oct 17)", st == 200 and [x["name"] for x in d["doors"]] == ["oread"], d)

# ---------- adding an app we didn't write ----------
# step 1: its key in the vault, with the program it's for
st, d = call("PUT", "/api/vault/mealie_token", {"value": "abc123456", "service": "mealie"})
st, d = call("GET", "/api/vault")
case("Grantors: a key added for a program not set up yet shows as its grantor",
     any(w["name"] == "MEALIE_TOKEN" and w["for"] == "mealie" for w in d.get("wanted", [])), d.get("wanted"))
st, d = call("PUT", "/api/topics/recipes", {"service": "", "seed": ["recipe", "recipes"], "always_tentative": [], "pinned": []})
case("A topic can wait for an app", st == 200 and _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["topics"]["recipes"]["service"] == "", d)
st, d = call("GET", "/api/integrations/add-choices")
case("Add an app offers the unused keys (with their program), the topics no app answers first, then the others (another of the same nature)",
     st == 200 and {"name": "MEALIE_TOKEN", "for": "mealie"} in d["keys"] and "DONETICK_TOKEN" not in [k["name"] for k in d["keys"]]
     and d["topics"][0] == "recipes" and "chores" in d["topics"][1:], d)
st, d = call("POST", "/api/integrations", {"name": "mealie2", "kind": "openapi", "url": "http://127.0.0.1:4999/api",
                                           "spec": "http://127.0.0.1:4999/swagger/doc.json", "topic": "chores"})
_s = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))
case("Add an app: a topic another app answers takes it after that one, of the same nature (topics: then:)",
     st == 200 and _s["topics"]["chores"]["service"] == "donetick" and _s["topics"]["chores"]["then"] == ["mealie2"], d)
_t = next(t for t in call("GET", "/api/topics")[1]["topics"] if t["name"] == "chores")
st, d = call("PUT", "/api/topics/chores", dict({k: _t[k] for k in ("service", "seed", "always_tentative", "pinned")}, then=["nosuch"]))
case("A topic's then lists only apps", st == 400, d)
st, d = call("PUT", "/api/topics/chores", dict({k: _t[k] for k in ("service", "seed", "always_tentative", "pinned")}, then=[]))
case("A topic's then emptied is taken out", st == 200 and "then" not in _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["topics"]["chores"], d)
st, d = call("POST", "/api/integrations", {"name": "mealie", "title": "Mealie (recipes)", "kind": "openapi",
                                           "url": "http://127.0.0.1:4999/api", "spec": "http://127.0.0.1:4999/swagger/doc.json",
                                           "secret": "MEALIE_TOKEN", "topic": "recipes"})
_s = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))
case("Add an app: saved switched off, with an empty voice map, and its topic is now its own", st == 200 and d["made"] == ["connectors/mealie.yaml"]
     and _s["services"]["mealie"]["enabled"] is False and _s["topics"]["recipes"]["service"] == "mealie"
     and _y.safe_load(open(os.path.join(ROOT, "connectors", "mealie.yaml")))["service"] == "mealie", d)
st, d = call("GET", "/api/integrations/add-choices")
case("Add an app: a key once used isn't offered again; its topic is offered only as one with an app", "MEALIE_TOKEN" not in [k["name"] for k in d["keys"]]
     and d["topics"].index("recipes") >= len([t for t in d["topics"] if t not in ("chores", "weather", "recipes")]), d)
st, d = call("POST", "/api/integrations", {"name": "mealie", "kind": "openapi", "url": "http://x", "spec": "http://x"})
case("Add an app: a name used twice is refused", st == 400, d)
st, d = call("GET", "/api/integrations/mealie/ready")
case("Getting ready: what's left for a new app (its spec not read yet)", st == 200 and not d["ready"]
     and d["steps"][0]["done"] and d["steps"][1]["step"].startswith("Its commands") and not d["steps"][1]["done"], d)

# step 3: its commands, read from its spec
st, d = call("GET", "/api/integrations/mealie/commands")
case("Commands: nothing until its spec is read", st == 200 and not d["saved"] and d["commands"] == [], d)
st, d = call("POST", "/api/integrations/mealie/commands/read")
case("Commands: the first read is saved at once", st == 200 and d["first"] and d["count"] == 3
     and os.path.exists(os.path.join(ROOT, "connectors", "mealie.commands.json")), d)
st, d = call("GET", "/api/integrations/mealie/commands")
post = next((c for c in d["commands"] if c["api"] == "POST /recipes"), {})
dele = next((c for c in d["commands"] if c["api"] == "DELETE /recipes/{id}"), {})
case("Commands: each with what the app requires (body fields, path parameters)", post.get("requires") == ["body: name"]
     and dele.get("requires") == ["path: id"] and d["title"] == "Stand-in recipes", d)
st, d = call("POST", "/api/integrations/mealie/commands/read")
case("Commands: read again with nothing changed", st == 200 and d["changes"] == 0 and not d["version_changed"], d)
st, d = call("GET", "/api/integrations/mealie/commands")
case("Commands: the app's version, accepted and running now, from its own spec", (d["version"], d["running"], d["version_changed"]) == ("1", "1", False) and d["checked_at"], d)
_cf = os.path.join(ROOT, "connectors", "mealie.commands.json")
_keep = open(_cf).read()
_j = json.loads(_keep)
_j.pop("version", None)
_j["checked"] = dict(_j.get("checked") or {}, version="9")
open(_cf, "w").write(json.dumps(_j))
st, d = call("GET", "/api/integrations/mealie/commands")
case("Commands: accepted before versions were recorded is not flagged as a change (Oct 14)", st == 200 and not d["version_changed"], d)
open(_cf, "w").write(_keep)

# step 4: the voice map, on the page
st, d = call("PUT", "/api/integrations/mealie/actions", {"actions": [
    {"name": "list", "api": "GET /recipes", "words": ["what", "show"], "needs": {}},
    {"name": "toss", "api": "DELETE /recipes/{id}", "words": ["delete"], "needs": {"recipe": "required"}},
    {"name": "add", "api": "POST /recipes", "words": ["add", "save"], "needs": {"name": "required", "when": "optional"}}]})
hand = _y.safe_load(open(os.path.join(ROOT, "connectors", "mealie.yaml")))
case("Voice map: saved from the page", st == 200 and list(hand["actions"]) == ["list", "toss", "add"]
     and hand["actions"]["add"]["needs"] == {"name": "required", "when": "optional"} and hand["actions"]["toss"]["words"] == ["delete"], hand.get("actions"))
st, d = call("PUT", "/api/integrations/mealie/actions", {"actions": [{"name": "list", "api": "GET /nowhere", "words": [], "needs": {}}]})
case("Voice map: a command the app doesn't have is refused", st == 400, d)
st, d = call("PUT", "/api/integrations/mealie/actions", {"actions": [{"name": "list", "api": "GET /recipes"}, {"name": "list", "api": "POST /recipes"}]})
case("Voice map: an action's word is its own", st == 400, d)
st, d = call("PUT", "/api/integrations/mealie/actions", {"actions": [{"name": "list", "api": "GET /recipes", "needs": {"who": "maybe"}}]})
case("Voice map: a spoken need is required, optional or default", st == 400, d)
st, d = call("GET", "/api/integrations/mealie/details")
case("Voice map: the details carry the app's commands and the needs the router hears", st == 200 and len(d["commands"]) == 3
     and d["heard_needs"] == {"who": "person", "when": "date"} and [a["name"] for a in d["actions"]] == ["list", "toss", "add"], d)

# the app is updated: read its spec again, the changes are marked and wait
open("/tmp/veil-test/fake/spec-v2", "w").close()
st, d = call("POST", "/api/integrations/mealie/commands/read")
case("Commands: the changes are counted, and wait", st == 200 and not d["first"] and d["changes"] == 3, d)
case("Commands: the new version is noticed", d["version_changed"] and (d["version"], d["running"]) == ("1", "2"), d)
st, d = call("GET", "/api/integrations")
case("Integrations: a changed version is flagged on the list", d["services"]["mealie"]["app_version"]["version_changed"], d["services"]["mealie"].get("app_version"))
st, d = call("GET", "/api/integrations/mealie/commands")
marks = {c["api"]: c["mark"] for c in d["commands"]}
gone = next((c for c in d["commands"] if c["mark"] == "deleted"), {})
case("Commands: each row marked add, modified or deleted", d["pending"] and marks.get("POST /recipes/{id}/rate") == "add"
     and marks.get("GET /recipes") == "modified" and marks.get("DELETE /recipes/{id}") == "deleted" and marks.get("POST /recipes") == "same"
     and gone.get("actions") == ["toss"], marks)
saved = json.load(open(os.path.join(ROOT, "connectors", "mealie.commands.json")))
case("Commands: nothing saved until accepted", len(saved["commands"]) == 3, len(saved["commands"]))
st, d = call("GET", "/api/integrations/mealie/ready")
st, d = call("POST", "/api/integrations/mealie/commands/accept")
case("Commands: accepted, and the voice map's lost command is named", st == 200 and d["deleted"] == ["DELETE /recipes/{id}"], d)
st, d = call("GET", "/api/integrations/mealie/commands")
case("Commands: accepting sets the version", (d["version"], d["running"], d["version_changed"]) == ("2", "2", False), d)
st, d = call("GET", "/api/integrations/mealie/ready")
vm = next((x for x in d["steps"] if x["step"].startswith("Its voice map")), {})
case("Getting ready: an action calling a command the app dropped", not vm.get("done") and "toss" in vm.get("how", ""), vm)
os.remove("/tmp/veil-test/fake/spec-v2")

st, d = call("GET", "/api/integrations/donetick/ready")
case("Getting ready: Donetick's steps", st == 200 and {x["step"].split(" (")[0].split(",")[0] for x in d["steps"] if x["done"]}
     >= {"Its commands are read from its spec", "A topic it answers", "Its voice map lists what can be said", "Its helper"}, d)
# ---------- defaults: an app's lists (people, project), each a card with its default ----------
st, d = call("GET", "/api/integrations/donetick/lists")
mem = next((c for c in d.get("choices", []) if c["api"] == "GET /circles/members"), {})
case("Lists: the cards, with the app's GET commands and their fields", st == 200 and d["words"] == ["people", "project"]
     and "userId" in mem.get("returns", []) and any(m["key"] == "Owner" for m in d["household"]), d.get("words"))
st, d = call("GET", "/api/integrations/donetick/lists/people")
case("Lists: the people card, its default and who me means", st == 200 and d["card"]["from"] == "GET /circles/members"
     and d["card"]["default"] == "Owner" and d["card"]["me"] == "default" and d["used_by"] == ["add: who"], d.get("card"))
case("Lists: an app that can't be reached says so", not d["reached"] and d.get("detail"), d.get("detail"))
st, d = call("GET", "/api/integrations/donetick/lists/project")
case("Lists: the project card fills the add's project field", st == 200 and d["card"]["default"] == "House" and d["used_by"] == ["add: project"], d)
st, d = call("PUT", "/api/integrations/donetick/lists/people", {"from": "GET /circles/members", "id": "userId", "name": "displayName",
                                                               "house": "people", "default": "Beth", "me": "speaker", "map": {"1": "Owner", "3": "", "2": "Beth"},
                                                               "names": {"Owner": ["sam", "me"]}})
pp = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["services"]["donetick"]["lists"]["people"]
case("Lists: which voice each is, the other names, the default voice and me are saved, nobody included", st == 200
     and pp["map"] == {"1": "Owner", "3": "", "2": "Beth"} and pp["default"] == "Beth" and pp["me"] == "speaker"
     and pp["names"] == {"Owner": ["sam", "me"]}, pp)
st, d = call("PUT", "/api/integrations/donetick/lists/people", {"from": "GET /circles/members", "id": "shoeSize", "name": "displayName", "house": "people"})
case("Lists: a field the command doesn't answer with is refused", st == 400, d)
st, d = call("PUT", "/api/integrations/donetick/lists/people", {"from": "GET /circles/members", "id": "userId", "name": "displayName", "house": "people", "map": {"1": "stranger"}})
case("Lists: only the voices", st == 400, d)
st, d = call("PUT", "/api/integrations/donetick/lists/people", {"from": "GET /circles/members", "id": "userId", "name": "displayName", "house": "people", "default": "stranger"})
case("Lists: the default person is someone in the house", st == 400, d)
st, d = call("PUT", "/api/integrations/donetick/lists/label", {"from": "POST /chores", "id": "id", "name": "name"})
case("Lists: items come from a command that lists (a GET)", st == 400, d)
st, d = call("PUT", "/api/integrations/donetick/lists/label", {"from": "GET /filters", "id": "id", "name": "name", "default": "Urgent"})
st2, d2 = call("GET", "/api/integrations/donetick/lists")
case("Lists: a new card of your own (label)", st == 200 and "label" in d2["words"], (d, d2.get("words")))
st, d = call("DELETE", "/api/integrations/donetick/lists/label")
st2, d2 = call("DELETE", "/api/integrations/donetick/lists/project")
case("Lists: a card can be taken out, unless the voice map fills a field from it", st == 200 and st2 == 409, (d, d2))
st, d = call("PATCH", "/api/integrations/donetick/voice-map", {"match_min": 0.65})
hand = _y.safe_load(open(os.path.join(ROOT, "connectors", "donetick.yaml")))
case("Voice map: match min is the voice map's own knob", st == 200 and hand["match_min"] == 0.65
     and "# share of" in open(os.path.join(ROOT, "connectors", "donetick.yaml")).read(), d)
st, d = call("PATCH", "/api/integrations/donetick/voice-map", {"match_min": 3})
case("Voice map: match min is a share from 0 to 1", st == 400, d)
st, d = call("GET", "/api/integrations/donetick/details")
case("Defaults: no project or me options left (they're on the cards), and the default chore time",
     st == 200 and "default_project" not in d["options"] and "me" not in d["options"] and "default_chore_time" in d["options"]
     and "timezone" not in d["options"] and d["match_min"] == 0.65, list(d.get("options", {})))
case("Defaults: the apps an option's choices can come from (any app with its commands read)", st == 200
     and any(x["app"] == "donetick" and any(c["api"] == "GET /projects" for c in x["commands"]) for x in d["sources"]), [x["app"] for x in d.get("sources", [])])
st, d = call("PATCH", "/api/integrations/donetick/options", {"key": "default_chore_time", "value": "08:30", "from": None})
case("Defaults: the default chore time is Donetick's own", st == 200 and _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["services"]["donetick"]["options"]["default_chore_time"] == "08:30", d)
st, d = call("GET", "/api/settings")
case("Settings: the house's timezone and location", st == 200 and "house" in json.dumps(d) and "America/New_York" in json.dumps(d), "")

# ---------- LiteLLM is an integration like any app: its Commands tab reads its own spec ----------
st, d = call("PATCH", "/api/integrations/litellm", {"spec": "http://127.0.0.1:4999/openapi.json"})
case("LiteLLM: its spec address is saved like any integration's", st == 200, d)
st, d = call("POST", "/api/integrations/litellm/commands/read")
st2, d2 = call("GET", "/api/integrations/litellm/commands")
case("LiteLLM: its Commands tab reads its spec, with its version", st == 200 and d["count"] == 2 and d2["running"] == "1.80.0", (d, d2.get("running")))

# ---------- the Wepwawet standard: an app's spec says how it fits (Oread) ----------
call("PUT", "/api/vault/oread_token", {"value": "oread-test-token", "service": "Oread"})
st, d = call("PATCH", "/api/integrations/oread", {"spec": "http://127.0.0.1:4999/oread/openapi.json"})
st, d = call("POST", "/api/integrations/oread/commands/read")
case("Oread: its spec is read with its token, like any app", st == 200 and d.get("first") and d["count"] == 2, d)
call("PUT", "/api/sparkle", {"voice_id_from": "oread"})
call("PUT", "/api/sparkle/calls", {"person": "Sam", "names": ["Owner"]})
st, d = call("POST", "/api/sparkle/pull")
case("sparkle: Pull adds the voices the voice ID knows that aren't saved yet", st == 200 and d["from"] == "oread"
     and "Sam" not in d["added"] and set(d["added"]) == set(d["known"]) - {"Sam"} and d["added"], d)
_c = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["names_in_replies"]["calls"]
case("sparkle: saved names stay through a pull; the new ones come with none", _c.get("Sam") == ["Owner"] and all(_c[x] == [] for x in d["added"]), _c)
st, d = call("POST", "/api/sparkle/pull")
case("sparkle: pulling again adds nobody", st == 200 and d["added"] == [], d)
saved_o = json.load(open(os.path.join(ROOT, "connectors", "oread.commands.json")))
case("Oread: its Wepwawet section and how to call it are kept beside its commands", saved_o["wepwawet"]["version"] == 1
     and saved_o["base"] == "http://127.0.0.1:4999/oread" and saved_o["auth"]["prefix"] == "Bearer ", {k: saved_o.get(k) for k in ("base", "auth")})
st, d = call("GET", "/api/integrations/oread/details")
case("Oread: compliant, its tabs and offers from its own spec", st == 200 and d["wepwawet"]["tabs"]["voice_map"] is False
     and [o["key"] for o in d["offers"]] == ["who_spoke"] and d["offers"][0]["way"] == "wyoming" and d["title"] == "Oread", d.get("offers"))
st, d = call("PATCH", "/api/integrations/oread/offers", {"key": "who_spoke", "on": True, "way": "api"})
o = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["integrations"]["oread"]
case("Oread: switching who spoke on keeps the router's own switch and source", st == 200 and o["enabled"] is True and o["source"] == "oread", o)
st, d = call("PATCH", "/api/integrations/oread/offers", {"key": "who_spoke", "on": False, "way": "wyoming"})
st2, d2 = call("PATCH", "/api/integrations/oread/offers", {"key": "telepathy", "on": True})
st3, d3 = call("PATCH", "/api/integrations/oread/offers", {"key": "who_spoke", "on": True, "way": "smoke signals"})
case("Oread: only what it offers, by the ways it offers", st == 200 and st2 == 400 and st3 == 400, (d2, d3))
st, d = call("GET", "/api/integrations/oread/lists")
case("Oread: its people list comes from its own spec", st == 200 and d["words"] == ["people"], d.get("words"))
st, d = call("GET", "/api/integrations/oread/lists/people")
case("Oread: its profiles listed by the router's own call (its token, its way)", st == 200 and d["reached"] and d["declared"]
     and [i["name"] for i in d["items"]] == ["Sam", "Elizabeth", "Sam Jr"], d)
st, d = call("GET", "/api/integrations/donetick/details")
case("Donetick: not compliant (no Wepwawet section), so nothing is grayed", st == 200 and d.get("wepwawet") is None, d.get("wepwawet"))

st, d = call("GET", "/api/integrations/donetick/details")
case("Donetick's voice map offers its saved commands", st == 200 and any(c["api"] == "POST /chores" and "body: name" in c["requires"] for c in d["commands"]), "")
before = open(os.path.join(ROOT, "connectors", "donetick.yaml")).read()
acts = [{"name": a["name"], "was": a["name"], "api": a["api"], "words": a["words"], "needs": a["needs"]} for a in d["actions"]]
acts[0]["name"] = "read"
st, d = call("PUT", "/api/integrations/donetick/actions", {"actions": acts})
after = open(os.path.join(ROOT, "connectors", "donetick.yaml")).read()
hand = _y.safe_load(after)
case("Voice map: renaming an action keeps its comment, its learn_from and the add's follow-up fields",
     st == 200 and "read" in hand["actions"] and "list" not in hand["actions"] and "# what's due" in after
     and hand["actions"]["read"]["learn_from"]["massive"] and hand["actions"]["add"]["fields"]["nag"]["default"] == "every 15 minutes"
     and hand["language"]["never_in_names"][0] == "a", d)

# ---------- user rules: the app's commands chained with the router's steps (the User rules tab) ----------
st, d = call("GET", "/api/integrations/donetick/details")
ren = next((r for r in d.get("rules") or [] if r["name"] == "rename"), {})
case("User rules: the details carry each rule's steps and the steps the router knows", st == 200
     and [x["kind"] for x in ren.get("steps", [])] == ["call", "search", "match", "confirm", "ask", "fresh_copy", "call", "response"]
     and {"search", "match", "confirm", "ask", "fresh_copy", "response", "who_spoke"} <= set(d.get("rule_steps") or {}), ren)
steps = [dict(x) for x in ren["steps"]]
steps[2]["act"] = 90
proj = next((r for r in d.get("rules") or [] if r["name"] == "rename_project"), {})
st, d = call("PUT", "/api/integrations/donetick/rules", {"rules": [{"name": "rename", "words": ren["words"], "objects": ren["objects"], "steps": steps},
                                                                   {"name": "rename_project", "words": proj["words"], "objects": proj["objects"], "steps": proj["steps"]}]})
after = open(os.path.join(ROOT, "connectors", "donetick.yaml")).read()
hand = _y.safe_load(after)
case("User rules: saved from the page, each step with its parameters, the rest of the file kept", st == 200
     and hand["rules"]["rename"]["steps"][2] == {"match": {"act": 90, "ask": 45}} and hand["rules"]["rename"]["steps"][0] == {"call": "GET /chores"}
     and hand["rules"]["rename"]["steps"][5]["fresh_copy"]["set"] == {"name": "new_name"} and "# what's due" in after
     and "objects" not in hand["rules"]["rename"] and hand["rules"]["rename_project"]["objects"] == ["project", "projects"]
     and hand["rules"]["rename"]["steps"][1]["search"]["last"] is True, hand.get("rules"))
st, d = call("PUT", "/api/integrations/donetick/rules", {"rules": [{"name": "rename", "words": ["rename"], "steps": [{"kind": "call", "command": "GET /nowhere"}]}]})
st2, d2 = call("PUT", "/api/integrations/donetick/rules", {"rules": [{"name": "add", "words": ["add"], "steps": [{"kind": "call", "command": "GET /chores"}]}]})
st3, d3 = call("PUT", "/api/integrations/donetick/rules", {"rules": [{"name": "rename", "words": ["rename"], "steps": [{"kind": "match", "act": 40, "ask": 60}]}]})
case("User rules: a command the app doesn't have, a voice map action's name, Match's Ask above Act: refused",
     (st, st2, st3) == (400, 400, 400), (d, d2, d3))

# ---------- brain fleas (the Brain fleas page; learn/fleas.yaml) ----------
st, d = call("GET", "/api/fleas")
case("Brain fleas: the page gets the fleas, the steps, the router's own commands and who may change them",
     st == 200 and "device_who_is_speaking_to_you" in [r["name"] for r in d["rules"]] and "who_spoke" in d["rule_steps"]
     and any(c["api"] == "POST /fleas" for c in d["commands"]) and d["changers"] == [], d.get("rules"))
rows = [{k: r[k] for k in ("name", "title", "words", "objects", "steps")} for r in d["rules"]]
rows.append({"name": "wifi_name", "title": "the wifi", "words": ["wifi {name | network}"], "objects": [],
             "steps": [{"kind": "response", "lines": ["The wifi is called Wepwawet."]}]})
st, d = call("PUT", "/api/fleas", {"rules": rows})
fl = _y.safe_load(open(os.path.join(ROOT, "learn", "fleas.yaml")))
case("Brain fleas: a flea added on the page, the built-in ones kept as they were", st == 200
     and fl["fleas"]["wifi_name"]["steps"] == [{"response": {"lines": ["The wifi is called Wepwawet."]}}]
     and fl["fleas"]["add_flea"]["system"] is True, fl.get("fleas", {}).get("wifi_name"))
said = chat("What's the wifi network called?", False)
case("Brain fleas: answered at home, at once (no restart)", "Wepwawet" in said, said)
said = chat("Who is talking?", False)
case("Brain fleas: who is talking, with Oread not sure: a way out, never a name",
     any(x in said for x in ("getting to know", "rather not guess", "tricky", "can't tell")), said)
st, d = call("PUT", "/api/fleas", {"rules": rows + [{"name": "add", "words": ["x"], "steps": [{"kind": "response", "lines": ["x"]}]}]})
st2, d2 = call("PATCH", "/api/fleas/settings", {"changers": ["Nobody Known"]})
st3, d3 = call("PATCH", "/api/fleas/settings", {"match_at": 0.8})
case("Brain fleas: a name another rule or action has is refused; changers must be known voices; match at saved",
     (st, st2, st3) == (400, 400, 200) and "Voice map" in d.get("detail", json.dumps(d)), (d, d2, d3))
said = chat("Add a brain flea, we only buy pizza from Sal's.", False)
case("Brain fleas: a voice add from someone not allowed is refused", "only change" in said, said)

# ---------- a page saved from an old copy is refused (Oct 18) ----------
st, d = call("GET", "/api/fleas")
old = d.get("stamp")
st, d = call("PUT", "/api/fleas", {"stamp": old, "rules": rows})
new = d.get("stamp")
st2, d2 = call("PUT", "/api/fleas", {"stamp": new, "rules": rows[:-1]})          # the wifi flea taken out, from the newer copy
st3, d3 = call("PUT", "/api/fleas", {"stamp": new, "rules": rows})               # a save from the copy before that
case("Brain fleas: saving from the page as opened works, and again from what that save returned; "
     "from a copy older than the file: refused (409), the file left alone",
     (st, st2, st3) == (200, 200, 409) and "reload" in d3.get("detail", "")
     and "wifi_name" not in (_y.safe_load(open(os.path.join(ROOT, "learn", "fleas.yaml")))["fleas"]), (d, d2, d3))
call("PUT", "/api/fleas", {"rules": rows[:-1]})
st, d = call("GET", "/api/integrations/donetick/details")
mine = [{k: r[k] for k in ("name", "words", "objects", "steps")} for r in d.get("rules") or []]
st1, d1 = call("PUT", "/api/integrations/donetick/rules", {"stamp": d["stamps"]["rules"], "rules": mine})
st2, d2 = call("PATCH", "/api/integrations/donetick/voice-map", {"match_min": d.get("match_min")})
st3, d3 = call("PUT", "/api/integrations/donetick/rules", {"stamp": d1.get("stamp"), "rules": mine})
other = [dict(r, words=r["words"] + ["retitle"]) if i == 0 else r for i, r in enumerate(mine)]
call("PUT", "/api/integrations/donetick/rules", {"rules": other})                # another page changes the rules
st4, d4 = call("PUT", "/api/integrations/donetick/rules", {"stamp": d3.get("stamp"), "rules": mine})
call("PUT", "/api/integrations/donetick/rules", {"rules": mine})
case("User rules: another tab saving another part of the file doesn't make the rules old; "
     "an old copy of the rules themselves is refused",
     (st1, st2, st3, st4) == (200, 200, 200, 409), (d1, d2, d3, d4))

# ---------- refusals on Integrations, and firewall device names against Home Assistant (Oct 18) ----------
st, d = call("GET", "/api/integrations")
case("Integrations: the page gets the addresses refused lately, and for how long it looks back",
     st == 200 and isinstance(d.get("refused"), list) and d.get("refused_minutes") == 60, {k: d.get(k) for k in ("refused", "refused_minutes")})
st, d = call("GET", "/api/firewall/devices")
case("Firewall: device names checked against Home Assistant, or why they can't be (no address or token in the copy)",
     st == 200 and ("error" in d or "unknown" in d), d)

# ---------- Words understood, sound alike beside match min, the swaps' table, Stats' own hops (Oct 18) ----------
st, d = call("GET", "/api/words")
ans = next((f for f in d.get("files") or [] if f["file"] == "answers"), {})
yes = next((x for x in ans.get("lists") or [] if x["path"] == ["yes"]), {})
case("Words understood: every vocab file's lists, each with its words", st == 200 and "continue" in yes.get("words", []), ans.get("file"))
st1, d1 = call("PUT", "/api/words/answers", {"path": ["yes"], "words": yes["words"] + ["on"], "stamp": ans["stamps"]["yes"]})
st2, d2 = call("PUT", "/api/words/answers", {"path": ["yes"], "words": yes["words"], "stamp": ans["stamps"]["yes"]})
on_kept = "on" in (_y.safe_load(open(os.path.join(ROOT, "vocab", "answers.yaml")))["yes"])
st3, d3 = call("PUT", "/api/words/answers", {"path": ["yes"], "words": yes["words"], "stamp": d1.get("stamp")})
st4, d4 = call("PUT", "/api/words/answers", {"path": ["nowhere"], "words": ["x"]})
case("Words understood: a list saved (a word like on kept a word, not true), an old copy refused, an unknown list refused",
     (st1, st2, on_kept, st3, st4) == (200, 409, True, 200, 400), (d1, d2, d3, d4))
st, d = call("PATCH", "/api/integrations/donetick/voice-map", {"sound_alike": False})
st2, d2 = call("GET", "/api/integrations/donetick/details")
call("PATCH", "/api/integrations/donetick/voice-map", {"sound_alike": True})
case("Voice map: sound alike saved beside match min (match min left as it was)",
     st == 200 and d2.get("sound_alike") is False and d2.get("match_min") is not None, d2.get("sound_alike"))
st, d = call("GET", "/api/mishearings")
case("Misses: each swap in use says when it was added and how often it was used", st == 200 and all("used" in x and "added" in x for x in d.get("swaps") or []), d.get("swaps"))
st, d = call("GET", "/api/stats?days=7")
case("Stats: Wepwawet Musings is a route name the page knows (fleas), and the routes carry their hops",
     st == 200 and isinstance(d.get("time_routes"), list), [r.get("route") for r in d.get("time_routes") or []])

# ---------- what's new in the starting copies (defaults/) ----------
st, d = call("GET", "/api/starting")
items = d.get("items") or []
words = [i for i in items if i["kind"] == "item"]
case("Starting copies: what's new is listed (the topic words changed above are in the starting copy, not yours)",
     st == 200 and any(i["file"] == "settings.yaml" and i["path"][:2] == ["topics", "chores"] for i in words), items[:3])
if len(words) >= 2:
    st, d = call("POST", f"/api/starting/{words[0]['id']}/add")
    back = _y.safe_load(open(os.path.join(ROOT, *words[0]["file"].split("/"))))
    node = back
    for k in words[0]["path"]:
        node = node[k]
    case("Starting copies: Add puts it into your file", st == 200 and words[0]["value"] in node, d)
    st, d = call("POST", f"/api/starting/{words[1]['id']}/dismiss")
    st2, d2 = call("GET", "/api/starting")
    case("Starting copies: added and hidden ones leave the list", st == 200 and not any(i["id"] in (words[0]["id"], words[1]["id"]) for i in d2["items"]), d2["items"][:3])
    st, d = call("POST", f"/api/starting/{words[0]['id']}/add")
    case("Starting copies: one already added can't be added again", st == 404, d)
st, d = call("GET", "/api/starting", who=opener())
case("Starting copies: not without signing in", st == 401, st)

# ---------- Persona Flair: books -> Accept -> lines bank (Oct 14) ----------
_P = os.path.join(ROOT, "personality")
_rd = lambda *p: _y.safe_load(open(os.path.join(_P, *p))) or {}          # noqa: E731
st, d = call("GET", "/api/flair/iris")
case("approved lines from before moved into her lines bank at start (none wait in approved)", d["approved"] == [], d["approved"])
st, d = call("GET", "/api/flair/iris/candidates")
_c0 = d["candidates"]
case("books: lines to look at", st == 200 and len(_c0) >= 2, len(_c0))
_one = _c0[0]
st, d = call("POST", "/api/flair/iris/candidates/accept", {"found": _one.get("found", _one["text"]), "slot": "closer"})
case("books: Accept puts a line straight into her lines bank, with the slot chosen", st == 200 and d["banked"]["slot"] == "closer", d)
case("books: it leaves the books list", not any(c.get("found", c["text"]) == _one.get("found", _one["text"])
     for c in call("GET", "/api/flair/iris/candidates")[1]["candidates"]), "")
st, d = call("POST", "/api/flair/iris/candidates/accept", {"found": _one.get("found", _one["text"])})
case("books: accepting it twice says so", st == 404, d)
_bank = call("GET", "/api/flair/iris")[1]["personality"]["flourishes"]
_bi = next((i for i, f in enumerate(_bank) if f["text"] == _one["text"]), None)
case("lines bank: it's there, with its book", _bi is not None and _bank[_bi].get("from") is not None and _bank[_bi].get("found") == _one.get("found", _one["text"]), _bank)
st, d = call("PATCH", "/api/flair/iris/lines", {"index": _bi, "text_was": "not this one", "text": "x"})
case("lines bank: an edit from a stale page is refused", st == 409, d)
st, d = call("PATCH", "/api/flair/iris/lines", {"index": _bi, "text_was": _one["text"], "text": "Is it?"})
case("lines bank: a line can't become a question", st == 400, d)
st, d = call("PATCH", "/api/flair/iris/lines", {"index": _bi, "text_was": _one["text"], "text": "Ziz-zy zuz-zy, bless you",
                                                      "slot": "closer", "topics": ["weather"], "mood": ["plain"]})
case("lines bank: a line is reworded and saved", st == 200 and d["lines"][_bi]["text"] == "Ziz-zy zuz-zy, bless you" and d["lines"][_bi]["topics"] == ["weather"], d)
case("lines bank: in her personality file, its knobs kept", "Ziz-zy zuz-zy, bless you" in open(os.path.join(_P, "iris.yaml")).read()
     and _rd("iris.yaml").get("rate") == 0.5, "")
st, d = call("POST", "/api/flair/iris/lines", {"lines": [{"text": "By my broom!"}, {"text": "Ziz-zy zuz-zy, bless you"}]})
case("lines bank: lines typed are added, ones she has left out", st == 200 and (d["added"], d["already"]) == (1, 1), d)
st, d = call("PUT", "/api/flair/iris", {"rate": 0.5, "max_in_a_row": 2})
case("how often: saving the knobs leaves her lines bank alone", any(f["text"] == "By my broom!" for f in _rd("iris.yaml")["flourishes"]), d)
_bank = call("GET", "/api/flair/iris")[1]["personality"]["flourishes"]
_bi = next(i for i, f in enumerate(_bank) if f["text"] == "By my broom!")
st, d = call("PATCH", "/api/flair/iris/lines", {"index": _bi, "text_was": "By my broom!", "delete": True})
case("lines bank: a line is deleted", st == 200 and not any(f["text"] == "By my broom!" for f in d["lines"]), d)
_bank = d["lines"]
_bi = next(i for i, f in enumerate(_bank) if f["text"] == "Ziz-zy zuz-zy, bless you")
st, d = call("PATCH", "/api/flair/iris/lines", {"index": _bi, "text_was": "Ziz-zy zuz-zy, bless you", "delete": True})
case("lines bank: a book line deleted is remembered, so combing won't bring it back",
     st == 200 and _one.get("found", _one["text"]) in _rd("approved", "iris.yaml")["dropped"], _rd("approved", "iris.yaml"))
os.environ["ROUTER_ROOT"] = ROOT
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from veil import flairlines as _fl  # noqa: E402
_two = call("GET", "/api/flair/iris/candidates")[1]["candidates"][0]
call("POST", "/api/flair/iris/candidates/accept", {"found": _two.get("found", _two["text"])})
_taken = _fl.taken("iris")
case("combing again leaves out what's in the bank and what was deleted from it",
     {_fl.key(_one.get("found", _one["text"])), _fl.key(_two.get("found", _two["text"]))} <= _taken, sorted(_taken)[:5])
st, d = call("POST", "/api/flair/iris/candidates/clear")
case("books: Clear empties the list", st == 200 and call("GET", "/api/flair/iris/candidates")[1]["candidates"] == [], d)

# ---------- her sayings: phrases/*.yaml on Persona Flair (Oct 14) ----------
st, d = call("GET", "/api/phrases")
_rf = next((f for f in d["files"] if f["file"] == "router"), None)
case("sayings: every file, each section with its note, lines and rules", st == 200 and _rf and _rf["personal"]
     and "ask_around" in _rf["sections"] and _rf["sections"]["ask_around"]["rules"]["needed"] == ["heard"]
     and _rf["sections"]["ask_around"]["rules"]["question"] is True and "QUESTION" in _rf["sections"]["ask_around"]["note"], _rf and _rf["sections"].get("ask_around"))
case("sayings: an app's lines are shared", any(f["file"] != "router" and not f["personal"] for f in d["files"]), [f["file"] for f in d["files"]])
_line = 'I think I heard "{heard}". That is beyond this lamp. Shall I ask the winds of the world?'
st, d = call("PUT", "/api/phrases/router/ask_around/felix", {"lines": [_line]})
case("sayings: Felix gets her own ask-around line", st == 200 and d["lines"] == [_line], d)
_pf = open(os.path.join(ROOT, "phrases", "router.yaml")).read()
case("sayings: in phrases/router.yaml, its comments kept", "beyond this lamp" in _pf and "QUESTION (path C)" in _pf, "")
st, d = call("PUT", "/api/phrases/router/ask_around/felix", {"lines": ["That is beyond this lamp. Shall I ask the winds?"]})
case("sayings: {heard} must stay in an ask-around line", st == 400, d)
st, d = call("PUT", "/api/phrases/router/ask_around/felix", {"lines": ['I think I heard "{heard}". Off I go.']})
case("sayings: a question section takes questions", st == 400, d)
st, d = call("PUT", "/api/phrases/router/dismissed/felix", {"lines": ["Back in the lamp {owner}."]})
case("sayings: a {placeholder} the section doesn't fill is refused", st == 400, d)
st, d = call("PUT", "/api/phrases/router/dismissed/felix", {"lines": ["Back in the lamp?"]})
case("sayings: no question where she isn't asking", st == 400, d)
st, d = call("PUT", "/api/phrases/router/dismissed/any", {"lines": []})
case("sayings: the shared lines keep one at least", st == 400, d)
_cf = next(f for f in call("GET", "/api/phrases")[1]["files"] if f["file"] != "router")
_ck = next(iter(_cf["sections"]))
st, d = call("PUT", f"/api/phrases/{_cf['file']}/{_ck}/felix", {"lines": ["x"]})
case("sayings: an app's lines aren't per personality", st == 400, d)
st, d = call("PUT", "/api/phrases/router/ask_around/felix", {"lines": []})
case("sayings: emptying hers takes them out (she uses the shared ones)", st == 200 and "felix" not in (_y.safe_load(open(os.path.join(ROOT, "phrases", "router.yaml")))["ask_around"]), d)
st, d = call("PUT", "/api/phrases/asking", {"words": ["ask", "coven", "winds"]})
case("sayings: her words for asking around", st == 200 and _y.safe_load(open(os.path.join(ROOT, "vocab", "answers.yaml")))["about_asking"] == ["ask", "coven", "winds"], d)

# ---------- User Sparkle: saying names (Oct 14) ----------
st, d = call("GET", "/api/sparkle")
case("sparkle: the house rule, the devices (from the personality files), where names come from", st == 200
     and {"iris", "felix"} <= {x["name"] for x in d["devices"]} and "min_score" not in d["settings"] and isinstance(d["sources"], list), d)
st, d = call("PUT", "/api/sparkle", {"min_score": 0.85, "rate": 0.4, "max_in_a_row": 2, "enabled": False})
_ni = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["names_in_replies"]
case("sparkle: no house switch, house rate or house voice match (Oct 15)", st == 200
     and not ({"enabled", "rate", "max_in_a_row", "min_score"} & set(_ni)), _ni)
st, d = call("PUT", "/api/sparkle/device/felix", {"rate": 0.3, "min_score": 1.5})
case("sparkle: a persona's least score over 100% is refused", st == 400, d)
st, d = call("PUT", "/api/sparkle/device/felix/calls", {"person": "Owner", "names": ["Sir", "sir", "My lord"]})
case("sparkle: a persona's own names for a voice, in its personality file", st == 200
     and _y.safe_load(open(os.path.join(ROOT, "personality", "felix.yaml")))["names"]["calls"]["Owner"] == ["Sir", "My lord"], d)
st, d = call("PUT", "/api/sparkle/device/felix/calls", {"person": "Owner", "names": []})
case("sparkle: no names left for a voice takes it out of the persona's own", st == 200
     and "calls" not in (_y.safe_load(open(os.path.join(ROOT, "personality", "felix.yaml"))).get("names") or {}), d)
st, d = call("PUT", "/api/sparkle", {"voice_id_from": "nothing_here"})
case("sparkle: names only from something with a people list", st == 400, d)
st, d = call("PUT", "/api/sparkle/calls", {"person": "Owner", "names": ["Owner", "Sam", "sam", " Captain "]})
case("sparkle: what she calls someone (duplicates and spaces tidied)", st == 200 and d["names"] == ["Owner", "Sam", "Captain"], d)
_n = _y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["names_in_replies"]["calls"]
case("sparkle: kept in settings.yaml under names_in_replies: calls", _n.get("Owner") == ["Owner", "Sam", "Captain"], _n)
st, d = call("PUT", "/api/sparkle/calls", {"person": "Owner", "names": ["Is it you?"]})
case("sparkle: a name isn't a question", st == 400, d)
st, d = call("PUT", "/api/sparkle/calls", {"person": "Owner", "names": []})
case("sparkle: a saved voice with no names stays", st == 200 and (_y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["names_in_replies"].get("calls") or {}).get("Owner") == [], d)
st, d = call("PUT", "/api/sparkle/calls", {"person": "Owner", "remove": True})
case("sparkle: deleting a voice takes it out", st == 200 and "Owner" not in (_y.safe_load(open(os.path.join(ROOT, "settings.yaml")))["names_in_replies"].get("calls") or {}), d)
st, d = call("PUT", "/api/sparkle/device/felix", {"enabled": True, "rate": 0.2, "max_in_a_row": ""})
case("sparkle: a device's share (its switch) in its personality file, no enabled", st == 200
     and _y.safe_load(open(os.path.join(ROOT, "personality", "felix.yaml")))["names"] == {"rate": 0.2}, d)
st, d = call("PUT", "/api/sparkle/device/felix", {"rate": 3})
case("sparkle: a device's share is 0 to 1", st == 400, d)
st, d = call("GET", "/api/sparkle")
case("sparkle: the device shows it", next(x for x in d["devices"] if x["name"] == "felix")["names"].get("rate") == 0.2, d["devices"])

# ---------- tools grouped ----------
st, d = call("GET", "/api/tools")
secs = {t["id"]: t.get("section") for t in d["tools"]}
case("tools: Maintenance and Utilities", secs.get("build") == "Maintenance" and secs.get("labels") == "Maintenance"
     and secs.get("word_shares") == "Utilities", secs)

# ---------- roles ----------
st, d = call("POST", "/api/users", {"name": "kid", "password": "kids password!", "role": "viewer"})
case("a viewer is added", st == 200, d)
KID = opener()
st, d = call("POST", "/api/session", {"name": "kid", "password": "kids password!"}, who=KID)
case("the viewer signs in", st == 200)
st, d = call("PATCH", "/api/settings", {"path": ["read_list_max"], "value": 3}, who=KID)
case("a viewer can't change settings", st == 403, d)
st, d = call("GET", "/api/users", who=KID)
case("a viewer can't see users", st == 403)
st, d = call("GET", "/api/overview", who=KID)
case("a viewer can read the overview", st == 200)

# ---------- tokens ----------
st, d = call("POST", "/api/tokens", {"name": "tools", "role": "reviewer"})
tok = d.get("token")
anon = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))
st, d = call("GET", "/api/bank", who=anon, header=False, token=tok)
case("a token reads the bank", st == 200, d)
st, d = call("PATCH", "/api/settings", {"path": ["read_list_max"], "value": 3}, who=anon, header=False, token=tok)
case("a reviewer token can't change settings", st == 403, d)
st, d = call("GET", "/api/tokens")
case("Doors: the doors come from the settings, with the sign-in rules", [x["name"] for x in d.get("doors", [])] ==
     ["chat", "tools", "guard", "oread"] and all(x["description"] and x["paths"] for x in d["doors"]) and d["rules"]["password_min_length"] >= 8, d)
case("Doors: a token named like a door shows on that door", any(t["name"] == "tools" for t in next(x for x in d["doors"] if x["name"] == "tools")["tokens"]), d["doors"])
def chat_with(token):
    req = urllib.request.Request(CHAT + "/v1/chat/completions", method="POST", headers={"Content-Type": "application/json",
        **({"Authorization": f"Bearer {token}"} if token else {})},
        data=json.dumps({"model": "house-router", "messages": [{"role": "user", "content": "never mind"}]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


st, d = call("POST", "/api/tokens", {"name": "litellm", "role": "viewer"})
chat_tok = d.get("token")
time.sleep(1.1)                                       # a new second: the token file's time changes
chat_with(chat_tok)                                   # shown while the door is still open
st, d = call("GET", "/api/tokens")
case("Doors: a token shown while the door is open counts as used", any(t["name"] == "litellm" and t["last_used"] for t in d["tokens"]), d["tokens"])
st, d = call("PATCH", "/api/settings", {"path": ["security", "chat_token_required"], "value": True})



case("Doors: the chat door locks at once, without a restart", (st, chat_with(None), chat_with(chat_tok)) == (200, 401, 200), st)
st, d = call("PATCH", "/api/settings", {"path": ["security", "chat_token_required"], "value": False})
case("Doors: and opens again", (st, chat_with(None)) == (200, 200), st)
st, d = call("PATCH", "/api/settings", {"path": ["security", "doors", "chat", "locked"], "value": True})
case("Doors: locked from the doors setting too", (st, chat_with(None), chat_with(chat_tok)) == (200, 401, 200), st)
call("PATCH", "/api/settings", {"path": ["security", "doors", "chat", "locked"], "value": False})


# Oct 19 night, dump20: Home Assistant straight to the router, in LiteLLM's place
def door_post(path, model, token=None, said="never mind"):
    req = urllib.request.Request(CHAT + path, method="POST", headers={"Content-Type": "application/json",
        **({"Authorization": f"Bearer {token}"} if token else {})},
        data=json.dumps({"model": model, "messages": [{"role": "system", "content": "Iris Personality"},
                                                      {"role": "user", "content": said}]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


with urllib.request.urlopen(CHAT + "/models", timeout=20) as r:
    _ids = [m["id"] for m in json.loads(r.read())["data"]]
case("dump20: /models, as LiteLLM answers it: the router's own model and LiteLLM's (once each)", (_ids[0], "gemini-lite" in _ids, _ids.count("house-router")), ("house-router", True, 1))
_st, _d = door_post("/chat/completions", "house-router")
case("dump20: /chat/completions is the chat door too (the router's own model, decided as always)", (_st, "Gemini says" not in json.dumps(_d)), (200, True))
_st, _d = door_post("/chat/completions", "gemini-lite", said="tell me a joke about cats")
case("dump20: another model (Felix's) is passed through to LiteLLM as it came", (_st, "Gemini says" in json.dumps(_d)), (200, True))
call("PATCH", "/api/settings", {"path": ["security", "doors", "chat", "locked"], "value": True})
case("dump20: the locked chat door holds at its other path too, for any model",
     (door_post("/chat/completions", "gemini-lite")[0], door_post("/chat/completions", "gemini-lite", chat_tok)[0]), (401, 200))
call("PATCH", "/api/settings", {"path": ["security", "doors", "chat", "locked"], "value": False})


def pull_mishearings(token):
    req = urllib.request.Request(CHAT + "/learn/mishearings", headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


os.makedirs(os.path.join(ROOT, "learn"), exist_ok=True)
with open(os.path.join(ROOT, "learn", "mishearings.yaml"), "w") as f:
    f.write("mishearings:\n- meant: add a chore\n  heard:\n  - said: at a chore\n    count: 2\n    first: 2026-10-17 09:00\n"
            "    last: 2026-10-17 09:10\n    taken: false\n    clips:\n    - {clip: 20261017-090000-001-iris, device: iris, "
            "when: 2026-10-17 09:00}\n")
st, d = call("POST", "/api/tokens", {"name": "oread", "role": "viewer", "door": "oread"})
oread_tok = d.get("token")
st1, d1 = pull_mishearings(None)
st2, d2 = pull_mishearings(oread_tok)
case("Mishearings for Oread: the oread door is locked as it ships, so no token, no list (Oct 17)", st1 == 401, (st1, d1))
case("Mishearings for Oread: with its token, each heard line with its clips", st2 == 200 and d2["router"] and
     d2["mishearings"][0]["heard"][0]["clips"][0]["clip"] == "20261017-090000-001-iris", (st2, d2))
call("PATCH", "/api/settings", {"path": ["security", "doors", "oread", "paths"], "value": ["/learn/elsewhere"]})
st3, d3 = pull_mishearings(oread_tok)
case("Mishearings for Oread: no door covering it means no list, never open by accident", st3 == 403 and "door" in d3["detail"], (st3, d3))
call("PATCH", "/api/settings", {"path": ["security", "doors", "oread", "paths"], "value": ["/learn/mishearings", "/people/oread"]})

# the people grid (Oct 17): one row per person, a column per app; an app pulls its own column only
grid = {"apps": ["oread", "donetick"], "rows": [{"wepwawet": "Owner", "called": [], "oread": ["Owner", "Sam"], "donetick": ["Owner"]},
                                               {"wepwawet": "", "called": [], "oread": ["Alexandra"], "donetick": []}]}
st, d = call("PUT", "/api/people", grid)
case("People: the grid is saved, a column per app", st == 200 and d["apps"] == ["oread", "donetick"] and d["rows"][0]["oread"] == ["Owner", "Sam"]
     and any(c["id"] == "donetick" for c in d["columns"]), d)
st, d = call("PUT", "/api/people", {"apps": ["oread"], "rows": [{"wepwawet": "Owner", "oread": ["Sam"]}, {"wepwawet": "Sam", "oread": []}]})
case("People: one name in two rows is refused (it would make two people one)", st == 400 and "two rows" in d.get("detail", ""), (st, d))


def pull_people(app_name, token):
    req = urllib.request.Request(CHAT + f"/people/{app_name}", headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


st, d = pull_people("oread", oread_tok)
case("People for Oread: its own column only, beside the router's name", st == 200 and d["people"] == [
     {"person": "Owner", "names": ["Owner", "Sam"]}, {"person": None, "names": ["Alexandra"]}], (st, d))
st, d = pull_people("donetick", oread_tok)
case("People: another app's column isn't Oread's to read (no door of Donetick's covers it)", st == 403, (st, d))
st, d = pull_people("oread", None)
case("People for Oread: no token, no names", st == 401, (st, d))


def push_person(app_name, token, body):
    req = urllib.request.Request(CHAT + f"/people/{app_name}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


st, d = push_person("oread", oread_tok, {"action": "add", "name": "Rachel"})
case("dump22: Oread adds a person the grid doesn't have: a row of their own", st == 200 and {"person": "Rachel", "names": ["Rachel"]} in d["people"], (st, d))
st, d = push_person("oread", oread_tok, {"action": "rename", "name": "Rach", "was": "Rachel"})
case("dump22: ...renames them (the router's name with it)", st == 200 and {"person": "Rach", "names": ["Rach"]} in d["people"], (st, d))
st, d = push_person("oread", oread_tok, {"action": "remove", "name": "Rach"})
_g = call("GET", "/api/people")[1]
case("dump22: ...and a delete takes the name out of Oread's column only, the row kept",
     st == 200 and not any(r["person"] == "Rach" for r in d["people"]) and any(r["wepwawet"] == "Rach" for r in _g["rows"]), (st, d))
case("dump22: no token, no change; another app's column, no change",
     (push_person("oread", None, {"action": "add", "name": "X"})[0], push_person("donetick", oread_tok, {"action": "add", "name": "X"})[0]), (401, 403))
st, d = call("POST", "/api/doors", {"name": "probe", "description": "a door added on the page", "who": "the tests",
                                    "paths": "/health", "role": "viewer"})
case("Doors: a new door is added with a name and description", st == 200 and d["paths"] == ["/health"], d)
st, d = call("POST", "/api/doors", {"name": "Bad Name", "description": "x", "paths": "/health"})
case("Doors: a bad door is refused", st == 400, d)
call("PATCH", "/api/settings", {"path": ["security", "doors", "probe", "locked"], "value": True})


def health(token):
    req = urllib.request.Request(CHAT + "/health", headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


case("Doors: the new door locks its paths at once", (health(None), health(chat_tok)) == (401, 200), "")
st, d = call("DELETE", "/api/doors/probe")
case("Doors: a door you added can be taken out", st == 200 and health(None) == 200, d)
st, d = call("DELETE", "/api/doors/chat")
case("Doors: a built-in door stays", st == 400, d)
st, d = call("PATCH", "/api/tokens/litellm", {"door": "chat"})
st2, d2 = call("GET", "/api/tokens")
case("Doors: a token is tied to its door", st == 200 and any(t["name"] == "litellm" for t in next(x for x in d2["doors"] if x["name"] == "chat")["tokens"]), d2)
st, d = call("GET", "/api/vault")
case("Grantors: each key names its program", any(w["name"] == "OFF_PLATFORM_KEY" and w["for"] == "LiteLLM" for w in d.get("wanted", [])), d.get("wanted"))
st, d = call("PATCH", "/api/settings", {"path": ["security", "lock_minutes"], "value": 0})
case("Sign-in rules: out of range is refused", st == 400, d)

# ---------- vault and addresses ----------
st, d = call("PUT", "/api/vault/oread_token", {"value": "oread_abcdefghijklmnopqrstuvwxyz"})
case("a vault key is saved", st == 200 and d["ends_with"] == "…wxyz", d)
st, d = call("GET", "/api/integrations")
case("integrations show where a token comes from", d["oread"]["token_from"] == "vault", d["oread"])
st, d = call("PUT", "/api/access", {"inbound_allowed": [], "admin_allowed": ["10.9.9.0/24"], "outbound_allowed": []})
case("you can't lock yourself out", st == 409, d)
st, d = call("PUT", "/api/access", {"inbound_allowed": [], "admin_allowed": ["127.0.0.1"], "outbound_allowed": []})
case("addresses are saved", st == 200 and d["admin_allowed"]["entries"] == ["127.0.0.1"], d)
call("PUT", "/api/access", {"inbound_allowed": [], "admin_allowed": [], "outbound_allowed": []})
st, d = call("GET", "/api/access")
seen = {x["address"]: x for x in d["admin_allowed"]["recently_allowed"]}
case("Addresses: the machines let in lately are listed", "127.0.0.1" in seen and seen["127.0.0.1"]["what"] == "the pages", seen)

# ---------- a tool ----------
st, d = call("POST", "/api/tools/unit_tests", {"args": {}})
case("a tool starts", st == 200 and d.get("job"), d)
jid = d.get("job")
for _ in range(120):
    st, j = call("GET", f"/api/jobs/{jid}")
    if j.get("state") != "running":
        break
    time.sleep(1)
case("the tool finishes", j.get("state") == "done", (j.get("state"), j.get("lines", [])[-5:]))
st, d = call("POST", "/api/tools/word_shares", {"args": {"topic": "weather; rm -rf /", "label": "x", "source": "massive"}})
case("tool arguments are checked", st == 400, d)
st, d = call("POST", "/api/tools/regress", {"args": {}})
jid = d.get("job")
for _ in range(300):
    st, j = call("GET", f"/api/jobs/{jid}")
    if j.get("state") != "running":
        break
    time.sleep(1)
tail = [x for x in call("GET", f"/api/jobs/{jid}")[1]["lines"] if " pass" in x]
case("regression cases run from the Tools page", bool(tail), j.get("lines", [])[-5:])
print("  regress from the page:", tail[-1] if tail else "?")

st, d = call("GET", "/api/audit")
case("the audit log has the changes", any(e.get("action") == "setting changed" for e in d["events"]), d["events"][:3])
st, d = call("DELETE", "/api/session")
st, d = call("GET", "/api/overview")
case("signed out", st == 401)

print(f"\n{len(PASSED)} pass" + (f", {len(FAILED)} fail" if FAILED else ""))
sys.exit(1 if FAILED else 0)
