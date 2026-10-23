// addons/flair/page.js - Persona Flair: her lines bank, the books she's combed, her knobs.
// An add-on's page (issue #25): the shell loads it when its menu item is chosen and hands it the page's
// helpers (kit). Moved out of the core's app.js with the add-on.
let K, api, h;
const allowed = (...a) => K.allowed(...a);
const busy = (...a) => K.busy(...a);
const check = (...a) => K.check(...a);
const chipList = (...a) => K.chipList(...a);
const cmp = (...a) => K.cmp(...a);
const errorBox = (...a) => K.errorBox(...a);
const field = (...a) => K.field(...a);
const hashParam = (...a) => K.hashParam(...a);
const hearButton = (...a) => K.hearButton(...a);
const input = (...a) => K.input(...a);
const number = (...a) => K.number(...a);
const okNote = (...a) => K.okNote(...a);
const runTool = (...a) => K.runTool(...a);
const select = (...a) => K.select(...a);
const sortHead = (...a) => K.sortHead(...a);
const infoTip = (...a) => K.infoTip(...a);
const route = (...a) => K.route(...a);
const when = (...a) => K.when(...a);

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  return flairPage();
}

// ---------- Personality: flair ----------

async function flairPage() {
  const d = await api("/api/flair");
  const who = hashParam("who") || (d.personalities[0] || {}).name || "";
  const tab = hashParam("tab") === "phrases" ? "phrases" : "main";
  const picker = h("div", { class: "pills" }, d.personalities.map((p) => h("a", { class: "pill", href: `#/flair?who=${p.name}${tab !== "main" ? `&tab=${tab}` : ""}`,
    "aria-pressed": p.name === who ? "true" : "false" }, p.name)));
  const tabs = h("div", { class: "tabs page-tabs", role: "tablist" }, [["main", "Persona Flair"], ["phrases", "Phrases"]].map(([id, text]) =>
    h("button", { role: "tab", type: "button", "aria-selected": id === tab ? "true" : "false",
      onclick: () => { location.hash = `#/flair?who=${who}${id !== "main" ? `&tab=${id}` : ""}`; } }, text)));
  const one = await api(`/api/flair/${who}`);
  const isAdmin = allowed("tools");
  let topicNames = ["weather", "chores"];
  try { if (allowed("topics")) topicNames = (await api("/api/topics")).topics.map((t) => t.name); } catch (e) { /* keep the two */ }
  FLAIR_TOPICS = ["any"].concat(topicNames, ["router"]);
  // Accept a line from her books and it goes straight into the lines bank
  const bankSec = h("div", {});
  const reload = async () => {
    const fresh = await api(`/api/flair/${who}`);
    bankSec.replaceChildren(linesBankCard(who, fresh, isAdmin, reload));
  };
  bankSec.append(linesBankCard(who, one, isAdmin, reload));
  const meP = d.personalities.find((p) => p.name === who) || {};
  const banner = h("div", { class: "flair-banner" },
    h("div", {}, h("div", { class: "flair-who" }, who || "nobody"), h("div", { class: "small" }, Number((one.personality || {}).rate || 0) > 0 ? "flair on (rate above 0)" : "flair off (rate 0)")),
    h("div", { class: "flair-stats" },
      h("span", {}, h("strong", {}, String(((one.personality || {}).flourishes || []).length)), " in the lines bank"),
      h("span", {}, h("strong", {}, String(meP.candidates || 0)), " from the books"),
      h("span", {}, h("strong", {}, `${Math.round(Number((one.personality || {}).rate || 0) * 100)}%`), " flourished")));
  const head = [h("h1", {}, "Persona Flair"), tabs, banner];
  if (tab === "phrases") return [...head, picker, isAdmin ? sourcesCard(who, one.sources || {}) : h("p", { class: "quiet" }, "Only an administrator can change where the lines come from."),
    isAdmin ? await combingCard() : null];
  return [...head,
    h("p", { class: "quiet" }, `Each persona's flair on answers given at home. The lines are in the Lines bank: type your own in, or Accept a line from the books and it goes straight there. Edit, save or delete any of them; an edit is heard after a restart.`),
    picker, knobsCard(who, one, isAdmin), bankSec, await candidatesCard(who, reload)];
}

