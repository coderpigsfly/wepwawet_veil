# Wepwawet Veil: Coder's Guide

*Private AI routing. Leaner context. Smarter handoff.*

How to use and look after Wepwawet Veil, the house router (`~/docker/house-router`): what to say, where things live, the pages, and the commands. The examples use the example personas, Iris and Felix.

(The project is named Wepwawet Veil; the folder, the container and the model name the router gives itself all keep the name house-router.)

## Talking to your assistant

An assistant whose conversation agent points at the router uses it; another can stay straight on the cloud model as an escape hatch. Home Assistant's own device commands (lights, doors) run first and never reach the router.

**Some satellite apps don't keep the mic open after the persona's question**, so answer with the wake word: "Iris, yes". The question waits 2 minutes.

| You say | It does |
|---|---|
| "What's the weather tomorrow?", "Do I need an umbrella Saturday?" | The weather brain answers (up to 7 days ahead, home only) |
| "When is sunset tomorrow?", "When does it get light?" | The weather brain's sun times (sun words are pinned to weather) |
| "What about Sunday?" right after a weather answer | Sunday's forecast |
| "What's on my list?", "What chores does Beth have?" | Reads 5, then "Want to hear the rest?" (yes / no thanks) |
| "What projects do I have?", "What's in the house project?" | Lists Donetick's projects, or that project's chores |
| "Mark the spray weeds chore done", "Skip watering the plants" (right after a chores answer, no chores word needed) | Changes that chore in Donetick and says which one |
| "Move the gutters to Saturday", "Remind Beth about the school keys" | Moves the due date / nudges Beth |
| "Undo that" | Undoes a completion; anything else: "Donetick doesn't let me undo an add. Please change it on Donetick's web page." |
| "Add clean the gutters to my task list", "Add a task to ..." | Creates the chore, then offers extras (below) |
| "Never mind", "go back to sleep" | Goodbye; clears any question it asked |
| "Good morning", "Thank you" (alone) | A short polite reply; nothing else happens |
| A fragment ("My.", "EPI.") | "Sorry, I didn't catch that." |
| Something odd, or only a few nouns ("Cook of chew, but you go", "honda stock price") | "I think I heard ... That's not something I know here at home. Want me to ask around?" in its own words. Yes sends your original words to Gemini; no ends it |
| A real question, command or need the house can't handle ("Tell me a joke") | Goes to Gemini |
| A whole sentence soon after a Gemini answer, or telling it something ("I have a cat named Tom") | Goes straight to Gemini (it's that conversation) |

**With Oread on (who spoke):** on a device whose names are switched on (Name Sparkle page), it says your name now and then, only when Oread is sure it's you ("Owner, you have 3 chores"; how often is the lower of the house rule and the device's own), and the firewall can stop some people from doing some things ("Sorry, that's not something I can do for you."). Both are set on the pages.

**Asking about the last answer (the learn level):**

- "Who answered that?" (or "What answered that?"): "The intent router answered that" for anything answered at home, "Gemini answered that", or "That one didn't come through me. Home Assistant answered it." A stray word is fine ("Who we answered that?").
- "What did you hear?": it repeats exactly what speech-to-text gave it: "I heard: ..."
- Both are about the turn just before; asking both, or twice, still looks at that same turn. They don't cancel a question it's waiting on.
- "Record that as a misunderstanding" right after one of those saves the turn: an engine miss to learn/misses.yaml after "Who answered that?"; a mishearing to learn/mishearings.yaml after "What did you hear?", under what was really said ("That should have been ..."). "Record that as a miss", "record as a myth" and "record as a mist" work too.
- "That should have been weather" adds a note to the miss just saved; it never acts on it. You can say both at once: "Record that as a misunderstanding, that should have been chores."
- After "Want me to ask around?", "Record that as a misunderstanding" saves what it heard as a mishearing and drops the question.

**Adding a chore, with extras.** After creating it, it says what else it can add; answer one at a time or several at once. It reads the whole chore back after each addition.

- "Yes, repeat every Tuesday at 7 pm" (fills repeat, due date and time)
- "Due tomorrow", "at 8 in the morning"
- "Remind me an hour before", "a reminder when it's due", "nag me" (every 15 minutes, 3 nags)
- "For Beth", "in the Garden project" (can be said in the first request too)
- Stop: "no", "forget that", "you misheard", "that's all". A bare "yes" gets the list of what's left; something it can't use gets "Could you repeat?"
- No name given ("Add a task to the house projects"): it asks "What should I call the chore?"
- Defaults: assigned to you, the House project, 9:00 when a date has no time.

## The pages (port 8771)

Open **https://<server>:8771/** from a computer on the home network. The certificate is made by the router itself, so the browser warns once; accept it (or give the browser `data/tls/veil.crt` to trust).

**The first time:** the pages ask for a setup code. On the server: `docker compose logs house-router | grep "setup code"` (or `cat data/setup-code.txt`). Enter it, then your username and password (as long as security: password_min_length says; the pages show it): that account is the super user. Add other people on Security, Users.

The menu has an icon beside each page and scrolls on its own; hide it with the arrow at its top (wide screens; remembered in this browser), Menu brings it back. On a phone it folds into the top bar.

