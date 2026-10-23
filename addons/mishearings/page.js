// addons/mishearings/page.js - Mishearings: what speech-to-text heard, under what was really said.
// An add-on's page (issue #25): the shell loads it when its menu item is chosen and hands it the page's
// helpers (kit). Moved out of the core's app.js (the Misses page) with the add-on.
let K, api, h;
const busy = (...a) => K.busy(...a);
const cmp = (...a) => K.cmp(...a);
const decisionText = (...a) => K.decisionText(...a);
const errorBox = (...a) => K.errorBox(...a);
const foldBox = (...a) => K.foldBox(...a);
const input = (...a) => K.input(...a);
const route = (...a) => K.route(...a);
const sortHead = (...a) => K.sortHead(...a);
const underBox = (...a) => K.underBox(...a);
const when = (...a) => K.when(...a);

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  return mishearingsPage();
}

function diffView(diff) {
  return diff ? h("span", { class: "diff" }, diff.map((x) => x.op === "same" ? h("span", {}, x.heard + " ")
    : [x.heard ? h("del", { title: "heard" }, x.heard) : null, x.said ? h("ins", { title: "really said" }, x.said) : null, " "])) : null;
}

// The phrase fix's two boxes, filled with the whole line as heard and as meant: trim them to the
// words that should be swapped (a short question is usually the phrase as it is).
function phraseStart(diff) {
  const join = (side) => diff.map((op) => op[side]).filter(Boolean).join(" ");
  return { heard: join("heard"), meant: join("said") };
}

function phraseBox(under, more, c) {
  const start = phraseStart(c.diff || []);
  const heard = input("text", { value: start.heard, "aria-label": "heard", class: "said-box" });
  const meant = input("text", { value: start.meant, "aria-label": "meant", class: "said-box" });
  const go = h("button", { type: "button", class: "primary" }, "Save");
  const msg = errorBox();
  const close = () => { under.hidden = true; more.replaceChildren(); };
  let warned = "";
  go.addEventListener("click", busy(go, msg, async () => {
    const words = heard.value.trim().split(/\s+/).filter(Boolean);
    if (words.length === 1 && warned !== words[0]) {
      // a word on its own is swapped everywhere: said here, not in a pop-up; Save again keeps it
      warned = words[0];
      go.textContent = "Save anyway";
      throw new Error(`This swaps "${words[0]}" everywhere it's heard. Add a word around it, or Save anyway.`);
    }
    await api("/api/mishearings/swap", { method: "POST", body: { heard: heard.value, meant: meant.value, on: true, line: c.said } });
    route();
  }));
  for (const box of [heard, meant]) box.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } if (e.key === "Escape") close(); });
  more.replaceChildren(h("div", { class: "misheard-fix" },
    h("span", { class: "small quiet" }, "The whole line as heard: trim it to the words that should be swapped (whole words, in this order)."), heard,
    h("span", { class: "small quiet" }, "Use these instead (trim to match):"), meant,
    h("div", { class: "row-actions" }, go, h("button", { type: "button", onclick: close }, "Cancel"), msg)));
  under.hidden = false;
  heard.focus();
}

const MH_COLUMNS = [["What was said / heard", "text"], ["Times", "times"], ["First", "first"], ["Last", "last"], ["Today", null], ["", null]];