// Where a flourish goes, and on which answers: the choices on the Flair page.
let FLAIR_TOPICS = ["any", "weather", "chores", "router"];
const FLAIR_SLOTS = [{ value: "any", label: "any (wherever it fits)" }, { value: "opener", label: "opener (before)" },
  { value: "closer", label: "closer (after)" }, { value: "aside", label: "aside (at a [[aside]])" }];

function topicSelect(topics, onChange) {
  const cur = (topics && topics.length ? topics : ["any"]).join(", ");
  const opts = FLAIR_TOPICS.map((t) => ({ value: t, label: t === "any" ? "any topic" : t === "router" ? "the router's own answers" : t }));
  if (!FLAIR_TOPICS.includes(cur)) opts.push({ value: cur, label: cur });
  return select(opts, cur, { "aria-label": "topic", onchange: (e) => onChange(e.target.value.split(",").map((x) => x.trim()).filter(Boolean)) });
}

function knobsCard(who, one, isAdmin) {
  const p = one.personality || {};
  const rate = input("number", { min: "0", max: "1", step: "0.05", value: p.rate ?? 0 });
  const streak = input("number", { min: "0", max: "10", step: "1", value: p.max_in_a_row ?? 1 });
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    await api(`/api/flair/${who}`, { method: "PUT", body: { rate: Number(rate.value), max_in_a_row: Number(streak.value) } });
    note.replaceChildren(okNote("Saved. Restart to hear it."));
    await K.refreshSession();
  }));
  // the deck: of every 10 answers at home, how many get a flourish
  const flairDeck = h("span", {});
  const drawDeck = () => flairDeck.replaceChildren(deckOf(Math.round(Number(rate.value || 0) * 10), "flair-on"));
  rate.addEventListener("input", drawDeck);
  drawDeck();
  return h("section", { class: "card panel flair-card flair-knobs" }, h("h2", {}, `${who}: how often`),
    h("div", { class: "deck-row" }, h("span", { class: "small quiet" }, "Of every 10 answers at home:"),
      h("span", { class: "deck-label" }, flairDeck, h("span", { class: "small" }, " flourished")),
      h("a", { class: "small", href: "#/sparkle" }, "Saying names: Name Sparkle")),
    h("div", { class: "grid2" },
      field("Flair rate", rate, "Share of answers at home with a flourish (0.6 = 6 of every 10, dealt like a deck)."),
      field("Most in a row", streak, "Never more flourished answers than this back to back (0 = no limit).")),
    box, h("div", { class: "row-actions" }, save, note));
}

// a row of 10 little cards, n of them filled: how many of every 10 answers
function deckOf(n, cls) {
  return h("span", { class: "deck", "aria-hidden": "true" },
    Array.from({ length: 10 }, (_, i) => h("span", { class: "card-dot" + (i < n ? ` on ${cls}` : "") })));
}

const LINE_COLUMNS = [["Line", "text"], ["Where", "slot"], ["Answers", "topics"], ["Mood", "mood"], ["From", "from"], ["", null]];
const lineKey = (f, k) => (Array.isArray(f[k]) ? f[k].join(", ") : f[k]) || "";

// one editable line as a table row: words, where, which answers, mood, its book; then the buttons
function lineRow(f, canEdit, buttons) {
  f._draft = f._draft || { text: f.text, slot: f.slot || "any", topics: f.topics || ["any"], mood: f.mood || ["plain"] };
  const dr = f._draft;
  const text = h("textarea", { rows: "1", class: "line-box", disabled: !canEdit, "aria-label": "The words", oninput: (e) => { dr.text = e.target.value; } }, dr.text);
  const slot = select(FLAIR_SLOTS, dr.slot, { disabled: !canEdit, "aria-label": "Where it goes", class: `tint slot-${dr.slot}`,
    onchange: (e) => { dr.slot = e.target.value; e.target.className = `tint slot-${dr.slot}`; } });
  const topic = topicSelect(dr.topics, (v) => { dr.topics = v; });
  if (!canEdit) topic.disabled = true;
  const mood = select(["plain", "warning", "sorry"], (dr.mood || ["plain"])[0], { disabled: !canEdit, "aria-label": "Mood", class: `tint mood-${(dr.mood || ["plain"])[0]}`,
    onchange: (e) => { dr.mood = [e.target.value]; e.target.className = `tint mood-${e.target.value}`; } });
  const box = errorBox();
  return h("tr", {},
    h("td", { class: "line-cell" }, text, f.placeholder ? h("span", { class: "badge", title: "A starter line: steps aside once there are real lines" }, "placeholder") : null),
    h("td", {}, slot), h("td", {}, topic), h("td", {}, mood),
    h("td", { class: "small quiet" }, f.from || ""),
    h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, hearButton(dr.text, true), ...buttons(dr, box)), box));
}

