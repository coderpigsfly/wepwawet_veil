// addons/roman_numerals/page.js - its page: try a sentence and hear how it will be said.
// An add-on's page is a module the shell loads: render(api, h) returns what the page shows.
export async function render(api, h) {
  const box = h("input", { type: "text", "aria-label": "a sentence to try", value: "Pope Leo XIV met Henry VIII after World War II." });
  const out = h("p", { class: "quiet", role: "status", "aria-live": "polite", "aria-label": "how she says it" });
  const go = async () => { out.textContent = (await api("/api/addons/roman_numerals/try", { method: "POST", body: { text: box.value } })).said; };
  const btn = h("button", { type: "button", class: "primary" }, "Say it");
  btn.addEventListener("click", go);
  return [h("h1", {}, "Roman numerals"),
    h("p", { class: "quiet" }, "A Roman numeral after a name is said as words, so her voice reads it right: John V is John the Fifth, World War II is World War Two."),
    h("div", { class: "card" }, h("label", {}, "A sentence", box), btn, out)];
}
