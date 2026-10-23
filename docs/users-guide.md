# Wepwawet Veil: the user's guide

Wepwawet Veil sits between your voice assistants (the examples here are Iris and Felix) and the cloud. When you
speak to one of them, the router decides whether the house can answer by itself or whether the
request has to go Off-Platform, to the cloud model. Everything it can keep at home is faster,
private, and free.

This guide is for using it. How it's built is in the Coder's guide.

## The routes a request can take

A route is the way a request travels, box by box. Wepwawet Veil is the router; every answer goes
back the way it came, through LiteLLM to Home Assistant, which speaks it on the device.

**The words** (only when the router is in the audio path, Integrations, Oread):

    Device -> Home Assistant -> Wepwawet Veil (the audio) -> Oread -> Wepwawet Veil -> Home Assistant

Oread turns speech into words and says who spoke. The router passes the audio through and notes
the speaker and the timings. With Oread on but not in the audio path:

    Device -> Home Assistant -> Oread -> Home Assistant

**Answered at home**, by an app the router knows (the weather, chores, the bakery and so on):

    Device -> Home Assistant -> LiteLLM -> Wepwawet Veil -> the app

**Answered by the router itself**: its own questions, "never mind", and answers from the
Off-Platform Bank:

    Device -> Home Assistant -> LiteLLM -> Wepwawet Veil

**Off-Platform**: everything the house can't answer:

    Device -> Home Assistant -> LiteLLM -> Wepwawet Veil -> LiteLLM -> the cloud model

**A device command from Off-Platform**: the model asks Home Assistant to act, then a second trip
for its words:

    Device -> Home Assistant -> LiteLLM -> Wepwawet Veil -> LiteLLM -> the cloud model
      -> Home Assistant does it -> LiteLLM -> Wepwawet Veil -> LiteLLM -> the cloud model

**Home Assistant's own commands**: understood by Home Assistant itself. With Veil Guard Service
installed, Home Assistant asks the router's firewall first:

    Device -> Home Assistant -> Wepwawet Veil (Veil Guard Service asks) -> Home Assistant does it

Wepwawet sits between all applications, both in-bound and out-bound: Home Assistant and Oread
never talk directly. For what Home Assistant answers by itself (the weather from its own weather
entity, the time), the words still pass through the router on their way back from Oread; when
Home Assistant sends them on to neither the chat door nor the guard within a few seconds, they
are counted as **Home Assistant itself**, so every request heard is on the pages.

    Device -> Home Assistant -> Wepwawet Veil (the audio) -> Oread -> Wepwawet Veil
      -> Home Assistant answers