function lineTable(lines, draw) {
  const state = { sort: null, desc: false };
  const head = h("thead", {});
  const body = h("tbody", {});
  const redraw = () => {
    head.replaceChildren(sortHead(LINE_COLUMNS, state, redraw));
    const shown = state.sort ? [...lines].sort((x, y) => cmp(lineKey(x, state.sort), lineKey(y, state.sort), state.desc)) : lines;
    body.replaceChildren(...(shown.length ? shown.map(draw) : [h("tr", {}, h("td", { colspan: String(LINE_COLUMNS.length), class: "empty-state" }, "None."))]));
  };
  redraw();
  return h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table line-table" }, head, body));
}

function linesBankCard(who, one, isAdmin, reload) {
  const lines = ((one.personality || {}).flourishes || []).map((f, i) => Object.assign({ _i: i }, f));
  const table = lineTable(lines, (f) => lineRow(f, isAdmin, (dr, box) => {
    const save = h("button", { type: "button", disabled: !isAdmin }, "Save");
    save.addEventListener("click", busy(save, box, async () => {
      await api(`/api/flair/${who}/lines`, { method: "PATCH", body: { index: f._i, text_was: f.text, text: dr.text, slot: dr.slot, topics: dr.topics, mood: dr.mood } });
      box.replaceChildren(okNote("saved"));
      f.text = dr.text.trim().replace(/\s+/g, " ");
    }));
    const del = h("button", { type: "button", disabled: !isAdmin }, "Delete");
    del.addEventListener("click", busy(del, box, async () => {
      if (!confirm(`Take "${f.text}" out of the lines bank?`)) return;
      await api(`/api/flair/${who}/lines`, { method: "PATCH", body: { index: f._i, text_was: f.text, delete: true } });
      await reload();
    }));
    return [save, del];
  }));
  // add one line, or many at once separated by |
  const many = h("textarea", { rows: "2", class: "said-box", placeholder: "One line, or many separated by |   e.g.  Abracadabra! | By my broom! | Hocus pocus." });
  const addBtn = h("button", { type: "button", disabled: !isAdmin }, "Add to the lines bank");
  const addNote = h("span", { class: "small" });
  addBtn.addEventListener("click", busy(addBtn, addNote, async () => {
    const parts = many.value.split(/[|\n]/).map((x) => x.trim().replace(/\s+/g, " ")).filter(Boolean);
    const questions = parts.filter((x) => x.endsWith("?"));
    const r = await api(`/api/flair/${who}/lines`, { method: "POST", body: { lines: parts.filter((x) => !x.endsWith("?")).map((t) => ({ text: t })) } });
    await reload();
    // (the card was redrawn; say it in the new one)
    const note = document.querySelector(".lines-bank .add-note");
    if (note) note.replaceChildren(okNote(`${r.added} added${r.already ? `, ${r.already} already there` : ""}${questions.length ? `; ${questions.length} left out (a question)` : ""}. Restart to hear them.`));
  }));
  const byslot = (k) => lines.filter((f) => (f.slot || "any") === k).length;
  const fold = h("details", { class: "card panel fold flair-card flair-bank lines-bank", open: BANK_OPEN },
    h("summary", {}, h("h2", {}, "Lines bank ", h("span", { class: "count-badge" }, String(lines.length))),
      h("span", { class: "slot-tally" }, ["opener", "closer", "aside", "any"].filter(byslot).map((k) => h("span", { class: `tag slot-${k}` }, `${byslot(k)} ${k}`)))));
  fold.append(h("p", { class: "quiet small" }, "The lines. Each: where it goes (any = wherever it fits; opener before the answer, closer after it, aside only where a phrase has a hand-placed [[aside]]), which answers (any topic, one topic, or the router's own answers), and the mood it suits. Change one and Save it, or Delete it. Never a question: a reply has to end on its own question. Click a heading to sort."),
    table, h("div", { class: "bulk-add" }, field("Add lines", many, "Any topic and any place to start with; change them in the table after."), h("div", { class: "row" }, addBtn, h("span", { class: "small add-note" }), addNote)));
  fold.addEventListener("toggle", () => { BANK_OPEN = fold.open; });
  return fold;
}
let BANK_OPEN = true;          // the lines bank stays open or folded as you left it while you work