// mishearings: each intention a band row (what was really said, its total), its heard lines under it
function mishearingRows(p, state, swaps) {
  const cols = MH_COLUMNS.length;
  const band = h("tr", { class: "mh-band" + (p.meant ? "" : " mh-unknown") },
    h("td", {}, p.meant ? h("strong", {}, p.meant) : h("strong", { class: "quiet" }, "Not given yet: type what was really said")),
    h("td", { class: "num" }, h("strong", {}, String(p.total))),
    h("td", {}), h("td", {}),
    h("td", { class: "small quiet" }, p.now_meant ? decisionText(p.now_meant) : ""), h("td", {}));
  const kids = [...p.heard].sort((x, y) => state.sort === "text" ? cmp(x.said, y.said, state.desc)
    : state.sort === "last" || state.sort === "first" ? cmp(x[state.sort], y[state.sort], state.desc) : cmp(x.count || 1, y.count || 1, state.desc));
  const rows = [band];
  for (const c of kids) {
    const msg = errorBox();
    const more = h("td", { colspan: String(cols) });
    const under = h("tr", { class: "txn-more", hidden: true }, more);
    const move = h("button", { type: "button", title: p.meant ? "File it under other words (its count goes with it)" : "File it under what was really said" }, p.meant ? "Move" : "Said");
    move.addEventListener("click", () => underBox(under, more, "What was really said", p.meant, p.meant ? "Move" : "Save",
      (v) => api("/api/mishearings/meant", { method: "POST", body: { heard: c.said, meant: v } })));
    const drop = h("button", { type: "button" }, "Drop");
    drop.addEventListener("click", busy(drop, msg, async () => {
      if (!confirm(`Take "${c.said}" out of the mishearings? Its count goes with it.`)) return;
      await api("/api/mishearings/drop", { method: "POST", body: { heard: c.said } });
      route();
    }));
    // each difference can be used before anything is decided (a swap, learn/swaps.yaml): whole words only
    const inUse = (heardW) => (swaps || []).some((x) => x.heard === heardW.toLowerCase());
    const useBtns = (c.diff || []).filter((op) => op.op === "both" && op.heard && op.said).map((op) => {
      const on = inUse(op.heard);
      const b = h("button", { type: "button", class: on ? "pill-ok small" : "small", title: on ? "In use: heard words swapped before anything is decided, and for Home Assistant. Click to stop." : `Swap "${op.heard}" for "${op.said}" whenever it's heard, before anything is decided and in the words Home Assistant gets (whole words only). A common word changes everywhere: use a phrase for it.` },
        on ? `Using: ${op.heard} → ${op.said}` : `Use it: ${op.heard} → ${op.said}`);
      b.addEventListener("click", busy(b, msg, async () => { await api("/api/mishearings/swap", { method: "POST", body: { heard: op.heard, meant: op.said, on: !on } }); route(); }));
      return b;
    });
    // a phrase fix: the changed words with a word either side (widen or narrow it), only that run swapped
    const phrase = (c.diff || []).some((op) => op.op !== "same") ? h("button", { type: "button", class: "small",
      title: "Swap a run of words (who taught you three → who taught you that), only when that whole run is heard" }, "Use a phrase") : null;
    if (phrase) phrase.addEventListener("click", () => phraseBox(under, more, c));
    rows.push(h("tr", { class: "mh-heard" },
      h("td", { class: "mh-said" }, c.diff ? diffView(c.diff) : `"${c.said}"`, c.taken ? [" ", h("span", { class: "badge" }, "taken")] : null,
        useBtns.length || phrase ? h("div", { class: "row-actions" }, ...useBtns, phrase) : null),
      h("td", { class: "num" }, String(c.count || 1)),
      h("td", { class: "quiet nowrap" }, c.first || ""), h("td", { class: "quiet nowrap" }, c.last || ""),
      h("td", { class: "small" }, c.now_heard ? [decisionText(c.now_heard), " ", h("span", { class: "nowrap " + (c.verdict.startsWith("harmless") ? "pill-ok" : "pill-bad"),
        title: c.verdict }, c.verdict.startsWith("harmless") ? "harmless now" : "still matters")] : ""),
      h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, move, drop), msg)), under);
  }
  return rows;
}

