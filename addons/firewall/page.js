// addons/firewall/page.js - the Firewall: who may use what, by voice.
// An add-on's page (issue #25): the shell loads it when its menu item is chosen and hands it the page's
// helpers (kit). Moved out of the core's app.js with the add-on.
let K, api, h;
const allowed = (...a) => K.allowed(...a);
const busy = (...a) => K.busy(...a);
const check = (...a) => K.check(...a);
const chipList = (...a) => K.chipList(...a);
const errorBox = (...a) => K.errorBox(...a);
const field = (...a) => K.field(...a);
const input = (...a) => K.input(...a);
const number = (...a) => K.number(...a);
const okNote = (...a) => K.okNote(...a);
const select = (...a) => K.select(...a);
const when = (...a) => K.when(...a);

export async function render(api_, h_, kit) {
  K = kit; api = api_; h = h_;
  return firewallPage();
}

// ---------- Protect: firewall ----------

// Ticks for one rule list, in the router's words, keeping the front end's names in the rule
// (frontend/<name>.yaml). A value the words don't know is still shown, so nothing is lost.
function picks(rule, key, title, options, hint) {
  const have = new Set(rule[key] || []);
  const known = new Set(options.map((o) => o.value));
  const boxes = options.map((o) => h("label", { class: "check small", title: o.value },
    h("input", { type: "checkbox", checked: have.has(o.value), onchange: (e) => {
      const now = new Set(rule[key] || []);
      if (e.target.checked) now.add(o.value); else now.delete(o.value);
      rule[key] = [...now];
    } }), ` ${o.label} `, h("code", { class: "quiet small" }, o.value)));
  const odd = [...have].filter((v) => !known.has(v));
  return h("div", {}, h("h3", {}, title), hint ? h("p", { class: "hint" }, hint) : null,
    h("div", { class: "pick-grid" }, ...boxes),
    odd.length ? h("p", { class: "small" }, "Also in this rule: ", ...odd.map((v) => h("code", {}, v + " "))) : null);
}