const BOOK_COLUMNS = [["Accept", null], ["Line", "text"], ["Where", "slot"], ["Mood", "mood"], ["Answers", "topics"], ["From", "from"]];

async function candidatesCard(who, reload) {
  const d = await api(`/api/flair/${who}/candidates`);
  const cands = d.candidates;
  const box = errorBox();
  const count = h("span", {}, String(cands.length));
  const state = { sort: null, desc: false };
  const head = h("thead", {});
  const body = h("tbody", {});
  let limit = 60;
  const more = h("button", { class: "more", type: "button", onclick: () => { limit += 100; redraw(); } }, "Show more");
  function rowFor(c) {
    const pick = { slot: c.slot, mood: c.mood || ["plain"] };
    const slot = select(["opener", "closer"], c.slot, { "aria-label": "Where it goes", class: `tint slot-${c.slot}`,
      onchange: (e) => { pick.slot = e.target.value; e.target.className = `tint slot-${pick.slot}`; } });
    const mood = select(["plain", "warning", "sorry"], (c.mood || ["plain"])[0], { "aria-label": "Mood", class: `tint mood-${(c.mood || ["plain"])[0]}`,
      onchange: (e) => { pick.mood = [e.target.value]; e.target.className = `tint mood-${e.target.value}`; } });
    const accept = h("input", { type: "checkbox", "aria-label": `Accept "${c.text}"`, title: "Accept: it goes into the lines bank" });
    const tr = h("tr", {},
      h("td", { class: "center" }, accept),
      h("td", { class: "line-cell" }, c.text, " ", hearButton(c.text, true)),
      h("td", {}, slot), h("td", {}, mood),
      h("td", { class: "small quiet" }, (c.topics || []).join(", ")),
      h("td", { class: "small quiet" }, c.from || ""));
    accept.addEventListener("change", async () => {
      accept.disabled = true;
      try {
        await api(`/api/flair/${who}/candidates/accept`, { method: "POST", body: { found: c.found || c.text, slot: pick.slot, mood: pick.mood } });
        cands.splice(cands.indexOf(c), 1);
        count.textContent = String(cands.length);
        tr.remove();
        await reload();
      } catch (e) { accept.checked = false; accept.disabled = false; box.textContent = e.message; }
    });
    return tr;
  }
  function redraw() {
    head.replaceChildren(sortHead(BOOK_COLUMNS, state, redraw));
    const shown = state.sort ? [...cands].sort((x, y) => cmp(lineKey(x, state.sort), lineKey(y, state.sort), state.desc)) : cands;
    body.replaceChildren(...(shown.length ? shown.slice(0, limit).map(rowFor)
      : [h("tr", {}, h("td", { colspan: String(BOOK_COLUMNS.length), class: "empty-state" }, "Empty. Comb the books (Phrases tab) to fill it again (lines already taken are left out)."))]));
    more.hidden = shown.length <= limit;
    more.textContent = `Show more (${shown.length - limit} left)`;
  }
  redraw();
  const clear = h("button", { type: "button", disabled: !cands.length }, "Clear the list");
  clear.addEventListener("click", busy(clear, box, async () => {
    if (!confirm(`Clear all ${cands.length} lines from the books list? Combing the books again fills it (leaving out what's been accepted or dropped).`)) return;
    await api(`/api/flair/${who}/candidates/clear`, { method: "POST" });
    cands.splice(0);
    count.textContent = "0";
    redraw();
  }));
  return h("details", { class: "card panel fold flair-card flair-books" }, h("summary", {}, h("h2", {}, "Lines from the books ", h("span", { class: "count-badge" }, count))),
    h("p", { class: "quiet small" }, "Best guesses first. Fix the slot or mood if the guess is wrong, then tick Accept: the line goes into the Lines bank at once (reword it there if it needs it) and leaves this list. The ones you don't want can stay or go: Clear the list empties it; combing the books again fills it, never with a line already in the bank or deleted from it. Click a heading to sort."),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table line-table" }, head, body)), more,
    box, h("div", { class: "row-actions" }, clear));
}

