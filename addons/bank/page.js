// addons/bank/page.js - the Off-Platform Bank: the sayings that went out, their answers, which come back from it.
// An add-on's page (issue #25): the shell loads it and hands it the page's helpers (kit).
let K, api, h;
const allowed = (...a) => K.allowed(...a);
const busy = (...a) => K.busy(...a);
const cmp = (...a) => K.cmp(...a);
const errorBox = (...a) => K.errorBox(...a);
const hearButton = (...a) => K.hearButton(...a);
const input = (...a) => K.input(...a);
const okNote = (...a) => K.okNote(...a);
const select = (...a) => K.select(...a);
const sortHead = (...a) => K.sortHead(...a);
const when = (...a) => K.when(...a);
const withRules = (...a) => K.withRules(...a);

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  K.rulesExtra("bank", bankTrim);          // the Rules tab's Trim, beside the bank's own settings
  return withRules("bank", "Off-Platform Bank", bankPage)();
}

// ---------- Watch: the Off-Platform bank ----------

function commandText(json) {
  // [{"name": "HassTurnOn", "arguments": "{\"name\": \"garage door\"}"}] -> HassTurnOn (name: garage door)
  let calls = [];
  try { calls = JSON.parse(json || "[]"); } catch (e) { return String(json || ""); }
  return calls.map((c) => {
    let a = c.arguments;
    if (typeof a === "string") { try { a = a.trim() ? JSON.parse(a) : {}; } catch (e) { return `${c.name} (${a})`; } }
    const parts = Object.entries(a || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`);
    return parts.length ? `${c.name} (${parts.join("; ")})` : c.name;
  }).join(", then ");
}

function pct(x) { return x === null || x === undefined ? "-" : `${Math.round(Number(x) * 100)}%`; }

async function bankPage() {
  const view = (location.hash.split("?view=")[1] || "sayings");
  const tabs = h("div", { class: "tabs", role: "tablist" }, [["sayings", "By saying"], ["results", "What it became"]]
    .map(([id, label]) => h("button", { role: "tab", "aria-selected": id === view ? "true" : "false", onclick: () => { location.hash = `#/bank?view=${id}`; } }, label)));
  const intro = h("p", { class: "quiet" }, "Each identical request (the same words from speech to text) that had to go Off-Platform, per personality, counted, with the Off-Platform answers that came back. A request you add (Bank on Transactions, or here) becomes a replacement answer; your formula decides how often the bank answers it instead.");
  // Export: the bank written to learn/bank.yaml, so it can go to git (the database never does)
  const exMsg = h("span", { class: "small" });
  const ex = h("button", { type: "button", disabled: !allowed("bank"), title: "Write the whole bank to learn/bank.yaml, to commit and push" }, "Export to learn/bank.yaml");
  ex.addEventListener("click", busy(ex, exMsg, async () => {
    const r = await api("/api/bank/export", { method: "POST" });
    exMsg.replaceChildren(okNote(`${r.sayings} sayings (${r.added} added) written to ${r.file}: commit and push it to share it`));
  }));
  const exportRow = h("div", { class: "row-actions" }, ex, exMsg);
  // the generic upload: sayings and the ways each may be answered, answered at home from then on
  const upBox = h("textarea", { rows: "6", class: "words-box", "aria-label": "sayings to upload, as YAML",
    placeholder: "- said: what is the capital of PA\n  answers:\n    - Harrisburg is the capital of Pennsylvania." });
  const upMsg = h("span", { class: "small" });
  const upBtn = h("button", { type: "button", disabled: !allowed("bank") }, "Add them to the bank");
  upBtn.addEventListener("click", busy(upBtn, upMsg, async () => {
    const r = await api("/api/bank/upload", { method: "POST", body: { yaml: upBox.value, generic: true } });
    upMsg.replaceChildren(okNote(`${r.added} added for ${r.personality}, generic: answered at home from now on (with Use the bank on)`));
  }));
  const upload = h("details", { class: "card panel fold" }, h("summary", {}, h("h2", {}, "Upload sayings")),
    h("p", { class: "quiet small" }, "Each saying with the ways it may be answered, as YAML: said, then answers. Each goes in as added and generic, so the bank answers it every time, with no trip Off-Platform."),
    upBox, h("div", { class: "row-actions" }, upBtn, upMsg));
  if (view === "results") return [h("h1", {}, "Off-Platform Bank"), intro, exportRow, upload, tabs, await bankResults()];
  return [h("h1", {}, "Off-Platform Bank"), intro, exportRow, upload, tabs, ...(await bankSayings())];
}

// on the bank's Rules tab: trim the one-offs now, rather than waiting for trim_days
async function bankTrim() {
  const canSet = allowed("settings");
  const trimMsg = h("span", { class: "small" });
  const trimBtn = h("button", { type: "button", disabled: !canSet }, "Trim one-offs now");
  trimBtn.addEventListener("click", busy(trimBtn, trimMsg, async () => {
    const r = await api("/api/bank/trim", { method: "POST" });
    trimMsg.replaceChildren(okNote(`${r.trimmed} taken out`));
  }));
  return h("section", { class: "card panel" }, h("h2", {}, "The formula"),
    h("p", { class: "quiet small formula" }, "N = Off-Platform trips − 1   ·   T = answers kept per saying (bank_answers_kept)   ·   Q = N ÷ T (at most 100%)   ·   with Q ≥ U (bank_use_from) the bank answers Q of the time, at random, with one of the words kept for it. Turn it on with answer_from_bank."),
    h("div", { class: "row-actions" }, trimBtn, trimMsg, h("span", { class: "small quiet" }, "Sayings heard once, not added or reviewed, older than trim_days.")));
}

const RESULT_COLUMNS = [["Device command", "sig"], ["Times", "count"], ["Wordings", "wordings"], ["Last", "last"], ["Said after", null], ["", null]];

async function bankResults() {
  const d = await api("/api/bank/results");
  if (d.off) return h("p", { class: "empty-state" }, "The activity log is off.");
  const state = { sort: "count", desc: true };
  const head = h("thead", {});
  const body = h("tbody", {});
  const val = (r) => ({ sig: r.sig, count: r.count, wordings: r.variants.length, last: r.last })[state.sort];
  const draw = () => {
    head.replaceChildren(sortHead(RESULT_COLUMNS, state, draw, ["Times", "Wordings"]));
    const rows = [...(d.results || [])].sort((x, y) => cmp(val(x), val(y), state.desc)).flatMap((r) => {
      const more = h("td", { colspan: String(RESULT_COLUMNS.length) },
        h("table", { class: "matrix sub" }, h("tbody", {}, r.variants.map((v) => h("tr", {},
          h("td", { class: "txn-heard" }, v.heard), h("td", { class: "num" }, `${v.count}×`), h("td", { class: "quiet" }, v.class), h("td", { class: "quiet" }, v.personality || ""))))));
      const under = h("tr", { class: "txn-more", hidden: true }, more);
      const open = h("button", { type: "button", class: "quiet-button" }, "Wordings");
      open.addEventListener("click", () => { under.hidden = !under.hidden; });
      return [h("tr", {},
        h("td", { class: "txn-heard" }, r.sig),
        h("td", { class: "num" }, String(r.count)),
        h("td", { class: "num" }, String(r.variants.length)),
        h("td", { class: "quiet nowrap" }, when(r.last)),
        h("td", { class: "txn-said" }, r.final ? h("div", { class: "said-line" }, hearButton(r.final, true), h("span", { class: "clamp", title: r.final }, r.final)) : ""),
        h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, open))), under];
    });
    body.replaceChildren(...(rows.length ? rows : [h("tr", {}, h("td", { colspan: String(RESULT_COLUMNS.length), class: "empty-state" }, "No device commands yet."))]));
  };
  draw();
  const a = d.answers || {};
  return h("div", {}, h("p", { class: "quiet small" }, "The device commands the Off-Platform model turned requests into, counted. Wordings opens every way it was asked."),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table" }, head, body)),
    h("p", { class: "quiet small" }, `Plus ${a.rows || 0} sayings it simply answered (${a.asked || 0} times): see By saying.`));
}

const BANK_COLUMNS = [["Saying", "heard"], ["Personality", "personality"], ["Kind", "class"], ["Heard", "count"], ["Trips", "trips"],
  ["By bank", "used"], ["State", "q"], ["Last", "last"], ["Generic", "generic"], ["Review", "review"], ["", null]];

async function bankSayings() {
  const added = select([{ value: "yes", label: "added (replacement answers)" }, { value: "no", label: "only counted" },
    { value: "all", label: "added and counted" }], "yes", { "aria-label": "Added" });
  const who = select([{ value: "", label: "every personality" }], "", { "aria-label": "Personality" });
  const review = select([{ value: "", label: "every review" }, "new", "keep", "ignore", "promote"], "", { "aria-label": "Review" });
  const search = input("search", { placeholder: "words in the request", "aria-label": "Search" });
  const state = { sort: "count", desc: true };
  const head = h("thead", {});
  const body = h("tbody", {});
  let d = { rows: [] };
  let filled = false;
  const status = h("p", { class: "small bank-status" });
  async function load() {
    const q = new URLSearchParams({ added: added.value, personality: who.value, review: review.value, order: "count", search: search.value, limit: "1000" });
    d = await api(`/api/bank?${q}`);
    // whether the bank answers at all, said once here rather than on every row
    status.replaceChildren(d.bank_keeps === false ? h("span", { class: "pill-bad" }, "The bank is off: answers kept is 0 (Rules tab). It still counts.")
      : d.answer_from_bank ? h("span", { class: "pill-ok" }, "The bank answers: Use the bank is on.")
        : h("span", {}, "The bank collects but doesn't answer yet: Use the bank is off (Rules tab)."));
    if (!filled) {
      for (const p of d.personalities || []) who.append(h("option", { value: p }, p));
      filled = true;
    }
    draw();
  }
  const draw = () => {
    head.replaceChildren(sortHead(BANK_COLUMNS, state, draw, ["Heard", "Trips", "By bank"]));
    const rows = [...d.rows].sort((x, y) => cmp(x[state.sort] ?? "", y[state.sort] ?? "", state.desc)).flatMap((r) => bankRow(r));
    body.replaceChildren(...(rows.length ? rows : [h("tr", {}, h("td", { colspan: String(BANK_COLUMNS.length), class: "empty-state" },
      added.value === "yes" ? "Nothing added yet: Bank a request that went Off-Platform on the Transactions page." : "Nothing here yet."))]));
  };
  function bankRow(r) {
    const box = errorBox();
    const more = h("td", { colspan: String(BANK_COLUMNS.length) });
    const under = h("tr", { class: "txn-more", hidden: true }, more);
    const reviewSel = select(["new", "keep", "ignore", { value: "promote", label: "answer at home later" }], r.review, { "aria-label": "Review" });
    reviewSel.addEventListener("change", async () => {
      try { await api(`/api/bank/${r.id}`, { method: "PATCH", body: { review: reviewSel.value } }); r.review = reviewSel.value; } catch (e) { box.textContent = e.message; }
    });
    // Generic: these answers suit every personality; another may use them, adding her own flair
    const generic = h("input", { type: "checkbox", checked: !!r.generic, "aria-label": `Generic: any personality may use "${r.heard}"`,
      title: "Generic: any personality may answer this from the bank, adding its own flair. Off: only " + (r.personality || "this personality") });
    generic.addEventListener("change", async () => {
      try { await api(`/api/bank/${r.id}`, { method: "PATCH", body: { generic: generic.checked } }); r.generic = generic.checked ? 1 : 0; }
      catch (e) { generic.checked = !generic.checked; box.textContent = e.message; }
    });
    const addBtn = h("button", { type: "button", class: r.added ? "" : "primary", title: r.added ? "Take it out of the bank (it's counted still)" : "A replacement answer: the bank may answer it" }, r.added ? "Take out" : "Add");
    addBtn.addEventListener("click", busy(addBtn, box, async () => {
      await api(`/api/bank/${r.id}`, { method: "PATCH", body: { added: !r.added } });
      load();
    }));
    const answers = h("button", { type: "button", class: "quiet-button", title: "The answers kept for it, and your note" }, `Answers (${(r.answers || []).length})`);
    answers.addEventListener("click", () => {
      if (!under.hidden) { under.hidden = true; return; }
      const note = h("textarea", { rows: "2", class: "said-box", placeholder: "a note (never acted on)", "aria-label": "Note" }, r.note || "");
      const save = h("button", { type: "button" }, "Save note");
      const nmsg = errorBox();
      // answer at home: its words and the answers kept become a brain flea (asked before Off-Platform)
      const flea = h("button", { type: "button", disabled: !(r.answers || []).some((a) => a.kind !== "tool" && a.answer),
        title: "Answer it at home: a brain flea with its words, saying the answers kept" }, "Make it a brain flea");
      flea.addEventListener("click", busy(flea, nmsg, async () => {
        const got = await api(`/api/bank/${r.id}/flea`, { method: "POST" });
        nmsg.replaceChildren(okNote(`Brain flea ${got.flea} made: answered at home now`));
      }));
      save.addEventListener("click", busy(save, nmsg, async () => {
        await api(`/api/bank/${r.id}`, { method: "PATCH", body: { review: r.review, note: note.value } });
        r.note = note.value;
        nmsg.replaceChildren(okNote("saved"));
      }));
      more.replaceChildren(
        h("table", { class: "matrix sub" }, h("tbody", {}, (r.answers || []).length ? r.answers.map((a) => h("tr", {},
          h("td", { class: "quiet nowrap" }, when(a.time)),
          h("td", { class: "txn-said" }, a.kind === "tool" ? [h("strong", {}, "Device command: "), commandText(a.tool_calls), a.answer ? ` · then said: ${a.answer}` : ""]
            : h("div", { class: "said-line" }, hearButton(a.answer, true), h("span", {}, a.answer || "(no words)"))),
          h("td", { class: "quiet nowrap" }, [a.model, a.ms ? `${(a.ms / 1000).toFixed(1)} s` : ""].filter(Boolean).join(" · ")))) :
          h("tr", {}, h("td", { class: "quiet" }, "No answers kept yet.")))),
        h("div", { class: "misheard-fix" }, note, h("div", { class: "row-actions" }, save, flea, nmsg)));
      under.hidden = false;
    });
    // the saying's own state; whether the bank answers at all is shown once, above the table
    const stateText = !r.added ? ["counted only", ""]
      : r.usable && d.answer_from_bank ? [`answers ${pct(r.q)} of the time`, "pill-ok"]
        : r.usable ? [`ready: ${pct(r.q)} of ${pct(d.u)}`, ""]
          : [(r.answers || []).length ? `added; ${pct(r.q)} of ${pct(d.u)}` : "added; no answers yet", ""];
    return [h("tr", { class: r.added ? "bank-added" : "" },
      h("td", { class: "txn-heard" }, r.heard, r.note ? h("div", { class: "small quiet", title: r.note }, `Note: ${r.note}`) : null),
      h("td", {}, r.personality || "?"),
      h("td", { class: "quiet" }, r.class + (r.qword ? ` (${r.qword})` : ""), r.topic_guess ? h("div", { class: "small", title: "closest home topic" }, `${r.topic_guess} ${Math.round((r.topic_score || 0) * 100)}%`) : null),
      h("td", { class: "num" }, String(r.count)),
      h("td", { class: "num" }, String(r.trips)),
      h("td", { class: "num" }, String(r.used || 0)),
      h("td", { class: "small" }, h("span", { class: stateText[1] }, stateText[0])),
      h("td", { class: "quiet nowrap" }, when(r.last)),
      h("td", { class: "center" }, generic),
      h("td", {}, reviewSel),
      h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, answers, addBtn), box)), under];
  }
  for (const el of [added, who, review, search]) el.addEventListener("change", load);
  await load();
  return [h("p", { class: "quiet small" }, "Each saying, how often it was heard and went Off-Platform, how often the bank answered it, and its state. Added ones are tinted. Generic: any personality may answer it from the bank, adding its own flair (left off, it stays with the personality that asked; a persona's own saying always comes first). Answers opens the answers kept for it (the newest T) and your note. Click a heading to sort. Reviewed and added sayings are never trimmed."), status,
    h("div", { class: "toolbar" }, added, who, review, search),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table bank-table" }, head, body))];
}