How many requests take each route, and how long each hop takes, is on the Stats page. Stats
calls the routes At home (the app's name), The router itself, Off-Platform Bank, Off-Platform
(every trip to the cloud model, including its words after a device command), Wepwawet Musings
(brain fleas) and Home Assistant itself. On Transactions, each request's **Went to** says
`home: <app>`, `home: the bank`, `home (path ...)` for the router itself, the cloud model's name
(or Off-Platform), Home Assistant itself, or blocked (the firewall).

## How a request is claimed

Every request on its way in is offered to the apps and add-ons in turn, each looking for its own
key word: an app's (integrations first), then an add-on's (Brain fleas). The first to find one
claims it; one with no key word in the words hands them back at once, and a request no one claims
goes Off-Platform. A day said in a request ("Saturday") is nobody's key word on its own.

When the one that claimed it can't answer yet, it says what's missing, and the others are asked
to fill it in. Each fills in at most once, so nothing goes round in circles:

- "Will it rain Easter Sunday?": the weather claims it; the Liturgical calendar knows Easter's
  date, so the weather is asked about Sunday, March 28.
- "Is it going to rain for the picnic?": the weather needs a day. If a chore is called picnic,
  she checks first ("You mean the picnic on Wednesday?"); if nothing is, she asks "When is the
  picnic?", and your answer goes to the weather.
- "Will it snow on the Feast of Steven?": two saints called Stephen fit, so she asks which.

## Add-ons

What isn't the router's own job is an add-on, switched on or off on the **Add-ons** page (System).
Each says what it does, whether it keeps requests at home, and where on the way it works:

- **On the way in**: Mishearings (fixes the words you marked first), Brain fleas, Time (a day
  another app knows, like a feast's date), Loose language (below), the Off-Platform Bank, Did you
  mean (below), and the Firewall (always last).
- **On the way out**: Persona Flair, Name Sparkle and Roman numerals ("Henry VIII" read as "Henry
  the Eighth", also in answers from the cloud). The page's **Outbound order** sets which goes
  first; one that changes words inside her answer always comes before one that adds to it. Two of
  those: try both orders with the same sentences and keep the one that reads right.

An add-on that's off has no page and no menu item, and the router works as it did without it.

## Saying it loosely (Loose language)

With Loose language on, an add said the way people talk is filled from your own picks and asked
about, a question at a time:

- "This weekend", "tomorrow morning": she offers a day or a time ("Would Saturday at 9 AM work?").
- **A deadline** ("submit tax documents by April 15", "renew car registration Sept 30"; by, before,
  due, till): it's due then, the last possible moment, 11:59 pm when no time was said, and she
  asks whether to remind you before ("Do you want a reminder before then, a week before at 9 AM?").
- **"Remind me to buy palms on Sunday"**: she asks whether Sunday is the day to remind you or the
  day it's due.
- **"... not until Friday"**: the reminder comes after Friday; she offers the day after.
- **"Bake a cake for Easter Sunday"**: the days before Easter are offered.
- An answer she can't use: she says she didn't follow and asks it another way.

With it off, chores work as they always did: the day you say is the due date, and after an add
she still offers a due date, a repeat, a reminder before, or nags.

## The menu

The menu has a small picture beside each page. Hide it with the arrow at its top (wide screens);
"Menu" brings it back. On a phone it folds into the bar at the top.

### Watch

- **Transactions**: every request, newest first. Up to four buttons on each:
  - **Why**: why it went where it went (shown when there's a reason to give).
  - **Delete**: it was right and routed right; nothing to learn, so it leaves the log.
  - **Bank**: a request that went Off-Platform goes into the Off-Platform Bank, so its answer can
    be given at home next time.
  - **Misheard** (with Mishearings on): speech to text got it wrong. Type what was really said
    (optional; you can type it later); it goes to the Mishearings page, under what was really
    said, and counts up each time the same thing is misheard. Those counts are how the router
    learns which words to catch.
  Once you bank a request or mark it misheard, it leaves the list
  (another asking of the same saying stays until you act on it); the "Handled" choice above the
  list brings handled ones back.
- **Off-Platform Bank** (an add-on): the answers kept from the cloud, per personality. It collects from the
  start but **answers nothing until you turn on Use the bank** (its Rules tab; off when
  installed). Then a saying you added (Bank, on Transactions) is answered from the bank some of
  the time instead of making the trip. The Rules tab has the formula's two knobs (answers kept,
  5, and use from, 0.2) beside the switch; a line above the table says whether the bank answers
  at all, and each saying's **State** column whether it answers that one yet.
- **Who can answer this?** (built in, Settings: ask_apps_first): a request nothing at home claimed is
  asked of the apps before it goes Off-Platform: each app whose own find opens it ("Can you find ...",
  "When is ...", "How many days until ...") looks it up, changing nothing, and the one that finds it
  answers ("When is Easter?" from the Liturgical calendar). It must fit by two words, or by the one
  word you said; two apps that both find it, she asks which. The weather brain is asked too, and says
  whether it's a weather question. When no app has it, a brain flea that fits is offered, never
  answered on a guess: "Did you mean "who is talking to you"? Shall I?" A sentence longer than 15
  words is taken as conversation. Why on Transactions shows it as step 12.
- **Trainer** (an add-on, Teach, Trainer): switched on for a person, it walks their requests that
  weren't said in full through the house's routine, announcing trainer mode first: "Trainer mode: I
  think you want to add a chore. Shall we do that together?", then the chore's name, the day, the
  time and who it's for, and the chore is added. A request said in full: it stays silent. Only when
  the voice ID is sure it's them. Switch it on the page (from their next request, no restart) or by
  voice: "Trainer mode" (she asks for whom and says its state), "Turn on trainer mode for Sam",
  "Turn off my trainer mode". Anyone may switch their own; someone else's needs a changer.
- **Did you mean** (an add-on, off when installed): when speech to text loses a seed word ("Mark
  the troll done" for "Mark the chore done") and the request would go Off-Platform, she asks first:
  "Did you mean "Mark the chore done"? Shall I?" Only the word in the chore's place (right after
  add, mark, find and the like) is corrected; the rest is left as you said it, and after add she says
  the name apart: "Did you mean: Add a chore, "Pack for the shore"? Shall I?" Yes does it at home and keeps the mishearing
  (Misses); no sends your words out as heard. She asks whenever an app at home would take the
  corrected words with one of its own action words. The never words, the close-by words and each
  seed word's place are yours to fill in, in addons/window/settings.yaml: chores, the weather, feast
  days and history to start. A household with its own odds for whether a guess is worth the question
  puts them beside it (odds.py); without them she always asks. Every request it weighs, asked or not,
  is recorded in data/tables/window.db with your answer (yes, no, or something else said instead)
  and the words as they were heard: your own count of what was misheard and what wasn't.
- **Misses**: the wrong part answered ("Who answered that?", then "Record that as a
  misunderstanding"), each with what should have happened. Its **Tools** tab reviews the misses
  against today's router, makes one a test case, or drops one.
- **Mishearings** (an add-on): what speech to text heard, under what was really said, word by word,
  and whether it would still go wrong today. The table sorts by First and Last too. The swaps in
  use are a folded table: heard, swapped for, when added, how often used, when last used.
- **Use it** (Mishearings): under a mishearing, each wrong-word difference has a Use it button
  ("grainsplate → brain flea"). Once used, those heard words are swapped for the right ones before
  anything is decided, every time, whole words only. **Use a phrase** does the same for a run of
  words ("who taught you three" → "who taught you that"): only that whole run is swapped, so a
  common word like "three" is left alone everywhere else. Stop takes either back. Swaps are also
  made in the words handed back to Home Assistant, so its own sentences and automations match
  ("Is the watcher running?" reaches your washer automation as "Is the washer running?"). That
  makes Use it on a common word change it everywhere: "watcher → washer" would turn "Who is the
  watcher?" into "Who is the washer?". Use a phrase for those ("the watcher running").
- **Every table** sorts by a click on a heading (again to reverse) and can be folded away with
  **Fold the table** (Show the table brings it back), remembered in your browser.
- **Rules tabs**: Off-Platform Bank, Misses, Savings, Seed Topics, Tools and Stats each have a
  **Rules** tab with that page's own settings (from settings.yaml).
- **Savings**: trips and tokens kept in the house.

### Teach

- **Try it**: type something (the **Say** box) and see where it would go, without doing it.
- **Seed Topics**: the words that point a request at an app. Each topic is folded; open one to
  change it. Services come from Integrations (and settings.yaml). Its **Build** tab rebuilds the
  word scores from the datasets (Build the keyword tiers, then restart) and has the utilities
  that look at the datasets; its **Rules** tab, the build's settings.
- **Words understood**: the words the router understands rather than says, from the vocab/
  files (yes and no, fillers, polite words, the learn commands, dates, moods), each list edited
  as chips and saved on its own; used after a restart.
- **Brain fleas** (an add-on): the household's small true facts, answered at home before anything goes
  Off-Platform ("Who is talking?", "Where do we get pizza?"). "What brain fleas do you have?"
  reads them, a few at a time. A sentence telling a fact ("we only get our pizza at...") isn't
  taken as asking a flea. This page, an app's User rules and
  its Voice map refuse a save made from a copy older than the file (the fleas or rules changed
  by voice, in the file or on another page since you opened it): reload, then make the change
  again, so the newer change isn't undone. Each flea has the ways it's asked
  (`who is {speaking | talking}` for choices) and its steps, built a line at a time like an app's
  User rules: **Who spoke** (Name Sparkle's name, or the voice ID's own; Sure 70% and Hedge 60%
  to start; never a guess) and
  **Response** (its lines, one each time, its flair added). A way of asking of one or two words is
  a key: hearing all of it is enough. **Match at** says how closely a sentence must fit. By voice:
  "Add a brain flea, we only buy pizza from Sal's" (it reads it back first), "Change the pizza
  flea to ...", "Forget the pizza flea", only for the voices ticked under **who may change fleas
  by voice**, and only when Oread is sure it's them. A topic still comes first: "When is trash
  pickup?" is a chores question. Saved fleas work at once, no restart. **Who spoke** names someone
  only when Oread's score reaches its Sure %; between Hedge and Sure it says it thinks so, and
  below Hedge it politely gets out of it ("I'd rather not guess"). A flea that says no ("that
  isn't nice") never answers one that doesn't ("that is nice").
- **Tools**: the tests (Regression cases, Regression cases live, Gemini gate test, Unit tests).
  Rebuilding the word scores is on Seed Topics, Build.

### Personality

- **Sayings**: every fixed line she says, her own or the shared ones any persona says, one
  assistant at a time. An edit is heard after a restart.
- **Persona Flair** (an add-on): the little lines it adds, one assistant at a time (pick it at the top).
  First **Flair rate** (the share of answers at home with a line; 0 is off) and **Most in a row**;
  then the **Lines bank**, its own lines (**Add lines**: one, or many separated by | or one per
  line, then **Add to the lines bank**); then **Lines from the books**, folded. Its **Phrases** tab says where
  the lines from the books come from; her fixed lines are on the Sayings page.
  - A line's **topic** is the kind of request it fits; **any** fits them all.
  - Its **place**: **opener** (before the answer), **closer** (after it), **any** (either), or
    **aside**: only where a reply has a hand-placed [[aside]] mark. Most lines want any.
- **Name Sparkle** (an add-on): a tab for each persona (how often it says your name, and its own names for you) and a Shared tab (the names every persona can use).

### System

- **Add-ons**: each add-on with what it does, switched on or off (used after a restart), and the
  outbound order (above, Add-ons).
- **Overview**: the numbers for the last day, where requests were answered over the last week,
  and what's running.
- **Stats**: built to find a bottleneck. Pick an assistant at the top to see only its own
  requests (to compare two assistants). Brain fleas are their own route, **Wepwawet Musings**.
  The 30-day usual comes from one summary per route per day, so it reaches back further than the
  activity log keeps its rows. In this order:
  - **Is anything slow?** Each route's typical time today, over 7 days and over 30, with its
    30 days as small bars; a route is flagged "slower than usual" when today is slower than its
    usual by the amount in settings (stats: slower_than_usual, 1.5 times, once there are at least
    slow_min_requests, 3, today). If one of your apps drags, it
    shows here first.
  - **Which leg was slow?** For each route used today, one line naming the slow leg: the
    router's own work (software), the machine (how busy the whole machine was), the outside
    hop (the app, or LiteLLM and the model) and, for Off-Platform, the internet, each today
    against usual. Under it, the slow requests, each with its internet check: "Slow. Internet
    4x slower than usual (120 ms, usual 30 ms)" means your internet provider; "Internet normal
    ... LiteLLM or the model was slow" means the far end. The check pings 1.1.1.1 and 8.8.8.8
    after an Off-Platform request, at most every 5 minutes (stats: internet_check).
  - **The requests that cost the most CPU** over the last week: the words as heard, how often,
    the most and typical CPU. **Try it** runs one through the router again; **Copy** takes the
    words so you can say or type them while debugging.
  - **What the router costs to run**: CPU and memory now, over the last hour, day, week and
    month (like Oread's Stats), and CPU hour by hour for the week.
  - **What the router is holding now**: each device's waiting question, last topic and turns.
  - **By period** (pick it there; everything below follows it): the numbers, **Where the time
    goes** (starting with **the router's own hops**, one after another: its hand-off to Oread and
    back, its deciding, LiteLLM's own time, the model's, the app's, and **back to Home Assistant**,
    read from Home Assistant's own record of each run a few seconds after the answer, which needs
    its address and token; then each hop of each route: speaking, Oread, Home Assistant in, the router deciding,
    LiteLLM itself, the app or the model, the router in all, and the router's CPU; and **Sent
    again**, the same request coming in a second time while it was still being answered, which
    is answered once and the answer sent to both), where requests were answered, by assistant,
    and a day. For the way back to Home Assistant and its text to speech, which the router can't
    see, run tools/ha_timings.py (the coders' guide).
  Point at any bar, slice or line for its number; every number is also written in a table.
  Every box folds by its heading, and the page remembers which you folded.
- **Every table**: drag a heading's right edge to make a column wider or narrower; double-click
  the edge to put it back. Widths are remembered in your browser. A table wider than the page has
  a scrollbar above it as well as below.

### Connect and protect

- **Integrations**: Home Assistant, Oread, LiteLLM and the apps. When an address was refused in the
  last hour (security: refused_warn_minutes, 60), a warning at the top says which, how often, and
  which address used that door before: a program back at a new address after a power cut. Permit
  it on Security, or give it its old address back. Every one has the same tabs, in
  the order you'd add an app. An app marked **Wepwawet compliant** (Oread, the weather brain)
  says in its own description which tabs apply; the others show grayed out:
  - **Connection**: on or off, its address, Test. A chores app's card also has **Clean-up**:
    **Bring overdue repeating chores forward** lists every repeating chore past its date (nobody
    marked it done) with its next date from today on, its time of day kept; **Move** moves them.
    A chore that doesn't repeat is never moved, so a real miss stays seen.
  - **URL / ports**: where it is, its spec's address, the key the router sends it, and the
    doors it uses to ask the router.
    Home Assistant is set up differently, but to the router it's one more program asking and
    being answered. Oread asks through the **oread door**: it pulls the mishearings (with the
    clip each was heard in) for its own Mishearings page. Make its token on Security, API keys
    (tied to the oread door) and put it in Oread's vault as wepwawet; Oread's Mishearings page
    has a box for it, and for the router's address.
  - **Commands**: the app's own commands, read from its spec. Read it again after the app is
    updated: each change is marked (ADD), (Modified) or (Deleted), and nothing changes until you
    press **Accept the changes** (or **Keep the saved list**). It also shows the app's version as its own spec gives it: the version its commands
    were accepted at, and the version it runs now (from the latest read). A new version waits for
    Accept even when the commands look the same, since an update can change what a command does,
    and the Integrations list flags it. The router also reads each app's spec once when it starts
    (Settings: check app versions at start), so a new version shows without you pressing anything.
    An app whose spec names no version is compared by its commands alone.
  - **Voice map**: **match min** and **sound alike** at the top (how much of a name must be said;
    sound alike also tries how the words sound, "by single hole faucet" for "Buy single whole
    faucet", and asks before acting; Save, then restart), then what can be
    said to it, one folded card per action. Each action is a word of your own, the command it
    calls, the words that pick it, what the app requires for that command, and the **spoken
    needs**: required (it asks if you didn't say it, like "When?"), optional, or default (the
    app's option fills it in).
  - **User rules**: for what one command can't do alone, like renaming a chore whose name was
    misheard. A rule chains the app's own commands with the router's steps (Call a command,
    Search, Filter, By date, Match, Confirm, Ask, Fresh copy, Who spoke, Response), one line per
    step, each with its own settings; point at a step
    to see what it does. Match has your two percentages: at or above Act (85) it acts; between Ask
    (45) and Act it asks "I believe I heard you say ... Is that right?"; below Ask it says it
    couldn't find it. A rule stays inside its topic: say a chores word ("Rename the chore mow
    lawn to cut the grass"), or right after it reads a chore back, "Rename that to ...". Donetick
    comes with **rename** and **rename_project** ("Rename the house project to home") and **find**
    ("Can you find the camera chore?", "When is the trash due?", "What time is it due?", "What's the
    due date on that chore?": the chore and when it's due; not sure which chore, it asks first).
    **Response** can say the matched item's own fields: under fields, a name and the item's field
    (due: nextDueDate) puts it in a line as {due}, a date said as a day and time ("tomorrow at
    1 pm"); empty lines are said instead when one of them is empty ("{item} has no due date.").
    **Save the rules**: used at once.
  - **ask_min** (Donetick 0.4, in its voice map): when no chore is sure, one that scores at least
    this, or has every word you said, is asked about ("Spray weeds? Say yes") instead of "couldn't
    find". **never_by_voice** (delete, archive, erase): said, it says it's done on the app's own
    page.
  - **Clean-up words**: the app's own lists. Its **strip_away** is the app's layer of the words
    left off either end of a thing's name ("add clean the gutters to my LIST"): how people talk
    ("I need to", "please") is shared by every app (vocab/language.yaml strip_away), the app adds
    its own nouns, and an action can add more (its voice map entry's strip_away).
  - **Defaults**: **What it offers** (a compliant app's switches, like Oread's **who spoke**
    and how it comes), its **Lists**, each a card you name (people, project...): where its items
    come from and its **default**. The people card also says who each of the app's people is in
    the house (so a voice Oread knows lands on the right person) and who "me" means. Then its
    knobs (like Donetick's default chore time, and **remind_when_timed**: a chore given a time is
    announced at that time unless you say "don't remind me"; and **extras_win_while_asking**, a
    stopgap: while it asks "anything else?", "put a nag every ten minutes" is an answer about the
    chore just added, not a new chore), typed or picked from what an app answers. A time said with
    no day means today (tomorrow if it has passed); "every half hour" and "a quarter of an hour"
    are understood as amounts. Save, then restart.
  - **Getting ready**, always last: each step of adding it, done or not.
  - **Add an app** (at the bottom of the list), for an app that isn't there yet: first add its
    key on Security (Grantors, Add a key); then pick the key here and the app takes its name. It
    starts switched off. Appendix A walks through it. The steps
    are in the Coder's guide, "Adding an app we didn't write".
- **People**: one row per person, a column per attached app (Add a column), plus Wepwawet (the
  router's own name, optional) and Called (what people call them out loud). Names in a cell are
  separated by commas. Inside the router any name in a row is the same person: the firewall and
  who may change brain fleas match on all of them, so Oread's "Sam" profile counts as Owner. A
  name is one person, like a sign-in: it can be in one row only, so two people can't both be
  "Alex" (call them Big Alex and Little Alex); a save that puts a name in two rows is refused. An
  app asks for its own column only (Oread through its door: GET /people/oread).
- **Firewall** (an add-on, always last): rules about who may do what. With Oread off, every voice is "unknown", so rules
  for anyone or unknown are the ones that apply. A device name that no Home Assistant device has
  (a misspelling stops nothing) is warned of at the top, read with Home Assistant's token. A rule's people match any name in that person's
  row on the People page.
- **Security**:
  - **Users**: people who sign in, and the sign-in rules.
  - **API keys and vault**, with a choice at the top:
    - **Grantees**: programs the router made a token for. Each door (the router's addresses a
      program calls) is one line: Locked, what it is and who calls it, its token, when the token
      was last used, and Revoke (or Make its token). Lock a door only after "last used" shows
      the program used its token. **Add a door** when a new program needs to call the router.
      A token made for a door opens that door only, and never these pages' own API; a token
      tied to no door works on the pages' API with its role.
    - **Grantors**: programs the router needs a key from (LiteLLM, Donetick...): where each key
      comes from and whether it's in the vault, with Set, Replace and Delete. **Add a key** is
      the first step of adding an app.
  - **Addresses**: which machines may reach the router (empty means the local network only;
    the entry **local** keeps the local network in a list that also names addresses, and the
    going-out list may name an app on the internet, like litcal.johnromanodorazio.com), the
    machines recently let in and the ones refused, each with an Add button.
  - **Audit log**: who changed what.
- **Settings**: **The house** first (its timezone, picked from the standard list; where the house
  is belongs to the app that needs it, like the weather brain), then the
  settings that have no page of their own, grouped in sections, each with what
  it does (End Device Settings has the **echo** guard: when a device like the Voice PE hears its own
  voice and sends its words back, it stays silent instead of answering itself, so the loop
  stops; Transactions shows it as an echo. It's caught by its words in the same order, or by most
  of its answer's words coming back, even misheard and with talk from the room on the end. The
  question it was waiting on stays through an echo, **echo_keeps_question**, so you can still
  answer it with the wake word; and a short yes or no to it, like "Read the rest.", is always
  your answer, never an echo, even when every word of it is its own; a request more than twice as
  long as its answer isn't an echo of it, **echo_cover_longest**).
  **add_name_max_words** (8) is the longest name it takes, said in the add or as the answer to
  "what's it called?": longer is talk, and it asks for the name. **lone_door_max_words** (12): a
  longer sentence whose only topic word is one door ("...we were talking about marriage") isn't
  sure of the topic; a topic's seed words ("chore", "list") are still enough. Type in **Find a setting** to narrow them. Save lights up once you change a value. A
  line at the top links the pages that keep the rest.
  When an update ships something new in the starting copies (below), **New in the starting
  copies**, at the bottom of the page, lists it, with **Add** or **Not for us**.

### You

- **Account**: your password, and **Look**: light, dark or follow the device, and the colour
  scheme (five, each with three colours). The look is kept in this browser only.
- **Guides**: tabs for the User's guide, the Coder's guide, Design (only in a development copy:
  a public install says it isn't there) and the README.

## When it isn't sure which one you mean

When you change something by voice (mark a chore done, skip it, move it, nudge someone), it
matches what you said against the app's own list, read fresh at that moment:

- **Every word you said is in one name:** it does it, and says its name back.
- **Two fit equally** (Mow Lawn and Mow the lawn): it asks "Do you mean Mow the lawn in Voice
  Tech, or Mow Lawn in House?", the default project's first. Answer with a word only one has
  ("the house one") or by order ("the first one"). Anything else, and it leaves both alone.
- **One fits, but you said a word it doesn't have** (often a mishearing, like "lawn pest"): it
  checks first, "Mow Lawn? Say yes and I'll check it off.", and does it only on a yes.
- **Only one has the words you said that no other has** ("the walkie-talkie tour" for "Leave the
  walkie-talkie at school"): it asks about that one, though you said only part of its name.
- **"That" or "it"** means the thing she last named, or the one she just asked about: "Yes, could
  you change the time on that to 3:45?" answers her "Is that right?" and changes that chore.

"Do you have a picnic in my chores?" is answered with its day, or "No, there's no picnic in your
chores."

## Your household's files, and the examples

Everything the pages save is your household's own: the settings, the firewall, each app's voice
map, the keyword files, the datasets list, your recorded misses, and your assistants' personality
and flair. A public release never carries yours: it ships the starting copies below instead.

A fresh install starts from **starting copies** (in defaults/), which are examples from one
household: the topics (weather, chores, feast days, history), Donetick's voice map, settings with
that house's addresses, an empty firewall, and an example assistant. Every app starts switched
off. **Change them to fit your house, and delete what you don't use**: a topic you don't want on
Seed Topics, an app on Integrations, the example assistant once you've made your own.

### The sample apps

| App | Answers | To switch it on |
| --- | --- | --- |
| Liturgical Calendar | "What feast is today?" | Nothing to install. Integrations, **On**, Save, and restart; ask it once, then Security, Addresses, Going out, Recently refused: **Add** it (by its name, litcal.johnromanodorazio.com) and Save |
| Wikipedia (On this day) | "What happened on this day?", "Who was born today?" | The same: nothing to install; permit en.wikipedia.org going out (and raw.githubusercontent.com, where its spec is checked for a new version) |
| The weather brain | The weather, sunrise and sunset | Its own install ([weather_brain](https://github.com/coderpigsfly/weather_brain)); then on Integrations its address, **On**, Save, and restart |
| Vikunja | Chores, each person's own list and a shared one: add, list, check off, move, change the time, delete (always asked first) | Its own install ([Vikunja](https://vikunja.io)); its key (Security, Grantors, **Add a key**, VIKUNJA_TOKEN); then **Add an app** on Integrations (its voice map and rules are already in the starting copies), its address, **On**, Save, and restart. Vikunja on SQLite needs its writes to lock up front: `VIKUNJA_DATABASE_PATH=/db/vikunja.db?_busy_timeout=5000&_txlock=immediate&_ignore=` |
| Donetick | Chores: add, list, check off, move, nag | Its own install ([Donetick](https://github.com/donetick/donetick)); its key (Security, API keys and vault, Grantors: **Set** on DONETICK_TOKEN); then on Integrations its address, **On**, Save, and restart |

The two on the internet are switched off on purpose: a question to one of them leaves the house,
and nothing leaves until you choose.

When a release ships something new in a starting copy (a new setting, a new pinned word), it
doesn't land in your files by itself. Settings, **New in the starting copies**, lists each one:
**Add** puts it into your file (your comments kept; most take effect after a restart), **Not for
us** hides it for good. Values you've changed are never listed: yours win.

Your assistants' personality is never shared at all: no starting copy but the example.

## Appendix A: adding an app that isn't Wepwawet compliant

An app that doesn't describe itself to the router (no `x-wepwawet` section in its spec) still
works: every tab stays open and you fill them in yourself. These are the steps for an app that
isn't on Integrations yet. Donetick, the chores app, already comes in the starting copies with
every step below done for it, so it's the example of what each step makes (its key is only
**Set**: see The sample apps). The full routine is in the Coder's guide, "Adding an app we didn't
write".

1. **Its key:** Security, API keys and vault, Grantors, **Add a key** (the app's own key, made
   on the app's own settings page).
2. **Add an app** on Integrations: **Its key** (picking it names the app; or type a **Name**),
   a **Title**, its **Kind** (an app we didn't write, with an OpenAPI or Swagger spec), its
   **Address**, **Its spec (OpenAPI)** (the address of its spec) and the **Topic** it answers,
   then **Add the app**. It starts switched off.
3. **Commands:** Read its spec. Every command the app has is saved with what it requires.
4. **Voice map:** one card per thing you can say (Donetick's: list, projects, add, complete,
   skip, move, nudge, undo), each calling one of its commands, with the words that pick it and
   its spoken needs. **User rules:** like Donetick's rename, which finds the chore even when its
   name was misheard.
5. **Clean-up words** and **Defaults** (Donetick's: its people and projects as list cards, who
   "me" is, its default chore time).
6. **Getting ready:** work down the checklist; when it says Ready, switch it on (Connection),
   Save, and restart.

### The app's own flaws: noted, not worked around

The router never patches over a gap in someone else's software. When the app can't do
something, it says so plainly and points you to the app's own page. Donetick's, found while
testing (Oct 2026):

- **Undo works only for a completion.** Donetick's spec says its undo reverses the last
  completion *or skip* within 5 minutes, but asked to undo a skip made seconds earlier it
  answers 400 Bad Request. It has no undo for a move, a nudge or a new chore at all. So the
  voice map's undo card says `reverses: [complete]`; for anything else it says "Donetick
  doesn't let me undo a skip. Please change it on Donetick's web page." If Donetick fixes it,
  add `skip` back to that list; no code changes.
- **A change needs the chore's `updatedAt`.** Moving a chore (and changing its status,
  assignee or timer) is refused unless the chore's last-updated time is sent with it. The
  router reads the chore fresh just before the change.
- **The address needs its last slash.** Creating a chore at `/chores` is redirected to
  `/chores/` and nothing is made; the router uses `/chores/`, and counts any redirect as a
  failure, so it never says "Added" unless Donetick returns the new chore.
- **An edit must send the whole chore back,** labels included (`labelsV2`), or Donetick fails.
- **Skipping a one-time chore archives it.** That's Donetick's design: a skip moves a
  repeating chore to its next time, but closes a chore that never repeats.