| Menu | Page | What it's for |
|---|---|---|
| Watch | Transactions | Every request, one to a row (Off-Platform rows tinted, firewall stops red; Why opens the reasons under the row): what it heard, who spoke, the path and why, where it went (the Off-Platform model's name, e.g. gemini-lite), what it said. Show everything, what left the router, what went Off-Platform, what was answered at home, or what the firewall stopped. **Hear it** plays an answer in your browser. Up to four buttons on each: **Why** (when there are reasons), **Delete** (right, and routed right: nothing to learn), **Bank** (a request that went Off-Platform, into the Off-Platform Bank), **Misheard** (into learn/mishearings.yaml, under what was really said, counted). Bank banks at once (no pop-up) and is greyed while the bank is off (answers kept 0). Why shows the numbered trace (1 the words ... 11 Off-Platform). A request you banked or marked misheard leaves the list with a link to where it went; another asking of the same saying stays until you act on it; **Handled** shows the ones you acted on |
| | Off-Platform Bank | An add-on (addons/bank). Your formula and its knobs (Use the bank; T, answers kept per saying; U, use the bank from), then each saying per personality: heard, Off-Platform trips, answered by the bank, whether the bank answers it now (point at the badge for Q and U), and its kept answers (By saying); what requests became (What it became: device commands, with every wording). Add or Take out; keep, ignore, answer at home later |
| | Misses | The wrong part answered, recorded by voice ("Who answered that?", then "Record that as a misunderstanding"; learn/misses.yaml): what should have happened (Should be), make one a test case, or drop it (by its words, never its place in the list). **Tools** tab: review the misses, make one a test case, drop one |
| | Savings | Trips kept at home and the tokens they'd have cost: at the tokens per request on its Rules tab, and measured from each request's size. A calculation, not a meter |
| | Trainer | An add-on (addons/trainer; #29): who has trainer mode on (data/tables/trainer.db, its services is_on, set_on, people_on, settings), a switch per person in the People grid. The conversation is the core's: router.trainer_due (after the firewall: the voice ID sure, a condition, a chores sentence with no action, a statement nothing claims), trainer_answer (pending kind trainer: offer, name, date, time, assign, then the add decided afresh), trainer_command and trainer_turn (switched by voice; a changer anyone's, a person their own) |
| | Mishearings | An add-on (addons/mishearings): what speech to text heard under what was really said (learn/mishearings.yaml), word by word (struck out and added), and whether today's router decides the same for both (harmless now / still matters); Move or drop one. **Use it** and **Use a phrase** make a swap (learn/swaps.yaml), made before anything is decided and in the words handed back to Home Assistant; the swaps in use are a folded table. Fed by Misheard on Transactions (shown only while this add-on is on) and by voice |
| Teach | Try it | Type a sentence, pick an assistant (the personalities) and who spoke: the decision and why. Calls nothing |
| | Brain fleas | An add-on (addons/brain_fleas, its key_word slot). The household's small true facts (learn/fleas.yaml, addons/brain_fleas/fleas.py): user rules with no app behind them, the router being the "app" (its commands GET, POST, PUT, DELETE /fleas, in-process). Found after the topics, follow-ups and an app's own thing, before the Off-Platform steps (trace step "brain fleas", path flea): ways of asking expanded ({a \| b}), trimmed and indexed by word when the file changes; a way of one or two words is a key, a flea with an Ask step is picked by its words opening the sentence, any other by Dice at match_at. Voice add, change, forget are built-in fleas (system: true) gated by changers: (voice ID names, Oread sure). Saved fleas and app rules are re-read when their file changes: no restart |
| | Seed Topics | Every topic, folded (open one to change it): who answers it, its seed words, pinned and tentative words; add a topic; the datasets (folded) on and off. **Build** tab: build the keyword tiers, dataset labels, download datasets, look at a dataset, score a topic, word shares. **Rules**: how sure before an app at home answers, and every build setting |
| | Tools | The tests, run in the container, output shown live: regression cases (plain and live), the Gemini gate test, the unit tests. **Rules**: capture_keep (copies of requests for debugging) |
| Personality | Sayings | Every fixed line she says, her own or the shared ones (phrases/), one persona at a time; core, whatever add-ons are on. An edit is heard after a restart |
| | Persona Flair | An add-on (addons/flair). Three tabs. **Persona Flair**: per persona, how often (a rate above 0 is its switch), the most in a row, its Lines bank (type your own, or Accept from the books) and the lines from its books. **Sayings**: every fixed line the router says, the persona's own and the shared ones. **Phrases**: where its lines come from (its books, speakers, Download and Comb) and how the books are combed. Place: opener, closer, any (either), aside (only at a hand-placed [[aside]]) |
| | Name Sparkle | An add-on (addons/name_sparkle). Where voices' names come from (Voice ID from), then a tab per persona (found from the personality files): its share of answers with a name (above 0 is its switch), most in a row, an optional least score (empty: the voice ID's own "known" for that device decides), and its own names for each voice; and a **Shared** tab: the names every persona can use, with Pull. A persona uses its own names first, the shared ones otherwise. The voices are the people in the house everywhere |
| System | Add-ons | Every add-on in addons/, grouped Inbound and Outbound: what it does, whether it serves on platform or comfort, on or off (settings.yaml addons: enabled:, used after a restart), and the **Outbound order** (addons: order:) with Earlier and Later. An add-on that's off has no page, doors or menu item |
| | Overview | The last 24 hours as four numbers (requests, at home, Off-Platform, blocked), where requests were answered over 7 days (a ring with the numbers beside it), and what's switched on. The routes a request can take are in the user's guide |
| | Stats | Built to find bottlenecks. **Is anything slow?**: each route's typical time today, 7 and 30 days, with 30 days of small bars, flagged when today is slower than usual (stats: slower_than_usual, slow_min_requests). **Which leg was slow?**: per route today against usual, the router's own work, its CPU, the machine's load (load on each row), the outside hop, and the internet check (veil/netcheck.py: a ping, or a DNS lookup when the container can't ping, after a request on stats: internet_check: routes, once per cooldown_minutes; net_ms, net_method, net_at on the row; the servers must be in security: outbound_allowed), with the slow requests and their check. **The requests that cost the most CPU** (stats: top_cpu over top_cpu_days), each with Try it (runs it again) and Copy. **What the router costs to run**: CPU and memory now and over the hour, day, week and month, CPU hour by hour (stats: sample_seconds, keep_days). Then **By period**: the numbers, **Where the time goes** (each hop of each route, and the router's CPU, typical and slowest tenth; LiteLLM itself is t_litellm, from integrations: litellm: own_time_header; Sent again counts repeats on the first request's row), where requests were answered, by assistant, a day |
| Connect and protect | Integrations | One line per integration (on or off, where it is; names come from each service's title:). Open one for its tabs, in the order of adding an app: **Connection** (address, on/off, Test; a chores app's card also has **Clean-up**: overdue repeating chores brought forward to their next date, listed first, GET/POST /api/integrations/<name>/overdue, Connector.overdue_forward), **URL / ports** (its spec's address, the key the router sends it, from Grantors, and the doors it calls the router through, from Grantees; Home Assistant also through the Wyoming ports), **Commands** (the app's own commands read from its spec and kept; read again, changes are marked (ADD), (Modified), (Deleted) and wait for **Accept the changes**), **Voice map** (edited on the page: action, the command it calls, its words, what the API requires, the spoken needs), **User rules**, **Clean-up words** (its language: lists), **Defaults** (its lists, each a card with a default: people, with who each is in the house and who "me" is; project; and its options, typed or picked from an app's answer), and **Getting ready** (the checklist below) last. The Voice map tab starts with **match min** and **sound alike**, the voice map's own knobs (connectors/<name>.yaml). Long lists open as folded cards. **Add an app** (folded) offers the vault's unused keys and the topics no app answers |
| | People | The people grid (settings.yaml people:, veil/people.py): a name is one person, like a sign-in, so a save that puts one name in two rows is refused (Big Alex and Little Alex, never two Alexes); a row per person, columns wepwawet (optional), called, then one per integration (apps:). people.names() gives every name in a row (the firewall's identity, brain fleas' changers); GET /people/<app> on the chat door returns that app's column only, through a door whose program is that app (oread covers /people/oread in the starting copy). Re-read when settings.yaml changes: no restart |
| | Firewall | An add-on (addons/firewall), always last on the pile. Rules by person (below); try a sentence against them before saving |
| | Security | Users (and the **sign-in rules**: shortest password, lock-out, idle and longest sessions); **API keys and vault** (with **Add a key**, step 1 of adding an app), with a choice at the top: **Grantees** (the programs the router made a token for: one line per door, with Locked, what it is, who calls it, its token, when that token was last used and Revoke or Make its token; tokens not tied to a door can be tied; **Add a door**) and **Grantors** (the programs the router needs a key from: the key's name, where it comes from, whether it's in the vault, Set, Replace, Delete; and other keys in the vault); permitted addresses in and out (with the machines let in lately, each with an Add button, and the ones refused); the audit log |
| | Settings | What has no page of its own: the house's clock, **End Device Settings** (how requests are heard and what carries from one request to the next), **What the router is holding now** (each device's waiting question, last topic and turns, with their ages; also on Stats), **General API Settings**, and the engines. Each setting shows its readable name and its variable name; its description is behind the (i) (point at it, or click to pin it). **Find a setting** filters as you type, and lists matches on other pages with a link. Every other page with settings has a **Rules** tab |
| You | Account | Your password; **Look**: light, dark or follow the device, and one of five colour schemes, three colours each (the look is kept in this browser only) |
| | Guides | Tabs: User's guide (the routes, and what each page does), Coder's guide (this one), Design (only in a development copy, where docs/design.md exists) and README |