async function firewallPage() {
  const d = await api("/api/firewall");
  // device names no Home Assistant device has (a misspelt rule silently stops nothing): checked after the page shows
  const unknownBox = h("div", {});
  api("/api/firewall/devices").then((c) => {
    if (c.error) { unknownBox.replaceChildren(h("p", { class: "quiet small" }, `Device names not checked: ${c.error}.`)); return; }
    if (!c.unknown.length) return;
    unknownBox.replaceChildren(h("div", { class: "card warn-box", role: "alert" },
      h("strong", {}, `Device names Home Assistant doesn't have (of its ${c.devices} devices)`),
      h("ul", {}, c.unknown.map((u) => h("li", {}, `Rule ${u.rule}${u.name ? ` (${u.name})` : ""}: "${u.device}" matches no device, so it stops nothing.`))),
      h("p", { class: "small" }, "Check the spelling against the device's name in Home Assistant.")));
  }).catch(() => {});
  const fw = JSON.parse(JSON.stringify(d.firewall || { enabled: false, rules: [] }));
  fw.rules = fw.rules || [];
  const isAdmin = allowed("tools");
  const rules = h("div", {});
  function draw() {
    rules.replaceChildren(...fw.rules.map((r, i) => {
      const name = input("text", { value: r.name || "", placeholder: "what it's for", oninput: (e) => { r.name = e.target.value; } });
      const msg = input("text", { value: r.message || "", placeholder: "empty: a line from phrases/router.yaml firewall_blocked", oninput: (e) => { r.message = e.target.value; } });
      const list = (k, label, hint) => h("div", {}, h("h3", {}, label), hint ? h("p", { class: "hint" }, hint) : null, chipList(r[k] || [], (v) => { r[k] = v; }));
      return h("section", { class: "card rule" },
        h("h3", {}, `Rule ${i + 1}`, h("span", {}, check(" on", r.enabled !== false, (e) => { r.enabled = e.target.checked; }), " ",
          h("button", { type: "button", onclick: () => { fw.rules.splice(i, 1); draw(); } }, "Remove"))),
        h("div", { class: "grid2" }, field("Name", name), field("Reply", msg)),
        h("div", { class: "grid2" },
          list("people", "Who", `The voice ID's own names, exactly (${d.people.join(", ") || "none saved yet: Pull on Name Sparkle"}), unknown, or anyone.`),
          list("assistants", "Only on these voice devices", "Empty: on all of them."),
          list("voice_devices", "May not use these voice devices at all", d.assistants.join(", ")),
          list("devices", "May not work these devices, by name", "Like garage door: in what they say, and in what the Off-Platform model tries to do."),
          list("commands", "May not say", "Whole words, like open the garage."),
          list("topics", "May not use these topics", `${d.topics.join(", ")}, or topic.action (chores.add).`)),
        h("div", { class: "grid2" },
          picks(r, "domains", "May not use these kinds of devices", (d.words || {}).kinds || [], "Every action on them, however it was asked."),
          picks(r, "intents", "May not do these to a device", (d.words || {}).actions || [], "Only these actions: unlock but not lock, say.")),
        check(" Nothing they say goes Off-Platform", r.gemini, (e) => { r.gemini = e.target.checked; }));
    }));
  }
  draw();
  const enabled = check(" Firewall on", fw.enabled, (e) => { fw.enabled = e.target.checked; });
  const sure = input("number", { min: "0", max: "1", step: "0.01", value: fw.sure_score ?? 0.8, oninput: (e) => { fw.sure_score = Number(e.target.value); } });
  const down = select([{ value: "unknown", label: "treat every voice as unknown" }, { value: "allow", label: "block nobody" }], fw.when_oread_down || "unknown",
    { onchange: (e) => { fw.when_oread_down = e.target.value; } });
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    await api("/api/firewall", { method: "PUT", body: { firewall: fw } });
    note.replaceChildren(okNote("Saved; in use now."));
  }));
  // try the rules being edited (before saving)
  const say = input("text", { placeholder: "open the garage door" });
  const who = input("text", { placeholder: "a voice's name, empty for unknown" });
  const score = input("number", { min: "0", max: "1", step: "0.01", value: "0.9" });
  const result = h("p", {});
  const tbtn = h("button", { type: "button" }, "Try");
  tbtn.addEventListener("click", busy(tbtn, result, async () => {
    const speaker = who.value.trim() ? { speaker: who.value.trim(), label: "known", score: Number(score.value) } : { label: "unknown", score: 0.2 };
    const r = await api("/api/try", { method: "POST", body: { say: say.value, speaker: speaker, firewall: Object.assign({}, fw, { enabled: true }) } });
    result.replaceChildren(r.path === "blocked" ? h("span", { class: "pill-bad" }, `Blocked: ${r.blocked}. Reply: ${r.speech}`) : h("span", { class: "pill-ok" }, `Allowed (path ${r.path}).`));
  }));
  return [h("h1", {}, "Firewall"), unknownBox,
    d.oread_on ? null : h("p", { class: "warn" }, ["Oread is off, so the router can't tell voices apart: every voice counts as unknown. Rules for anyone or unknown apply now; rules naming a person wait until Oread is on: ", h("a", { href: "#/integrations?open=oread" }, "switch it on in Integrations"), " (the firewall has its own On switch, on this page)."]),
    h("p", { class: "quiet" }, "Who may use what, by voice. A rule that matches stops the request and its message is said. Kinds of devices and actions also cover the front end's own device commands and the Off-Platform model's, however they were understood, once the front end asks the router first (Veil Guard Service, for Home Assistant)."),
    h("section", { class: "card panel" }, enabled, h("div", { class: "grid2" },
      field("A voice counts as a person when the voice ID is this sure", sure, "The firewall's own number: it can be stricter than Name Sparkle's."),
      field("While the voice ID can't be asked", down))),
    rules, h("button", { type: "button", onclick: () => { fw.rules.push({ name: "", enabled: true, people: ["unknown"], assistants: [], voice_devices: [], devices: [], commands: [], topics: [], intents: [], domains: [], gemini: false, message: "" }); draw(); } }, "Add a rule"),
    box, h("div", { class: "row-actions" }, save, note),
    h("section", { class: "card panel" }, h("h2", {}, "Try the rules above"), h("div", { class: "grid2" }, field("Say", say), field("Who spoke", who), field("How sure the voice ID is", score)), tbtn, result)];
}