// the mishearings pushed back: each heard words swapped before anything is decided (learn/swaps.yaml),
// as a table (Oct 18: a run of chips grew too long): folded, sortable like the rest
const SWAP_COLUMNS = [["Heard", "heard"], ["Swapped for", "meant"], ["Added", "added"], ["Used", "used"], ["Last used", "last_used"], ["", null]];
function swapsInUse(swaps, days) {
  if (!swaps.length) return null;
  const msg = errorBox();
  const state = { sort: "heard", desc: false };
  const head = h("thead", {});
  const body = h("tbody", {});
  const draw = () => {
    head.replaceChildren(sortHead(SWAP_COLUMNS, state, draw, ["Used"]));
    body.replaceChildren(...[...swaps].sort((x, y) => cmp(x[state.sort] ?? "", y[state.sort] ?? "", state.desc)).map((x) => {
      const stop = h("button", { type: "button", class: "small", "aria-label": `stop swapping ${x.heard}` }, "Stop");
      stop.addEventListener("click", busy(stop, msg, async () => { await api("/api/mishearings/swap", { method: "POST", body: { heard: x.heard, meant: x.meant, on: false } }); route(); }));
      return h("tr", {}, h("td", {}, h("code", {}, x.heard)), h("td", {}, h("code", {}, x.meant)),
        h("td", { class: "quiet nowrap" }, x.added || "-"), h("td", { class: "num" }, String(x.used || 0)),
        h("td", { class: "quiet nowrap" }, x.last_used ? when(x.last_used) : "-"), h("td", { class: "txn-actions" }, stop));
    }));
  };
  draw();
  return foldBox("swaps", `In use before anything is decided, and in the words Home Assistant gets (${swaps.length})`, false,
    h("p", { class: "quiet small" }, `Used: how many requests had it swapped in the last ${days} days (the activity log keeps that long). Stop takes it out at once.`),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table swaps-table" }, head, body)), msg);
}

async function mishearingsPage() {
  const mh = await api("/api/mishearings");
  // mishearings: not given yet first, then the intentions in the chosen order
  const mstate = { sort: "times", desc: true };
  const mbody = h("tbody", {});
  const mhead = h("thead", {});
  const lastOf = (p) => p.heard.reduce((a, c) => (c.last || "") > a ? c.last : a, "");
  const firstOf = (p) => p.heard.reduce((a, c) => c.first && (!a || c.first < a) ? c.first : a, "");
  const drawM = () => {
    mhead.replaceChildren(sortHead(MH_COLUMNS, mstate, drawM, ["Times"]));
    const groups = [...mh.mishearings].sort((x, y) => (x.meant === null) !== (y.meant === null) ? (x.meant === null ? -1 : 1)
      : mstate.sort === "text" ? cmp(x.meant, y.meant, mstate.desc) : mstate.sort === "last" ? cmp(lastOf(x), lastOf(y), mstate.desc)
        : mstate.sort === "first" ? cmp(firstOf(x), firstOf(y), mstate.desc) : cmp(x.total, y.total, mstate.desc));
    mbody.replaceChildren(...(groups.length ? groups.flatMap((p) => mishearingRows(p, mstate, mh.swaps))
      : [h("tr", {}, h("td", { colspan: String(MH_COLUMNS.length), class: "empty-state" }, "No mishearings recorded."))]));
  };
  drawM();
  return [h("h1", {}, "Mishearings"),
    h("p", { class: "quiet" }, "What speech-to-text heard, under what was really said: each intention is a band with its total, the ways it was heard under it, each counted, with the wrong words crossed out and the right ones beside them. They come from Misheard on the Transactions page, or by voice (\"What did you hear?\", then \"Record that as a misunderstanding\"). They stay, counting, until you drop them or they're taken into the words. Move files one under other words, count and all (Enter saves, Esc closes). Today says where the router sends each now, and whether the mishearing still matters. Use it on a difference (grainsplate → brain flea) swaps those heard words for the right ones before anything is decided, whenever they're heard, whole words only, and in the words handed back to Home Assistant too, so its own sentences match; Use a phrase swaps a run of words only when the whole run is heard (who taught you three → who taught you that), so a common word on its own is left alone. Use it on a common word changes it everywhere (watcher → washer would make \"Who is the watcher?\" \"Who is the washer?\"): use a phrase for those. The trace says when a swap happened."),
    swapsInUse(mh.swaps || [], mh.swap_days),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table mh-table" }, mhead, mbody))];
}