**Roles:** viewer reads; reviewer also works the Off-Platform bank and Transactions' buttons, the misses and the flair choices, and runs the tests; administrator changes settings and runs the tools; super manages security.

**What takes effect when.** The firewall and the permitted addresses are used as soon as you save. Everything else is written to its file at once (your comments stay), and the router uses it after a restart: the restart bar at the top of every page ("Saved changes wait for a restart: …") says what's waiting, and **Restart now** restarts the container (it's back in about 15 seconds). Files the pages change show in `git diff` like your own edits; commit them the same way.

**Integrations, out of the box:** Oread (who spoke), the weather brain, Donetick, the Liturgical Calendar and Wikipedia (Vikunja's voice map and rules ship too: add it with Add an app), all switched off until you set them up (the README's Sample apps). Switching a service off takes its topics with it (their requests go Off-Platform).

**The firewall** (needs Oread on). Each rule names people (household keys like owner or beth, Oread names, "unknown" for a voice Oread can't name, or "anyone") and what they may not do:

- use some voice devices at all (Iris, Felix),
- work some home devices (those words in what they say, or in a Gemini tool call: the router holds that voice's Gemini answer until it's checked),
- say some commands (whole words),
- use a topic or one action of it (chores, chores.add),
- ask Gemini anything.

A rule can also name **Home Assistant commands** (intents: HassTurnOn, HassTurnOff, HassSetPosition..., or HassTurnOn:lock for one kind of device) and **kinds of device** (domains: lock, cover, alarm_control_panel). A rule can be limited to some assistants. While Oread can't be asked, every voice counts as unknown (or nobody is blocked, if you choose that).

**Careful:** with Oread off, every voice is "unknown", so a rule for unknown voices stops everyone, you included. Turn Oread on before a rule for unknown.

**Home Assistant's own commands: Veil Guard Service (the router's hook in Home Assistant).** Home Assistant carries out device commands itself ("Prefer handling commands locally"), and Gemini works devices through Home Assistant's tools. Both pass through one function in Home Assistant, and the small Veil Guard Service integration asks the router before each command runs: allowed, it goes straight on; stopped, nothing moves and it says the rule's message. With the firewall off or no rules, Veil Guard Service doesn't ask at all. Install it once (below).

### Installing Veil Guard Service in Home Assistant

1. Copy the folder `ha/custom_components/veil_guard_service` from the router's repo to `/config/custom_components/veil_guard_service` in Home Assistant (with the Samba or SSH add-on; from the server with the SSH add-on: `scp -r ~/docker/house-router/ha/custom_components/veil_guard_service root@<ha address>:/config/custom_components/`).
2. Copy `ha/packages/veil_guard_service.yaml` to `/config/packages/veil_guard_service.yaml` (your packages folder). It holds the router's address (http://192.168.1.20:8770), the wait (4 seconds by default; set it there, in Home Assistant), and on_no_answer: allow (the house keeps working when the router is down; block stops anything unchecked).
3. Restart Home Assistant. In Settings, System, Logs, look for "Veil Guard Service is checking Home Assistant's commands with Wepwawet Veil". If instead it says "Veil Guard Service did NOT start", Home Assistant changed the function the guard wraps: nothing is checked, nothing is broken; open an issue with the Home Assistant version.
4. Which assistant a satellite is: found from its name ("Iris tablet"). If a satellite's name doesn't hold the assistant's name, add it in settings.yaml, integrations: home_assistant: satellites: (device id, assist_satellite entity, or device name: assistant).
5. Try it: a firewall rule for a kind of device (domains: [light] for one test person), then say "turn on the kitchen light" as that person. The Transactions page shows Home Assistant's command and the rule that stopped it.

After a Home Assistant update, the guard checks itself at startup (step 3). Its tests run in a copy of Home Assistant: from the repo's ha/ folder, `python -m pytest` (needs `pip install pytest-homeassistant-custom-component hassil home-assistant-intents`).

### Putting the router in front of Oread (who spoke)

The router sits in the Wyoming audio path where Oread sat: each device's audio goes to the router's port, the router passes it to Oread untouched, and reads who spoke from Oread's answer on its way back to Home Assistant. No Oread token is needed. The one change on the way back: the mishearings marked Use it (learn/swaps.yaml) are fixed in Oread's words before Home Assistant gets them (integrations: oread: wyoming: fix_mishearings, on by default; veil/wyoming.py fixed() and rebuilt()); the log line and the request's trace give what Oread really heard beside them.

