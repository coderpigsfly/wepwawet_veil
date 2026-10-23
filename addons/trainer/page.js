// addons/trainer/page.js - its page: trainer mode, switched on or off for each person in the People grid.
export async function render(api, h) {
  const list = h("div", { class: "card" });
  const note = h("p", { class: "quiet", role: "status", "aria-live": "polite" });
  const draw = async () => {
    const d = await api("/api/addons/trainer");
    list.replaceChildren(...d.people.map((p) => {
      const box = h("input", { type: "checkbox", checked: p.on, "aria-label": "Trainer mode for " + p.name });
      box.addEventListener("change", async () => {
        try {
          const r = await api("/api/addons/trainer", { method: "POST", body: { person: p.name, on: box.checked } });
          note.textContent = "Trainer mode is " + (r.on ? "on" : "off") + " for " + p.name + " from their next request.";
        } catch (e) { box.checked = !box.checked; note.textContent = e.message; }
      });
      return h("label", { class: "check" }, box, " " + p.name);
    }));
    topics.textContent = "It trains: " + (d.topics.join(", ") || "nothing yet") + ".";
  };
  const topics = h("p", { class: "quiet" });
  await draw();
  return [h("h1", {}, "Trainer"),
    h("p", { class: "quiet" }, "Switched on for a person, it walks their requests that weren't said in full through the house's routine " +
      "(a chore's name, date, time and who it's for), announcing trainer mode first. A request said in full: it stays silent. " +
      "Only when the voice ID is sure it's them. By voice: \"Trainer mode\", \"Turn on trainer mode for <name>\", \"Turn off my trainer mode\"."),
    topics, list, note];
}