function sourcesCard(who, src) {
  const state = { speakers: src.speakers || [], near: src.near || [], books: (src.books || []).map((b) => Object.assign({}, b)) };
  const books = h("div", {});
  function draw() {
    books.replaceChildren(...state.books.map((b, i) => h("div", { class: "flourish" },
      input("text", { value: b.title, "aria-label": "title", oninput: (e) => { b.title = e.target.value; } }),
      input("text", { value: b.url, "aria-label": "address", oninput: (e) => { b.url = e.target.value; } }),
      input("text", { value: b.local, "aria-label": "local path", oninput: (e) => { b.local = e.target.value; } }),
      h("span", {}), h("button", { type: "button", "aria-label": "remove", onclick: () => { state.books.splice(i, 1); draw(); } }, "×"))));
  }
  draw();
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button" }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    await api(`/api/flair/${who}/sources`, { method: "PUT", body: state });
    note.replaceChildren(okNote("Saved. Download and comb again on the Tools page."));
  }));
  return h("details", { class: "card panel fold flair-card flair-sources", open: true }, h("summary", {}, h("h2", {}, "Phrases")),
    h("p", { class: "quiet small" }, "Public-domain books only (before 1929). Speakers: who the persona is in the books; near: words that put a quote in that world."),
    h("div", { class: "grid2" }, h("div", {}, h("h3", {}, "Speakers"), chipList(state.speakers, (v) => { state.speakers = v; })),
      h("div", {}, h("h3", {}, "Near words"), chipList(state.near, (v) => { state.near = v; }))),
    bookTools(who),
    h("h3", {}, "Books (title, address, local path)"), books,
    h("button", { type: "button", onclick: () => { state.books.push({ title: "", url: "https://www.gutenberg.org/cache/epub/", local: "~/datasets/books/" }); draw(); } }, "Add a book"),
    box, h("div", { class: "row-actions" }, save, note));
}

// Download her books and Comb the books, right here (the same tools as on the Tools page)
function bookTools(who) {
  const output = h("pre", { class: "output", hidden: true });
  const status = h("p", { class: "quiet small" });
  const run = (id, label) => {
    const b = h("button", { type: "button", class: id === "flair_mine" ? "primary" : "" }, label);
    b.addEventListener("click", () => runTool(id, { assistant: who }, output, status, label));
    return b;
  };
  return h("div", { class: "book-tools" },
    h("h3", {}, "Books"),
    h("p", { class: "quiet small" }, `First Download the books (from the addresses below to the local paths), then Comb the books: new lines appear in Lines from the books. Combing leaves out lines already in the bank or deleted from it.`),
    h("div", { class: "row-actions" }, run("flair_refresh", "Download the books"), run("flair_mine", "Comb the books")),
    status, output);
}

async function combingCard() {
  const d = (await api("/api/combing")).combing || {};
  const c = JSON.parse(JSON.stringify(d));
  const lists = [["said_words", "Said verbs (\"said the Witch\")"], ["speaker_adjectives", "Words before the speaker's kind (\"the good Witch\")"],
    ["never", "Never said"], ["story_words", "Story-bound words (a line about \"him\" or \"her\" makes no sense alone)"],
    ["allowed_capitals", "Capitalized words allowed"], ["closer_words", "Closer words (guess: goes after the answer)"],
    ["interjections", "Interjections (ranked higher)"]];
  const groups = [];
  for (const [k, label] of lists) groups.push(h("div", {}, h("h3", {}, label), chipList(c[k] || [], (v) => { c[k] = v; })));
  for (const g of ["moods", "topics"]) {
    for (const [k, v] of Object.entries(c[g] || {})) {
      groups.push(h("div", {}, h("h3", {}, `${g === "moods" ? "Mood" : "Topic"}: ${k}`), chipList(v, (nv) => { c[g][k] = nv; })));
    }
  }
  const maxWords = input("number", { min: "1", max: "30", value: c.max_words ?? 9, oninput: (e) => { c.max_words = Number(e.target.value); } });
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button" }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    await api("/api/combing", { method: "PUT", body: { combing: c } });
    note.replaceChildren(okNote("Saved. Comb the books again to use it."));
  }));
  return h("details", { class: "card panel flair-card flair-sources" }, h("summary", {}, h("strong", {}, "How the books are combed (personality/combing.yaml)")),
    h("p", { class: "quiet small" }, "Words and short phrases, whole words, ignoring case. A * at the end means any ending; -? an optional hyphen."),
    field("Longest line (words)", maxWords), h("div", { class: "grid2" }, groups), box, h("div", { class: "row-actions" }, save, note));
}

