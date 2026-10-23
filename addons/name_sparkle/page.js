// addons/name_sparkle/page.js - Name Sparkle: the names she calls people by.
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
// the deck drawing, as Flair's page draws it
function deckOf(n, cls) {
  return h("span", { class: "deck", "aria-hidden": "true" },
    Array.from({ length: 10 }, (_, i) => h("span", { class: "card-dot" + (i < n ? ` on ${cls}` : "") })));
}

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  return sparklePage();
}

// ---------- Personality: Name Sparkle (saying people's names) ----------

async function sparklePage() {
  const d = await api("/api/sparkle");
  const isAdmin = allowed("people");
  // where the names come from: one line at the top
  const from = select([{ value: "", label: "(none picked)" }].concat(d.sources.map((x) => ({ value: x.name, label: `${x.title}${x.who_spoke ? " (names who spoke)" : " (people list)"}` }))),
    d.voice_id_from || "", { "aria-label": "Voice ID from" });
  const fromBox = errorBox();
  const fromSave = h("button", { type: "button", disabled: !isAdmin }, "Save");
  fromSave.addEventListener("click", busy(fromSave, fromBox, async () => {
    await api("/api/sparkle", { method: "PUT", body: { voice_id_from: from.value } });
    route();
  }));
  // a tab per persona (found from the personality files, so a new device gets one), and Shared
  let current = hashParam("tab") || (d.devices.find((x) => x.has_file) || d.devices[0] || {}).name || "shared";
  const tabs = h("div", { class: "tabs page-tabs", role: "tablist" });
  const body = h("div", {});
  const isOn = (n) => Number((n || {}).rate || 0) > 0;
  function draw() {
    tabs.replaceChildren(...d.devices.map((x) => h("button", { role: "tab", type: "button", "aria-selected": x.name === current ? "true" : "false",
      onclick: () => { current = x.name; draw(); } }, x.name, isOn(x.names) ? h("span", { class: "tab-dot on", title: "names on" }) : h("span", { class: "tab-dot", title: "names off" }))),
      h("button", { role: "tab", type: "button", "aria-selected": current === "shared" ? "true" : "false", onclick: () => { current = "shared"; draw(); } }, "Shared"));
    const dev = d.devices.find((x) => x.name === current);
    body.replaceChildren(...(dev ? personaTab(d, dev, isAdmin, draw) : [namesTable(d, d.calls, isAdmin, {
      title: "Shared names", hint: "The names any persona may use for each voice, when it has none of its own for them.",
      put: async (person, names) => (await api("/api/sparkle/calls", { method: "PUT", body: { person: person, names: names } })).names,
      remove: async (person) => api("/api/sparkle/calls", { method: "PUT", body: { person: person, remove: true } }), pull: true })]));
  }
  draw();
  return [h("h1", {}, "Name Sparkle"),
    h("div", { class: "flair-banner sparkle-banner" },
      h("div", {}, h("div", { class: "flair-who" }, "Name Sparkle"), h("div", { class: "small" }, "saying your name now and then")),
      h("div", { class: "flair-stats" },
        h("span", {}, h("strong", {}, String(d.people.length)), " voices saved"),
        h("span", {}, h("strong", {}, String(d.devices.filter((x) => isOn(x.names)).length)), " personas saying names"))),
    h("div", { class: "row" }, h("label", { class: "small" }, "Voice ID from ", from), fromSave, fromBox,
      infoTip("The integration that knows people by voice. Its own names are the people everywhere: here, each app's people card, and the firewall. How sure it must be is its own, per device (its \"known\").")),
    tabs, body];
}

// One persona's tab on Name Sparkle: how often it says names, an optional least score, and its own
// names for each voice (used first; the shared names when it has none for someone).
function personaTab(d, dev, isAdmin, redraw) {
  const n = dev.names || {};
  const drate = input("number", { min: "0", max: "1", step: "0.05", value: n.rate ?? 0, "aria-label": `${dev.name}: share of answers` });
  const dstreak = input("number", { min: "0", max: "10", step: "1", value: n.max_in_a_row ?? 1, "aria-label": `${dev.name}: most in a row` });
  const dscore = input("number", { min: "0", max: "1", step: "0.01", value: n.min_score ?? "", placeholder: "the voice ID's own", "aria-label": `${dev.name}: at least this score` });
  const ddeck = h("span", {});
  const drawD = () => ddeck.replaceChildren(...(Number(drate.value || 0) > 0
    ? [deckOf(Math.round(Number(drate.value) * 10), "name-on"), h("span", { class: "small" }, " with a name")]
    : [h("span", { class: "quiet small" }, `no names on ${dev.name} (share 0)`)]));
  drate.addEventListener("input", drawD);
  drawD();
  const dbox = errorBox();
  const dnote = h("span", {});
  const dsave = h("button", { class: "primary", type: "button", disabled: !isAdmin }, `Save ${dev.name}`);
  dsave.addEventListener("click", busy(dsave, dbox, async () => {
    const r = await api(`/api/sparkle/device/${dev.name}`, { method: "PUT", body: { rate: drate.value, max_in_a_row: dstreak.value, min_score: dscore.value } });
    dev.names = Object.assign({}, dev.names, r.names);
    if (dscore.value === "") delete dev.names.min_score;
    dnote.replaceChildren(okNote("Saved. Restart to use it."));
    redraw();
  }));
  const own = Object.assign({}, n.calls || {});
  for (const v of d.people) if (!(v in own)) own[v] = [];
  return [h("section", { class: "card panel flair-card flair-knobs" },
      h("div", { class: "deck-row" }, h("span", { class: "small quiet" }, `On ${dev.name}, of every 10 answers:`), h("span", { class: "deck-label" }, ddeck)),
      h("div", { class: "grid3" },
        field("Share of answers", drate, "0 = no names on this persona. Random, dealt like a shuffled deck (0.3 = 3 of every 10)."),
        field("Most in a row", dstreak, "Never more answers with a name than this back to back (0 = no limit)."),
        field("At least this score", dscore, "Empty: the voice ID's own \"known\" for this device decides. A number asks for more.")),
      dbox, h("div", { class: "row-actions" }, dsave, dnote)),
    namesTable(d, own, isAdmin, { title: `${dev.name}'s own names`, hint: `What ${dev.name} calls each voice. Used first; a voice with none here gets the shared names.`,
      put: async (person, names) => (await api(`/api/sparkle/device/${dev.name}/calls`, { method: "PUT", body: { person: person, names: names } })).names })];
}

