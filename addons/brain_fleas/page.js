// addons/brain_fleas/page.js - Brain fleas: the household's small true facts.
// An add-on's page (issue #25): the shell loads it when its menu item is chosen and hands it the page's
// helpers (kit). Moved out of the core's app.js with the add-on.
let K, api, h;
const allowed = (...a) => K.allowed(...a);
const busy = (...a) => K.busy(...a);
const errorBox = (...a) => K.errorBox(...a);
const input = (...a) => K.input(...a);
const okNote = (...a) => K.okNote(...a);
const userRulesView = (...a) => K.userRulesView(...a);

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  return fleasPage();
}

// Brain fleas: the household's small true facts, answered at home before the Off-Platform Bank, built
// with the same line-by-line builder as an app's User rules (addons/brain_fleas/fleas.py, learn/fleas.yaml).
async function fleasPage() {
  const d = await api("/api/fleas");
  const isAdmin = allowed("tools");
  const intro = h("p", { class: "quiet small" }, `Brain fleas are small true facts of the household ("We only buy pizza from Sal's", "who is talking to you"). Each has the ways it's asked ({speaking | talking} for choices) and its steps: Who spoke (Name Sparkle's name, only when Oread is sure) and Response (the persona's lines, with its flair added). One is answered at home after the topics and before the Off-Platform Bank. A way of asking of one or two words is a key: hearing all of it is enough. Built in: add, change and forget a flea by voice ("add a brain flea, we only buy pizza from Sal's"), each read back first. Kept in ${d.file}; used as soon as it's saved.`);
  const at = input("number", { step: "0.05", min: "0.05", max: "1", value: d.match_at, class: "num-in", "aria-label": "match at" });
  const who = new Set(d.changers.map((x) => x.toLowerCase()));
  const boxes = d.voices.map((v) => { const c = input("checkbox", { checked: who.has(v.toLowerCase()), "aria-label": v }); return [v, c]; });
  const sbox = errorBox();
  const sset = h("button", { type: "button", disabled: !isAdmin }, "Save");
  sset.addEventListener("click", busy(sset, sbox, async () => {
    await api("/api/fleas/settings", { method: "PATCH", body: { match_at: Number(at.value), changers: boxes.filter(([, c]) => c.checked).map(([v]) => v) } });
    sset.after(okNote("Saved."));
  }));
  const settings = h("section", { class: "card panel" }, h("h3", {}, "How fleas are found and changed"),
    h("div", { class: "setting" }, h("div", {}, h("strong", {}, "match at"), h("p", { class: "hint" }, "How closely a sentence must fit a flea's ways of asking for the persona to answer with it (0 to 1).")), at),
    h("div", { class: "setting" }, h("div", {}, h("strong", {}, "who may change fleas by voice"), h("p", { class: "hint" }, "Only these voices, and only when Oread is sure it's them. Anyone may ask.")),
      h("div", { class: "needs" }, boxes.length ? boxes.map(([v, c]) => h("label", { class: "chip" }, c, " ", v)) : h("span", { class: "quiet small" }, "No voices yet (Name Sparkle)"))),
    h("div", { class: "row-actions" }, sset, sbox));
  const x = { id: "fleas", title: "the router" };
  return [h("h1", {}, "Brain fleas"), settings,
    userRulesView(x, d, isAdmin, { saveUrl: "/api/fleas", intro: intro, noun: "flea", objects: false, titles: true })];
}