1. On Oread's Connections page, permit the router's address (192.168.1.20 in the examples): Oread now sees the router as its client.
2. On the pages, Integrations, Oread: On, "Who spoke comes from" in the audio path, Oread's address (192.168.1.20), and the ports, assistant=router's port>Oread's port: `iris=10413>10313, felix=10412>10312`. Save, Restart now, then Test: each Oread port should answer, and the card says which ports are open.
3. In Home Assistant, add a **new** Wyoming entry for the router, and leave the Oread entry as it is: Settings, Devices and services, Add integration, Wyoming Protocol, host 192.168.1.20, port 10413 (Iris's). Name it by hand (for example "Veil iris"). Then Settings, Voice assistants, Iris's assistant (the Tablet assistant): Speech-to-text, pick the new entry, Update. Going back is picking the Oread entry again. Leave Felix on Oread until it moves to the router.
4. Say something to it. The log shows `Wyoming (iris): Oread heard "..."; who spoke: Sam (known 0.93)`, then `who spoke: owner`; the Transactions page shows it too.

The router's ports must be published in docker-compose.yml (10410–10419 are). A new device: add its pair on the Integrations page, Restart now, and point its Home Assistant entry at the new port. If the router is down, that device's speech-to-text is down too; picking the Oread entry again in its assistant's Speech-to-text takes the router out of the way.

The other two ways to learn who spoke stay available (Integrations, "Who spoke comes from"): Oread's API (needs an Oread token with the reviewer role, saved in the vault as `oread_token`) or the sensor Oread sets in Home Assistant.

### Linking people to Home Assistant and Oread

People stay the router's own. On Integrations, Home Assistant: its address (http://<ha>:8123) and a long-lived token (your Home Assistant profile, Security), saved in the vault as `ha_token`, for its satellites (Veil Guard Service). Who each voice is: Oread's people card; what to call them: Name Sparkle.

### Doors: the router's own addresses that need a token

A door is a few of the router's addresses one program calls. They're settings (settings.yaml, security: doors:), not code: each has a description, who calls it, its paths (one ending in * covers everything under it), the least role its token needs, the program (the integration whose URL / ports tab shows it), and locked. Out of the box: chat (LiteLLM), tools (the Tools page and command-line tools), guard (Veil Guard Service in Home Assistant), and oread (Oread pulling the mishearings; a starting-copy door, so it can be taken out). Home Assistant isn't set up like the other apps, but to the router it is one more program that asks (through the guard door and the Wyoming ports) and is answered.

A new program calls the router: Security, API keys and vault, Grantees, **Add a door** (its name, what comes through it, who calls it, the paths, the role), then **Make its token** on its line and give the token to the program. Lock the door only once "last used" shows the program used its token: the page won't lock any door while no token exists. A door added on the page can be taken out; the three built-in ones can't. A token named like its door ties itself; others are tied with the select under "Tokens not tied to a door". A tied token opens its own door only (router the_doors) and is refused on the pages' API (port 8771, web.actor_of), so the key LiteLLM or Home Assistant holds can't read the activity log; an untied token works on the pages' API with its role. Changes take effect at once.

## The Wepwawet standard (apps that say how they fit)

An app whose own OpenAPI document carries an `x-wepwawet` section is **Wepwawet compliant**: the router lays it out from that section, not from code. The section is in the standard (its own repo: github.com/coderpigsfly/wepwawet_standard; docs/wepwawet-standard.md points there); what the router does with it is below. Oread and the weather brain carry one; Donetick doesn't, so all its tabs stay open.

- **Every app has the same tabs**: Connection, URL / ports, Commands, Voice map, User rules, Clean-up words, Defaults, Getting ready. A tab a compliant app says doesn't apply is shown grayed out (it can't be opened); its title says why. A **Wepwawet compliant** badge sits by its name.
- **URL / ports** has its spec's address (any app, Oread and the weather brain included); **Commands** reads it, with the app's key sent the way its spec says (else as a bearer token). What's kept: connectors/<name>.commands.json, with its Wepwawet section, its base address and how its key is sent.
- **What it offers** (Defaults, first): each offer is a switch and its way. Oread's **who spoke** is one: on, and in the audio path, Oread's API or the Home Assistant sensor, kept as integrations: oread: enabled: and source: as before. Oread's Connection tab then keeps only where Oread is.
- **Its lists** (Defaults): a compliant app fills in its own cards (Oread's people from GET /profiles); you check who each voice is and save. Oread's people card says who each voice is (then the household's other names).

## Add-ons (issue #25)

What isn't the router's own job is an add-on: a folder addons/<name>/ with **addon.yaml** (what it
is: name, title, version, about, kind: action, dress or guard, serves: on_platform with serves_how
or comfort, its data life, path: inbound or outbound, its slots, positions, provides, needs, may,
pages, on_error, budget_ms, last), **addon.py** (one function per slot, and its services), and
optionally **api.py** (its pages' doors, registered only while it's on), **page.js** (its page,
handed the shell's helpers as a kit) and **test_addon.py**. veil/addons.py loads the ones on
(settings.yaml addons: enabled:), each after what it needs; the core calls whatever is in a slot
and never imports an add-on by name. Before an add-on counts as one it passes the gate:
`python3 tools/test_addon.py <name>` (its manifest, that it loads with only what it needs, hostile
words, its time budget, its own tests). The gate is in the tests run before every push.

**Slots**, in the order a request meets them:

| Slot | Path | What it gets and gives | Who fills it |
|---|---|---|---|
| check | inbound | the words: None, or {block} | Firewall (on_error: block, last: true) |
| understand | inbound | the words: the words to decide on | Mishearings (swaps) |
| key_word | inbound | after the integrations found nothing: None, or {action, score, how} | Brain fleas |
| supply | inbound | after the claim: the words for the claimer, with another app's day put in | Time |
| fill | inbound | the claimer's blank {need, about}: None, {words}, or {ask, choices} | Time, Loose language |
| before_off_platform | inbound | None, an answer from home, or {kind: ask, meant, by}: she asks "I think you meant ...? Shall I?" first (the core's heard_as question; ctx at_home tells the add-on which app or flea would take other words, router.taken_at_home) | Bank, Did you mean (the window; its answer comes back through its service answered, from the decision's window_answer) |
| dress | outbound | her answer: the answer to speak | Roman numerals (replace), Flair, Name Sparkle |
| learn | outbound | after the answer: nothing back | |

**Precedence on the way out:** a replace add-on first (it changes the words inside the answer),
then the household's order (Add-ons, Outbound order), the Firewall last. A line Loose language
holds while it asks (util.HOLD, an invisible mark) is never dressed, and util.unslot takes the
mark out before Home Assistant gets it. An Off-Platform answer is dressed only by the replace
add-ons, a sentence at a time as it streams (router.SpokenStream).

**The chaining protocol.** A request is claimed by the first with its key word, integrations
first; a day said is no one's key word in a request with its own verb. The claimer that can't
answer names its blank (the weather brain's reply `status: need, need: when, about: the picnic`,
in its OpenAPI). router.chain asks each fill add-on with its flag still on; one that fills or asks
turns its flag off, a fill asks the claimer again, and when no one can fill it she asks (pending
kind clarify, answered on path C: yes, a choice, or a day). Every module contributes once.

**Loose language and Time.** Time (addons/time) puts a day another integration names (a feast)
as its date, for the weather (supply) or an add (Loose language's days service, which needs it);
two that fit are asked about, never picked. Loose language (addons/loose_language: loose.py,
prefs.py) fills an add said loosely: spans and parts of the day offered from each person's picks,
a deadline (by, before, due, till: 11:59 pm, a reminder before offered), "remind me to ... on
Sunday" asked (the reminder's day or the day it's due), "until" a reminder after, a chore "for" an
event offered the days before it (connector.EVENT_DAY). The connector calls it through
connector.LOOSE; with it off, an add is plain.

## Adding an app we didn't write

Donetick is the model: an app with its own API that knows nothing about the router. Three layers make it sayable: the app's **spec** (its contract: what each command demands, in its own terms), the **voice map** (what's said, and the spoken needs: what it must hear), and the **helper** that turns one into the other ("Beth" into its user number, "Friday" into a date). The Integrations page, Getting ready tab, checks each step as it's done. The steps, in order:

1. **Its key** (step 1, before the app): Security, API keys and vault, Grantors, **Add a key**: its name (MEALIE_TOKEN), the program it's for (mealie) and the key from the app's own settings. It's kept encrypted in the vault, never in settings.yaml.
2. **Add an app** (Integrations, at the bottom): pick its key (the vault's keys no app uses yet): the app's name follows the key's program, so the key, the service, its voice map, helper and lines all go by one name. Then the title, the kind (an app we didn't write, with an OpenAPI spec; or one of ours that speaks the router's /ask door), its address, its spec's address (often /swagger/doc.json or /openapi.json) and its topic (the topics no app answers yet, or none). It's added switched off, with a starting connectors/<name>.yaml. Permit its address under Security, Addresses, going out.
3. **Commands: Read its spec.** Every command the app lists is kept in connectors/<name>.commands.json, each with what the app requires (path parameters, required body fields). After the app is updated, **Read its spec again**: each changed row is marked (ADD), (Modified, with what it was) or (Deleted), nothing changes until **Accept the changes**, and a deleted command the voice map still calls is named.
4. **Voice map.** Its **match min** at the top (how much of an item's name must be said). Then one folded card per thing that can be said: the **Action** (a word of your own, unique), **Calls** (one of its commands, from step 3), **API requires** (shown from the spec when Calls is picked), **Words** (the words that pick it) and **Spoken needs** (each a detail word with required, optional or default). Save writes connectors/<name>.yaml, keeping what the page doesn't show (learn_from, objects, the add's follow-up fields) and each action's comment.
   - **required**: missing means it asks. The router asks itself for the needs it can hear (settings.yaml router: heard_needs: who is a person, when is a date): "When?" (phrases/router.yaml need_when, need_who; need for any other), and the answer is added to what was said and the request runs again. Any other required need (chore, name) is the helper's job.
   - **default**: not said means the app's option fills it in (Defaults tab; who "me" is, the default project).
4a. **User rules** (optional). For what one command can't do alone: the app's commands chained with the router's steps (veil/rules.py: Call a command, Search, Filter, By date, Match, Confirm, Ask, Fresh copy, Who spoke, Response), a line per step, each with its parameters; point at a step for what it does. Saved in connectors/<name>.yaml under rules:, used after a restart. A rule is reached like an action, inside its topic only: a topic word, or (in the app's context, right after it answered) a rule's words opening the sentence ("rename that to ..."). Its words are heard by their stems (renamed); a rule with nouns (objects:) fits only when one is said and wins over a rule with the same words and none. Search's Last makes "that"/"it" the item it last named (vocab/language.yaml this_words). Its questions inside a rule (Confirm, which one, Ask) are pending questions of kind rule, answered on path C. A new step: add it to STEPS (its title, what it does, its parameters) and to run() in veil/rules.py; the page builds its line from STEPS. Steps now: Call, Search, Filter, By date, Match, Confirm, Ask, Fresh copy, Who spoke ({speaker}: Sure and Hedge % of Oread's score, the voice's own name or a nickname, Hedge and Unsure lines; router.speaker_info gives it own, nicknames, score, known), Response (lines; fields {name: the matched item's field}, each said as {name}, an ISO date and time spoken by fields.say_date/say_time (rules._spoken); empty_lines when one is empty; Search keeps each candidate's plain fields for it; an older say: still reads). Donetick's find is the worked example of a read-only rule. Mishearings marked Use it on the Misses page are swaps (learn/swaps.yaml, veil/mishearings.py swap()), made on what was heard before the decision's first step. router: off_platform_tool_rounds caps the cloud model's action rounds per request (at the cap tools are taken out of the request; past it the router answers tool_rounds_over itself). Every rule is checked when it loads and when it's saved (rules.check: steps known, settings known, commands the app has); one that doesn't check out isn't used, and the tab, Getting ready and the log say why. Names are unique across voice map actions, user rules and brain fleas. Donetick's rename is the worked example. Saves from the page carry a stamp of the section they replace (config.stamp: rules:, actions: or fleas:, from the details or GET /api/fleas, and returned by each save); a save from an older copy is refused with 409 (config.check_stamp), while another tab saving another section of the same file isn't a conflict. A save with no stamp (a tool) isn't checked.
   - **optional**: used if said.
5. **Defaults.** **Lists**: the app's own lists the router uses, each a card you name (people, project, or a word of your own): where its items come from (one of its GET commands, and the fields that are an item's id and name, from its spec), what its items are here (people in the house, or nothing in the house), and its **default**. A people card also says which voice each is (the voice ID's own names, saved on Name Sparkle) or nobody, matched by name until saved, the other names each voice is heard by in what's said to this app ("for Sam"), and who "me" means (the default voice, or whoever the voice ID is sure spoke). Saved as services: <name>: lists: <word>:. The voice map's fields name the list they fill (connectors/<name>.yaml, fields: project: list: project). A list with no default and nothing said is left out (later it may ask: the standard). Then the app's own options, each typed by hand or picked from an app's answer (Comes from); a time a chore gets when only a day is said is Donetick's default_chore_time, its own, with nothing in the code standing in for it. The timezone is the house's (Settings, The house), not an app's; where the house is lives in the app that needs it (the weather brain's own house.json).
6. **A topic**, if none was picked in step 2: Seed Topics, Add a topic, with this app as its service, and seed words that point at it. A topic can also be made first with "no app yet"; Add an app then offers it.
7. **The helper**, connectors/<name>.py: the code that speaks the app's API and its quirks. It's written for each app, with connectors/donetick.py as the pattern and the voice map's Calls and API requires as its contract.
8. **Its lines**, phrases/<name>.yaml in the shape of phrases/chores.yaml.
9. **Build.** Seed Topics, Build tab, Build the keyword tiers. Its report says which of the voice map's commands it found in the spec.
10. **Regression cases**: tests/cases/<topic>.yaml with requires: [<name>].
11. **Switch it on**: Connection, On, Save, Restart now. Then Test, a few sentences on Try it, then by voice.

The tabs follow the same order: Connection, URL / ports, Commands, Voice map, User rules, Clean-up words, Defaults, and Getting ready always last.

**What an app's card and lists may say besides:** its spec's paths start (spec_prefix: Wikipedia's spec lists /{domain}/v1/feed/..., served at /feed/...), its spoken name ("the feast days", in its "which app?"), pages it reads (an answer in pages, its next), send only the fields a change accepts, and for an app that takes the words as said, its test question. A path part the spec gives a pattern is written to fit it (01); a path parameter with a few allowed values is a command per value ("GET .../onthisday/births/{month}/{day}"). Every call out says who it is (router: user_agent). A list of things may say what's kept out, how much each matters, and **What should be** (the app's list of every thing with its usual day: one defined there but missing from the list was superseded, and it says what took its place). **Apps of the same nature** (Seed Topics, a topic's Then, when it's busy): the next app answers when the one before is at its limit or doesn't answer; Add an app may join a topic that has one.

## Where things live

Everything is in the router's folder, ~/docker/house-router. Rule of thumb: settings say how much, vocab says what it means, topics say what it's about, phrases say what it replies.

**Your files and the shipped ones.** Your settings, voice maps, personality and recorded misses are your household's own. A release ships each household file's **skeleton** from defaults/ instead, put in place on a new install's first start; defaults/examples/ holds examples (an example assistant with no lines), copied only into a folder with none of its own. When an update ships something new in a skeleton, Settings shows it under **New in the starting copies**, with Add or Not for us.

| File or folder | Holds | Edit by hand? |
|---|---|---|
| settings.yaml | Knobs, topics with seed and pinned words, people (the grid: apps, rows), services (enabled, address, options, cache refresh), engines (language, router), integrations (LiteLLM: its model, timeout, key name and spec; Oread and its Wyoming ports; Home Assistant), names_in_replies, security, web, activity, savings | Yes, or on the pages |
| frontend/home_assistant.yaml | The router's words for kinds of devices and actions, with Home Assistant's names behind them (the Firewall page) | Yes |
| firewall.yaml | The firewall's rules | Yes, or on the Firewall page |
| vocab/*.yaml | What words mean (filler, never mind, yes/no, follow-ups, the Gemini gate, learn commands and mishearings, moods); vocab/language.yaml holds the date and number words (weekdays, months, number words, units, parts of the day, before/after, repeat words, the read-back) | Yes |
| phrases/router.yaml, phrases/chores.yaml | Its lines | Yes |
| personality/<assistant>.yaml | Its flair: rate, max_in_a_row, names:, its lines bank (flourishes) | Yes, or on the Persona Flair page |
| personality/sources.yaml | Its books, speakers and near words | Yes, or on the Persona Flair page |
| personality/combing.yaml | How the books are combed (never-say words, story words, said-verbs, closers, moods, topics, ranking) | Yes, or on the Persona Flair page |
| personality/candidates/, personality/approved/ | Lines from the books; approved/ keeps dropped: the book lines you deleted from its bank, so combing leaves them out | On the Persona Flair page |
| tools/sources.yaml | The datasets, and the Gemini gate's test set (gate_test) | Yes |
| tools/tools.yaml | The tools the Tools page may run | Rarely |
| connectors/<app>.yaml | An app's voice map (actions: each with api, words, needs), and its own words (language:: the stop words, "me", the read-back); donetick.yaml is the first | Yes, or on its Integrations tabs |
| connectors/<app>.commands.json | The app's commands as read from its spec and accepted (Integrations, Commands) | On the page only |
| learn/misses.yaml | Engine misses you recorded by voice (written by the router) | Delete a record once dealt with |
| learn/bank.yaml | The Off-Platform Bank, written out by Export on the bank page (the database never goes to git); nothing reads it back | Export, then commit and push |
| learn/swaps.yaml | The mishearings marked Use it: heard words swapped before anything is decided | On the Mishearings page |
| learn/mishearings.yaml | Mishearings: what was heard under what was really said, each counted (written by the router; never cut for size). A line heard through the audio path keeps each Oread clip it was heard in (clips: clip id, device, when); Oread pulls the whole list through the oread door (GET /learn/mishearings on port 8770, a token of role viewer) for its Mishearings page and looks each clip up itself. The same door covers GET /learn/windows (?since=seconds&limit=): the Did you mean windows with their answers and Oread's clips of the request and the answer | Drop or Move on the Mishearings page |
| tests/cases/ (core, weather, chores, veil; household-* for cases that need your own people, projects and assistants, never published) | Regression cases | Yes |
| topics/, scores/, actions/ | Generated by the keyword build | Never |
| router.py, connector.py, scoring.py, fields.py, series.py, shape.py, learn.py, connectors/donetick.py, connectors/vikunja.py | The router's code | In code |
| addons/<name>/ | Each add-on's own code, page and tests: bank, brain_fleas, firewall, flair, loose_language, mishearings, name_sparkle, roman_numerals, time (above, Add-ons) | In code |
| veil/ | Wepwawet Veil's own parts: settings and secrets, security, the vault, addresses, who spoke (and the Wyoming audio path, veil/wyoming.py), the firewall, the activity log, the pages | In code |
| docs/ | The guides | Yes |
| ha/custom_components/veil_guard_service/, ha/packages/veil_guard_service.yaml | The guard that goes into Home Assistant (copied there, not run here), and its package file | In code; copy to Home Assistant |
| .env | Secrets and addresses (the Off-Platform address and key, Donetick's token, FILE_OWNER); never on GitHub. See .env.example | Rarely |
| data/ | Accounts, sessions, tokens, the vault and its key (data/keys/), the activity database (veil.db), the certificate; never on GitHub | Never (back up data/keys/ apart) |
| data/tables/<app>.db | A slow app's table, one SQLite file per app (veil/tables.py): each address's answer as it came (reads) and its things as rows with known fields (things: id, name, day, weight, the whole item). Read from the app only when its hold runs out (services: <app>: table: {hold_days: 180}), and when the app can't be reached, the table's copy, however old. An app that writes never gets one. Rebuilt from the app if deleted | Never |
| CHANGELOG.md | What changed in each version (year.month.release, like Home Assistant: 2026.10.0); tools/release.py refuses a version with no section | Yes, with every release |
| state/, captures/ | Its memory and pending questions; full copies of requests | Never |

## Everyday changes

After any of these: docker compose restart (or Restart now on the pages), then commit and push your edit.

**Give it more ways to say something.** In phrases/router.yaml or phrases/chores.yaml, add a line under the section's any: list. It draws lines at random and doesn't repeat until all are used. Keep {blanks} as they are. Lines are never questions, except in sections marked QUESTION.

**Lines for one assistant only.** Beside any:, add iris: (or felix:) with its own list.

**A reply for a polite phrase heard alone.** Make sure the phrase is in polite_phrases in vocab/path0.yaml; in phrases/router.yaml add a section polite_ plus the phrase, spaces as underscores (polite_good_afternoon:), with an any: list. Without its own section, the phrase uses the shared polite: list.

**Make a word always count for a topic.** Seed words count at full strength and also help the keyword build find data; adding one means rerunning the build. A household word that isn't a seed goes in pinned: (restart only). Both on Seed Topics.

**Common knobs** (on the page named, or settings.yaml):

| Knob | Now | What it does |
|---|---|---|
| read_list_max | 5 | Items read before "Want to hear the rest?" (Settings, any app) |
| context_window_minutes | 2 | How long the last topic at home and the router's question last (Settings, memory) |
| followup_max_words / followup_lookback | 4 / 3 | How short a follow-up is; how many requests of history path B searches (Settings, memory) |
| answer_max_words | 4 | Longest plain yes/no answer (Settings, memory) |
| gemini_conversation_minutes | 2 | How long a whole sentence after an Off-Platform answer goes straight back (Settings, memory) |
| false_wake_max_letters | 1 | Letters or fewer counted as a false wake (Settings) |
| strip_away (vocab/language.yaml; connectors/<app>.yaml language:; an action's voice map entry) | how people talk; the app's nouns; the action's own | The words left off either end of a spoken name (connector.spoken_value, veil/spoken.py thing), in three layers so each word is typed once, at the highest layer it fits. A verb whose subject is "you" ("I need you to find...") is asked of it, never a name |
| tree_stays_home | true (starting copy; missing = off) | A request in a tree (a topic sure of it) never goes Off-Platform: no answer from the app, or a verb none of its actions has (connector.real_verb, veil/spoken.py main_verb), gets the tree's own line or phrases/router.yaml stay_home with {tree} (topics: <t>: spoken). An app's "not mine" still lets it go on |
| echo_overlap, echo_seconds, echo_min_words | 0.6, 30, 3 | An echo: its own last answer on that device heard back (a Voice PE hearing itself) gets silence (Settings, End Device Settings). Compared as word pairs in order (veil/speakers.py in_order), so a real request that borrows its words isn't one, or by how much of its answer's own words come back (covered(): misheard, room talk on the end) |
| echo_cover_longest | 2 | Its words brought back count as an echo only when what was heard is at most this many times as long as its answer or its sentence (router.echo_of) |
| echo_keeps_question | true | Its waiting question survives an echo (router: the new-request clear and path 0's echo keep it). Before the echo guard, answers_waiting(): a short yes or no to the waiting question is its answer, never an echo ("Read the rest."). leading_answer(): "Yes." then room talk naming no topic and no app thing answers a yes-or-no question (list_rest, ask_around, a confirm). d["spoken"] keeps the words as said, so a "Yes." that goes on with the request it confirms is logged, matched to Oread's clip and looked up for who spoke as "Yes." |
| stats: internet_check: min_outside_ms | 200 | The internet check runs only after an outside hop this long or longer: quicker, the app answered from its own memory (netcheck.Checker.wanted) |
| integrations: home_assistant: time_way_back_seconds | 6 (0 = off) | Seconds after an answer heard through the audio path, Home Assistant's run record is read (veil/hadebug.py, also used by tools/ha_timings.py) for the way back: t_back on the row. The router's own hand-off in the audio path is t_relay (veil/wyoming.py _pump). Daily route summaries (activity route_days) keep the 30-day usual for stats: keep_days |
| security: refused_warn_minutes | 60 (0 = off) | Integrations warns of addresses refused this recently (veil/access.py counts per list, address and door; lately() names the address that used the door before) |
| confidence_local | 0.85 | How sure before an app at home answers (Seed Topics, Rules) |
| lone_door_max_words | 12 (0 = off) | A longer sentence whose only topic word is one door, not a seed or pinned word, is held by the guard (scoring.score) |
| connectors/<app>.yaml ask_min / never_by_voice | 0.4 / [delete, archive, erase] (Donetick) | A weak match at or above ask_min, or with every word said, is asked about (match.find ask_min; asking=False where a guess would change the request); a never_by_voice word said gets phrases never_by_voice (router.stay_home, home_line) |
| router: add_name_max_words | 8 | The longest name taken, said in the add (connector.spoken_value, any app) or as the answer to "what's it called?"; longer, it asks |
| integrations: litellm: fallback_model | gemini-lite | The LiteLLM model for everything not answered at home (Integrations, LiteLLM) |
| language: spacy_model | en_core_web_sm | Sentence diagramming (installed in the image) |
| personality/<persona>.yaml names: rate / min_score / calls | | How often a persona says a name, an optional least score, its own names per voice (Name Sparkle) |
| capture_keep | 0 | How many full copies of requests are kept in captures/, the newest; 0 = none (Tools, Rules) |
| miss_log_max | 500 | Wrong-part misses and mishearings each kept at most this many, oldest first out (Misses, Rules) |
| activity: keep_days | 14 | How long the activity log keeps requests (Off-Platform Bank, Rules) |
| activity: answer_from_bank | false | Use the bank: an added saying is answered from the bank when your formula allows |
| activity: bank_answers_kept | 5 | T: Off-Platform answers kept per saying; 0 = no bank at all |
| activity: bank_use_from | 0.2 | U: the bank answers once Q = (trips − 1) ÷ T reaches this, Q of the time |
| activity: trim_days | 30 | Sayings heard only once, not added or reviewed, are trimmed after this many days |
| savings: tokens_per_request | 3000 | What one cloud request costs (Savings, Rules) |
| services: donetick: cache_refresh_seconds | 60 | How often the router reads Donetick's chores and people again (Integrations, Donetick) |
| donetick options nag_max / default_chore_time | 3 / 09:00 | Nags on a new chore; time for a date given without one |
| personality/<device>.yaml rate / names: rate | | Flair and names per device: above 0 is the switch (Persona Flair, Name Sparkle) |

**Who is who.** The people are the voices the voice ID names (Oread's own names, saved on Name Sparkle with Pull). The firewall matches those names exactly. Each app's people card (its Defaults tab) maps its people to voices, gives other names they're heard by ("sam, me, myself" for Owner), and says who "me" is. What to call each voice: Name Sparkle.

## Deploying and testing

All commands run on the server from the router's folder: `cd ~/docker/house-router`

**Update to a new version:** `git pull`, then restart or rebuild (below). Your own files aren't touched by an update.

**Restart or rebuild?**

| What changed | Command |
|---|---|
| Any .py, .yaml or phrase file (most changes) | docker compose restart |
| docker-compose.yml | docker compose up -d |
| Dockerfile | docker compose up -d --build |
| .env | docker compose up -d --force-recreate, then check with docker exec house-router printenv \<NAME\> |

After a restart, wait about 15 seconds (spaCy takes a moment to load) before testing.

**Run the tests** (or Tools, Tests on the pages). They need the router's Python packages, so run them in its container (`docker exec -w /app house-router python3 tools/...`, or the Tools page), or install the Dockerfile's pip line on the host. On a fresh clone, start the router once first: its first start puts settings.yaml, the topics and the other starting copies in place. regress.py and replay.py ask the running router.

- python3 tools/regress.py: what the running router would decide for every case (asks its /explain; nothing is changed); --live also fetches answers that change nothing; --why shows every reason
- python3 tools/test_fields.py, test_series.py: dates and fields, the "anything else?" conversations; python3 tools/test_addon.py <name>: an add-on's gate and its own tests (flair, name_sparkle, roman_numerals)
- python3 tools/test_which_app.py: which app a sentence is for with no topic word (an app's action word plus one of its things; two apps: it asks which); who can answer this (#28: router.who_answers, from decide_live, before the Off-Platform steps: each app whose user rule with a Match step and no change opens the request is asked at once, read only, within router: ask_apps_seconds; found means the rule's reply has no not_found and its looked_for fits its found_item by two words or the one said, router.enough_words); Did you mean's answers
- python3 tools/test_veil.py: Wepwawet Veil's own parts (names, firewall, addresses, saving, the log and bank, accounts, the vault, the audio path), in a throwaway folder (the audio path checks need `pip install wyoming==1.10.2`; without it they're skipped)
- python3 tools/shape_test.py (from the Tools page, or `docker run --rm -v "$PWD":/w -v ~/datasets:/root/datasets house-router-house-router python /w/tools/shape_test.py`): how the Gemini gate sorts real questions and your misses
- python3 tools/replay.py 20261010-14 weather: saved requests from captures/ with the path it'd pick today (captures/ fills only with capture_keep above 0)
- `docker exec -w /app house-router python3 tools/ha_timings.py` (-v for each event): Home Assistant's own timings for its last voice runs (speech to text, the conversation, text to speech, the whole run) next to the router's time for the same words. Needs integrations: home_assistant: url and its token (a Home Assistant long-lived access token) in the vault
- python3 tools/misses.py: your recorded misses, then → today (also at the end of every regress run)
- tests/web_test.py: the pages end to end, **only against a throwaway copy**, never the live router (it creates accounts and saves settings). Make the copy with python3 tests/make_copy.py <folder>: the code, the starting copies and stand-in assistants (tests/fixtures/personality/), never your own files. test_veil.py and test_which_app.py make their own copy the same way. The stand-in it talks to (LiteLLM, Home Assistant, a recipes app, Oread) is tests/standin.py; the commands to start it and a throwaway copy are at its top (OFF_PLATFORM_KEY must be set to any value, or every Off-Platform case fails)

With the tools door locked (Security, API keys and vault, Grantees), the tools need `ROUTER_TOKEN=<an API token>` in front (Make its token on that door's line). The Tools page hands its own.

**Review your misses.** After a change, each miss reads same, CHANGED, or LOOKS FIXED. For one that's really fixed: python3 tools/misses.py fix 3 (shows the case, asks y/n, then takes the miss out of the log), or Make it a test case on the Misses page. For one not worth keeping: drop 3. Then git diff, regress, and push. Never fix a silly test miss: it would become a permanent test.

**Read the router's log.**

- docker logs --since 10m house-router 2>&1 | grep -v "HTTP Request" (the routine /v1/models, /health and /firewall/summary check-ins are already left out: router: quiet_paths)
- Lines to look for: Wyoming (device): Oread heard, heard, who spoke, decided: path ... (and why), -> local (its answer), -> blocked by the firewall, pending question saved / cleared, name: / flair:.
- Or the Transactions page, which keeps 14 days.

## The keyword build

The build reads the datasets (in ~/datasets/, described in tools/sources.yaml) and writes topics/, scores/ and actions/. Run it after changing a topic's seed words, adding a topic or a dataset, or editing a connector's words. Then restart. Every tool reads datasets through tools/datasets.py, so no dataset or model is named in the code.

| To | Command (or the Tools page) |
|---|---|
| Build everything | python3 tools/build_scores.py build |
| Test a topic against every dataset sentence | python3 tools/test_scores.py weather (or chores) |
| Compare cut-offs | python3 tools/test_scores.py weather 0.80 0.85 0.90 |
| Test on sentences the scores never saw | python3 tools/test_scores.py --held-back weather (builds in a throwaway folder from four of every five) |
| See every dataset label and which topic claims it | python3 tools/build_scores.py labels |
| Refresh datasets from their download URLs | python3 tools/build_scores.py refresh (or refresh massive) |
| Look at one dataset's labels | python3 tools/datasets.py massive |
| Word shares on any dataset | python3 tools/word_shares.py topics/weather.yaml weather massive |

**Add a topic:** on Seed Topics (Add a topic), or under topics: in settings.yaml with the same keys as the others (service, seed, always_tentative, pinned; [] when empty), then build. The build reports the labels it found, the doors with their strength, and warnings such as thin data.

### The build routine, start to finish

1. **Refresh the data** (only when a dataset is new): refresh, or refresh \<name\>.
2. **Build.** Read its summary: labels found per topic, doors with their measured strength, the connector check (every Donetick command [ok]), warnings.
3. **Test the scores:** test_scores weather and chores. Last time: weather about 92% at home with 0.15% wrong; chores about 90% with 0.82% wrong. A big drop means the change hurt.
4. **Restart.**
5. **Regression:** regress --live. Everything that passed must still pass.
6. **Save it:** git add -A, git commit -m "what changed", git push origin main (topics/, scores/ and actions/ are saved too).

### Adding a data source

The datasets now: MASSIVE (Amazon, 18 scenarios, doors and depth), CLINC150 (150 intents, doors), SNIPS GetWeather (weather depth).

1. **Add an entry** under sources: in tools/sources.yaml (copy one and change it): description, url, local (~/datasets/...), format, use ([doors] broad, [depth] one topic), roles (when / where / who labels), ignore, never_claim, intent_field. Formats: massive_jsonl, clinc_json, snips_json, and for your own data jsonl or csv (text_field and label_field name the fields) or lines (one sentence per line, all with one label:). enabled: false leaves a source out.
2. **Download it:** refresh my_source.
3. **See its labels:** labels. If a topic should own a label it isn't claiming, add a seed word to that topic.
4. **Run the build routine** from step 2.

A dataset in a shape none of these read needs a small reader in tools/datasets.py: open an issue with its address.

## Flair: its lines from the books

1. Persona Flair page: its books, speakers and near words (or personality/sources.yaml). Public domain only (before 1929).
2. Persona Flair, Phrases: Download the books, then Comb the books. Combing never offers a line already in its lines bank or deleted from it; with none of its books on disk it stops and says so.
3. Persona Flair, Lines from the books: fix a slot or mood, then tick Accept: the line goes straight into its Lines bank and leaves the list. Clear the list empties it (combing fills it again). (`python3 addons/flair/tools/build_flair.py approve <persona>` does the same for keep: yes lines in the file.)
4. Persona Flair, Lines bank: reword a line if it needs it (▶ plays it), Save or Delete it; add your own. A book line you delete is remembered, so combing never offers it again. Then Restart now.

How the books are combed (the words it must never say, the story words that rule a line out, the closers, moods and topics) is in personality/combing.yaml and on the Flair page; an assistant can override any part under combing: in personality/sources.yaml.

## When something goes wrong

First look: the Transactions page, the router's log, and for what HA did, Settings > Voice assistants > the assistant > three dots > Debug.

| What you see | Likely cause | What to do |
|---|---|---|
| Tests all say "Connection reset" or "Connection refused" | The router was still starting | Wait 15 seconds and run them again |
| A change you pulled has no effect | The router wasn't restarted | docker compose restart |
| A change on the pages has no effect | It waits for a restart (the bar at the top says so) | Restart now |
| The pages won't open: "This address isn't permitted" | Your computer isn't in security: admin_allowed | Edit settings.yaml on the server (empty list = the local network), restart |
| The pages say "Sign in first" again and again | The browser blocks the cookie on plain http with a secure cookie | Use https://, accept the certificate |
| Forgot the password | | docker compose exec house-router python -m veil.security reset \<name\> |
| A page says "Not saved: ... wouldn't read back" | Something in the edit would make the file unreadable; nothing was written | Change the wording, or open an issue |
| It says "Sorry, that's not something I can do for you." | A firewall rule matched (Transactions shows which) | Check the rule; Try it on the Firewall page |
| A device command is stopped for everyone | A rule for unknown voices while Oread is off (everyone is unknown) | Turn Oread on, or the rule off |
| Device commands are slow by a second | Veil Guard Service is waiting on the router (firewall on, router slow or Oread slow) | Transactions shows the time; lower Veil Guard Service's timeout or Oread's |
| Home Assistant's log: "Wepwawet Veil didn't answer about ..." | The router was down or slow; on_no_answer decided | Check the router; the house kept working with on_no_answer: allow |
| No name in its answers with Oread on | Oread wasn't sure (score below min_score, or "maybe"), or the deck said not this time | Transactions shows who spoke and the score |
| "who spoke: Oread not reached" in the log | Oread's address, token or certificate (API source) | Integrations, Oread, Test |
| A device stops hearing anything | The router is down or can't reach Oread ("Wyoming (...): couldn't reach Oread"), or Oread doesn't permit the router's address | Integrations, Oread, Test; or pick the Oread entry again in its assistant's Speech-to-text |
| Who spoke is always nobody with the audio path on | Its assistant's Speech-to-text is still the Oread entry, not the router's; or the words differ too much (min_word_overlap) | The log shows a Wyoming line per request when it's in the path |
| It answers a question you asked with something off-topic | The answer went to Gemini, not the router | Check decided: on Transactions; open an issue with the log and the HA debug |
| "Iris, yes" does nothing useful | Its question expired (2 minutes) or another request came in between | Ask again |
| The mic closes right after the persona's question | Some satellite apps don't reopen it, though HA asked (not the router's) | Answer with the wake word |
| "Something went wrong talking to Donetick, so I didn't change anything" | Donetick refused or wasn't reachable; nothing was changed | The log keeps Donetick's own error text |
| A chore shows up in Donetick with no due date | The router missed the add and Gemini added it with HA's to-do tool | "Who answered that?", then "Record that as a misunderstanding" |
| It says "Want me to ask around?" to something you meant for it | Speech-to-text garbled it, or it isn't shaped like a request | Say it again, or record it |
| Files the router wrote can't be saved in your editor | They belong to root | FILE_OWNER=1000:1000 in .env, then docker compose up -d --force-recreate; for old files: sudo chown -R $(id -u):$(id -g) . |

Anything else: open an issue with the log lines and the HA debug for that run.