// The names under each voice: shared (with Pull and Delete) or one persona's own.
function namesTable(d, start, isAdmin, o) {
  const calls = JSON.parse(JSON.stringify(start || {}));
  const body = h("tbody", {});
  const box = errorBox();
  const pullNote = h("span", { class: "small" });
  async function put(person, names) { calls[person] = await o.put(person, names); draw(); }
  function draw() {
    const people = Object.keys(calls);
    body.replaceChildren(...(people.length ? people.flatMap((person) => {
      const names = calls[person] || [];
      const add = input("text", { placeholder: `another name for ${person}`, "aria-label": `Add a name for ${person}`, disabled: !isAdmin });
      const addBtn = h("button", { type: "button", disabled: !isAdmin }, "Add");
      const doAdd = busy(addBtn, box, async () => { if (add.value.trim()) await put(person, names.concat([add.value.trim()])); });
      addBtn.addEventListener("click", doAdd);
      add.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); doAdd(); } });
      const gone = o.remove ? h("button", { type: "button", disabled: !isAdmin, title: `Delete ${person} and the names under them` }, "Delete") : null;
      if (gone) gone.addEventListener("click", busy(gone, box, async () => { await o.remove(person); delete calls[person]; draw(); }));
      const rows = [h("tr", { class: "mh-band" },
        h("td", {}, h("strong", {}, person)),
        h("td", { class: "num" }, h("span", { class: "count-badge" }, String(names.length))),
        h("td", {}, h("div", { class: "row" }, add, addBtn, gone)))];
      names.forEach((nm, i) => {
        const t = input("text", { value: nm, "aria-label": `${person}: name ${i + 1}`, disabled: !isAdmin });
        const sv = h("button", { type: "button", disabled: !isAdmin }, "Save");
        sv.addEventListener("click", busy(sv, box, async () => { const nn = names.slice(); nn[i] = t.value; await put(person, nn); }));
        t.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sv.click(); } });
        const del = h("button", { type: "button", disabled: !isAdmin }, "Delete");
        del.addEventListener("click", busy(del, box, async () => { await put(person, names.filter((_, j) => j !== i)); }));
        rows.push(h("tr", { class: "mh-heard" }, h("td", {}, t), h("td", {}), h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, hearButton(nm, true), sv, del))));
      });
      return rows;
    }) : [h("tr", {}, h("td", { colspan: "3", class: "empty-state" }, "No voices saved yet: press Pull on the Shared tab."))]));
  }
  draw();
  const srcTitle = ((d.sources || []).find((x) => x.name === d.voice_id_from) || {}).title || d.voice_id_from || "the voice ID";
  let pull = null;
  if (o.pull) {
    pull = h("button", { type: "button", class: "primary", disabled: !isAdmin || !d.voice_id_from }, `Pull from ${srcTitle}`);
    pull.addEventListener("click", busy(pull, pullNote, async () => {
      const r = await api("/api/sparkle/pull", { method: "POST" });
      for (const p of r.added) calls[p] = [];
      draw();
      pullNote.replaceChildren(okNote(r.added.length ? `${r.added.length} new: ${r.added.join(", ")}` : `nobody new (${r.from} knows ${r.known.length})`));
    }));
  }
  return h("section", { class: "card panel flair-card flair-bank" }, h("h2", {}, o.title, " ", infoTip(o.hint)),
    pull ? h("div", { class: "row-actions" }, pull, pullNote) : null,
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table mh-table calls-table" },
      h("thead", {}, h("tr", {}, h("th", {}, "Voice / names to use"), h("th", { class: "num" }, "Names"), h("th", {}, ""))), body)), box);
}

