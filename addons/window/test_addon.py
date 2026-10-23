"""The window's own tests (run by tools/test_addon.py window), written as conversations: what was heard, what
an app at home would take, and whether she asks. These run by the plain rule; a household's own odds (odds.py)
bring their own tests (test_odds.py beside them), run after these when they're there."""
import importlib.util
import os
import sqlite3
import tempfile


def at_home(words):
    """A stand-in for the core: the chores app takes a chore said with one of its words."""
    w = words.lower()
    return "chores" if "chore" in w and any(v in w.split() for v in ("mark", "add", "delete", "find", "my")) else None


def run(mod, check):
    notes = []
    ctx = {"assistant": "iris", "at_home": at_home, "step": notes.append}
    ask = lambda said, c=None: mod.before_off_platform(said, c or ctx)       # noqa: E731
    meant = lambda said, c=None: (ask(said, c) or {}).get("meant")           # noqa: E731

    folder = tempfile.mkdtemp()
    mod.DB = os.path.join(folder, "window.db")
    odds, mod.ODDS = mod.ODDS, None          # the plain rule: asked whenever an app at home takes the words
    check("heard 'Mark the troll done': she asks about the chore", ask("Mark the troll done"),
          {"kind": "ask", "meant": "Mark the chore done", "by": "window", "head": "Mark the chore", "payload": ""})
    check("heard 'Add a chew to mow the lawn': she asks about the chore", meant("Add a chew to mow the lawn"),
          "Add a chore to mow the lawn")
    check("heard 'what's on my chews': a never word said with an s comes back as chores", meant("What's on my chews"),
          "What's on my chores")
    check("the chore was heard: nothing was lost, she doesn't ask", ask("Mark the chore done"), None)
    check("heard 'I took a tour of Rome': the tour isn't in a chore's place, she doesn't ask", ask("I took a tour of Rome"), None)
    check("heard 'Rename the tour': no app at home takes 'Rename the chore' here, she doesn't ask", ask("Rename the tour"), None)
    check("...and the why says so", notes[-1], "\"tour\" might be chore, but \"Rename the chore\" isn't taken at home: not asked")
    check("'short' alone is a word of its own: 'a short walk' isn't asked about", ask("Take a short walk with my dog"), None)
    check("'short' with a close-by word: 'Mark the short five complete' is", meant("Mark the short five complete"),
          "Mark the chore five complete")
    check("'shore' (ch said as sh) with a close-by word: 'Mark the shore done' is asked about", meant("Mark the shore done"),
          "Mark the chore done")
    check("'shore' alone: 'We drove to the shore' isn't", ask("We drove to the shore"), None)
    check("'Add a shore. Pack for the shore.': the command is corrected, the name kept as heard",
          {k: v for k, v in (ask("Add a shore. Pack for the shore.") or {}).items() if k in ("meant", "head", "payload")},
          {"meant": "Add a chore. Pack for the shore.", "head": "Add a chore", "payload": "Pack for the shore"})
    check("'Pack for the shore, add a shore': only the shore in the chore's place", meant("Pack for the shore, add a shore"),
          "Pack for the shore, add a chore")
    check("'add a chew to mow the lawn': the name said back is 'mow the lawn'", (ask("Add a chew to mow the lawn") or {}).get("payload"),
          "mow the lawn")
    check("a never word away from the chore's place isn't asked about ('find the coffee tour')", ask("Find the coffee tour"), None)
    check("words already sent out by a yes or a no: never asked again", ask("Mark the troll done", dict(ctx, rewrite=True)), None)
    check("no core to ask (the gate): never asks", ask("Mark the troll done", {"assistant": "iris"}), None)
    old_home = ctx["at_home"]
    ctx["at_home"] = lambda words: "weather" if "weather" in words.lower() else old_home(words)
    check("heard 'What's the whether tomorrow': she asks about the weather", meant("What's the whether tomorrow"),
          "What's the weather tomorrow")
    check("'whether' as a word of its own ('I don't know whether to go'): not asked", ask("I don't know whether to go"), None)
    ctx["at_home"] = lambda words: "feasts" if "feast day" in words.lower() else None
    check("heard 'Whose beast day is today': she asks about the feast", meant("Whose beast day is today"), "Whose feast day is today")
    check("'a piece of cake': no feast app takes it, not asked", ask("Give me a piece of cake"), None)
    ctx["at_home"] = old_home

    check("the plain rule says so in the why", '"beast" might be feast ("Whose feast day is today", feasts): '
          'the plain rule: she asks' in notes, True)

    with sqlite3.connect(mod.DB) as db:
        rows = db.execute("select heard, meant, asked, p, l from windows order by id").fetchall()
    check("every window weighed is recorded, with no odds by the plain rule", (len(rows), rows[0], rows[-1]),
          (10, ("Mark the troll done", "Mark the chore done", 1, None, None), ("Whose beast day is today", "Whose feast day is today", 1, None, None)))
    mod.answered("iris", "yes", "Yeth, pleathe.", "20261022-111013-347-iris")
    mod.answered("iris", "no", "No.")
    with sqlite3.connect(mod.DB) as db:
        got = db.execute("select heard, answer, answer_heard from windows where answer is not null order by id").fetchall()
    check("the answer is kept on the newest window she asked, once, with the words as heard",
          got, [("Whose beast day is today", "yes", "Yeth, pleathe.")])
    pulled = mod.rows()
    check("Oread pulls every window, oldest first, with the answer and its clip",
          (len(pulled), pulled[0]["heard"], [(x["heard"], x["answer"], x["answer_clip"]) for x in pulled if x["answer"]]),
          (10, "Mark the troll done", [("Whose beast day is today", "yes", "20261022-111013-347-iris")]))
    check("...and only the ones since a time", mod.rows(since=pulled[-1]["at"]), [])
    with_clip = mod.before_off_platform("Delete the chop", dict(ctx, at_home=at_home, clip="20261022-120000-001-iris", device="iris"))
    check("a window keeps Oread's clip and device of the request", (bool(with_clip), mod.rows()[-1]["clip"], mod.rows()[-1]["device"]),
          (True, "20261022-120000-001-iris", "iris"))
    old_db = os.path.join(folder, "old.db")
    with sqlite3.connect(old_db) as db:
        db.execute("create table windows (id integer primary key, at real not null, assistant text, heard text not null, "
                   "meant text not null, seed text, never text, close_by text, app text, a real, b real, lr real, k real, "
                   "e real, p real, l real, asked integer not null)")
        db.execute("insert into windows (at, assistant, heard, meant, asked) values (1, 'iris', 'x', 'y', 1)")
    mod.DB = old_db
    mod.answered("iris", "no", "Nope.")
    with sqlite3.connect(old_db) as db:
        check("a table from before answers were kept gets their columns", db.execute("select answer from windows").fetchone(), ("no",))
    mod.DB, mod.ODDS = None, odds

    own = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_odds.py")
    if odds and os.path.exists(own):
        spec = importlib.util.spec_from_file_location("addon_window_odds_tests", own)
        theirs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(theirs)
        theirs.run(mod, check, at_home)
