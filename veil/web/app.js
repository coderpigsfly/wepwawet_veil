// Wepwawet Veil's pages. Plain JavaScript, ECMAScript 2020 only: no framework, no build step,
// nothing loaded from the internet (the same rules as Oread's pages).
// Every page talks to the admin API under /api/ (veil/web.py); the hash picks the page.

const app = document.getElementById("app");
let session = null; // {user, can, version, restart_needed}

// ---------- small helpers ----------

// Build an element. Text always goes in as text, never as HTML.
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key === "value") el.value = value;
    else if (key === "checked") el.checked = Boolean(value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

async function api(path, options) {
  const opts = options || {};
  const init = { method: opts.method || "GET", credentials: "same-origin",
                 headers: { "X-Requested-With": "veil" } };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, init);
  let data = null;
  const text = await response.text();
  try { data = JSON.parse(text); } catch (e) { data = text; }
  if (!response.ok) {
    const error = new Error(messageOf(data) || `Wepwawet Veil answered ${response.status}`);
    error.status = response.status;
    if (response.status === 401 && path !== "/api/session") { session = null; route(); }
    throw error;
  }
  if (init.method !== "GET" && path !== "/api/session" && path !== "/api/restart") refreshRestartBar();
  return data;
}

// After any change: if it waits for a restart, show the Restart bar now (no page reload needed).
async function refreshRestartBar() {
  try {
    session = await api("/api/session");
  } catch (e) { return; }
  const slot = document.getElementById("restart-slot");
  if (!slot) return;
  const what = session.restart_needed || [];
  slot.replaceChildren(...(what.length && allowed("settings") ? [restartBar(what)] : []));
}

function messageOf(data) {
  if (!data || typeof data !== "object" || data.detail === undefined) return "";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  return "";
}

let fieldCount = 0;
function uid(prefix) { fieldCount += 1; return `${prefix || "f"}-${fieldCount}`; }

function field(label, input, hint) {
  if (!input.id) input.id = uid("in");
  if (hint) input.setAttribute("aria-describedby", input.id + "-hint");
  return h("div", { class: "field" },
    h("label", { for: input.id }, label),
    input,
    hint ? h("span", { class: "hint", id: input.id + "-hint" }, hint) : null);
}

function input(type, extra) { return h("input", Object.assign({ type: type, id: uid("in") }, extra || {})); }

function select(options, value, extra) {
  const el = h("select", Object.assign({ id: uid("sel") }, extra || {}));
  for (const o of options) {
    const v = typeof o === "object" ? o.value : o;
    const label = typeof o === "object" ? o.label : o;
    el.append(h("option", { value: v, selected: String(v) === String(value) }, label));
  }
  return el;
}

function check(label, checked, onchange) {
  const box = h("input", { type: "checkbox", checked: checked, onchange: onchange });
  return h("label", { class: "check" }, box, label);
}

function brand() {
  return h("div", { class: "brand" }, h("img", { src: "icon.svg", alt: "" }), h("span", {}, "Wepwawet Veil"));
}

function errorBox() { return h("p", { class: "error", role: "alert" }); }

function when(t) {
  if (!t) return "";
  const d = new Date(typeof t === "number" ? t * 1000 : t);
  const today = new Date();
  const same = d.toDateString() === today.toDateString();
  return same ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })
              : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// a busy button: runs fn, shows errors in box, never twice at once
function busy(button, box, fn) {
  return async (event) => {
    if (event) event.preventDefault();
    if (button.disabled) return;
    button.disabled = true;
    if (box) box.textContent = "";
    try { await fn(); } catch (e) { if (box) box.textContent = e.message; else alert(e.message); }
    finally { button.disabled = false; }
  };
}

function okNote(text) {
  const p = h("p", { class: "ok", role: "status" }, text);
  setTimeout(() => p.remove(), 4000);
  return p;
}

// Say a line out loud in this browser (to hear what an Off-Platform model said). Local speech only.
function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function hearButton(text, compact) {
  if (!("speechSynthesis" in window) || !text) return null;
  return h("button", { class: "hear" + (compact ? " compact" : ""), type: "button", title: "Hear it (spoken by this browser)", "aria-label": "Hear it",
    onclick: () => { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } },
    compact ? "▶" : "▶ Hear it");
}

// An editable list of words, shown as chips.
// check (optional): a word -> an error message, or null when it may be added.
function chipList(words, onChange, placeholder, check) {
  const list = (words || []).slice();
  const wrap = h("div", {});
  const chips = h("div", { class: "chips" });
  const box = input("text", { placeholder: placeholder || "add a word or phrase" });
  const bad = h("span", { class: "error small", role: "alert" });
  function draw() {
    chips.replaceChildren(...list.map((w, i) => h("span", { class: "chip" }, w,
      h("button", { type: "button", "aria-label": `remove ${w}`, onclick: () => { list.splice(i, 1); draw(); onChange(list.slice()); } }, "×"))));
    if (!list.length) chips.append(h("span", { class: "quiet small" }, "(none)"));
  }
  function add() {
    const refused = [];
    for (const part of box.value.split(",")) {
      const w = part.trim();
      const why = w && check ? check(w) : null;
      if (why) refused.push(w);
      else if (w && !list.includes(w)) list.push(w);
    }
    box.value = refused.join(", ");                 // what wasn't taken stays in the box, with why
    bad.textContent = refused.length ? check(refused[0]) : "";
    draw();
    onChange(list.slice());
  }
  box.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  box.addEventListener("blur", () => { if (box.value.trim() && !bad.textContent) add(); });   // typed but not added: added anyway
  wrap.append(chips, h("div", { class: "chip-add" }, box, h("button", { type: "button", onclick: add }, "Add")), bad);
  draw();
  return wrap;
}

function pathTag(row) {
  const path = row.path || "?";
  const engine = row.engine || "";
  let cls = "pathtag";
  let label = `path ${path}`;
  if (row.blocked || path === "blocked") { cls += " blocked"; label = "blocked"; }
  else if (engine === "gemini") { cls += " gemini"; label = row.sent_to || "Off-Platform"; }   // who did it, from the log
  else if (engine === "bank") { cls += " home"; label = "home: the bank"; }
  else if (engine === "home_assistant") { cls += " home"; label = "Home Assistant itself"; }
  else if (engine) { cls += " home"; label = engine === "router" ? `home (path ${path})` : `home: ${engine}`; }
  return h("span", { class: cls }, label);
}

// ---------- the frame ----------

const PAGES = [
  ["Watch", [["transactions", "Transactions"], ["bank", "Off-Platform Bank"], ["misses", "Misses"], ["savings", "Savings"]]],
  ["Teach", [["try", "Try it"], ["topics", "Seed Topics"], ["fleas", "Brain fleas"], ["words", "Words understood"], ["tools", "Tools"]]],
  ["Personality", [["flair", "Persona Flair"], ["sparkle", "Name Sparkle"]]],
  ["System", [["overview", "Overview"], ["stats", "Stats"]]],
  ["Connect and protect", [["integrations", "Integrations"], ["people", "People"], ["firewall", "Firewall"], ["security", "Security"], ["settings", "Settings"]]],
  ["You", [["account", "Account"], ["guide", "Guides"]]],
];
const NEEDS = { candidates: "flair", users: "security", audit: "security", savings: "overview", stats: "overview", sparkle: "people" };

// A small line icon for each page (24 x 24, drawn with the text colour; nothing from the internet).
const ICONS = {
  transactions: ["M4 7h13", "M14 4l3 3-3 3", "M20 17H7", "M10 14l-3 3 3 3"],
  bank: ["M3 10l9-6 9 6", "M5 10v8", "M9.5 10v8", "M14.5 10v8", "M19 10v8", "M3 21h18"],
  savings: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18", "M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .9 3 2.1-1.3 1.9-3 1.9c-1.4 0-2.6-.6-3-1.6", "M12 6.5v1.5", "M12 16v1.5"],
  try: ["M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3", "M5 11a7 7 0 0 0 14 0", "M12 18v3"],
  topics: ["M12 21v-9", "M12 12c0-4 3-7 8-7 0 5-3 7-8 7", "M12 14c0-3-2.5-5.5-7-5.5 0 4 2.5 5.5 7 5.5"],
  tools: ["M14.7 6.3a4 4 0 0 0-5.4 5.4L3.5 17.5a1.4 1.4 0 0 0 2 2l5.8-5.8a4 4 0 0 0 5.4-5.4l-2.5 2.5-2-2z"],
  misses: ["M6 8.5a6 6 0 0 1 12 0c0 3.5-3 4.5-3 7a3 3 0 0 1-5.5 1.5", "M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-1.5 2-1.5 3.5", "M3 3l18 18"],
  flair: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"],
  sparkle: ["M9 4l1.4 4.1L14.5 9.5l-4.1 1.4L9 15l-1.4-4.1L3.5 9.5l4.1-1.4z", "M17 3v4", "M15 5h4", "M17.5 14l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9z"],
  people: ["M9 11a3.5 3.5 0 1 0 0-7a3.5 3.5 0 1 0 0 7", "M2.5 20a6.5 6.5 0 0 1 13 0", "M16 4.3a3.5 3.5 0 0 1 0 6.4", "M18 14a6.5 6.5 0 0 1 3.5 6"],
  overview: ["M4 4h7v7H4z", "M13 4h7v4h-7z", "M13 10h7v10h-7z", "M4 13h7v7H4z"],
  stats: ["M4 20V10", "M10 20V4", "M16 20v-7", "M22 20H2"],
  words: ["M4 6h10", "M4 10h16", "M4 14h12", "M4 18h7", "M17 15l2 2 3-4"],
  fleas: ["M12 4a3 3 0 1 0 0 6a3 3 0 1 0 0-6", "M8 14a4 4 0 0 0 8 0v-1a4 4 0 0 0-8 0z", "M8 13l-4-2", "M16 13l4-2", "M8.5 16.5L5 19", "M15.5 16.5L19 19", "M10.5 4.5L9 2", "M13.5 4.5L15 2"],
  integrations: ["M9 2v5", "M15 2v5", "M6 7h12v4a6 6 0 0 1-12 0z", "M12 17v5"],
  firewall: ["M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z", "M9 12l2 2 4-4"],
  security: ["M5 11h14v10H5z", "M8 11V7a4 4 0 0 1 8 0v4", "M12 15v2"],
  settings: ["M4 6h9", "M17 6h3", "M15 4v4", "M4 12h3", "M11 12h9", "M9 10v4", "M4 18h11", "M19 18h1", "M17 16v4"],
  account: ["M12 12a4 4 0 1 0 0-8a4 4 0 1 0 0 8", "M4 21a8 8 0 0 1 16 0"],
  guide: ["M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z", "M4 21a2 2 0 0 1 2-2h13v2H6", "M8 7h7"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  hide: ["M15 6l-6 6 6 6"],
  alert: ["M12 3l9.5 17h-19z", "M12 10v4", "M12 17.5v.01"],
  check: ["M5 12.5l4.5 4.5L19 7"],
};

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICONS[name] || []) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function allowed(page) { return session && session.can && session.can.includes(NEEDS[page] || page); }

// The menu can be hidden on a wide screen; remembered in this browser only.
function menuHidden() { try { return localStorage.getItem("veil-menu") === "hidden"; } catch (e) { return false; } }
function setMenuHidden(hidden) {
  try { if (hidden) localStorage.setItem("veil-menu", "hidden"); else localStorage.removeItem("veil-menu"); } catch (e) { /* private window */ }
}

function frame(current, ...content) {
  const nav = h("nav", { class: "nav", "aria-label": "Pages" });
  for (const [group, pages] of PAGES) {
    const shown = pages.filter(([id]) => allowed(id));
    if (!shown.length) continue;
    const list = h("div", { class: "nav-group", role: "group", "aria-label": group }, h("div", { class: "group", "aria-hidden": "true" }, group));
    for (const [id, label] of shown) {
      list.append(h("a", { href: `#/${id}`, class: "with-icon", "aria-current": id === current ? "page" : null }, icon(id), h("span", {}, label)));
    }
    nav.append(list);
  }
  const box = h("div", { class: "frame" + (menuHidden() ? " menu-hidden" : "") });
  const hideBtn = h("button", { class: "menu-hide", type: "button", title: "Hide the menu", "aria-label": "Hide the menu",
    onclick: () => { box.classList.add("menu-hidden"); setMenuHidden(true); showBtn.focus(); } }, icon("hide"));
  const showBtn = h("button", { class: "menu-show", type: "button", title: "Show the menu", "aria-label": "Show the menu",
    onclick: () => { box.classList.remove("menu-hidden"); setMenuHidden(false); } }, icon("menu"), h("span", {}, "Menu"));
  const side = h("aside", { class: "side" }, h("div", { class: "side-head" }, brand(), hideBtn), nav,
    h("div", { class: "who" }, h("strong", {}, session.user.name), h("span", { class: "badge" }, session.user.role)));
  const toggle = h("button", { class: "menu-toggle", type: "button", "aria-expanded": "false",
    onclick: (e) => { const open = side.classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(open)); } }, icon("menu"), h("span", {}, "Menu"));
  const restart = h("div", { id: "restart-slot" },
    (session.restart_needed || []).length && allowed("settings") ? restartBar(session.restart_needed) : null);
  box.append(
    h("header", { class: "top" }, brand(), toggle),
    side,
    h("main", { class: WIDE_PAGES.has(current) ? "main wide" : "main", id: "main" }, showBtn, restart, ...content));
  return box;
}

// pages that are mostly tables and charts use the whole width (Oct 15); on the others only a box
// with a table in it does, and reading keeps a comfortable line length
const WIDE_PAGES = new Set(["stats", "transactions", "inbound", "outbound", "bank", "savings", "misses", "audit"]);

function restartBar(what) {
  const btn = h("button", { class: "primary", type: "button" }, "Restart now");
  btn.addEventListener("click", busy(btn, null, async () => {
    await api("/api/restart", { method: "POST" });
    btn.textContent = "Restarting…";
    setTimeout(() => location.reload(), 6000);
  }));
  return h("div", { class: "restart-bar", role: "status" },
    h("span", {}, `Saved changes wait for a restart: ${what.join("; ")}.`), btn);
}

// Descriptions behind a ? (Oct 15): a page's opening paragraph, and the note under a box's heading,
// go into a ? beside the heading (point at it, or click to pin it), so the page keeps its room for
// the things themselves. Only text: a paragraph with a link or a button stays where it is.
function tuckIntros(root) {
  const textOnly = (p) => p && p.matches && p.matches("p.quiet, p.hint, p.group-note") && !p.querySelector("a, button, input, select, textarea");
  for (const h1 of root.querySelectorAll("main h1, .content h1, h1")) {
    let p = h1.nextElementSibling;
    while (p && (p.classList.contains("tabs") || p.classList.contains("page-tabs"))) p = p.nextElementSibling;
    if (textOnly(p) && !h1.querySelector(".info-wrap")) { h1.append(" ", infoTip(p.textContent.trim())); p.remove(); }
  }
  for (const head of root.querySelectorAll("section > h2, details > summary > h2, section > h3")) {
    const box = head.closest("section, details");
    const after = head.parentElement.tagName === "SUMMARY" ? head.parentElement.nextElementSibling : head.nextElementSibling;
    if (box && textOnly(after) && !head.querySelector(".info-wrap")) { head.append(" ", infoTip(after.textContent.trim())); after.remove(); }
  }
}

// ---------- remembered in this browser: folded boxes and column widths ----------

function remembered(key) { try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { return {}; } }
function remember(key, all) { try { localStorage.setItem(key, JSON.stringify(all)); } catch (e) { /* private window */ } }
function pageNow() { return (location.hash.replace(/^#\/?/, "").split("?")[0]) || "overview"; }

// A box that folds by its heading (Oct 15): open unless open is false, and the browser remembers
// how each was left, per page (id names the box; it stays put when its title has a number in it).
function foldBox(id, title, open, ...children) {
  const key = `${pageNow()}:${id}`;
  const was = remembered("veil-folds")[key];
  const box = h("details", { class: "card panel fold", open: was === undefined ? open !== false : was },
    h("summary", {}, h("h2", {}, title)), ...children);
  box.addEventListener("toggle", () => { const all = remembered("veil-folds"); all[key] = box.open; remember("veil-folds", all); });
  return box;
}

// Every table with headings, on every page (Oct 15): drag a heading's right edge to make its column
// wider or narrower, double-click the edge to put the table back. Widths are remembered in this
// browser per page and table (its headings name it). A table wider than its box also gets a
// scrollbar above it, so a long table scrolls sideways without going to its bottom.
const EDGE = 6;
function tableKey(table) {
  const row = table.tHead.rows[table.tHead.rows.length - 1];
  return `${pageNow()}|${[...row.cells].map((c) => c.textContent.replace(/[▲▼]/g, "").trim()).join("|")}`;
}
function setWidths(table, widths) {
  let cols = table.querySelector(":scope > colgroup");
  if (!cols) { cols = document.createElement("colgroup"); table.insertBefore(cols, table.firstChild); }
  cols.replaceChildren(...widths.map((w) => { const c = document.createElement("col"); c.style.width = `${w}px`; return c; }));  // set in script: the page's rules allow no style attributes
  table.style.width = `${widths.reduce((a, b) => a + b, 0)}px`;
  table.classList.add("resized");
}
function resizable(table) {
  table.dataset.kit = "1";
  const cells = () => [...table.tHead.rows[table.tHead.rows.length - 1].cells];
  if (cells().some((c) => c.colSpan > 1)) return;
  const saved = remembered("veil-cols")[tableKey(table)];
  if (saved && saved.length === cells().length) setWidths(table, saved);
  const edgeAt = (x) => cells().findIndex((c) => Math.abs(c.getBoundingClientRect().right - x) <= EDGE);
  let drag = null, dragged = false;
  table.tHead.addEventListener("pointermove", (e) => {
    if (drag) {
      const w = drag.widths.slice();
      w[drag.i] = Math.max(32, Math.round(drag.start + e.clientX - drag.x));
      setWidths(table, w);
      dragged = true;
      return;
    }
    table.classList.toggle("at-edge", edgeAt(e.clientX) >= 0);
  });
  table.tHead.addEventListener("pointerleave", () => { if (!drag) table.classList.remove("at-edge"); });
  table.tHead.addEventListener("pointerdown", (e) => {
    const i = edgeAt(e.clientX);
    if (i < 0 || e.button !== 0) return;
    e.preventDefault();
    const widths = cells().map((c) => Math.round(c.getBoundingClientRect().width));
    setWidths(table, widths);
    drag = { i, x: e.clientX, start: widths[i], widths };
    dragged = false;
    table.tHead.setPointerCapture(e.pointerId);
  });
  const done = () => {
    if (!drag) return;
    drag = null;
    const all = remembered("veil-cols");
    all[tableKey(table)] = [...table.querySelectorAll(":scope > colgroup > col")].map((c) => parseInt(c.style.width, 10));
    remember("veil-cols", all);
  };
  table.tHead.addEventListener("pointerup", done);
  table.tHead.addEventListener("pointercancel", done);
  // a drag that ends on a heading isn't a click on it (no sorting)
  table.tHead.addEventListener("click", (e) => { if (dragged) { e.stopPropagation(); e.preventDefault(); dragged = false; } }, true);
  table.tHead.addEventListener("dblclick", (e) => {
    if (edgeAt(e.clientX) < 0) return;
    const all = remembered("veil-cols"); delete all[tableKey(table)]; remember("veil-cols", all);
    const cols = table.querySelector(":scope > colgroup");
    if (cols) cols.remove();
    table.style.width = "";
    table.classList.remove("resized");
  });
}
function topScroll(wrap) {
  wrap.dataset.kit = "1";
  const inner = h("div", {});
  const bar = h("div", { class: "top-scroll", "aria-hidden": "true" }, inner);
  wrap.before(bar);
  bar.addEventListener("scroll", () => { if (wrap.scrollLeft !== bar.scrollLeft) wrap.scrollLeft = bar.scrollLeft; });
  wrap.addEventListener("scroll", () => { if (bar.scrollLeft !== wrap.scrollLeft) bar.scrollLeft = wrap.scrollLeft; });
  const fit = () => { inner.style.width = `${wrap.scrollWidth}px`; bar.hidden = wrap.scrollWidth <= wrap.clientWidth + 1; };
  const watch = new ResizeObserver(fit);
  watch.observe(wrap);
  if (wrap.firstElementChild) watch.observe(wrap.firstElementChild);
  fit();
}
// Every table sorts and folds, the same way everywhere (Oct 18, your rule). A table that sorts
// itself (its headings are sort buttons: Transactions, Misses, the bank) keeps its own; any
// other with plain rows sorts by a click on a heading (again to reverse), by the cell's numbers
// when it has them ("1.2s", "42"), else its words. Each table in a box can be folded away: its
// Fold button, remembered in this browser per page and table.
function cellKey(td) {
  const t = (td && (td.dataset.sort ?? td.textContent) || "").trim();
  const n = t.match(/^-?\d+(\.\d+)?/);
  return t === "" || t === "-" ? null : n ? parseFloat(n[0]) : t.toLowerCase();
}
function sortable(table) {
  const head = table.tHead.rows[table.tHead.rows.length - 1];
  const body = table.tBodies[0];
  if (!body || head.querySelector("button.sort") || [...head.cells].some((c) => c.colSpan > 1)) return;
  if ([...body.rows].some((r) => r.classList.contains("txn-more") || r.classList.contains("mh-band") || [...r.cells].some((c) => c.colSpan > 1))) return;
  let on = -1, desc = false;
  [...head.cells].forEach((th, i) => {
    if (!th.textContent.trim()) return;
    th.classList.add("sorts");
    th.setAttribute("aria-sort", "none");
    th.title = th.title || `Sort by ${th.textContent.trim().toLowerCase()}`;
    th.addEventListener("click", () => {
      desc = on === i ? !desc : false;
      on = i;
      const rows = [...body.rows];
      rows.sort((x, y) => {
        const a = cellKey(x.cells[i]), b = cellKey(y.cells[i]);
        if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;      // the empty ones last
        const r = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
        return desc ? -r : r;
      });
      body.replaceChildren(...rows);
      [...head.cells].forEach((c, j) => { if (c.classList.contains("sorts")) c.setAttribute("aria-sort", j === i ? (desc ? "descending" : "ascending") : "none"); });
    });
  });
}
function foldable(wrap) {
  const table = wrap.querySelector(":scope > table");
  if (!table || !table.tHead || !table.tHead.rows.length || wrap.closest(".txn-more")) return;
  const key = tableKey(table);
  const rows = () => [...(table.tBodies[0] || { rows: [] }).rows].filter((r) => !r.classList.contains("txn-more")).length;
  const b = h("button", { type: "button", class: "small quiet table-fold" });
  const bar = wrap.previousElementSibling && wrap.previousElementSibling.classList.contains("top-scroll") ? wrap.previousElementSibling : null;
  const set = (folded) => {
    wrap.hidden = folded;
    if (bar) bar.classList.toggle("folded", folded);
    b.textContent = folded ? `Show the table (${rows()} row${rows() === 1 ? "" : "s"})` : "Fold the table";
    b.setAttribute("aria-expanded", folded ? "false" : "true");
  };
  b.addEventListener("click", () => {
    const all = remembered("veil-table-folds");
    all[key] = !wrap.hidden;
    remember("veil-table-folds", all);
    set(all[key]);
  });
  (bar || wrap).before(h("div", { class: "table-fold-row" }, b));
  set(Boolean(remembered("veil-table-folds")[key]));
}
let tablesPending = false;
new MutationObserver(() => {
  if (tablesPending) return;
  tablesPending = true;
  requestAnimationFrame(() => {
    tablesPending = false;
    app.querySelectorAll("table:not([data-kit])").forEach((t) => { if (t.tHead && t.tHead.rows.length) { resizable(t); sortable(t); } else t.dataset.kit = "0"; });
    app.querySelectorAll(".table-wrap:not([data-kit])").forEach((w) => { topScroll(w); foldable(w); });
  });
}).observe(app, { childList: true, subtree: true });

let shown = 0;          // the newest page asked for: a slower page finishing later doesn't cover it
async function show(page) {
  const mine = ++shown;
  try {
    const content = await (PAGE_FNS[page] || PAGE_FNS.overview)();
    if (mine !== shown) return;
    app.replaceChildren(frame(page, ...[].concat(content)));
    tuckIntros(app);
    const first = app.querySelector("[autofocus]");
    if (first) first.focus();
  } catch (e) {
    if (e.status === 401 || mine !== shown) return;
    app.replaceChildren(frame(page, h("h1", {}, "Something went wrong"), h("p", { class: "error" }, e.message)));
  }
}

async function route() {
  if (!session) {
    try { session = await api("/api/session"); } catch (e) { session = null; }
    if (!session || !session.user) {
      const needs = session && session.needs_setup;
      if (session && session.password_min_length) passwordMin = session.password_min_length;
      session = null;
      return needs ? setupPage() : signInPage();
    }
  }
  const page = (location.hash.replace(/^#\/?/, "").split("?")[0]) || "overview";
  return show(allowed(page) ? page : "overview");
}

window.addEventListener("hashchange", route);

// ---------- setup and sign-in ----------

function doorCard(title, ...children) {
  return h("div", { class: "door" }, h("div", { class: "card" }, brand(), h("h1", {}, title), ...children));
}

// security.password_min_length, from the router (never written into the page)
let passwordMin = null;
function minPassword() { return (session && session.password_min_length) || passwordMin; }
function passwordRule() { const n = minPassword(); return n ? `At least ${n} characters` : "Long enough for the router's rule"; }

function setupPage() {
  const code = input("text", { autocomplete: "one-time-code", autofocus: true });
  const name = input("text", { autocomplete: "username" });
  const pw = input("password", { autocomplete: "new-password" });
  const box = errorBox();
  const btn = h("button", { class: "primary wide", type: "submit" }, "Create the first account");
  const f = h("form", {}, h("ol", { class: "steps" },
      h("li", {}, "On the server: docker compose logs house-router | grep \"setup code\" (or data/setup-code.txt)."),
      h("li", {}, "Enter that code, then the name and password for the first (super) account.")),
    field("Setup code", code), field("Username", name), field("Password", pw, `${passwordRule()}.`), box, btn);
  f.addEventListener("submit", busy(btn, box, async () => {
    await api("/api/setup", { method: "POST", body: { code: code.value, name: name.value, password: pw.value } });
    session = null;
    route();
  }));
  app.replaceChildren(doorCard("Set up Wepwawet Veil", f));
}

function signInPage() {
  const name = input("text", { autocomplete: "username", autofocus: true });
  const pw = input("password", { autocomplete: "current-password" });
  const box = errorBox();
  const btn = h("button", { class: "primary wide", type: "submit" }, "Sign in");
  const f = h("form", {}, field("Username", name), field("Password", pw), box, btn);
  f.addEventListener("submit", busy(btn, box, async () => {
    await api("/api/session", { method: "POST", body: { name: name.value, password: pw.value } });
    session = null;
    route();
  }));
  app.replaceChildren(doorCard("Sign in", h("p", { class: "quiet" }, "Private AI routing. Leaner context. Smarter handoff."), f));
}

// ---------- Watch: overview ----------

function stat(label, value, sub) {
  return h("div", { class: "card stat" }, h("span", { class: "stat-label" }, label),
    h("span", { class: "stat-value" }, value), sub ? h("span", { class: "stat-sub" }, sub) : null);
}

function onOff(v) { return h("span", { class: v ? "pill-ok" : "pill-off" }, v ? "on" : "off"); }

async function overviewPage() {
  const tz = tzMinutes();
  const stats = (days) => (allowed("stats") ? api(`/api/stats?days=${days}&tz=${tz}`).catch(() => null) : null);
  const [o, day, week] = await Promise.all([api("/api/overview"), stats(1), stats(7)]);
  if (week && week.apps) APP_LABELS = week.apps;
  const services = h("ul", { class: "rows" }, o.services.map((x) => h("li", {},
    h("span", {}, h("strong", {}, x.name), " ", h("span", { class: "quiet small" }, `${x.kind}, ${x.url || ""}`)),
    h("span", {}, x.topics.length ? `topics: ${x.topics.join(", ")} · ` : "", onOff(x.enabled)))));
  const st = week;
  const w = (day && !day.off && day.shares.where) || null;     // the same counting as the charts
  const total = w ? WHERE.reduce((a, [k]) => a + (w[k] || 0), 0) : 0;
  const tiles = w ? h("div", { class: "stats-row tiles" },
    tile("transactions", "t1", "Requests, last 24 hours", total, total ? `${shareOf(w.home + w.bank, total)} kept at home` : "nothing yet"),
    tile("overview", "t2", "Answered at home", w.home + w.bank, w.bank ? `${w.bank} from the Off-Platform Bank` : "no trip to the cloud"),
    tile("savings", "t3", "Went Off-Platform", w.off_platform, `to ${o.fallback_model}`),
    tile("firewall", "terr", "Blocked by the firewall", w.blocked, "last 24 hours")) : null;
  return [
    h("h1", {}, "Overview"),
    h("p", { class: "tagline" }, "Private AI routing. Leaner context. Smarter handoff."),
    tiles,
    st && !st.off ? h("section", { class: "card panel" }, h("h2", {}, "Where requests were answered, last 7 days"),
      whereDonut(st.shares.where), h("p", { class: "quiet small" }, "Day by day, by assistant, and how long each hop takes: ", h("a", { href: "#/stats" }, "Stats"), ". The routes a request can take are in the user's guide (Guides).")) : null,
    h("section", { class: "card panel" }, h("h2", {}, "Running now"),
      h("dl", { class: "kv" },
        h("dt", {}, "Answers at home from"), h("dd", {}, Object.entries(o.topics).map(([t, x]) => `${t} (${x})`).join(", ") || "no topics"),
        h("dt", {}, "Answers at home when sure"), h("dd", {}, `${Math.round(o.confidence_local * 100)}% or more`),
        h("dt", {}, "Everything else goes"), h("dd", {}, `Off-Platform: ${o.fallback_model}, through LiteLLM (${o.litellm})`),
        h("dt", {}, "Who spoke (Oread)"), h("dd", {}, onOff(o.oread.enabled), o.oread.enabled ? ` ${o.oread.source === "wyoming" ? "in the audio path" : o.oread.url} (${o.oread.source})` : ""),
        h("dt", {}, "Firewall"), h("dd", {}, onOff(o.firewall.enabled), ` ${o.firewall.rules} rules`),
        h("dt", {}, "Persona Flair"), h("dd", {}, onOff(o.flair.on), o.flair.on ? ` for ${o.flair.personalities.join(", ")}` : " (every rate is 0)"),
        h("dt", {}, "Sentence diagramming"), h("dd", {}, onOff(o.spacy)),
        h("dt", {}, "Shows as"), h("dd", {}, `${o.model_name} (in LiteLLM and Home Assistant)`))),
    h("section", { class: "card panel" }, h("h2", {}, "Services"), services),
  ];
}

// ---------- charts (Overview and Stats): drawn here as SVG, nothing from the internet ----------
// Colours: four fixed series slots (veil.css --series-1..4, checked for colour blindness, light and
// dark), always in the same order for the same thing. Every value is also in the legend, as text.

const WHERE = [["home", "At home", "the router or an app in the house"], ["bank", "Off-Platform Bank", "a kept answer, no trip"],
  ["off_platform", "Off-Platform", "a trip to the cloud model"], ["blocked", "Blocked", "stopped by the firewall"]];
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const c of children.flat()) if (c) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

// one tooltip for every chart: the value first, then what it is (text only)
let vizTip = null;
function tipOn(mark, value, what) {
  const showTip = (x, y) => {
    if (!vizTip) { vizTip = h("div", { class: "viz-tip", role: "tooltip" }); document.body.append(vizTip); }
    vizTip.replaceChildren(h("strong", {}, value), h("span", {}, what));
    vizTip.hidden = false;
    const r = vizTip.getBoundingClientRect();
    vizTip.style.left = `${Math.min(window.innerWidth - r.width - 8, Math.max(8, x + 12))}px`;
    vizTip.style.top = `${Math.max(8, y - r.height - 10)}px`;
  };
  const hideTip = () => { if (vizTip) vizTip.hidden = true; };
  mark.addEventListener("pointermove", (e) => showTip(e.clientX, e.clientY));
  mark.addEventListener("pointerleave", hideTip);
  mark.addEventListener("focus", () => { const b = mark.getBoundingClientRect(); showTip(b.left + b.width / 2, b.top); });
  mark.addEventListener("blur", hideTip);
  mark.setAttribute("tabindex", "0");
}

const shareOf = (n, t) => (t ? `${Math.round((100 * n) / t)}%` : "0%");

function legendRows(parts, total) {
  return h("ul", { class: "viz-legend" }, parts.map((p) => h("li", {},
    h("span", { class: `key s${p.slot}`, "aria-hidden": "true" }),
    h("span", { class: "what" }, p.label, h("span", { class: "quiet small" }, ` ${p.about}`)),
    h("span", { class: "num" }, String(p.value)), h("span", { class: "quiet num" }, shareOf(p.value, total)))));
}

// Where requests were answered: a ring of four parts, the total in the middle, the numbers beside it.
function whereDonut(where) {
  const parts = WHERE.map(([key, label, about], i) => ({ key, label, about, value: where[key] || 0, slot: i + 1 }));
  const total = parts.reduce((a, p) => a + p.value, 0);
  if (!total) return h("p", { class: "empty-state" }, "Nothing in this period yet.");
  const R = 54, C = 2 * Math.PI * R, GAP = 2;
  const shown = parts.filter((p) => p.value);
  const ring = svgEl("g", { transform: "rotate(-90 70 70)" });
  let at = 0;
  for (const p of shown) {
    const len = (p.value / total) * C;
    const draw = shown.length > 1 ? Math.max(len - GAP, 0.5) : len;
    const seg = svgEl("circle", { cx: 70, cy: 70, r: R, fill: "none", class: `seg s${p.slot}`, "stroke-width": 20,
      "stroke-dasharray": `${draw} ${C - draw}`, "stroke-dashoffset": -at, "aria-label": `${p.label}: ${p.value}` });
    tipOn(seg, `${p.value} (${shareOf(p.value, total)})`, p.label);
    ring.append(seg);
    at += len;
  }
  const svg = svgEl("svg", { viewBox: "0 0 140 140", class: "donut", role: "img",
    "aria-label": `Where requests were answered: ${parts.map((p) => `${p.label} ${p.value}`).join(", ")}` },
    svgEl("circle", { cx: 70, cy: 70, r: R, fill: "none", class: "track", "stroke-width": 20 }), ring,
    svgEl("text", { x: 70, y: 68, "text-anchor": "middle", class: "donut-total" }, String(total)),
    svgEl("text", { x: 70, y: 86, "text-anchor": "middle", class: "donut-sub" }, "requests"));
  return h("div", { class: "donut-wrap" }, svg, legendRows(parts, total));
}

function niceMax(v) {
  if (v <= 5) return 5;
  const step = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step;
  return 10 * step;
}

// Requests day by day: one column a day, stacked in the same four parts, the day's total on top.
function dayColumns(byDay) {
  if (!byDay.length) return h("p", { class: "empty-state" }, "Nothing in this period yet.");
  const W = 640, H = 220, L = 34, B = 26, T = 18;
  const totals = byDay.map((d) => WHERE.reduce((a, [k]) => a + (d[k] || 0), 0));
  const top = niceMax(Math.max(...totals));
  const band = (W - L - 4) / byDay.length;
  const bw = Math.min(24, band * 0.6);
  const y = (v) => H - B - (v / top) * (H - B - T);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "columns", role: "img",
    "aria-label": `Requests a day: ${byDay.map((d, i) => `${d.day} ${totals[i]}`).join(", ")}` });
  for (const t of [0, top / 2, top]) {
    svg.append(svgEl("line", { x1: L, x2: W - 4, y1: y(t), y2: y(t), class: "grid" }),
      svgEl("text", { x: L - 6, y: y(t) + 4, "text-anchor": "end", class: "tick" }, t >= 1000 ? `${t / 1000}K` : String(t)));
  }
  const every = Math.ceil(byDay.length / 8);              // at most about eight day labels
  byDay.forEach((d, i) => {
    const x = L + band * i + (band - bw) / 2;
    let base = 0;
    const segs = WHERE.map(([k, label], j) => ({ v: d[k] || 0, label, slot: j + 1 })).filter((p) => p.v);
    segs.forEach((p, j) => {
      const y0 = y(base), y1 = y(base + p.v);
      const last = j === segs.length - 1;
      const hgt = Math.max(y0 - y1 - (last ? 0 : 2), 1);  // a 2px gap between parts
      const r = last ? Math.min(4, hgt, bw / 2) : 0;        // rounded at the data end only
      const top1 = y1 + (last ? 0 : 2);
      const path = r
        ? `M${x},${y0} V${top1 + r} Q${x},${top1} ${x + r},${top1} H${x + bw - r} Q${x + bw},${top1} ${x + bw},${top1 + r} V${y0} Z`
        : `M${x},${y0} V${top1} H${x + bw} V${y0} Z`;
      const mark = svgEl("path", { d: path, class: `bar s${p.slot}` });
      tipOn(mark, String(p.v), `${p.label}, ${dayLabel(d.day)}`);
      svg.append(mark);
      base += p.v;
    });
    if (totals[i] && byDay.length <= 14) svg.append(svgEl("text", { x: x + bw / 2, y: y(totals[i]) - 5, "text-anchor": "middle", class: "cap" }, String(totals[i])));
    if (i % every === 0 || i === byDay.length - 1) svg.append(svgEl("text", { x: x + bw / 2, y: H - 8, "text-anchor": "middle", class: "tick" }, dayLabel(d.day)));
  });
  svg.append(svgEl("line", { x1: L, x2: W - 4, y1: y(0), y2: y(0), class: "axis" }));
  const sums = WHERE.map(([k, label, about], i) => ({ label, about, slot: i + 1, value: byDay.reduce((a, d) => a + (d[k] || 0), 0) }));
  return h("div", {}, svg, legendRows(sums, sums.reduce((a, p) => a + p.value, 0)));
}

function dayLabel(day) {
  const [yy, mm, dd] = day.split("-").map(Number);
  return new Date(yy, mm - 1, dd).toLocaleDateString([], { month: "short", day: "numeric" });
}

// Requests by assistant (or any one-series list): bars, the number at the tip.
function rankBars(items, what) {
  if (!items.length) return h("p", { class: "empty-state" }, "Nothing in this period yet.");
  const most = Math.max(...items.map(([, n]) => n));
  return h("ul", { class: "rank-bars" }, items.map(([name, n]) => {
    const bar = h("span", { class: "rank-fill" });
    bar.style.width = `${Math.max(2, (100 * n) / most)}%`;
    const li = h("li", {}, h("span", { class: "rank-name" }, name),
      h("span", { class: "rank-track" }, bar, h("span", { class: "rank-num" }, String(n))));
    tipOn(bar, String(n), `${what}: ${name}`);
    return li;
  }));
}

// A number with a coloured round mark (tier 1, 2, 3 of the colour scheme, or the error colour).
function tile(iconName, tone, label, value, sub) {
  return h("div", { class: "card stat tile" },
    h("span", { class: `tile-mark ${tone}`, "aria-hidden": "true" }, icon(iconName)),
    h("span", { class: "tile-text" }, h("span", { class: "stat-label" }, label),
      h("span", { class: "stat-value" }, String(value)), sub ? h("span", { class: "stat-sub" }, sub) : null));
}

function tzMinutes() { return -new Date().getTimezoneOffset(); }

// ---------- Watch: stats (counts, and Time Routes) ----------

const HOP_LABELS = [
  ["t_speech", "Speaking", "from the first sound to the end of the speech (the person, not software)"],
  ["t_stt", "Oread: speech to text", "from the end of the speech to Oread's words"],
  ["stt_per_s", "Oread per second of speech", "Oread's time for each second the person spoke: compare this across days (the time itself grows with how long they talked)"],
  ["t_relay", "The router's hand-off to Oread and back", "the router's own time passing the end of the speech to Oread and Oread's words back (its part of the Oread hop)"],
  ["t_ha_in", "Home Assistant and LiteLLM, in", "from Oread's words to the request reaching the router"],
  ["t_decide", "The router deciding", "from the request arriving to handing it on"],
  ["t_litellm", "LiteLLM itself", "LiteLLM's own time inside the Off-Platform hop, as LiteLLM reports it; the rest of that hop is the model"],
  ["t_engine", "The app or Off-Platform", "the answer's own time (an app at home, or LiteLLM and the model)"],
  ["ms", "The router, in all", "from the request arriving to the answer leaving the router"],
  ["t_back", "Back to Home Assistant", "from the answer leaving the router to Home Assistant done with it (LiteLLM and Home Assistant on the way back), from Home Assistant's own record of the run"],
  ["cpu_ms", "Router CPU", "CPU time the router itself used for the request (not the app's or the model's)"],
];

let APP_LABELS = {};       // each app's title, and whether its data comes from outside (/api/stats apps)

function routeName(route) {
  if (route === "off_platform") return "Off-Platform";
  if (route === "bank") return "Off-Platform Bank";
  if (route === "home_assistant") return "Home Assistant itself";
  if (route === "router") return "The router itself";
  if (route === "musings") return "Wepwawet Musings";      // the router's own small things: brain fleas
  if (route.startsWith("app:")) {
    const a = APP_LABELS[route.slice(4)];
    if (a) return `At home${a.outside ? ", outside data" : ""}: ${a.title}`;
    return `At home: ${route.slice(4).replace(/_/g, " ")}`;
  }
  return route;
}

function msText(x) {
  if (x === null || x === undefined) return "-";
  return x < 1000 ? `${Math.round(x)} ms` : `${(x / 1000).toFixed(1)} s`;
}

// On a phone a wide table reads row by row: each cell carries its column's heading (veil.css: table.stack).
function stack(wrap) {
  const table = wrap.querySelector("table") || wrap;
  const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent);
  table.classList.add("stack");
  for (const tr of table.querySelectorAll("tbody tr")) {
    [...tr.children].forEach((cell, i) => { if (heads[i]) cell.setAttribute("data-label", heads[i]); });
  }
  return wrap;
}

function hashParam(name) { return new URLSearchParams(location.hash.split("?")[1] || "").get(name); }

// One route's typical time a day as small columns (one colour: it's one thing over time), the
// last day marked; point at a day for its time.
function dayBars(values, days) {
  const W = 150, H = 34, n = values.length || 1, band = W / n, bw = Math.max(1, Math.min(6, band - 1));
  const top = Math.max(...values.filter((v) => v !== null), 1);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "daybars", role: "img",
    "aria-label": `Typical time a day: ${values.map((v, i) => `${days[i]} ${v === null ? "none" : msText(v)}`).filter((x) => !x.endsWith("none")).join(", ") || "no requests"}` });
  svg.append(svgEl("line", { x1: 0, x2: W, y1: H - 0.5, y2: H - 0.5, class: "axis" }));
  values.forEach((v, i) => {
    if (v === null) return;
    const hgt = Math.max(2, (v / top) * (H - 4));
    const mark = svgEl("rect", { x: i * band + (band - bw) / 2, y: H - 1 - hgt, width: bw, height: hgt, rx: 1,
      class: i === n - 1 ? "bar today" : "bar" });
    tipOn(mark, msText(v), `typical, ${dayLabel(days[i])}`);
    svg.append(mark);
  });
  return svg;
}

// Which leg was slow? Each route's legs today against usual, a verdict, and the slow requests
// with the internet check they carry.
const LEG_LABELS = [
  ["own_ms", "The router's own work", "its time less the outside hop (deciding, and the answer on its way back)"],
  ["cpu_ms", "Router CPU", "CPU time the router used for the request"],
  ["load", "The machine", "how busy the whole machine was: the last minute's load over its cores (100% = every core busy)"],
  ["t_engine", "Outside hop", "the app, or LiteLLM and the model"],
];

function farEnd(route) { return route === "off_platform" ? "LiteLLM or the model" : "the app itself"; }

function legValue(k, v) { return v === null || v === undefined ? "-" : k === "load" ? `${Math.round(v)}%` : msText(v); }

function legWord(x) {
  if (!x || !x.today) return "not measured today";
  if (x.times === undefined) return "nothing usual to compare yet";
  return x.slow ? `${x.times}x slower` : "normal";
}

function legVerdict(r, net, checking) {
  const L = r.legs, slow = (k) => L[k] && L[k].slow;
  const parts = [["own_ms", "router"], ["load", "machine"], ["t_engine", "outside hop"]]      // legs never measured are left out
    .filter(([k]) => L[k] && (L[k].today || L[k].usual)).map(([k, name]) => `${name} ${legWord(L[k])}`);
  const checked = (checking || []).includes(r.route) && net.today;
  if (checked) parts.push(`internet ${net.times === undefined ? "checked, nothing usual yet" : net.slow ? `${net.times}x slower` : "normal"} (${msText(net.today.median)}${net.usual ? `, usual ${msText(net.usual.median)}` : ""})`);
  let cause = "";
  if (slow("t_engine")) cause = checked && net.slow ? "the internet" : checked && net.times !== undefined ? farEnd(r.route) : `${farEnd(r.route)}, or the internet (not checked on this route)`;
  else if (slow("own_ms")) cause = slow("load") ? "the machine was busy" : "the router's own work";
  const anySlow = Object.values(L).some((x) => x.slow), netSlow = checked && net.slow;
  const said = parts.join(", ");
  return { bad: anySlow || netSlow,
    text: `${routeName(r.route)}: ${anySlow ? "slower today" : netSlow ? "as usual, but the internet is slower" : "as usual"}. ${said.charAt(0).toUpperCase()}${said.slice(1)}${cause ? `: ${cause}.` : "."}` };
}

function slowLine(x) {
  if (x.net_ms === null || x.net_ms === undefined) {
    return x.net_method === "not permitted" ? "Slow. Internet not checked: the servers aren't in security: outbound_allowed."
      : "Slow. Internet didn't answer the check.";
  }
  const when_ = x.net_after < 0 ? ` (the check from ${Math.round(-x.net_after / 60) || 1} min before)` : "";
  if (x.net_usual === null) return `Slow. Internet ${msText(x.net_ms)} by ${x.net_method}, nothing usual to compare yet${when_}.`;
  return x.net_slow
    ? `Slow. Internet ${(x.net_ms / x.net_usual).toFixed(1)}x slower than usual (${msText(x.net_ms)}, usual ${msText(x.net_usual)})${when_}.`
    : `Slow. Internet normal (${msText(x.net_ms)}, usual ${msText(x.net_usual)}): ${farEnd(x.route)} was slow${when_}.`;
}

function legsCard(L) {
  const net = L.internet || {};
  const today = L.routes.filter((r) => r.today);
  const cell = (k, x) => h("td", { class: "num", title: x && x.usual ? `usual ${legValue(k, x.usual.median)} over ${x.usual.n}` : "nothing usual yet" },
    h("span", {}, legValue(k, x && x.today && x.today.median), h("span", { class: "quiet small" }, x && x.usual ? ` (usual ${legValue(k, x.usual.median)})` : "")),
    x && x.slow ? h("span", { class: "flag warn" }, icon("alert"), `${x.times}x`) : null);
  return h("div", {},
    today.length ? today.map((r) => {
      const v = legVerdict(r, net, L.checking);
      return h("p", { class: v.bad ? "status-line warn" : "status-line ok-line", role: "status" }, icon(v.bad ? "alert" : "check"), v.text);
    }) : h("p", { class: "empty-state" }, "No requests today yet."),
    today.length ? stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix legs" },
      h("thead", {}, h("tr", {}, h("th", {}, "Route"), h("th", { class: "num" }, "Today (requests)"),
        LEG_LABELS.map(([, label, about]) => h("th", { class: "num", title: about }, label)))),
      h("tbody", {}, today.map((r) => h("tr", {}, h("th", { scope: "row" }, routeName(r.route)),
        h("td", { class: "num" }, `${r.today} (usual ${r.usual})`), LEG_LABELS.map(([k]) => cell(k, r.legs[k])))))))) : null,
    h("p", { class: "small" }, net.today || net.usual
      ? `Internet: ${net.today ? `${msText(net.today.median)} typical today` : "no check today"}${net.usual ? `, usual ${msText(net.usual.median)}` : ""} (${net.checks} checks by ${net.method}).`
      : "Internet: no checks yet."),
    h("h3", {}, "Slow requests and the internet"),
    L.slow_requests.length ? stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix slow-requests" },
      h("thead", {}, h("tr", {}, h("th", {}, "When"), h("th", {}, "Heard"), h("th", {}, "Route"), h("th", { class: "num" }, "Outside hop (typical)"), h("th", {}, "The internet"))),
      h("tbody", {}, L.slow_requests.map((x) => h("tr", {}, h("td", {}, when(x.time)), h("td", {}, x.heard || ""), h("td", {}, routeName(x.route)),
        h("td", { class: "num" }, `${msText(x.t_engine)} (${msText(x.typical)})`), h("td", {}, slowLine(x))))))))
      : h("p", { class: "empty-state" }, "No slow request with an internet check yet."),
    h("p", { class: "quiet small" }, `Today against usual: every day the log holds before today${L.first ? ` (since ${when(L.first)})` : ""}. A leg is flagged at ${L.slower} times usual or more; the internet at ${L.net_slower} times. ` +
      (L.checking ? `The internet check: after a request on ${L.checking.map(routeName).join(", ")}, at most once every ${L.cooldown_minutes} minutes, the fastest reply from ${L.servers.join(", ")} (stats: internet_check in settings.yaml).`
        : "The internet check is off (stats: internet_check in settings.yaml).")));
}

// Is anything slow? Each route today, this week and this month; flagged when today is slower than usual.
function slowCard(t, monthLabel) {
  if (!t.routes.length) return h("p", { class: "empty-state" }, "Nothing timed in the last 30 days yet.");
  const cell = (x) => (x ? h("td", { class: "num" }, h("span", {}, msText(x.median), h("span", { class: "quiet small" }, ` (${x.n})`))) : h("td", { class: "quiet num" }, "-"));
  const flagged = t.routes.filter((r) => r.slow);
  return h("div", {},
    h("p", { class: flagged.length ? "status-line warn" : "status-line ok-line", role: "status" },
      icon(flagged.length ? "alert" : "check"),
      flagged.length ? `Slower than usual today: ${flagged.map((r) => routeName(r.route)).join(", ")}.`
        : "Nothing is slower than usual today."),
    stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix slow-table" },
      h("thead", {}, h("tr", {}, h("th", {}, "Route"), h("th", { class: "num" }, "Today"), h("th", { class: "num" }, "Last 7 days"),
        h("th", { class: "num" }, monthLabel || "Last 30 days"), h("th", {}, "Day by day, 30 days"), h("th", {}, ""))),
      h("tbody", {}, t.routes.map((r) => h("tr", { class: r.slow ? "slow" : null },
        h("th", { scope: "row" }, routeName(r.route)), cell(r.today), cell(r.week), cell(r.month),
        h("td", {}, dayBars(r.by_day, t.days)),
        h("td", {}, r.slow ? h("span", { class: "flag warn" }, icon("alert"), "slower than usual")
          : r.today ? h("span", { class: "flag" }, "as usual") : h("span", { class: "quiet small" }, "none today"))))))))
  );
}

// A line over time with a crosshair: point anywhere for the hour's numbers.
function cpuLine(week, sampleSeconds) {
  if (!week.length) return h("p", { class: "empty-state" }, `The router notes its CPU every ${sampleSeconds} seconds; the first hour shows here once it's noted.`);
  const W = 640, H = 200, L = 40, B = 24, T = 12, R = 8;
  const t0 = week[0].hour, t1 = week[week.length - 1].hour || t0 + 1;
  const span = Math.max(t1 - t0, 3600);
  const top = niceMax(Math.max(...week.map((x) => x.cpu_average), 1));
  const x = (t) => L + ((t - t0) / span) * (W - L - R);
  const y = (v) => H - B - (Math.min(v, top) / top) * (H - B - T);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "linechart", role: "img", tabindex: "0",
    "aria-label": `Router CPU, hour by hour: average ${Math.round(week.reduce((a, w) => a + w.cpu_average, 0) / week.length)}% of one core, busiest minute ${Math.round(Math.max(...week.map((w) => w.cpu_busiest)))}%` });
  for (const v of [0, top / 2, top]) {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }),
      svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", class: "tick" }, `${Math.round(v)}%`));
  }
  const dayTicks = [];
  for (let t = Math.ceil(t0 / 86400) * 86400; t <= t1; t += 86400) dayTicks.push(t);
  dayTicks.filter((_, i) => i % Math.ceil(dayTicks.length / 7 || 1) === 0).forEach((t) =>
    svg.append(svgEl("text", { x: x(t), y: H - 6, "text-anchor": "middle", class: "tick" },
      new Date(t * 1000).toLocaleDateString([], { weekday: "short" }))));
  let d = "";
  week.forEach((w, i) => {
    const gap = i && w.hour - week[i - 1].hour > 3600;        // an hour not noted (the router was off): a break
    d += `${i && !gap ? "L" : "M"}${x(w.hour).toFixed(1)},${y(w.cpu_average).toFixed(1)} `;
  });
  svg.append(svgEl("path", { d, class: "line s1" }), svgEl("line", { x1: L, x2: W - R, y1: y(0), y2: y(0), class: "axis" }));
  const last = week[week.length - 1];
  svg.append(svgEl("circle", { cx: x(last.hour), cy: y(last.cpu_average), r: 4, class: "dot s1" }));
  const hair = svgEl("line", { y1: T, y2: H - B, class: "hair", visibility: "hidden" });
  const dot = svgEl("circle", { r: 4, class: "dot s1", visibility: "hidden" });
  svg.append(hair, dot);
  const showAt = (i, clientX, clientY) => {
    const w = week[i];
    hair.setAttribute("x1", x(w.hour)); hair.setAttribute("x2", x(w.hour)); hair.setAttribute("visibility", "visible");
    dot.setAttribute("cx", x(w.hour)); dot.setAttribute("cy", y(w.cpu_average)); dot.setAttribute("visibility", "visible");
    if (!vizTip) { vizTip = h("div", { class: "viz-tip", role: "tooltip" }); document.body.append(vizTip); }
    vizTip.replaceChildren(h("strong", {}, `${w.cpu_average}% average`), h("span", {}, `busiest minute ${w.cpu_busiest}%`),
      h("span", {}, new Date(w.hour * 1000).toLocaleString([], { weekday: "short", hour: "numeric" })));
    vizTip.hidden = false;
    const r = vizTip.getBoundingClientRect();
    vizTip.style.left = `${Math.min(window.innerWidth - r.width - 8, Math.max(8, clientX + 12))}px`;
    vizTip.style.top = `${Math.max(8, clientY - r.height - 10)}px`;
  };
  let at = week.length - 1;
  const nearest = (clientX) => {
    const box = svg.getBoundingClientRect();
    const t = t0 + (((clientX - box.left) / box.width) * W - L) / (W - L - R) * span;
    let best = 0;
    week.forEach((w, i) => { if (Math.abs(w.hour - t) < Math.abs(week[best].hour - t)) best = i; });
    return best;
  };
  svg.addEventListener("pointermove", (e) => { at = nearest(e.clientX); showAt(at, e.clientX, e.clientY); });
  const hide = () => { hair.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); if (vizTip) vizTip.hidden = true; };
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    at = Math.max(0, Math.min(week.length - 1, at + (e.key === "ArrowRight" ? 1 : -1)));
    const b = svg.getBoundingClientRect();
    showAt(at, b.left + (x(week[at].hour) / W) * b.width, b.top + (y(week[at].cpu_average) / H) * b.height);
  });
  return svg;
}

function costCard(r) {
  const p = r.periods || {}, now = r.now || {};
  const pct = (v) => (v === undefined || v === null ? "-" : `${Math.round(v)}%`);
  const mb = (v) => (v === undefined || v === null ? "-" : v >= 1024 ? `${(v / 1024).toFixed(1)} GB` : `${Math.round(v)} MB`);
  const rows = [["last_hour", "Last hour"], ["last_24_hours", "Last 24 hours"], ["last_7_days", "Last 7 days"], ["last_30_days", "Last 30 days"]]
    .filter(([k]) => p[k]);
  return h("div", {},
    h("div", { class: "stats-row tiles" },
      tile("stats", "t1", "CPU now", pct(now.cpu_last_5_minutes ?? now.cpu_since_start), `of one core, last 5 minutes · ${now.cores} cores`),
      tile("overview", "t2", "Memory", mb(now.memory_mb), `peak ${mb(now.memory_peak_mb)}`),
      tile("settings", "t3", "Running for", now.running_hours < 1 ? `${Math.round(now.running_hours * 60)} min` : `${now.running_hours.toFixed(1)} h`, "since the last restart")),
    rows.length ? stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, ["", "CPU average", "Busiest minute", "Memory average", "Memory highest", "Requests"].map((x, i) => h("th", { class: i ? "num" : null }, x)))),
      h("tbody", {}, rows.map(([k, label]) => h("tr", {}, h("th", { scope: "row" }, label),
        h("td", { class: "num" }, pct(p[k].cpu_average)), h("td", { class: "num" }, pct(p[k].cpu_busiest)),
        h("td", { class: "num" }, mb(p[k].memory_average)), h("td", { class: "num" }, mb(p[k].memory_highest)),
        h("td", { class: "num" }, String(p[k].requests)))))))) : null,
    h("h3", { class: "chart-title" }, "Router CPU, hour by hour, last 7 days"),
    cpuLine(r.week || [], r.sample_seconds),
    h("p", { class: "quiet small" }, "CPU is a share of one core: 150% means one and a half cores busy. The router only: the apps and Oread run in their own containers."));
}

const TOP_CPU_COLUMNS = [["What was heard", "heard"], ["When (last)", "last"], ["Times", "count"], ["Most CPU", "cpu_max"],
  ["Typical CPU", "cpu_median"], ["Typical time", "ms_median"], ["Front end in", "t_ha_in_median"], ["Router deciding", "t_decide_median"],
  ["App or Off-Platform", "t_engine_median"], ["Route", "route"], ["", null]];

function topCpuCard(rows, days) {
  if (!rows.length) return h("p", { class: "empty-state" }, "No request has had its CPU measured yet.");
  const state = { sort: "cpu_max", desc: true };
  const head = h("thead", {});
  const body = h("tbody", {});
  const numeric = ["Times", "Most CPU", "Typical CPU", "Typical time", "Front end in", "Router deciding", "App or Off-Platform"];
  const num = (v) => h("td", { class: "num" }, v == null ? "-" : msText(v));
  const draw = () => {
    head.replaceChildren(sortHead(TOP_CPU_COLUMNS, state, draw, numeric));
    body.replaceChildren(...[...rows].sort((x, y) => cmp(x[state.sort] ?? "", y[state.sort] ?? "", state.desc)).map((r) => h("tr", {},
      h("td", { class: "heard" }, h("code", {}, r.heard)), h("td", { class: "nowrap quiet" }, when(r.last)),
      h("td", { class: "num" }, String(r.count)), num(r.cpu_max), num(r.cpu_median), num(r.ms_median),
      num(r.t_ha_in_median), num(r.t_decide_median), num(r.t_engine_median), h("td", {}, routeName(r.route)),
      h("td", { class: "actions" },
        h("a", { href: `#/try?say=${encodeURIComponent(r.heard)}&assistant=${encodeURIComponent(r.assistant || "")}`, title: "Run it through the router again on Try it (calls nothing)" }, "Try it"),
        navigator.clipboard ? h("button", { type: "button", class: "quiet-button", onclick: (e) => {
          navigator.clipboard.writeText(r.heard).then(() => { e.target.textContent = "Copied"; }, () => {}); } }, "Copy") : null))));
  };
  draw();
  return stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix top-cpu" }, head, body)),
    h("p", { class: "quiet small" }, "Front end in: from the voice ID's words to the request reaching the router (the front end and LiteLLM). A slow request with a big number there was slow before the router saw it."));
}

async function statsPage() {
  const days = select([{ value: "1", label: "last 24 hours" }, { value: "7", label: "last 7 days" }, { value: "30", label: "last 30 days" }, { value: "90", label: "last 90 days" }],
    (hashParam("days") || "7"), { "aria-label": "Period", onchange: () => go() });
  const who = select([{ value: "", label: "every assistant" }, ...(session.assistants || [])], hashParam("assistant") || "",
    { "aria-label": "Assistant", onchange: () => go() });
  const go = () => { location.hash = `#/stats?days=${days.value}${who.value ? `&assistant=${encodeURIComponent(who.value)}` : ""}`; };
  const o = await api(`/api/stats?days=${days.value}&tz=${tzMinutes()}${who.value ? `&assistant=${encodeURIComponent(who.value)}` : ""}`);
  APP_LABELS = o.apps || APP_LABELS;
  if (o.off) return [h("h1", {}, "Stats"), h("p", { class: "empty-state" }, "The activity log is off, so there's nothing to count.")];
  const period = days.options[days.selectedIndex].textContent;
  const w = o.shares.where;
  const total = WHERE.reduce((a, [k]) => a + (w[k] || 0), 0);
  for (const opt of days.options) {      // the log holds keep_days at most: a longer period would only repeat it
    if (Number(opt.value) > Math.max(1, o.keep_days) && !opt.selected) { opt.hidden = true; opt.disabled = true; }
  }
  const sp = o.span || {}, since = (d) => Date.now() / 1000 - d * 86400;
  const short = (s, d) => s.first && s.first > since(d) + 3600;       // the log starts inside the period
  const spanLine = sp.n ? `From ${when(sp.first)} to ${when(sp.last)}: ${number(sp.n)} requests${short(sp, Number(days.value)) ? ` (the log starts there; it keeps ${o.keep_days} days)` : ""}.` : "";
  const monthLabel = short(o.trend_span || {}, 30) ? `Since ${when(o.trend_span.first)}` : "Last 30 days";
  const ms = (x, k) => (x === undefined ? h("td", { class: "quiet num" }, "-") :
    h("td", { class: "num", title: `${x.n} measured; average ${msText(x.mean)}, all together ${msText(x.total)}; the slowest tenth took ${msText(x.p90)} or more` },
      h("span", {}, msText(x.median), h("span", { class: "quiet small" }, ` (${msText(x.p90)})`)),
      x.n !== k ? h("span", { class: "quiet small" }, ` · ${x.n}`) : null));
  const table = o.time_routes.length ? stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix hops" },
    h("thead", {}, h("tr", {}, h("th", {}, "Route"), h("th", { class: "num" }, "Requests"),
      h("th", { class: "num", title: "the same request coming in again while it was still being answered (LiteLLM giving up waiting and retrying): answered once, the answer sent to both" }, "Sent again"),
      HOP_LABELS.map(([, label, about]) => h("th", { class: "num", title: about }, label)))),
    h("tbody", {}, o.time_routes.map((r) => h("tr", {}, h("th", { scope: "row" }, routeName(r.route)), h("td", { class: "num" }, String(r.requests)),
      h("td", { class: r.repeats ? "num" : "quiet num" }, String(r.repeats || 0)),
      HOP_LABELS.map(([k]) => ms(r.hops[k], r.requests)))))))) : h("p", { class: "empty-state" }, "Nothing in this period yet.");
  // the router's own hops, one after another (Oct 18): what the router does, and what it waits on
  const OWN_HOPS = [["t_relay", "Hand-off to Oread and back", "the router passing the end of the speech to Oread, and Oread's words back to Home Assistant"],
    ["t_decide", "Deciding", "from the request arriving to handing it on"],
    ["t_litellm", "LiteLLM itself", "LiteLLM's own time, as LiteLLM reports it"],
    ["t_model", "The model", "the Off-Platform hop less LiteLLM's own time: the model, and the internet to it"],
    ["t_engine", "The app, or LiteLLM and the model", "the answer's own time: an app at home, or the whole trip Off-Platform"],
    ["t_back", "Back to Home Assistant", "from the answer leaving the router to Home Assistant done with it (from Home Assistant's own record of the run)"]];
  const own = o.time_routes.length ? h("div", { class: "table-wrap" }, h("table", { class: "matrix own-hops" },
    h("thead", {}, h("tr", {}, h("th", {}, "Route"), h("th", { class: "num" }, "Requests"), OWN_HOPS.map(([, label, about]) => h("th", { class: "num", title: about }, label)))),
    h("tbody", {}, o.time_routes.map((r) => h("tr", {}, h("th", { scope: "row" }, routeName(r.route)), h("td", { class: "num" }, String(r.requests)),
      OWN_HOPS.map(([k]) => ms(r.hops[k], r.requests))))))) : null;
  const t = o.trend;
  return [h("h1", {}, "Stats"),
    h("div", { class: "toolbar filters" }, field("Assistant", who,
      "Everything below is for this assistant, except what the router costs to run (that's the whole router).")),
    foldBox("slow", "Is anything slow?", true,
      h("p", { class: "quiet small" }, `Each route's typical time in the router: its own work plus the app or model it waits for (requests in brackets). Flagged when today's typical is ${t.slower} times its 30-day typical or more, once today has ${t.min_requests} requests (stats: in settings.yaml).`),
      slowCard(t, monthLabel)),
    foldBox("legs", "Which leg was slow?", true,
      h("p", { class: "quiet small" }, "Each route today against usual, leg by leg: the router's own work and its CPU (software), how busy the machine was (hardware), and the outside hop, with the internet check on routes that leave the house."),
      legsCard(o.legs)),
    foldBox("top-cpu", `The requests that cost the most CPU, last ${o.top_cpu_days} days`, true,
      h("p", { class: "quiet small" }, "One line per saying, most CPU first, as heard: Try it runs it through the router again, Copy takes the words to say or type it yourself."),
      topCpuCard(o.top_cpu, o.top_cpu_days)),
    foldBox("cost", "What the router costs to run", true, costCard(o.resources)),
    lazyView(holdingView),
    h("h2", { class: "band" }, "By period"),
    h("div", { class: "toolbar filters" }, field("Period", days)),
    h("div", { class: "stats-row tiles" },
      tile("transactions", "t1", "Requests", total, short(sp, Number(days.value)) ? `since ${when(sp.first)}` : period),
      tile("overview", "t2", "Answered at home", w.home, total ? `${shareOf(w.home, total)} of them` : ""),
      tile("bank", "t3", "From the Off-Platform Bank", w.bank, "no trip needed"),
      tile("savings", "t2", "Went Off-Platform", w.off_platform, `to ${o.model}`),
      tile("firewall", "terr", "Blocked", w.blocked, "by the firewall")),
    foldBox("time", "Where the time goes", true,
      h("p", { class: "small" }, "Each cell: the typical time (the median), in brackets the slowest tenth, and after the dot how many were measured when fewer than the route's requests. Point at a cell for its average and its time all together, at a heading for what it measures."),
      spanLine ? h("p", { class: "quiet small" }, spanLine) : null,
      own ? h("h3", {}, "The router's own hops") : null,
      own ? h("p", { class: "quiet small" }, "The trip through the router one hop after another: its hand-off to Oread, its deciding, LiteLLM's own time and the model's (the trip Off-Platform split; there and back aren't apart, LiteLLM's clock isn't ours), the app's, and the way back to Home Assistant. A dash: not measured on that route (the way back needs Home Assistant's address and token on Integrations).") : null,
      own,
      h("h3", {}, "Every hop"),
      table,
      h("p", { class: "quiet small" }, o.audio_path
        ? "Wepwawet sits between all applications listed above, both in-bound and out-bound."
        : "Speaking, Oread and Home Assistant-in need the router in the audio path (Integrations, Oread); until then only the router's own hops are measured."),
      h("p", { class: "quiet small" }, "Not measured yet: Home Assistant speaking the answer (text to speech) and playing it on the device; those happen after the way back.")),
    h("div", { class: "chart-grid" },
      foldBox("where", "Where requests were answered", true, whereDonut(w)),
      foldBox("by-assistant", "Requests by assistant", true, rankBars(o.shares.by_assistant, "Requests"))),
    foldBox("per-day", "Requests a day", true, dayColumns(o.shares.by_day)),
  ];
}

// ---------- Watch: transactions (everything in, and what went out) ----------

// the columns, and what each sorts by on the router (activity.SORTS); null: not sortable
const TXN_COLUMNS = [["When", "time"], ["Assistant", "assistant"], ["Who spoke", "speaker"], ["Heard", "heard"],
  ["Went to", "went"], ["Reply", "said"], ["Took", null], ["", null]];

// one request as a table row (and a hidden row under it for Why and Misheard); Off-Platform rows
// are tinted (most mishearings end up there), firewall stops too
function activityRow(r, bankOn = true) {
  const who = r.speaker ? `${r.speaker}${r.speaker_score != null ? ` (${Number(r.speaker_score).toFixed(2)})` : ""}` : "";
  const box = h("span", { class: "small" });
  const can = allowed("bank");
  const offPlatform = r.engine === "gemini" && r.bank_id;
  const cols = TXN_COLUMNS.length;
  // Delete: right, and routed right, so nothing to learn from it
  const del = h("button", { type: "button", disabled: !can, title: "Nothing to learn from it: take it out of the log" }, "Delete");
  // Bank: an Off-Platform request into the Off-Platform Bank
  const add = r.in_bank
    ? h("span", { class: "badge pill-ok", title: "In the Off-Platform Bank as a replacement answer" }, "banked")
    : h("button", { type: "button", disabled: !can || !offPlatform || !bankOn,
        title: !bankOn ? "The bank is off (answers kept is 0, on the Off-Platform Bank's Rules tab)"
          : offPlatform ? "Into the Off-Platform Bank as a replacement answer" : "Only a request that went Off-Platform goes into the bank" }, "Bank");
  // Misheard: into the mishearings (learn/mishearings.yaml), under what was really said
  const misheard = r.marked === "misheard"
    ? h("span", { class: "badge", title: "In the mishearings (Misses page)" }, "misheard")
    : h("button", { type: "button", disabled: !can || !r.heard, title: "Speech to text got it wrong: into the mishearings, under what was really said" }, "Misheard");
  const reasons = [...(r.blocked ? [`Firewall: ${r.blocked}`] : []), ...(r.why || [])];
  const why = reasons.length ? h("button", { type: "button", class: "quiet-button", title: "Why it went where it went" }, "Why") : null;
  const more = h("td", { colspan: String(cols) });
  const under = h("tr", { class: "txn-more", hidden: true }, more);
  const open = (...content) => { more.replaceChildren(...content); under.hidden = false; };
  const close = () => { under.hidden = true; more.replaceChildren(); };
  const tone = r.blocked || r.path === "blocked" ? " txn-blocked" : r.engine === "gemini" ? " txn-off" : "";
  const row = h("tr", { class: "txn" + tone },
    h("td", { class: "quiet" }, when(r.time)),
    h("td", {}, r.assistant || "?"),
    h("td", { class: who ? "" : "quiet" }, who || "-"),
    h("td", { class: "txn-heard" }, r.heard || h("span", { class: "quiet" }, "(nothing heard)")),
    h("td", {}, pathTag(r), r.topic ? [" ", h("span", { class: "badge" }, r.topic)] : null,
      r.sent_to && r.engine !== "gemini" ? h("div", { class: "small quiet" }, `→ ${r.sent_to}`) : null,
),
    h("td", { class: "txn-said" }, r.answer ? h("div", { class: "said-line" }, hearButton(r.answer, true), h("span", { class: "clamp", title: r.answer }, r.answer))
      : h("span", { class: "quiet small" }, r.engine === "gemini" ? "(still answering, or no words came back)" : "")),
    h("td", { class: "num quiet" }, r.ms != null ? `${(r.ms / 1000).toFixed(1)} s` : ""),
    h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, why, del, add, misheard), box));
  // once dealt with, it leaves the list (Handled shows it again)
  const gone = (where, href) => {
    close();
    row.replaceChildren(h("td", { colspan: String(cols), class: "small quiet" }, `"${r.heard}" went to `, h("a", { href: href }, where), "."));
    setTimeout(() => { row.remove(); under.remove(); }, 2500);
  };
  if (why) why.addEventListener("click", () => {
    if (!under.hidden && more.dataset.what === "why") return close();
    more.dataset.what = "why";
    open(h("ul", { class: "small why-list" }, reasons.map((w) => h("li", {}, w))));
  });
  del.addEventListener("click", busy(del, box, async () => {
    await api(`/api/activity/${r.id}`, { method: "DELETE" });
    row.remove(); under.remove();
  }));
  if (!r.in_bank) add.addEventListener("click", busy(add, box, async () => {
    await api("/api/bank/add", { method: "POST", body: { activity_id: r.id } });
    gone("the Off-Platform Bank", "#/bank");
  }));
  if (r.marked !== "misheard") misheard.addEventListener("click", () => {
    const said = h("textarea", { rows: "3", class: "said-box", placeholder: "what was really said (optional: you can type it later on the Misses page)", "aria-label": "What was really said" });
    const rec = h("button", { type: "button", class: "primary" }, "Record");
    const rbox = h("span", { class: "small" });
    rec.addEventListener("click", busy(rec, rbox, async () => {
      await api(`/api/activity/${r.id}/misheard`, { method: "POST", body: { said: said.value } });
      gone("the Misses page", "#/misses");
    }));
    // Enter records, Shift+Enter is a new line: quick for going down a long list
    said.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); rec.click(); } if (e.key === "Escape") close(); });
    more.dataset.what = "misheard";
    open(h("div", { class: "misheard-fix" }, h("span", { class: "small quiet" }, `Heard "${r.heard}". Really said:`), said,
      h("div", { class: "row-actions" }, rec, h("button", { type: "button", onclick: close }, "Cancel"), rbox)));
    said.focus();
  });
  return [row, under];
}

// Every page with knobs has two tabs across the top (Oct 15): the page itself, and Rules, holding
// the settings.yaml knobs for what that page shows (SETTINGS_ELSEWHERE says which).
const RULES_ABOUT = {
  misses: "How many wrong-part misses and mishearings are kept. When mishearings are used to correct what was heard (later), its settings come here too.",
  tools: "Settings for debugging: full copies of requests (captures) for tools/replay.py.",
  bank: "How much activity is kept, the Off-Platform Bank's formula (N, T, Q, U), and trimming one-offs.",
  savings: "What one request to the cloud model costs, for the calculation on the Savings page.",
  stats: "How often the router notes its CPU and memory, how long it keeps them, and when a route counts as slower than usual.",
  topics: "How sure the router must be before an app at home answers, and how the keyword build turns the datasets into each topic's words and each app's verbs.",
};
// A page under its own name with a Rules tab for its settings; more: other tabs ({id: [label, fn]}),
// placed between the page and Rules.
function withRules(page, label, inner, more = {}) {
  return async () => {
    const list = [["main", label], ...Object.entries(more).map(([id, [text]]) => [id, text]), ["rules", "Rules"]];
    const want = hashParam("tab");
    const tab = list.some(([id]) => id === want) ? want : "main";
    const tabs = h("div", { class: "tabs page-tabs", role: "tablist" }, list.map(([id, text]) =>
      h("button", { role: "tab", type: "button", "aria-selected": id === tab ? "true" : "false",
        onclick: () => { location.hash = id === "main" ? `#/${page}` : `#/${page}?tab=${id}`; } }, text)));
    if (tab === "rules") return [h("h1", {}, label), tabs, ...(await rulesView(page))];
    if (more[tab]) return [h("h1", {}, label), tabs, ...[].concat(await more[tab][1]())];
    const out = await inner();
    return [out[0], tabs, ...out.slice(1)];
  };
}

async function rulesView(page) {
  const kit = await settingsKit();
  const here = (k) => (SETTINGS_ELSEWHERE[k] || [])[1] === `${page}?tab=rules`;
  const extra = page === "bank" ? [await bankTrim()] : [];
  return [h("p", { class: "quiet" }, `${RULES_ABOUT[page] || ""} Each from settings.yaml, with its comment; change one and its Save lights up.`),
    ...extra, ...kit.cards(here)];
}

async function transactionsList() {
  const body = h("tbody", {});
  // sorting: a column heading sorts by it (again: the other way); paging follows the sort
  let sort = "time", desc = true;
  const head = h("tr", {});
  const drawHead = () => head.replaceChildren(...TXN_COLUMNS.map(([label, key]) => {
    if (!key) return h("th", { class: label === "Took" ? "num" : "" }, label);
    const on = sort === key;
    const b = h("button", { type: "button", class: "sort" + (on ? " on" : ""), title: `Sort by ${label.toLowerCase()}` },
      label, h("span", { class: "arrow", "aria-hidden": "true" }, on ? (desc ? " ▼" : " ▲") : ""));
    b.addEventListener("click", () => {
      if (on) desc = !desc; else { sort = key; desc = key === "time"; }
      drawHead(); load(true);
    });
    return h("th", { "aria-sort": on ? (desc ? "descending" : "ascending") : "none" }, b);
  }));
  drawHead();
  const list = h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table" }, h("thead", {}, head), body));
  const empty = (text) => body.append(h("tr", {}, h("td", { colspan: String(TXN_COLUMNS.length), class: "empty-state" }, text)));
  const shown = select([{ value: "all", label: "everything" }, { value: "out", label: "left the router (Off-Platform, the apps)" },
    { value: "gemini", label: "went Off-Platform" }, { value: "home", label: "answered at home" },
    { value: "blocked", label: "stopped by the firewall" }], "all", { "aria-label": "Show" });
  const handled = select([{ value: "hide", label: "to look at (not yet handled)" }, { value: "only", label: "handled (you banked it or marked it misheard)" },
    { value: "all", label: "handled or not" }], "hide", { "aria-label": "Handled" });
  const search = input("search", { placeholder: "words heard or said", "aria-label": "Search" });
  const who = select([{ value: "", label: "every assistant" }, ...(session.assistants || [])], "", { "aria-label": "Assistant" });
  const more = h("button", { class: "more", type: "button" }, "Older");
  let before = 0, offset = 0;
  async function load(reset) {
    if (reset) { body.replaceChildren(); before = 0; offset = 0; }
    const q = new URLSearchParams({ direction: shown.value, handled: handled.value, limit: "50", search: search.value, assistant: who.value,
      sort: sort, order: desc ? "desc" : "asc", offset: String(offset) });
    if (before) q.set("before", String(before));
    const d = await api(`/api/activity?${q}`);
    if (d.off) { empty("The activity log is off (settings.yaml activity: enabled)."); return; }
    for (const r of d.rows) body.append(...activityRow(r, d.bank_keeps !== false));
    if (!d.rows.length && reset) empty("Nothing yet.");
    // newest first pages by the last id seen; any other sort by how many are shown
    if (sort === "time" && desc) before = d.rows.length ? d.rows[d.rows.length - 1].id : before;
    else offset += d.rows.length;
    more.hidden = d.rows.length < 50;
  }
  more.addEventListener("click", () => load(false));
  for (const el of [shown, handled, search, who]) el.addEventListener("change", () => load(true));
  await load(true);
  let keep = null;
  if (allowed("settings")) {
    const st = await api("/api/settings");
    const cur = ((st.settings || {}).activity || {}).keep_days ?? st.defaults.activity.keep_days;
    const daysBox = input("number", { min: "1", max: "3650", step: "1", value: cur, "aria-label": "Days kept" });
    const msg = h("span", { class: "small" });
    const save = h("button", { type: "button" }, "Keep");
    save.addEventListener("click", busy(save, msg, async () => {
      await api("/api/settings", { method: "PATCH", body: { path: ["activity", "keep_days"], value: Number(daysBox.value) } });
      msg.replaceChildren(okNote("in use now"));
    }));
    keep = h("div", { class: "row small" }, h("span", { class: "quiet" }, "Keep transactions for"), daysBox, h("span", { class: "quiet" }, "days"), save, msg);
  }
  return [h("h1", {}, "Transactions"),
    h("p", { class: "quiet" }, "Every request the router handled, one to a row, newest first until you sort. Rows that went Off-Platform are tinted (that's where most mishearings end up); firewall stops are red. Why shows the router's reasons (and the firewall's); Delete takes out one that was right and routed right (nothing to learn); Bank puts an Off-Platform request into the Off-Platform Bank; Misheard opens a box under the row for what was really said (Enter records it, Esc closes) and files it on the Misses page. Banked and misheard ones leave this list (choose handled to see them); the rest age out after the days kept. Click a column heading to sort by it, again to reverse."),
    keep,
    h("div", { class: "toolbar" }, shown, handled, search, who, h("button", { type: "button", onclick: () => load(true) }, "Refresh")),
    list, more];
}

// ---------- Watch: savings ----------

function number(n) { return n === null || n === undefined ? "-" : Number(n).toLocaleString(); }

async function savingsPage() {
  const days = select([{ value: "1", label: "today and yesterday" }, { value: "7", label: "last 7 days" },
    { value: "30", label: "last 30 days" }, { value: "365", label: "last year" }],
    (location.hash.split("?days=")[1] || "30"), { "aria-label": "Period", onchange: (e) => { location.hash = `#/savings?days=${e.target.value}`; } });
  const d = await api(`/api/savings?days=${days.value}`);
  if (d.off) return [h("h1", {}, "Savings"), h("p", { class: "empty-state" }, "The activity log is off, so there's nothing to count.")];
  const max = Math.max(1, ...d.by_day.map((x) => x.home + x.gemini));
  const bars = d.by_day.map((x) => h("div", { class: "bar-row" },
    h("span", { class: "bar-label" }, x.day),
    h("span", { class: "bar-track", title: `${x.home} at home, ${x.gemini} Off-Platform` },
      h("span", { class: "bar-fill", style: null, "data-w": String(Math.round((100 * x.home) / max)) })),
    h("span", { class: "bar-count" }, `${x.home} / ${x.home + x.gemini}`)));
  const page = [h("h1", {}, "Savings"),
    h("p", { class: "quiet" }, "Trips to the cloud model that answering at home saved, and their tokens. A calculation from the activity log, not a meter: no tokens are used or counted by anyone else."),
    h("div", { class: "toolbar" }, days),
    h("div", { class: "stats-row" },
      stat("Trips kept at home", number(d.trips_saved), d.home_share !== null ? `${Math.round(d.home_share * 100)}% of ${number(d.requests)} requests` : ""),
      stat("Trips Off-Platform", number(d.trips_out), d.avg_tokens_per_trip_out ? `about ${number(d.avg_tokens_per_trip_out)} tokens each, measured` : ""),
      stat("Tokens saved", number(d.tokens_saved), `at ${number(d.tokens_per_request)} a request`),
      stat("Tokens saved, measured", number(d.tokens_saved_measured), `from each request's own size (${number(d.measured_rows)} measured)`)),
    h("section", { class: "card panel" }, h("h2", {}, "By day: kept at home / all requests"), bars.length ? bars : h("p", { class: "quiet" }, "Nothing yet.")),
    h("section", { class: "card panel" }, h("h2", {}, "Who answered at home"),
      h("ul", { class: "rows" }, d.by_engine.map((x) => h("li", {}, h("span", {}, x.engine === "router" ? "the router itself (path 0, questions back, learn)" : x.engine === "bank" ? "the Off-Platform bank (an Off-Platform answer reused at home)" : x.engine), h("strong", {}, number(x.n)))))),
    h("p", { class: "quiet small" }, `The activity log keeps ${d.keep_days} days (Transactions page), so savings older than that aren't counted.`)];
  setTimeout(() => { for (const el of document.querySelectorAll(".bar-fill[data-w]")) el.style.width = `${el.dataset.w}%`; }, 0);
  return page;
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

// ---------- Teach: try a sentence ----------

async function tryPage() {
  const given = hashParam("say");                 // from Stats: the request to run again
  const say = input("text", { placeholder: "what's the weather tomorrow", autofocus: true, value: given || null });
  const assistant = select(session.assistants || [], hashParam("assistant") || (session.assistants || [])[0]);
  const speaker = input("text", { placeholder: "Sam (empty: nobody known)" });
  const label = select(["known", "maybe", "unknown"], "known");
  const score = input("number", { min: "0", max: "1", step: "0.01", value: "0.9" });
  const live = check(" Also ask the service (only calls that change nothing)", false);
  const out = h("div", {});
  const box = errorBox();
  const btn = h("button", { class: "primary", type: "submit" }, "Try it");
  const f = h("form", { class: "card panel" }, field("Say", say), h("div", { class: "grid2" },
      field("Assistant", assistant), field("Who spoke (Oread)", speaker, "As Oread names them; empty for nobody known."),
      field("Oread's label", label), field("Oread's score", score)), live, box, btn);
  f.addEventListener("submit", busy(btn, box, async () => {
    const body = { say: say.value, assistant: assistant.value, live: live.querySelector("input").checked };
    if (speaker.value.trim()) body.speaker = { speaker: speaker.value.trim(), label: label.value, score: Number(score.value) };
    const d = await api("/api/try", { method: "POST", body: body });
    out.replaceChildren(h("section", { class: "card panel" },
      h("h2", {}, d.path === "gemini" ? "Off-Platform" : `Path ${d.path}`, d.topic ? ` · ${d.topic}${d.score != null ? ` ${Math.round(d.score * 100)}%` : ""}` : "", d.action ? ` · ${d.action}` : ""),
      d.speech ? h("p", { class: "heard" }, d.speech, " ", hearButton(d.speech)) : null,
      d.status ? h("p", { class: "quiet" }, d.status) : null,
      d.name_sure !== undefined ? h("p", { class: "small" }, d.name_sure ? (d.name_on ? `"${d.say_name_as}" may be said in an answer.` : `Sure it is ${d.say_name_as}, but names are off on this device (Flair).`) : "Not sure enough of the voice to say a name.") : null,
      h("ul", {}, (d.why || []).map((w) => h("li", {}, w)))));
  }));
  if (given) setTimeout(() => f.requestSubmit(), 0);      // run it straight away
  return [h("h1", {}, "Try it"),
    h("p", { class: "quiet" }, "The same decision a real request would get, and why. Nothing goes Off-Platform and nothing is changed."), f, out];
}

// ---------- Teach: topics and their seed words ----------

async function topicsPage() {
  const d = await api("/api/topics");
  const src = await api("/api/sources");
  const isAdmin = allowed("tools");
  const want = decodeURIComponent((location.hash.split("?topic=")[1] || "").split("&")[0]);
  const cards = d.topics.length ? d.topics.map((t) => topicCard(t, d.services, isAdmin, t.name === want))
    : [h("p", { class: "empty-state" }, "No topics yet: add one below.")];
  const sources = h("ul", { class: "rows" }, src.sources.map((s) => h("li", {},
    h("span", {}, h("strong", {}, s.name), " ", h("span", { class: "quiet small" }, `${s.description || ""} (${(s.use || []).join(", ")})`)),
    h("span", {}, s.present ? h("span", { class: "pill-ok" }, "downloaded") : h("span", { class: "pill-bad" }, "not downloaded"), " ",
      isAdmin ? check(" use", s.enabled, async (e) => { await api(`/api/sources/${s.name}`, { method: "PATCH", body: { enabled: e.target.checked } }); }) : null))));
  const add = isAdmin ? addTopicForm(d.services) : null;
  return [h("h1", {}, "Seed Topics"),
    h("p", { class: "quiet" }, "Each topic the router answers at home, the service that answers it, and its words. Seed words find the topic's labels in the datasets and always count fully; pinned words are your household's own (they count fully too, no rebuild needed); tentative words always need backup. After changing seeds, run Build the keyword tiers (the Build tab), then restart. Every topic is folded: open one to see or change its words."),
    h("p", { class: "quiet small" }, "Where the services come from: settings.yaml, under services: (today ",
      d.services.map((x, i) => [i ? ", " : "", h("strong", {}, x)]), "). Each has a kind (contract: it speaks the router's own /ask door; openapi: it's described by its own OpenAPI or Swagger file), an address and a timeout. Switch them on or off and change their addresses on the ",
      h("a", { href: "#/integrations" }, "Integrations"), " page; a new kind of service is added in settings.yaml."),
    ...cards, add,
    h("details", { class: "card panel fold" }, h("summary", {}, h("h2", {}, "Datasets"),
      h("span", { class: "quiet small" }, ` ${src.sources.filter((s) => s.enabled !== false).length} in use of ${src.sources.length}`)),
      h("p", { class: "quiet small" }, "Described in tools/sources.yaml. Download them on the Build tab."), sources)];
}

function topicCard(t, services, isAdmin, open) {
  const state = { service: t.service, seed: t.seed, always_tentative: t.always_tentative, pinned: t.pinned, then: t.then || [], datasets: t.datasets !== false };
  const box = errorBox();
  const status = h("span", {});
  const svc = select([{ value: "", label: "no app yet" }].concat(services), t.service || "", { disabled: !isAdmin, onchange: (e) => {
    if (t.service && e.target.value !== t.service && !confirm(`Have ${e.target.value || "no app"} answer the ${t.name} topic instead of ${t.service}?`)) {
      e.target.value = state.service;
      return;
    }
    state.service = e.target.value;
  } });
  const save = h("button", { class: "primary", type: "button" }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    await api(`/api/topics/${t.name}`, { method: "PUT", body: state });
    status.replaceChildren(okNote("Saved. Build, then restart."));
    session = await api("/api/session");
  }));
  const gen = t.generated || {};
  return h("details", { class: "card panel fold", open: Boolean(open) },
    h("summary", {}, h("h2", {}, t.name), " ", t.running ? h("span", { class: "badge" }, "running") : h("span", { class: "badge" }, "not running"),
      h("span", { class: "quiet small" }, t.service ? ` answered by ${t.service} · ${(t.seed || []).length} seed, ${(t.pinned || []).length} pinned` : " no service yet")),
    h("p", { class: "quiet small" }, gen.built ? `Built tree: doors ${JSON.stringify(gen.doors)}; learns from ${JSON.stringify(gen.learn_from || {})}` : "Not built yet: run Build the keyword tiers."),
    field("Answered by", svc, "The service that answers this topic's requests."),
    field("Then, when it's busy", chipList(t.then || [], (v) => { state.then = v; }, "another app"),
      `Apps of the same nature, in order (${services.join(", ")}): when the one before is at its limit or doesn't answer, the next answers instead. Restart after saving.`),
    h("div", {}, check(" Learn from the datasets too", state.datasets, (e) => { state.datasets = e.target.checked; }),
      h("span", { class: "quiet small" }, " (off: built from your own words alone; a rebuild after changing it)")),
    h("div", { class: "grid2" },
      h("div", {}, h("h3", {}, "Seed words"), chipList(t.seed, (v) => { state.seed = v; })),
      h("div", {}, h("h3", {}, "Pinned words"), chipList(t.pinned, (v) => { state.pinned = v; })),
      h("div", {}, h("h3", {}, "Always tentative"), chipList(t.always_tentative, (v) => { state.always_tentative = v; }))),
    box, isAdmin ? h("div", { class: "row-actions" }, save, status,
      h("button", { type: "button", onclick: async () => {
        if (!confirm(`Remove the topic ${t.name}? Its generated files stay until the next build.`)) return;
        try { await api(`/api/topics/${t.name}`, { method: "DELETE" }); route(); } catch (e) { box.textContent = e.message; }
      } }, "Remove topic")) : null);
}

function addTopicForm(services) {
  const name = input("text", { placeholder: "a new topic, like sensors" });
  const svc = select([{ value: "", label: "no app yet (Add an app offers it)" }].concat(services), services[0]);
  const box = errorBox();
  const btn = h("button", { type: "submit" }, "Add topic");
  const f = h("form", { class: "card panel" }, h("h2", {}, "Add a topic"),
    h("div", { class: "grid2" }, field("Name", name), field("Service", svc)), box, btn);
  f.addEventListener("submit", busy(btn, box, async () => {
    await api(`/api/topics/${name.value.trim().toLowerCase()}`, { method: "PUT", body: { service: svc.value, seed: [], always_tentative: [], pinned: [] } });
    route();
  }));
  return f;
}

// ---------- Teach: tools ----------

let jobTimer = null;

async function toolsPage() {
  return [h("h1", {}, "Tools"),
    h("p", { class: "quiet" }, "The same tools you run on the server, run inside the router's container from its folder: the tests. One runs at a time; their output shows below. The keyword tools are on Seed Topics (Build), the miss tools on Misses (Tools), the books on Persona Flair (Phrases)."),
    ...(await toolsView("tools"))];
}

// The tools tools.yaml puts on one page (page:), grouped, with their output below one another.
async function toolsView(page) {
  const d = await api("/api/tools");
  const output = h("pre", { class: "output", hidden: true, "aria-live": "polite" });
  const status = h("p", { class: "quiet" });
  const groups = {};
  for (const t of d.tools.filter((x) => (x.page || "tools") === page)) (groups[t.group] = groups[t.group] || []).push(t);
  const sections = Object.entries(groups).map(([g, tools]) => {
    const parts = {};
    for (const t of tools) (parts[t.section] = parts[t.section] || []).push(t);
    return h("section", { class: "panel" }, h("h2", {}, g),
      Object.entries(parts).map(([sec, list]) => [sec ? h("h3", { class: "tool-section" }, sec) : null,
        h("div", { class: "clips" }, list.map((t) => toolCard(t, output, status)))]));
  });
  return [status, output, ...sections];
}

function toolCard(t, output, status) {
  const args = {};
  const inputs = Object.entries(t.args || {}).map(([name, a]) => {
    let el;
    if (a.choices) el = select([{ value: "", label: a.optional ? `${name}: all` : `${name}: pick one` }].concat(a.choices), "");
    else el = input("text", { placeholder: name });
    el.setAttribute("aria-label", name);
    args[name] = el;
    return el;
  });
  const btn = h("button", { class: "primary", type: "button", disabled: !t.allowed }, "Run");
  btn.addEventListener("click", busy(btn, null, async () => {
    const values = {};
    for (const [k, el] of Object.entries(args)) values[k] = el.value;
    const r = await api(`/api/tools/${t.id}`, { method: "POST", body: { args: values } });
    output.hidden = false;
    output.textContent = `$ ${r.cmd}\n`;
    status.textContent = `${t.label}: running…`;
    followJob(r.job, output, status, t);
  }));
  return h("div", { class: "card tool" }, h("h3", {}, t.label), h("p", { class: "quiet small" }, t.about),
    inputs.length ? h("div", { class: "args" }, inputs) : null, btn,
    t.allowed ? null : h("p", { class: "quiet small" }, `Needs the ${t.role} role.`));
}

function followJob(jid, output, status, tool) {
  let since = 0;
  if (jobTimer) clearInterval(jobTimer);
  jobTimer = setInterval(async () => {
    try {
      const j = await api(`/api/jobs/${jid}?since=${since}`);
      if (j.lines.length) {
        output.textContent += j.lines.join("\n") + "\n";
        output.scrollTop = output.scrollHeight;
      }
      since = j.next;
      if (j.state !== "running") {
        clearInterval(jobTimer);
        jobTimer = null;
        status.textContent = `${tool.label}: ${j.state === "done" ? "finished" : "failed"} (exit ${j.exit}, ${j.seconds} s)` +
          (tool.restart && j.state === "done" ? ". Restart the router to use what it made." : "");
        if (tool.restart) session = await api("/api/session");
      }
    } catch (e) { clearInterval(jobTimer); status.textContent = e.message; }
  }, 1000);
}

// ---------- Teach: misses ----------

function decisionText(d) {
  if (!d) return "?";
  const where = { A: "a home topic", B: "a follow-up", C: "a question back", "0": "a short reply", gemini: "Off-Platform", ask: "ask first", learn: "learn" }[d.path] || `path ${d.path}`;
  return [where, d.topic, d.action ? `(${d.action})` : ""].filter(Boolean).join(" ");
}

function diffView(diff) {
  return diff ? h("span", { class: "diff" }, diff.map((x) => x.op === "same" ? h("span", {}, x.heard + " ")
    : [x.heard ? h("del", { title: "heard" }, x.heard) : null, x.said ? h("ins", { title: "really said" }, x.said) : null, " "])) : null;
}

// a sortable heading for the tables sorted on the page itself: [label, key] -> th; state {sort, desc}
function sortHead(columns, state, redraw, numeric) {
  return h("tr", {}, columns.map(([label, key]) => {
    if (!key) return h("th", { class: numeric && numeric.includes(label) ? "num" : "" }, label);
    const on = state.sort === key;
    const b = h("button", { type: "button", class: "sort" + (on ? " on" : ""), title: `Sort by ${label.toLowerCase()}` },
      label, h("span", { class: "arrow", "aria-hidden": "true" }, on ? (state.desc ? " ▼" : " ▲") : ""));
    b.addEventListener("click", () => {
      if (on) state.desc = !state.desc; else { state.sort = key; state.desc = key !== "text"; }
      redraw();
    });
    return h("th", { class: numeric && numeric.includes(label) ? "num" : "", "aria-sort": on ? (state.desc ? "descending" : "ascending") : "none" }, b);
  }));
}

function cmp(a, b, desc) {
  const r = typeof a === "number" && typeof b === "number" ? a - b : String(a ?? "").localeCompare(String(b ?? ""), undefined, { sensitivity: "base" });
  return desc ? -r : r;
}

// a box under a row (Move, what should have happened): Enter saves, Shift+Enter a new line, Esc closes
function underBox(under, more, label, value, button, save) {
  const box = h("textarea", { rows: "2", class: "said-box", "aria-label": label, placeholder: label }, value || "");
  const go = h("button", { type: "button", class: "primary" }, button);
  const msg = errorBox();
  const close = () => { under.hidden = true; more.replaceChildren(); };
  go.addEventListener("click", busy(go, msg, async () => { await save(box.value); route(); }));
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go.click(); } if (e.key === "Escape") close(); });
  more.replaceChildren(h("div", { class: "misheard-fix" }, h("span", { class: "small quiet" }, label + ":"), box,
    h("div", { class: "row-actions" }, go, h("button", { type: "button", onclick: close }, "Cancel"), msg)));
  under.hidden = false;
  box.focus();
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

const MISS_COLUMNS = [["Heard", "text"], ["Assistant", "assistant"], ["Times", "times"], ["First", "first"], ["Last", "last"], ["Then", "then"], ["Reply", null], ["Should have been", null], ["", null]];

async function missesPage() {
  const [d, mh] = await Promise.all([api("/api/misses"), api("/api/mishearings")]);
  const canFix = allowed("tools");
  const output = h("pre", { class: "output", hidden: true });
  const status = h("p", { class: "quiet" });
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
  // the wrong part answered
  const estate = { sort: "last", desc: true };
  const ebody = h("tbody", {});
  const ehead = h("thead", {});
  const key = (m) => ({ text: m.heard, assistant: m.assistant, times: m.count || 1, first: m.first, last: m.last, then: decisionText({ path: m.path, topic: m.topic }) })[estate.sort];
  const drawE = () => {
    ehead.replaceChildren(sortHead(MISS_COLUMNS, estate, drawE, ["Times"]));
    const rows = [...d.misses].sort((x, y) => cmp(key(x), key(y), estate.desc)).flatMap((m) => {
      const msg = errorBox();
      const more = h("td", { colspan: String(MISS_COLUMNS.length) });
      const under = h("tr", { class: "txn-more", hidden: true }, more);
      const note = h("button", { type: "button", title: "What should have happened" }, m.should_be ? "Change" : "Should be");
      note.addEventListener("click", () => underBox(under, more, "What should have happened", m.should_be, "Save",
        (v) => api("/api/misses/should_be", { method: "POST", body: { kind: m.kind, heard: m.heard, should_be: v } })));
      const drop = h("button", { type: "button" }, "Drop");
      drop.addEventListener("click", busy(drop, msg, async () => {
        if (!confirm(`Take "${m.heard}" out of the miss log?`)) return;
        await api("/api/misses/drop", { method: "POST", body: { kind: m.kind, heard: m.heard } });
        route();
      }));
      const fix = canFix ? h("button", { type: "button", title: "Make it a test case expecting what happens today" }, "Test case") : null;
      if (fix) fix.addEventListener("click", busy(fix, msg, async () => {
        // its place in the log now (never a number from when the page was loaded)
        const fresh = await api("/api/misses");
        const at = fresh.misses.findIndex((x) => x.kind === m.kind && x.heard === m.heard);
        if (at < 0) throw new Error("That miss isn't in the log any more (reload the page)");
        await runTool("miss_fix", { miss: String(at + 1) }, output, status, "Make it a test case");
      }));
      return [h("tr", { class: m.engine === "gemini" ? "txn-off" : "" },
        h("td", { class: "txn-heard" }, m.heard),
        h("td", {}, m.assistant || "?"),
        h("td", { class: "num" }, String(m.count || 1)),
        h("td", { class: "quiet nowrap" }, m.first || ""),
        h("td", { class: "quiet nowrap" }, m.last || ""),
        h("td", { class: "small" }, `${decisionText({ path: m.path, topic: m.topic })} (${m.engine || "?"})`),
        h("td", { class: "txn-said" }, m.answer ? h("span", { class: "clamp", title: m.answer }, m.answer) : ""),
        h("td", {}, m.should_be ? h("strong", {}, m.should_be) : h("span", { class: "quiet" }, "-")),
        h("td", { class: "txn-actions" }, h("div", { class: "row-actions" }, note, fix, drop), msg)), under];
    });
    ebody.replaceChildren(...(rows.length ? rows : [h("tr", {}, h("td", { colspan: String(MISS_COLUMNS.length), class: "empty-state" }, "No misses recorded."))]));
  };
  drawE();
  return [h("h1", {}, "Misses"),
    h("h2", {}, "Mishearings"),
    h("p", { class: "quiet" }, "What speech-to-text heard, under what was really said: each intention is a band with its total, the ways it was heard under it, each counted, with the wrong words crossed out and the right ones beside them. They come from Misheard on the Transactions page, or by voice (\"What did you hear?\", then \"Record that as a misunderstanding\"). They stay, counting, until you drop them or they're taken into the words. Move files one under other words, count and all (Enter saves, Esc closes). Today says where the router sends each now, and whether the mishearing still matters. Use it on a difference (grainsplate → brain flea) swaps those heard words for the right ones before anything is decided, whenever they're heard, whole words only, and in the words handed back to Home Assistant too, so its own sentences match; Use a phrase swaps a run of words only when the whole run is heard (who taught you three → who taught you that), so a common word on its own is left alone. Use it on a common word changes it everywhere (watcher → washer would make \"Who is the watcher?\" \"Who is the washer?\"): use a phrase for those. The trace says when a swap happened."),
    swapsInUse(mh.swaps || [], mh.swap_days),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table mh-table" }, mhead, mbody)),
    h("h2", {}, "The wrong part answered"),
    h("p", { class: "quiet" }, "Recorded by voice: \"Who answered that?\", then \"Record that as a misunderstanding\". Off-Platform ones are tinted. Should be: what should have happened; Test case: what happens today becomes a test."),
    status, output,
    h("div", { class: "table-wrap" }, h("table", { class: "matrix txn-table" }, ehead, ebody))];
}

async function runTool(id, args, output, status, label) {
  try {
    const r = await api(`/api/tools/${id}`, { method: "POST", body: { args: args } });
    output.hidden = false;
    output.textContent = `$ ${r.cmd}\n`;
    followJob(r.job, output, status, { label: label, restart: false });
  } catch (e) { status.textContent = e.message; }
}

// ---------- Personality: flair ----------

async function flairPage() {
  const d = await api("/api/flair");
  const who = hashParam("who") || (d.personalities[0] || {}).name || "";
  const tab = ["sayings", "phrases"].includes(hashParam("tab")) ? hashParam("tab") : "main";
  const picker = h("div", { class: "pills" }, d.personalities.map((p) => h("a", { class: "pill", href: `#/flair?who=${p.name}${tab !== "main" ? `&tab=${tab}` : ""}`,
    "aria-pressed": p.name === who ? "true" : "false" }, p.name)));
  const tabs = h("div", { class: "tabs page-tabs", role: "tablist" }, [["main", "Persona Flair"], ["sayings", "Sayings"], ["phrases", "Phrases"]].map(([id, text]) =>
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
  if (tab === "sayings") return [...head, picker, await sayingsCard(who, isAdmin)];
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
    session = await api("/api/session");
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
      : [h("tr", {}, h("td", { colspan: String(BOOK_COLUMNS.length), class: "empty-state" }, "Empty. Comb the books on the Tools page to fill it again (lines already taken are left out)."))]));
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

// Her sayings: every fixed line she says (phrases/*.yaml), her own or the shared ones, editable here.
async function sayingsCard(who, isAdmin) {
  const d = await api("/api/phrases");
  const search = input("search", { placeholder: "find a saying (words in it, or its name: ask, coven, chores...)", "aria-label": "Find a saying" });
  const list = h("div", {});
  const pretty = (k) => k.replace(/_/g, " ");
  function editor(file, key, sec, whose, lines, after) {
    const rows = lines.map((x) => ({ text: x }));
    const box = errorBox();
    const body = h("div", { class: "say-rows" });
    const r = sec.rules;
    const draw = () => body.replaceChildren(...rows.map((row, i) => h("div", { class: "row say-row" },
      input("text", { value: row.text, disabled: !isAdmin, "aria-label": `${pretty(key)} line ${i + 1}`, oninput: (e) => { row.text = e.target.value; } }),
      hearButton(row.text.replace(/{\w+}/g, "something"), true),
      h("button", { type: "button", disabled: !isAdmin, "aria-label": "remove", onclick: () => { rows.splice(i, 1); draw(); } }, "×"))));
    draw();
    const add = h("button", { type: "button", disabled: !isAdmin, onclick: () => { rows.push({ text: rows.length ? "" : (lines[0] || "") }); draw(); body.lastChild && body.lastChild.querySelector("input").focus(); } }, "Add a line");
    const save = h("button", { type: "button", class: "primary", disabled: !isAdmin }, "Save");
    save.addEventListener("click", busy(save, box, async () => {
      const res = await api(`/api/phrases/${file}/${key}/${whose}`, { method: "PUT", body: { lines: rows.map((x) => x.text) } });
      sec.lines[whose] = res.lines;
      if (!res.lines.length) delete sec.lines[whose];
      box.replaceChildren(okNote("saved, in use now"));
      if (after) after();
    }));
    const rule = [r.needed.length ? `keep ${r.needed.map((x) => `{${x}}`).join(", ")}` : "",
      r.allowed.filter((x) => !r.needed.includes(x)).length ? `may use ${r.allowed.filter((x) => !r.needed.includes(x)).map((x) => `{${x}}`).join(", ")}` : "",
      r.question === true ? "ends with a question (it waits for your answer)" : r.question === false ? "never a question" : ""].filter(Boolean).join("; ");
    return h("div", { class: "say-editor" }, rule ? h("p", { class: "small quiet" }, rule) : null, body, h("div", { class: "row-actions" }, add, save, box));
  }
  function sectionFor(f, key) {
    const sec = f.sections[key];
    const own = f.personal ? (sec.lines[who] || null) : null;
    const shared = sec.lines.any || [];
    const slot = h("div", {});
    const draw = () => {
      const mine = f.personal ? (sec.lines[who] || null) : null;
      const sharedBlock = h("div", { class: "say-block say-shared-block" },
        h("p", { class: "small" }, h("strong", {}, "Shared, for everyone"),
          f.personal ? (mine ? ` (${who} says ${who}'s own instead; these are for anyone without their own)` : ` (${who} says these now)`) : " (an app's lines don't know who's speaking)"),
        editor(f.file, key, sec, "any", sec.lines.any || [], () => { draw(); tag.replaceChildren(countTag()); }));
      if (!f.personal) { slot.replaceChildren(sharedBlock); return; }
      const ownBlock = mine
        ? h("div", { class: "say-block say-own-block" }, h("p", { class: "small" }, h("strong", {}, `${who}'s own`), " (said instead of the shared ones; empty them all and save to go back to the shared ones)"),
            editor(f.file, key, sec, who, mine, () => { draw(); tag.replaceChildren(countTag()); }))
        : h("div", { class: "say-block say-own-block" }, h("p", { class: "small" }, h("strong", {}, `${who}'s own`), ": none yet."),
            h("button", { type: "button", disabled: !isAdmin, onclick: () => { sec.lines[who] = (sec.lines.any || []).slice(); draw(); } }, `Give ${who} own lines (starting from the shared ones)`));
      slot.replaceChildren(ownBlock, sharedBlock);
    };
    const countTag = () => h("span", { class: "small quiet" }, f.personal ? ((sec.lines[who] || []).length ? `${(sec.lines[who] || []).length} own, ${(sec.lines.any || []).length} shared` : `${(sec.lines.any || []).length} shared (in use)`) : `${(sec.lines.any || []).length} lines`);
    const tag = h("span", {}, countTag());
    const item = h("details", { class: "say-section", "data-find": `${key} ${pretty(key)} ${Object.values(sec.lines).flat().join(" ")} ${sec.note}`.toLowerCase() },
      h("summary", {}, h("strong", {}, pretty(key)), " ", tag, sec.note ? h("span", { class: "small quiet say-note" }, ` · ${sec.note}`) : null), slot);
    item.addEventListener("toggle", () => { if (item.open && !slot.childNodes.length) draw(); }, { once: false });
    void own;
    return item;
  }
  for (const f of [...d.files].sort((a, b) => (b.personal - a.personal) || a.file.localeCompare(b.file))) {
    const fileBox = h("div", { class: "say-filebox" }, h("h3", { class: "say-file" }, f.personal ? "The router's own replies" : `The ${pretty(f.file)} app's replies`));
    for (const part of f.parts) {
      fileBox.append(h("div", { class: "say-partbox" }, h("p", { class: "say-part small" }, part.title), ...part.sections.map((k) => sectionFor(f, k))));
    }
    list.append(fileBox);
  }
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    for (const el of list.querySelectorAll(".say-section")) {
      const hit = !q || el.dataset.find.includes(q);
      el.hidden = !hit;
      if (q && hit && !el.open) { el.open = true; }
    }
    // a heading with nothing found under it steps aside
    for (const box of list.querySelectorAll(".say-partbox, .say-filebox")) box.hidden = !box.querySelector(".say-section:not([hidden])");
  });
  // the words she uses for asking around: so "yes, check with the coven" counts as a yes
  let asking = d.about_asking.slice();
  const askMsg = h("span", { class: "small" });
  const askSave = h("button", { type: "button", disabled: !isAdmin }, "Save the asking words");
  askSave.addEventListener("click", busy(askSave, askMsg, async () => {
    await api("/api/phrases/asking", { method: "PUT", body: { words: asking } });
    askMsg.replaceChildren(okNote("Saved. Restart to use them."));
  }));
  return h("details", { class: "card panel fold flair-card flair-sayings" }, h("summary", {}, h("h2", {}, "Sayings")),
    h("p", { class: "quiet small" }, `Every fixed line the router says, from "Shall I check with my coven?" to "Plus 3 more.": the router says these itself, never Home Assistant. Pick a saying, give ${who} own lines or change the shared ones, and save: in use at once. Each says what it must keep ({heard} is the words that were heard) and whether it's a question.`),
    h("div", { class: "say-asking" }, h("strong", { class: "small" }, "Words for asking around"),
      h("p", { class: "small quiet" }, "When it offers to ask around, \"yes, check with the coven\" counts as a yes only if its asking word is here. Add the words your lines use (coven, cauldron, winds...)."),
      chipList(asking, (v) => { asking = v; }), h("div", { class: "row-actions" }, askSave, askMsg)),
    search, list);
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

// ---------- Connect: integrations ----------

async function integrationsPage() {
  const d = await api("/api/integrations");
  const isAdmin = allowed("tools");
  const ha = d.home_assistant || {};
  const items = [
    { id: "oread", title: "Oread", what: "who spoke", on: d.oread.enabled,
      where: d.oread.source === "wyoming" ? `in the audio path, ${(d.oread.wyoming || {}).host || "?"}` : (d.oread.url || ""),
      card: (det) => oreadCard(d.oread, isAdmin, det) },
    { id: "home_assistant", title: "Home Assistant", what: "its People, Veil Guard Service's satellites", on: Boolean(ha.url),
      where: ha.url || "not set", card: () => haCard(ha, isAdmin) },
    ...Object.entries(d.services).map(([name, sv]) => ({ id: name, title: sv.title || name,
      what: sv.topics.length ? `answers ${sv.topics.join(", ")}` : `${sv.kind} service`, on: sv.enabled, where: sv.url || "",
      ver: sv.app_version, card: () => serviceCard(name, sv, isAdmin) })),
    { id: "litellm", title: "LiteLLM", what: "the way Off-Platform", on: true, where: d.litellm.url || "",
      card: () => litellmCard(d.litellm, isAdmin) },
  ];
  const want = hashParam("open") || "";
  const open = items.find((x) => x.id === want);
  const det = open ? await api(`/api/integrations/${encodeURIComponent(open.id)}/details`).catch(() => null) : null;
  const list = h("ul", { class: "rows integration-list" }, items.map((x) => h("li", { class: x === open ? "current" : null },
    h("span", {}, h("strong", {}, x.title), " ", h("span", { class: "quiet small" }, x.what),
      versionFlag(x.ver || (x.id === "oread" ? d.oread.app_version : null), x.title)),
    h("span", { class: "small quiet where" }, x.where),
    h("span", {}, onOff(x.on), " ",
      h("a", { class: "button-link", href: x === open ? "#/integrations" : `#/integrations?open=${encodeURIComponent(x.id)}`,
        "aria-expanded": x === open ? "true" : "false" }, x === open ? "Close" : "Open")))));
  // an address kept being refused lately (a program at a new address: Home Assistant after a power cut)
  const listName = { inbound_allowed: "coming in", admin_allowed: "the pages", outbound_allowed: "going out" };
  const refused = (d.refused || []).length ? h("div", { class: "card warn-box", role: "alert" },
    h("strong", {}, `Refused in the last ${d.refused_minutes} minutes`),
    h("ul", {}, d.refused.map((r) => h("li", {}, `${r.address}, ${r.what} (${listName[r.list] || r.list}): ${r.n} time${r.n === 1 ? "" : "s"}, last ${when(r.last)}`,
      r.before ? `. That door was used from ${r.before} before: the same program at a new address?` : "."))),
    h("p", { class: "small" }, "If it's one of these programs, permit its address on the Security page (or give it its old address back).")) : null;
  return [h("h1", {}, "Integrations"), refused,
    h("p", { class: "quiet" }, "What the router talks to. Open one to change it or test it. Switching one off takes its topics with it. Secrets (tokens) are set on the Security page, in the vault, or in .env; here you see only where each comes from."),
    h("section", { class: "card panel" }, list),
    isAdmin ? lazyView(addAppForm) : null,
    open ? integrationView(open, det, d, isAdmin) : null];
}

// Every integration opens the same way: its connection, how it and the router ask each other,
// and, when it has them, its options, its clean-up words and its voice map (an app we didn't write).
// Every app is laid out the same way: the same tabs, in the order of adding an app. A Wepwawet
// compliant app says in its spec (x-wepwawet: tabs:) which don't apply to it: those show grayed
// out. An app that isn't compliant has them all open (the router can't know).
const APP_TABS = [["connection", "Connection", null], ["talks", "URL / ports", null], ["commands", "Commands", "commands"],
  ["map", "Voice map", "voice_map"], ["rules", "User rules", "voice_map"], ["words", "Clean-up words", "clean_up"], ["options", "Defaults", null], ["ready", "Getting ready", null]];
function integrationView(x, det, d, isAdmin) {
  det = det || { options: {}, language: {}, actions: [], doors: [] };
  const sv = d.services[x.id];
  const w = det.wepwawet || null;
  const title = det.title || x.title;
  const wt = (w && w.tabs) || {};
  const off = (key, tab) => {
    if (tab === "options") return w && wt.lists === false && wt.options === false && !(det.offers || []).length ? "its Wepwawet section says it has no lists, options or offers" : null;
    if (tab === "ready") return sv ? null : "for apps answered through (a service)";
    return key && w && wt[key] === false ? `doesn't apply to ${title} (its Wepwawet section)` : null;
  };
  const views = APP_TABS.map(([v, label, key]) => ({ v, label, why: off(key, v) }));
  const want = hashParam("view");
  const view = views.some((t) => t.v === want && !t.why) ? want : "connection";
  const tabs = h("div", { class: "tabs", role: "tablist" }, views.map((t) => h("button", { role: "tab", "aria-selected": t.v === view ? "true" : "false",
    "aria-disabled": t.why ? "true" : null, class: t.why ? "tab-off" : null, title: t.why || null,
    onclick: () => { if (!t.why) location.hash = `#/integrations?open=${encodeURIComponent(x.id)}&view=${t.v}`; } }, t.label)));
  const x2 = Object.assign({}, x, { title: title });
  const body = view === "talks" ? talksView(x2, det, d, isAdmin) : view === "options" ? optionsView(x2, det, isAdmin)
    : view === "words" ? wordsView(x2, det, isAdmin) : view === "map" ? (det.connector ? mapView(x2, det, isAdmin) : emptyTab(`${title} has no voice map (connectors/${x.id}.yaml): nothing is said to it through the router.`))
      : view === "rules" ? (det.connector ? userRulesView(x2, det, isAdmin) : emptyTab(`${title} has no voice map (connectors/${x.id}.yaml): rules are spoken through it.`))
      : view === "commands" ? lazyView(() => commandsView(x2, isAdmin)) : view === "ready" ? lazyView(() => readyView(x2)) : x.card(det);
  return h("section", { class: "integration-view" }, h("h2", { class: "band" }, title,
    w ? h("span", { class: "pill-ok small wep-badge", title: `Its spec carries the Wepwawet section (version ${w.version})` }, ` Wepwawet compliant`) : null), tabs, h("div", { class: "gap-top" }, body));
}

function emptyTab(text) { return h("section", { class: "card panel" }, h("p", { class: "quiet" }, text)); }

function talksView(x, det, d, isAdmin) {
  const key = x.id === "litellm" ? { name: d.litellm.key_name, from: d.litellm.key_from }
    : x.id === "home_assistant" ? { name: d.home_assistant.token, from: d.home_assistant.token_from }
      : x.id === "oread" ? { name: d.oread.token, from: d.oread.token_from }
        : d.services[x.id] && d.services[x.id].secret ? { name: d.services[x.id].secret, from: d.services[x.id].secret_from } : null;
  const ports = x.id === "home_assistant" ? Object.entries(((d.oread || {}).wyoming || {}).devices || {}) : [];
  const keysLink = (side) => h("a", { href: `#/security?tab=keys&side=${side}` }, "Security, API keys");
  return [
    h("section", { class: "card panel" }, h("h3", {}, "The router asks it"),
      h("dl", { class: "kv" }, h("dt", {}, "Where"), h("dd", {}, x.where || "-"),
        h("dt", {}, "Its key (a grantor)"), h("dd", {}, key && key.name ? [h("code", {}, key.name), " ", h("span", { class: key.from ? "pill-ok" : "pill-bad" }, key.from ? `from ${key.from}` : "not set"), " · ", keysLink("grantors")] : "none needed"))),
    h("section", { class: "card panel" }, h("h3", {}, "It asks the router"),
      det.doors.length || ports.length ? h("ul", { class: "rows" },
        det.doors.map((door) => h("li", {}, h("span", {}, h("strong", {}, `the ${door.name} door`), " ", h("span", { class: "quiet small" }, door.description), " ",
          ...door.paths.map((p) => [h("code", {}, p), " "])), h("span", {}, h("span", { class: door.locked ? "pill-ok" : "pill-off" }, door.locked ? "locked: needs its token" : "open"), " · ", keysLink("grantees")))),
        ports.map(([who, p]) => h("li", {}, h("span", {}, h("strong", {}, `${who}'s speech`), " ", h("span", { class: "quiet small" }, `the router's Wyoming port ${p.listen}, passed on to Oread's ${p.oread}`)),
          h("span", { class: "quiet small" }, "permitted by Addresses (coming in)")))) :
        h("p", { class: "quiet small" }, "Nothing: only the router asks it. When it starts asking the router something, add a door for it (Security, API keys), with program: its name.")),
    specPart(x, det, isAdmin)];
}

// Where an app's spec (its OpenAPI document) is: read on its Commands tab, and where a Wepwawet
// compliant app says how it fits the router.
function specPart(x, det, isAdmin) {
  if (!("spec" in det)) return null;
  const spec = input("text", { value: det.spec || "", placeholder: "http://<server>:<port>/openapi.json", "aria-label": "its spec's address" });
  const box = errorBox();
  const save = h("button", { type: "button", disabled: true }, "Save");
  spec.addEventListener("input", () => { save.disabled = !isAdmin; });
  save.addEventListener("click", busy(save, box, async () => {
    await api(`/api/integrations/${encodeURIComponent(x.id)}`, { method: "PATCH", body: { spec: spec.value.trim() } });
    save.disabled = true; save.after(okNote("Saved. Read it on the Commands tab."));
  }));
  return h("section", { class: "card panel" }, h("h3", {}, "Its spec (OpenAPI)"),
    h("p", { class: "quiet small" }, `Where ${x.title} describes its own commands. Read on the Commands tab; a Wepwawet compliant app also says there which tabs apply, what it offers and its lists.`),
    h("div", { class: "row-actions" }, spec, save, box),
    det.wepwawet ? h("p", { class: "small" }, h("span", { class: "pill-ok" }, "Wepwawet compliant"), ` version ${det.wepwawet.version}${det.wepwawet.role ? `, ${det.wepwawet.role}` : ""}.`)
      : h("p", { class: "quiet small" }, det.commands ? "Its spec has no Wepwawet section: every tab stays open." : "Not read yet."));
}

// Defaults and options: the values an app uses when nothing is said (who "me" is, the default
// project) and its knobs. Each value is typed by hand, or picked from an app's answer (this app's
// or any other connected app's: a command that lists things, and the field to take). Its people
// are a section here when it has them: where they come from, and who each is in the house.
function optionsView(x, det, isAdmin) {
  const id = encodeURIComponent(x.id);
  const people = "commands" in det ? lazyView(() => listsPart(x, isAdmin)) : null;     // apps we didn't write
  const rows = Object.entries(det.options).map(([k, v]) => optionRow(x, det, k, v, isAdmin));
  const offers = (det.offers || []).length ? offersPart(x, det, isAdmin) : null;
  return h("section", { class: "card panel" },
    h("p", { class: "quiet small" }, `What ${x.title} offers, what it uses when nothing is said, and its knobs. A value is typed here, or picked from what an app answers (Comes from). Each saves on its own; the router uses it after a restart.`),
    offers, people,
    rows.length ? h("h3", {}, "Defaults and knobs") : null, rows);
}

function optionRow(x, det, k, v, isAdmin) {
  const id = encodeURIComponent(x.id);
  const box = errorBox();
  const src = (det.options_from || {})[k] || null;
  const isText = typeof v === "string";
  let el = typeof v === "boolean" ? h("input", { type: "checkbox", checked: v, "aria-label": k })
    : input(typeof v === "number" ? "number" : "text", { value: String(v), step: "any", "aria-label": k });
  const holder = h("span", {}, el);
  const save = h("button", { type: "button", disabled: !isAdmin }, "Save");
  // where its value comes from (text values only): typed, or an app's answer
  const sources = det.sources || [];
  const appSel = select([{ value: "", label: "typed here" }].concat(sources.map((a) => ({ value: a.app, label: `${a.title}'s answer` }))), src ? src.app : "", { "aria-label": `${k} comes from` });
  const cmdSel = h("select", { "aria-label": "its command" });
  const fieldSel = h("select", { "aria-label": "the field" });
  const fill = (sel, opts, cur) => { sel.replaceChildren(...opts.map((o) => h("option", { value: o.value, selected: o.value === cur }, o.label))); };
  const showValues = async () => {
    if (!appSel.value || !cmdSel.value || !fieldSel.value) { holder.replaceChildren(el); return; }
    try {
      const r = await api(`/api/integrations/${id}/choices?app=${encodeURIComponent(appSel.value)}&api=${encodeURIComponent(cmdSel.value)}&field=${encodeURIComponent(fieldSel.value)}`);
      const vals = r.values.includes(String(el.value)) || !el.value ? r.values : [String(el.value)].concat(r.values);
      const pick = select(vals.map((w) => ({ value: w, label: w === String(v) && !r.values.includes(w) ? `${w} (not in its answer now)` : w })), String(el.value || v), { "aria-label": k });
      pick.addEventListener("change", () => { el.value = pick.value; });
      holder.replaceChildren(pick);
    } catch (e) { holder.replaceChildren(el, h("span", { class: "error small" }, ` ${e.message}`)); }
  };
  const drawCmds = () => {
    const a = sources.find((y) => y.app === appSel.value);
    cmdSel.hidden = fieldSel.hidden = !a;
    if (!a) { holder.replaceChildren(el); return; }
    fill(cmdSel, a.commands.map((c) => ({ value: c.api, label: `${c.api}${c.summary ? " - " + c.summary : ""}` })), src && src.app === a.app ? src.api : (a.commands[0] || {}).api);
    drawFields();
  };
  const drawFields = () => {
    const a = sources.find((y) => y.app === appSel.value);
    const c = a && a.commands.find((y) => y.api === cmdSel.value);
    fill(fieldSel, (c ? c.returns : []).map((f) => ({ value: f, label: f })), src && src.api === cmdSel.value ? src.field : ((c && (c.returns.find((f) => /name|title/i.test(f)))) || ""));
    showValues();
  };
  appSel.addEventListener("change", drawCmds);
  cmdSel.addEventListener("change", drawFields);
  fieldSel.addEventListener("change", showValues);
  if (isText) setTimeout(drawCmds, 0);
  save.addEventListener("click", busy(save, box, async () => {
    const value = typeof v === "boolean" ? el.checked : typeof v === "number" ? Number(el.value) : el.value;
    const body = { key: k, value: value };
    if (isText) body.from = appSel.value ? { app: appSel.value, api: cmdSel.value, field: fieldSel.value } : null;
    await api(`/api/integrations/${id}/options`, { method: "PATCH", body: body });
    save.after(okNote("Saved. Restart to use it."));
  }));
  return h("div", { class: "setting" }, h("div", {}, h("strong", {}, k.replace(/_/g, " ")), " ", h("code", { class: "quiet small" }, k),
    det.option_notes[k] ? h("p", { class: "hint" }, det.option_notes[k]) : null),
    h("div", { class: "option-value" }, holder,
      isText && sources.length ? h("div", { class: "option-from" }, h("span", { class: "quiet small" }, "Comes from "), appSel, cmdSel, fieldSel) : null),
    h("div", {}, save, box));
}

// What a Wepwawet compliant app offers the router (its x-wepwawet: offers:), each a switch and,
// when there's more than one, its way.
function offersPart(x, det, isAdmin) {
  return h("section", { class: "lists-part" }, h("h3", {}, "What it offers"),
    h("p", { class: "quiet small" }, `From ${x.title}'s own spec (its Wepwawet section). Off until you switch it on.`),
    det.offers.map((o) => {
      const on = h("input", { type: "checkbox", checked: o.on, disabled: !isAdmin, "aria-label": o.title });
      const ways = Object.entries(o.ways || {});
      const way = ways.length ? select(ways.map(([k, label]) => ({ value: k, label: label })), o.way || ways[0][0], { "aria-label": `${o.title}: its way`, disabled: !isAdmin }) : null;
      const box = errorBox();
      const save = h("button", { type: "button", disabled: true }, "Save");
      const dirty = () => { save.disabled = !isAdmin; };
      on.addEventListener("change", dirty);
      if (way) way.addEventListener("change", dirty);
      save.addEventListener("click", busy(save, box, async () => {
        await api(`/api/integrations/${encodeURIComponent(x.id)}/offers`, { method: "PATCH", body: { key: o.key, on: on.checked, way: way ? way.value : null } });
        save.disabled = true; save.after(okNote("Saved. Restart to use it."));
      }));
      return h("div", { class: "setting" }, h("div", {}, h("label", { class: "check" }, on, " ", h("strong", {}, o.title)), o.description ? h("p", { class: "hint" }, o.description) : null),
        way ? field("Comes", way) : h("span", {}), h("div", {}, save, box));
    }));
}

// An app's lists, each a card you name (people, project...): where its items come from (one of
// the app's commands, and the fields that are an item's id and name), its default, and for people,
// which voice each is, the other names each voice is heard by in this app, and who "me" is.
async function listsPart(x, isAdmin) {
  const id = encodeURIComponent(x.id);
  const d = await api(`/api/integrations/${id}/lists`);
  const cards = d.words.map((w) => listCardFold(x, d, w, isAdmin, false));
  const word = input("text", { placeholder: "a word, like label", "aria-label": "the new list's word" });
  const box = errorBox();
  const add = h("button", { type: "button", disabled: !isAdmin || !d.choices.length }, "Add a list");
  add.addEventListener("click", () => {
    const w = word.value.trim().toLowerCase();
    if (!/^[a-z][a-z0-9_]{0,30}$/.test(w)) { box.textContent = "A list's word is one short word, like label"; return; }
    if (d.words.includes(w)) { box.textContent = `There's already a list called ${w}`; return; }
    box.textContent = "";
    d.words.push(w);
    add.closest(".lists-part").insertBefore(listCardFold(x, d, w, isAdmin, true), add.closest(".row-actions"));
    word.value = "";
  });
  return h("section", { class: "lists-part" }, h("h3", {}, "Lists"),
    h("p", { class: "quiet small" }, `The lists of ${x.title}'s own that the router uses, each a card you name. Each says where its items come from, and its default (used when none is said). A list of people also says who each is in the house. The voice map's fields name the list they fill.`),
    d.choices.length ? null : h("p", { class: "warn small" }, "Read its spec first (Commands): its lists come from its commands."),
    ...cards, h("div", { class: "row-actions" }, word, add, box));
}

function listCardFold(x, d, word, isAdmin, open) {
  const body = h("div", {}, h("p", { class: "quiet" }, "Loading…"));
  const det = h("details", { class: "card panel fold list-card", open: open || null },
    h("summary", {}, h("h3", {}, word), h("span", { class: "quiet small list-sum" }, "")), body);
  const load = (trial) => listCard(x, d, word, isAdmin, trial, det).then((el) => body.replaceChildren(el)).catch((e) => body.replaceChildren(h("p", { class: "error" }, e.message)));
  det._reload = load;
  load(null);
  return det;
}

async function listCard(x, d, word, isAdmin, trial, det) {
  const id = encodeURIComponent(x.id);
  const q = trial ? `?source=${encodeURIComponent(trial.from)}&id=${encodeURIComponent(trial.id)}&label=${encodeURIComponent(trial.name)}` : "";
  const r = await api(`/api/integrations/${id}/lists/${encodeURIComponent(word)}${q}`);
  const c = r.card || {};
  const sum = det.querySelector(".list-sum");
  if (sum) sum.textContent = ` ${c.from || "not set up"}${c.default ? `; default ${c.default}` : "; no default"}${r.used_by.length ? `; fills ${r.used_by.join(", ")}` : ""}`;
  const cmd = select([{ value: "", label: "pick a command" }].concat(d.choices.map((y) => ({ value: y.api, label: `${y.api}${y.summary ? " - " + y.summary : ""}` }))), c.from || "", { "aria-label": `the command that lists the ${word}` });
  const idSel = h("select", { "aria-label": "the field that is an item's id" });
  const nameSel = h("select", { "aria-label": "the field that is an item's name" });
  const fields = () => {
    const y = d.choices.find((z) => z.api === cmd.value) || { returns: [] };
    const pick = (sel, cur, guess) => sel.replaceChildren(...[""].concat(y.returns).map((f) => h("option", { value: f, selected: f === (cur || y.returns.find((g) => guess.test(g)) || "") }, f || "pick a field")));
    pick(idSel, c.id, /^(user)?id$/i);
    pick(nameSel, c.name, /display|^name$|title/i);
  };
  fields();
  cmd.addEventListener("change", fields);
  const house = select([{ value: "", label: "nothing in the house (like projects)" }, { value: "people", label: "people in the house" }], c.house || (word === "people" ? "people" : ""), { "aria-label": "what its items are here" });
  const tryBtn = h("button", { type: "button" }, "List them");
  tryBtn.addEventListener("click", () => det._reload({ from: cmd.value, id: idSel.value, name: nameSel.value }));
  const isPeople = () => house.value === "people";
  // the default: a person in the house (people), or one of its items
  const defOpts = () => isPeople()
    ? [{ value: "", label: "none" }].concat(d.household.map((m) => ({ value: m.key, label: m.say_as })))
    : [{ value: "", label: "none" }].concat(r.items.map((i) => ({ value: i.name, label: i.name })), c.default && !r.items.some((i) => i.name === c.default) ? [{ value: c.default, label: `${c.default} (not in its list now)` }] : []);
  const def = select(defOpts(), c.default || (isPeople() && !r.exists ? d.house_default || "" : ""), { "aria-label": `the default ${word}` });
  const me = select([{ value: "default", label: "the default voice" }, { value: "speaker", label: "whoever the voice ID is sure spoke" }], c.me || "default", { "aria-label": "who me means" });
  const who = {};
  const opts = [{ value: "", label: "nobody in the house" }].concat(d.household.map((m) => ({ value: m.key, label: m.key })));
  // other names each voice is heard by in what's said to this app ("for Sam"): names: on the card
  const otherNames = {};
  for (const m of d.household) otherNames[m.key] = (((c.names || {})[m.key]) || m.names || []).slice();
  const namesBox = h("div", {});
  const drawNames = () => namesBox.replaceChildren(...(isPeople() ? [h("h3", {}, "Other names each voice is heard by"),
    h("p", { class: "hint" }, "Said to this app, like \"for Sam\" or \"my\". The voice's own name always counts.")]
    .concat(d.household.map((m) => h("div", { class: "row" }, h("strong", {}, m.key), chipList(otherNames[m.key], (v) => { otherNames[m.key] = v; })))) : []));
  const mapTable = h("div", {});
  const drawMap = () => {
    for (const k of Object.keys(who)) delete who[k];
    mapTable.replaceChildren(isPeople() && r.items.length ? stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, [`In ${x.title}`, "Its id", "Which voice"].map((t) => h("th", {}, t)))),
      h("tbody", {}, r.items.map((m) => {
        const sel = select(opts, m.household, { "aria-label": `who ${m.name} is` });
        who[m.id] = sel;
        return h("tr", {}, h("th", { scope: "row" }, m.name), h("td", {}, h("code", {}, m.id)),
          h("td", {}, sel, m.suggested ? h("span", { class: "hint" }, "matched by name: check it, then save") : null));
      }))))) : (!isPeople() && r.items.length ? h("p", { class: "small" }, `Its ${word} now: ${r.items.map((i) => i.name).join(", ")}`) : ""));
  };
  const meField = field("Who \"me\" and \"my\" mean", me, "With the voice ID on: \"what's on my list?\" reads the list of whoever spoke.");
  // a list of things (not people): the kinds kept out (skip), how much each matters (weight), and the app's
  // list of what should be (defined: a thing defined there but left out of this list was superseded)
  const returns = () => (d.choices.find((z) => z.api === cmd.value) || { returns: [] }).returns;
  const fieldSel = (cur, label) => select([{ value: "", label: "none" }].concat(returns().map((f) => ({ value: f, label: f }))), cur || "", { "aria-label": label });
  const skipBox = h("textarea", { rows: "2", class: "words-box", "aria-label": "kept out: field = value, one a line" });
  skipBox.value = Object.entries(c.skip || {}).map(([k, v]) => `${k} = ${v}`).join("\n");
  const w = c.weight || {};
  const wField = fieldSel(w.field, "the field for how much each matters");
  const wHigher = input("checkbox", { checked: w.higher !== false, "aria-label": "higher matters more" });
  const wFrom = input("number", { value: w.from ?? "", "aria-label": "worth it from" });
  const wWords = fieldSel(w.words, "the field that says how much in words");
  const df = c.defined || {};
  const dFrom = select([{ value: "", label: "none" }].concat(d.choices.map((y) => ({ value: y.api, label: y.api }))), df.from || "", { "aria-label": "the command that lists what should be" });
  const dMonth = input("text", { value: df.month || "", placeholder: "month", "aria-label": "its month field" });
  const dDay = input("text", { value: df.day || "", placeholder: "day", "aria-label": "its day field" });
  const thingsBox = h("div", { hidden: isPeople() },
    h("div", { class: "grid3" }, field("Kept out", skipBox, "field = value, one a line (is_vigil_mass = true)"),
      field("How much each matters", h("span", {}, wField, h("label", { class: "check" }, wHigher, " higher first")), "The field, and whether a higher value comes first"),
      field("Worth it from", wFrom, "Kept only from this value (empty: all)")),
    h("div", { class: "grid3" }, field("Said in words by", wWords, "A field that says it in words (solemnity)"),
      field("What should be", dFrom, "The app's list of every thing with its usual day: one left out of this list was superseded, and the persona says so"),
      field("Its usual month and day", h("span", {}, dMonth, " ", dDay))));
  const value = (v) => v === "true" ? true : v === "false" ? false : v !== "" && !Number.isNaN(Number(v)) ? Number(v) : v;
  const meApplies = () => isPeople() && r.used_by.length > 0;      // "me" matters only where the voice map fills a who from it
  const showPeople = () => { meField.hidden = !meApplies(); thingsBox.hidden = isPeople(); def.replaceChildren(...defOpts().map((o) => h("option", { value: o.value, selected: o.value === (c.default || "") }, o.label))); drawMap(); drawNames(); };
  house.addEventListener("change", showPeople);
  drawMap();
  drawNames();
  meField.hidden = !meApplies();
  const box = errorBox();
  const save = h("button", { type: "button", class: "primary", disabled: !isAdmin }, "Save the list");
  save.addEventListener("click", busy(save, box, async () => {
    const map = {};
    for (const [k, sel] of Object.entries(who)) map[k] = sel.value;
    const skip = {};
    for (const l of skipBox.value.split("\n")) { const [a, ...b] = l.split("="); if (a.trim()) skip[a.trim()] = value(b.join("=").trim()); }
    const weight = wField.value ? { field: wField.value, higher: wHigher.checked, from: wFrom.value === "" ? null : Number(wFrom.value), words: wWords.value } : {};
    const defined = dFrom.value ? { from: dFrom.value, month: dMonth.value.trim() || "month", day: dDay.value.trim() || "day" } : {};
    await api(`/api/integrations/${id}/lists/${encodeURIComponent(word)}`, { method: "PUT",
      body: { from: cmd.value, id: idSel.value, name: nameSel.value, house: house.value, default: def.value, me: me.value, map: map, names: otherNames,
        skip: isPeople() ? {} : skip, weight: isPeople() ? {} : weight, defined: isPeople() ? {} : defined } });
    save.after(okNote("Saved. Restart to use it."));
  }));
  const del = r.exists && isAdmin ? h("button", { type: "button", onclick: async () => {
    if (!confirm(`Take the ${word} list out?`)) return;
    try { await api(`/api/integrations/${id}/lists/${encodeURIComponent(word)}`, { method: "DELETE" }); det.remove(); } catch (e) { box.textContent = e.message; }
  } }, "Take it out") : null;
  return h("div", {},
    h("div", { class: "grid3" }, field("Its items come from", cmd), field("An item's id is", idSel), field("An item's name is", nameSel)),
    h("div", { class: "grid3" }, field("Its items are", house), field(isPeople() ? "Default person" : `Default ${word}`, def, "Used when none is said. None: left out (later it may ask)."), meField),
    h("div", { class: "row-actions" }, tryBtn),
    r.detail ? h("p", { class: "warn small" }, r.detail) : null,
    isPeople() && !r.saved_map && r.items.length ? h("p", { class: "small" }, "Not saved yet: matched by name, the way it worked before. Change any, then save.") : null,
    thingsBox,
    mapTable,
    namesBox,
    r.used_by.length ? h("p", { class: "quiet small" }, `The voice map fills ${r.used_by.join(", ")} from it.`) : null,
    h("div", { class: "row-actions" }, save, del, box));
}

function wordsView(x, det, isAdmin) {
  return h("section", { class: "card panel" },
    det.connector ? h("p", { class: "quiet small" }, `The words ${x.title}'s helper uses to clean up what was said before it calls the app, from ${det.connector} (language:). One word or phrase a line; for a matched list, "word = what it means". Each list saves on its own, comments kept; used after a restart.`) : null,
    Object.keys(det.language).length ? null : h("p", { class: "quiet" }, `${x.title} has no clean-up words (only an app whose helper cleans up what was said has them).`),
    Object.entries(det.language).map(([k, v]) => {
      const box = errorBox();
      const isMap = !Array.isArray(v);
      const area = h("textarea", { rows: String(Math.min(12, Math.max(3, isMap ? Object.keys(v).length : Math.ceil(v.length / 6)))), "aria-label": k, class: "words-box" });
      area.value = isMap ? Object.entries(v).map(([a, b]) => `${a} = ${b}`).join("\n") : v.join("\n");
      const save = h("button", { type: "button", disabled: !isAdmin }, "Save");
      save.addEventListener("click", busy(save, box, async () => {
        let value;
        if (isMap) {
          value = {};
          for (const l of area.value.split("\n")) { const [a, ...b] = l.split("="); if (a.trim()) value[a.trim()] = b.join("=").trim(); }
        } else value = area.value.split("\n").map((l) => l.trim()).filter(Boolean);
        await api(`/api/integrations/${encodeURIComponent(x.id)}/language`, { method: "PUT", body: { key: k, value: value } });
        save.after(okNote("Saved. Restart to use it."));
      }));
      return h("details", { class: "card panel fold" }, h("summary", {}, h("h3", {}, k.replace(/_/g, " ")), h("span", { class: "quiet small" }, ` ${isMap ? Object.keys(v).length : v.length} ${isMap ? "pairs" : "words"}`)),
        det.language_notes[k] ? h("p", { class: "hint" }, det.language_notes[k]) : null, area, h("div", { class: "row-actions" }, save, box));
    }));
}

// A tab whose content is fetched when it opens.
function lazyView(make) {
  const box = h("div", {}, h("p", { class: "quiet" }, "Loading…"));
  make().then((el) => box.replaceChildren(...[].concat(el))).catch((e) => box.replaceChildren(h("p", { class: "error" }, e.message)));
  return box;
}

async function readyView(x) {
  const r = await api(`/api/integrations/${encodeURIComponent(x.id)}/ready`);
  return h("section", { class: "card panel" },
    h("p", { class: r.ready ? "status-line ok-line" : "status-line warn" }, icon(r.ready ? "check" : "alert"),
      r.ready ? "Ready: switch it on (Connection) and restart." : "Not ready yet: the steps not done are below."),
    h("ol", { class: "ready-steps" }, r.steps.map((st) => h("li", { class: st.done ? "done" : "todo" },
      h("span", { class: st.done ? "pill-ok" : "pill-bad" }, st.done ? "done" : "to do"), " ", h("strong", {}, st.step),
      h("p", { class: "hint" }, st.how)))),
    h("p", { class: "quiet small" }, "The whole routine is in the coder's guide (Guides), \"Adding an app we didn't write\"."));
}

const MARKS = { add: "(ADD)", modified: "(Modified)", deleted: "(Deleted)" };

// The app's version as its own spec says it (info: version:): when its commands were accepted,
// and at the latest read. Nothing about any one app: an app whose spec names none says so.
function versionFlag(v, title) {
  if (!v || !v.version_changed) return null;
  return h("span", { class: "status-line warn small" }, icon("alert"),
    ` ${title} changed from ${v.version || "no version"} to ${v.running || "no version"}: look at its Commands`);
}
function versionLine(r, title) {
  if (!r.saved) return null;
  const said = (v) => (v ? `version ${v}` : "no version in its spec");
  const parts = [`Commands accepted at ${said(r.version)}.`,
    r.checked_at ? ` Running now (read ${r.checked_at}): ${said(r.running)}.` : " Read its spec again to see what it runs now."];
  return r.version_changed
    ? h("p", { class: "status-line warn" }, icon("alert"), ` ${title} has changed since its commands were accepted. `, ...parts,
      " An update can change what a command does even when the list looks the same: try what it does by voice, then accept.")
    : h("p", { class: "quiet small" }, ...parts);
}
async function commandsView(x, isAdmin) {
  const r = await api(`/api/integrations/${encodeURIComponent(x.id)}/commands`);
  const id = encodeURIComponent(x.id);
  const box = errorBox();
  const readBtn = h("button", { type: "button", class: r.saved ? null : "primary" }, r.saved ? "Read its spec again" : "Read its spec");
  readBtn.addEventListener("click", busy(readBtn, box, async () => {
    const got = await api(`/api/integrations/${id}/commands/read`, { method: "POST" });
    if (!got.first && !got.changes && !got.version_changed && !got.key_change) { box.replaceWith(okNote(`No changes: the spec still lists the same ${got.count} commands${got.running ? ` at version ${got.running}` : ""}.`)); return; }
    route();
  }));
  const accept = h("button", { type: "button", class: "primary" }, "Accept the changes");
  accept.addEventListener("click", busy(accept, box, async () => { await api(`/api/integrations/${id}/commands/accept`, { method: "POST" }); route(); }));
  const discard = h("button", { type: "button" }, "Keep the saved list");
  discard.addEventListener("click", busy(discard, box, async () => { await api(`/api/integrations/${id}/commands/discard`, { method: "POST" }); route(); }));
  const changed = r.commands.filter((c) => c.mark !== "same");
  const lostUsed = r.commands.filter((c) => c.mark === "deleted" && c.actions.length);
  const used = r.commands.filter((c) => c.actions.length && c.mark !== "deleted").length;
  const intro = r.saved
    ? `${r.title || x.title}'s own commands, read from its spec (${r.read_from}) and accepted ${r.accepted}: ${r.commands.filter((c) => c.mark !== "add").length}, of which the voice map calls ${used}. They are the voice map's Calls choices. Read the spec again after the app is updated: what changed is marked on its row, and nothing changes until you accept.`
    : "Not read yet. Read its spec: every command the app lists is kept here, and they become the voice map's Calls choices.";
  const head = h("div", { class: "row-actions" }, isAdmin ? readBtn : null, box);
  const pending = r.pending ? h("div", { class: "status-line warn" }, icon("alert"),
    changed.length ? `${changed.length} change${changed.length === 1 ? "" : "s"} since the saved list. ` : "The same commands, at a new version. ",
    lostUsed.length ? h("strong", {}, `The voice map still calls ${lostUsed.map((c) => c.api).join(", ")}, which the spec no longer lists. `) : null,
    r.key_change ? h("strong", {}, `${r.key_change} `) : null,
    isAdmin ? accept : null, " ", isAdmin ? discard : null) : null;
  const ver = versionLine(r, r.title || x.title);
  if (!r.commands.length) return h("section", { class: "card panel" }, h("p", { class: "quiet small" }, intro), ver, head);
  return h("section", { class: "card panel" }, h("p", { class: "quiet small" }, intro), ver, head, pending,
    stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, ["Command", "What it does", "API requires", "Voice map", "Change"].map((t) => h("th", {}, t)))),
      h("tbody", {}, r.commands.map((c) => h("tr", { class: [c.actions.length ? "used" : "", c.mark !== "same" ? `mark-${c.mark}` : ""].join(" ").trim() || null },
        h("td", {}, h("code", {}, c.api)), h("td", {}, c.summary || "-"),
        h("td", { class: "small" }, (c.requires || []).join(", ") || "-",
          c.mark === "modified" && c.was ? h("span", { class: "hint" }, `was: ${(c.was.requires || []).join(", ") || "nothing"}${c.was.summary !== c.summary ? `; "${c.was.summary}"` : ""}`) : null),
        h("td", {}, c.actions.length ? h("span", { class: c.mark === "deleted" ? "pill-bad" : "pill-ok" }, c.actions.join(", ")) : h("span", { class: "quiet" }, "-")),
        h("td", {}, c.mark === "same" ? "" : h("strong", { class: `mark ${c.mark}` }, MARKS[c.mark])))))))));
}

async function addAppForm() {
  const ch = await api("/api/integrations/add-choices");
  const key = select([{ value: "", label: "none (it needs no key)" }].concat(ch.keys.map((k) => ({ value: k.name, label: k.for ? `${k.name} (for ${k.for})` : k.name }))), "");
  const nm = input("text", { placeholder: "a short word, like mealie" });
  const ti = input("text", { placeholder: "how the pages name it, like Mealie (recipes)" });
  const kind = select([{ value: "openapi", label: "an app we didn't write (it has an OpenAPI / Swagger spec)" },
    { value: "contract", label: "one of ours (it speaks the router's /ask door)" }], "openapi");
  const url = input("text", { placeholder: "http://192.168.1.20:9000/api" });
  const spec = input("text", { placeholder: "http://192.168.1.20:9000/openapi.json" });
  const topic = select([{ value: "", label: "none yet" }].concat(ch.topics.map((t) => ({ value: t, label: t }))), "");
  // the app's name follows its key's program (step 1), so the key, the service and its
  // voice map all go by one name; it can still be changed before adding
  key.addEventListener("change", () => {
    const k = ch.keys.find((y) => y.name === key.value);
    if (k && k.for) {
      nm.value = k.for.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      if (!ti.value) ti.value = k.for;
    }
  });
  const box = errorBox();
  const btn = h("button", { class: "primary", type: "submit" }, "Add the app");
  const f = h("form", {},
    h("p", { class: "quiet small" }, "Step 1 is its key: Security, API keys and vault, Grantors, Add a key (with the program it's for). Then add the app here; it's added switched off. Its tabs follow the order of the work: Commands (read its spec), Voice map, Clean-up words, and Getting ready, which lists what's left."),
    h("div", { class: "grid2" }, field("Its key", key, ch.keys.length ? "Keys in the vault no app uses yet. Picking one names the app after its program." : "No unused keys in the vault: add one on Security, Grantors first (or none)."),
      field("Name", nm, "The service's name: the voice map, its helper and its lines all use it."), field("Title", ti), field("Kind", kind), field("Address", url), field("Its spec (OpenAPI)", spec),
      field("Topic", topic, ch.topics.length ? "Topics no app answers yet." : "Every topic already has an app: add one on Seed Topics, or none for now.")),
    box, btn);
  const show = () => { spec.closest(".field").hidden = kind.value !== "openapi"; };
  kind.addEventListener("change", show);
  setTimeout(show, 0);
  f.addEventListener("submit", busy(btn, box, async () => {
    await api("/api/integrations", { method: "POST", body: { name: nm.value, title: ti.value, kind: kind.value, url: url.value, spec: spec.value, secret: key.value, topic: topic.value } });
    location.hash = `#/integrations?open=${encodeURIComponent(nm.value.trim().toLowerCase())}&view=commands`;
  }));
  return h("details", { class: "card panel fold" }, h("summary", {}, h("h2", {}, "Add an app")), f);
}

// The voice map, edited on the page: each action is a word of your own, the app command it calls
// (from the Commands tab), the words that pick it, what the app's spec requires for that command,
// and the spoken needs: what she must hear (required: she asks), may hear (optional), or fills in
// from the app's options (default).
const NEED_RULES = ["required", "optional", "default"];
function mapView(x, det, isAdmin) {
  const cmds = det.commands || null;
  const byApi = {};
  for (const c of cmds || []) byApi[c.api.toUpperCase()] = c;
  const heard = det.heard_needs || {};
  const reqText = (apiv) => { const c = byApi[(apiv || "").toUpperCase()]; return c ? ((c.requires || []).join(", ") || "nothing") : (cmds ? "not one of its commands" : "read its spec (Commands)"); };
  const intro = h("p", { class: "quiet small" }, `What can be said to ${x.title}: each action, the app command it calls, the words that pick it, and its spoken needs. Kept in ${det.connector}. Your words count after a restart; Tools, Maintenance, build adds the words it learns from the datasets. The router asks for a required ${Object.keys(heard).join(" or ") || "need"} itself when it isn't heard; the app's helper handles the rest.`);
  if (!isAdmin) {
    return h("section", { class: "card panel" }, intro, stack(h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, ["Action", "Calls", "Words", "API requires", "Spoken needs"].map((t) => h("th", {}, t)))),
      h("tbody", {}, det.actions.map((a) => h("tr", {}, h("th", { scope: "row" }, a.name, a.note ? h("span", { class: "hint" }, a.note) : null),
        h("td", {}, h("code", {}, a.api || "-")), h("td", {}, [...a.words, ...a.objects].join(", ") || "-"), h("td", { class: "small" }, reqText(a.api)),
        h("td", {}, Object.entries(a.needs).map(([k, v]) => `${k} (${v})`).join(", ") || "-"))))))));
  }
  const rows = det.actions.map((a) => ({ name: a.name, was: a.name, api: a.api, words: a.words.slice(), objects: a.objects, needs: Object.assign({}, a.needs), note: a.note }));
  const tbody = h("div", { class: "vm-list" });
  const box = errorBox();
  const save = h("button", { type: "button", class: "primary", disabled: true }, "Save the voice map");
  const dirty = () => { save.disabled = false; };
  const callOptions = (cur) => {
    const opts = [{ value: "", label: "pick its command" }].concat((cmds || []).map((c) => ({ value: c.api, label: `${c.api}${c.summary ? " - " + c.summary : ""}` })));
    if (cur && !byApi[cur.toUpperCase()]) opts.push({ value: cur, label: `${cur} (not in its commands)` });
    return opts;
  };
  function needsCell(row) {
    const wrap = h("div", { class: "needs" });
    const draw = () => {
      wrap.replaceChildren(...Object.entries(row.needs).map(([k, v]) => {
        const sel = select(NEED_RULES, v, { "aria-label": `${k}: required, optional or default` });
        sel.addEventListener("change", () => { row.needs[k] = sel.value; dirty(); });
        return h("span", { class: "chip need" + (heard[k] ? " heard" : ""), title: heard[k] ? "the router hears this one itself" : "the app's helper handles this one" }, k, " ", sel,
          h("button", { type: "button", "aria-label": `remove ${k}`, onclick: () => { delete row.needs[k]; dirty(); draw(); } }, "×"));
      }));
      const word = input("text", { placeholder: "a need", list: "need-words", class: "need-word" });
      const rule = select(NEED_RULES, "required");
      const add = () => { const k = word.value.trim().toLowerCase(); if (!k) return; row.needs[k] = rule.value; dirty(); draw(); };
      word.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
      wrap.append(h("span", { class: "chip-add" }, word, rule, h("button", { type: "button", onclick: add }, "Add")));
    };
    draw();
    return wrap;
  }
  function draw() {
    tbody.replaceChildren(...rows.map((row, i) => {
      const nm = input("text", { value: row.name, "aria-label": "action (one word)", class: "action-word" });
      nm.addEventListener("input", () => { row.name = nm.value; dirty(); });
      const reqCell = h("span", { class: "small vm-req" }, reqText(row.api));
      const call = cmds ? select(callOptions(row.api), row.api, { "aria-label": "the command it calls" }) : input("text", { value: row.api, placeholder: "GET /path", "aria-label": "the command it calls" });
      call.addEventListener(cmds ? "change" : "input", () => { row.api = call.value; reqCell.textContent = reqText(row.api); dirty(); });
      const words = chipList(row.words, (list) => { row.words = list; dirty(); }, "a word that picks it");
      const part = (label, ...kids) => h("div", { class: "vm-part" }, h("span", { class: "vm-label" }, label), ...kids);
      const summary = `${row.api || "no command yet"}${row.words.length ? " · " + row.words.join(", ") : ""}${Object.keys(row.needs).length ? " · needs " + Object.entries(row.needs).map(([k, v]) => `${k} (${v})`).join(", ") : ""}`;
      return h("details", { class: "vm-action", open: row.open || null, ontoggle: (e) => { row.open = e.target.open; } },
        h("summary", {}, h("strong", {}, row.name || "(new action)"), h("span", { class: "quiet small" }, " " + summary)),
        h("div", { class: "vm-line" },
          part("Action", nm, row.note ? h("span", { class: "hint" }, row.note) : null),
          part("Calls", call),
          h("div", { class: "vm-part" }, h("span", { class: "vm-label" }, "API requires"), reqCell)),
        h("div", { class: "vm-line" },
          part("Words", words, row.objects.length ? h("span", { class: "hint" }, `also decided outright by: ${row.objects.join(", ")}`) : null),
          part("Spoken needs", needsCell(row)),
          h("div", { class: "vm-part vm-end" }, h("button", { type: "button", onclick: () => { if (confirm(`Take the action ${row.name || "(unnamed)"} out of the voice map?`)) { rows.splice(i, 1); dirty(); draw(); } } }, "Take out"))));
    }));
  }
  draw();
  const addRow = h("button", { type: "button", onclick: () => { rows.push({ name: "", was: null, api: "", words: [], objects: [], needs: {}, open: true }); dirty(); draw(); } }, "Add an action");
  save.addEventListener("click", busy(save, box, async () => {
    const names = rows.map((r) => r.name.trim().toLowerCase());
    const twice = names.find((n, i) => names.indexOf(n) !== i);
    if (twice) throw new Error(`Two actions are named ${twice}: each must be its own word`);
    await api(`/api/integrations/${encodeURIComponent(x.id)}/actions`, { method: "PUT",
      body: { stamp: (det.stamps || {}).actions, actions: rows.map((r) => ({ name: r.name, was: r.was, api: r.api, words: r.words, needs: r.needs })) } });
    route();
  }));
  const known = h("datalist", { id: "need-words" }, [...new Set([...Object.keys(heard), ...det.actions.flatMap((a) => Object.keys(a.needs))])].map((w) => h("option", { value: w })));
  // how closely a spoken name must match one of its items (the voice map's own knob)
  const mm = input("number", { step: "0.05", min: "0", max: "1", value: det.match_min ?? "", "aria-label": "match min", class: "num-in" });
  const mmBox = errorBox();
  const mmSave = h("button", { type: "button", disabled: true }, "Save");
  mm.addEventListener("input", () => { mmSave.disabled = false; });
  // sound alike, beside it: when the words find nothing sure, how they sound is tried too
  const sa = check(" sound alike", Boolean(det.sound_alike), () => { mmSave.disabled = false; });
  mmSave.addEventListener("click", busy(mmSave, mmBox, async () => {
    await api(`/api/integrations/${encodeURIComponent(x.id)}/voice-map`, { method: "PATCH",
      body: { match_min: mm.value === "" ? null : Number(mm.value), sound_alike: sa.querySelector("input").checked } });
    mmSave.disabled = true; mmSave.after(okNote("Saved. Restart to use it."));
  }));
  const matching = h("div", { class: "setting" }, h("div", {}, h("strong", {}, "match min"), " ", h("code", { class: "quiet small" }, "match_min"),
    " and ", h("strong", {}, "sound alike"), " ", h("code", { class: "quiet small" }, "sound_alike"),
    h("p", { class: "hint" }, `The share of an item's words that must be said to count as that item (a chore's name, say). Empty: nothing said matches one until it's set. Sound alike: when the words find nothing sure, try how they sound ("by single hole faucet" for "Buy single hole faucet").`)),
    h("div", {}, mm, sa), h("div", {}, mmSave, mmBox));
  return h("section", { class: "card panel" }, matching, intro,
    cmds ? null : h("p", { class: "warn small" }, "Its spec hasn't been read: Commands, Read its spec, so Calls can offer the app's own commands."),
    known, tbody,
    h("div", { class: "row-actions" }, addRow, save, box));
}

// User rules: the app's own commands chained with the router's steps (veil/rules.py), built a line
// at a time: each line is a step (a command, or one of the router's steps, its hover saying what it
// does) and its parameters. Saved in the app's connectors/<name>.yaml (rules:).
// opts (the Brain fleas page uses the same builder): {saveUrl, intro, noun ("rule" or "flea"), objects (false: no
// Needs a noun), titles (true: a Title box)}.
function userRulesView(x, det, isAdmin, opts) {
  opts = Object.assign({ saveUrl: `/api/integrations/${encodeURIComponent(x.id)}/rules`, noun: "rule", objects: true, titles: false }, opts || {});
  const noun = opts.noun;
  const cmds = det.commands || [];
  const kinds = det.rule_steps || {};
  const byApi = {};
  for (const c of cmds) byApi[c.api.toUpperCase()] = c;
  const about = (st) => st.kind === "call" ? (byApi[(st.command || "").toUpperCase()] || {}).summary || "one of the app's commands" : (kinds[st.kind] || {}).about || "";
  const label = (st) => st.kind === "call" ? st.command || "a command" : (kinds[st.kind] || {}).title || st.kind;
  const summary = (r) => `${r.words.join(", ") || "no words yet"}${r.objects.length ? " + " + r.objects.join(" or ") : ""} · ${r.steps.map(label).join(" → ") || "no steps"}`;
  const intro = opts.intro || h("p", { class: "quiet small" }, `Rules chain ${x.title}'s own commands with the router's steps (Search, Match, Confirm...), for what one command can't do alone: renaming a chore whose name was misheard, say. A rule is reached like an action, inside its topic: a topic word ("rename the chore ..."), or right after ${x.title} answered ("rename that to ..."). Point at a step to see what it does. Kept in ${det.connector}; used as soon as it's saved.`);
  const problem = (r) => r.problem ? h("p", { class: "warn small" }, `Not used: ${r.problem}. Fix it and save.`) : null;
  if (!isAdmin) {
    return h("section", { class: "card panel" }, intro, (det.rules || []).length ? h("ul", { class: "rows" }, det.rules.map((r) =>
      h("li", {}, h("strong", {}, r.name), " ", h("span", { class: "quiet small" }, summary(r)), problem(r)))) : h("p", { class: "quiet" }, `No ${noun}s yet.`));
  }
  const rules = (det.rules || []).map((r) => ({ name: r.name, title: r.title || "", system: r.system, problem: r.problem, words: r.words.slice(), objects: (r.objects || []).slice(), steps: r.steps.map((st) => Object.assign({}, st)) }));
  const list = h("div", { class: "vm-list" });
  const box = errorBox();
  const save = h("button", { type: "button", class: "primary", disabled: true }, `Save the ${noun}s`);
  const dirty = () => { save.disabled = false; };
  const stepOptions = [{ value: "", label: "pick a step" }]
    .concat(Object.entries(kinds).filter(([k]) => k !== "call").map(([k, v]) => ({ value: "step:" + k, label: v.title })))
    .concat(cmds.map((c) => ({ value: "call:" + c.api, label: `${c.api}${c.summary ? " - " + c.summary : ""}` })));
  function paramInput(st, p) {
    const cur = st[p.name] ?? p.default;
    const set = (v) => { st[p.name] = v; dirty(); };
    const tip = { title: p.about, "aria-label": `${p.name}: ${p.about}` };
    if (p.kind === "number") { const el = input("number", Object.assign({ value: cur ?? "", class: "num-in", min: "0", max: "100" }, tip)); el.addEventListener("input", () => set(el.value === "" ? null : Number(el.value))); return el; }
    if (p.kind === "yesno") { const el = input("checkbox", Object.assign({ checked: Boolean(cur) }, tip)); el.addEventListener("change", () => set(el.checked)); return el; }
    if (p.kind === "choice") { const el = select(p.choices, cur, tip); el.addEventListener("change", () => set(el.value)); return el; }
    if (p.kind === "words") return h("span", tip, chipList(cur || [], (l) => set(l), p.name));
    if (p.kind === "lines") return h("span", tip, chipList(cur || [], (l) => set(l), "a line the persona may say"));
    if (p.kind === "command") {
      const el = select([{ value: "", label: "pick its command" }].concat(cmds.filter((c) => c.api.startsWith("GET ")).map((c) => ({ value: c.api, label: c.api }))), cur || "", tip);
      el.addEventListener("change", () => set(el.value)); return el;
    }
    if (p.kind === "fields") {
      const pairs = Object.assign({}, cur || {});
      const wrap = h("span", { class: "needs" });
      const draw = () => {
        wrap.replaceChildren(...Object.entries(pairs).map(([k, v]) => h("span", { class: "chip" }, `${k}: ${v}`,
          h("button", { type: "button", "aria-label": `remove ${k}`, onclick: () => { delete pairs[k]; set(Object.assign({}, pairs)); draw(); } }, "×"))));
        const f = input("text", { placeholder: "field", class: "need-word" });
        const v = input("text", { placeholder: "value", class: "need-word" });
        const add = () => { if (!f.value.trim()) return; pairs[f.value.trim()] = v.value.trim(); set(Object.assign({}, pairs)); draw(); };
        wrap.append(h("span", { class: "chip-add" }, f, v, h("button", { type: "button", onclick: add }, "Add")));
      };
      draw();
      return h("span", tip, wrap);
    }
    const el = input("text", Object.assign({ value: cur ?? "", placeholder: p.name }, tip));
    el.addEventListener("input", () => set(el.value));
    return el;
  }
  function stepLine(r, st, i, redraw) {
    const pick = select(stepOptions, st.kind === "call" ? "call:" + (st.command || "") : st.kind ? "step:" + st.kind : "", { title: about(st), "aria-label": `step ${i + 1}` });
    pick.addEventListener("change", () => {
      const [k, ...rest] = pick.value.split(":");
      r.steps[i] = k === "call" ? { kind: "call", command: rest.join(":") } : { kind: rest.join(":") };
      dirty(); redraw();
    });
    const params = st.kind && st.kind !== "call" ? ((kinds[st.kind] || {}).params || []).map((p) =>
      h("span", { class: "vm-part" }, h("span", { class: "vm-label", title: p.about }, p.name.replace("_", " ")), paramInput(st, p))) : [];
    const move = (d) => { const j = i + d; if (j < 0 || j >= r.steps.length) return; [r.steps[i], r.steps[j]] = [r.steps[j], r.steps[i]]; dirty(); redraw(); };
    return h("div", { class: "vm-line rule-step" }, h("strong", { class: "rule-n" }, `${i + 1}.`), pick, h("div", { class: "rule-params" }, ...params),
      h("span", { class: "vm-end" },
        h("button", { type: "button", "aria-label": "move up", disabled: i === 0, onclick: () => move(-1) }, "↑"),
        h("button", { type: "button", "aria-label": "move down", disabled: i === r.steps.length - 1, onclick: () => move(1) }, "↓"),
        h("button", { type: "button", "aria-label": "remove step", onclick: () => { r.steps.splice(i, 1); dirty(); redraw(); } }, "×")));
  }
  function draw() {
    list.replaceChildren(...rules.map((r, ri) => {
      const body = h("div", {});
      const redraw = () => body.replaceChildren(...r.steps.map((st, i) => stepLine(r, st, i, redraw)),
        h("div", { class: "row-actions" }, h("button", { type: "button", onclick: () => { r.steps.push({ kind: "" }); dirty(); redraw(); } }, "Add a step")));
      redraw();
      const nm = input("text", { value: r.name, "aria-label": `${noun} (one word)`, class: "action-word" });
      nm.addEventListener("input", () => { r.name = nm.value; dirty(); });
      const tt = input("text", { value: r.title, "aria-label": "title", placeholder: "what it's about" });
      tt.addEventListener("input", () => { r.title = tt.value; dirty(); });
      const words = chipList(r.words, (l) => { r.words = l; dirty(); }, noun === "flea" ? "a way it's asked: who is {speaking | talking}" : "a word that picks it");
      const objects = chipList(r.objects, (l) => { r.objects = l; dirty(); }, "a noun it needs (project)");
      return h("details", { class: "vm-action", open: r.open || null, ontoggle: (e) => { r.open = e.target.open; } },
        h("summary", {}, h("strong", {}, r.name || `(new ${noun})`), r.system ? h("span", { class: "pill-ok small" }, " built in") : null,
          r.problem ? h("span", { class: "pill-bad small" }, " not used") : null, h("span", { class: "quiet small" }, " " + summary(r))),
        problem(r),
        h("div", { class: "vm-line" },
          h("div", { class: "vm-part" }, h("span", { class: "vm-label" }, noun === "flea" ? "Flea" : "Rule"), nm),
          opts.titles ? h("div", { class: "vm-part" }, h("span", { class: "vm-label", title: "How the persona names it when asking which one (the pizza flea)" }, "Title"), tt) : null,
          h("div", { class: "vm-part" }, h("span", { class: "vm-label" }, noun === "flea" ? "Ways it's asked" : "Words"), words),
          opts.objects ? h("div", { class: "vm-part" }, h("span", { class: "vm-label", title: "When it has any, one of them must be said too (rename the house project): it wins over a rule with the same words and none" }, "Needs a noun"), objects) : null,
          h("div", { class: "vm-part vm-end" }, h("button", { type: "button", onclick: () => { if (confirm(`Take the ${noun} ${r.name || "(unnamed)"} out?`)) { rules.splice(ri, 1); dirty(); draw(); } } }, "Take out"))),
        body);
    }));
  }
  draw();
  const addRule = h("button", { type: "button", onclick: () => { rules.push({ name: "", title: "", words: [], objects: [], steps: [], open: true }); dirty(); draw(); } }, `Add a ${noun}`);
  save.addEventListener("click", busy(save, box, async () => {
    const res = await api(opts.saveUrl, { method: "PUT",
      body: { stamp: det.stamps ? det.stamps.rules : det.stamp, rules: rules.map((r) => ({ name: r.name, title: r.title, words: r.words, objects: r.objects, steps: r.steps })) } });
    if (det.stamps) det.stamps.rules = res.stamp; else det.stamp = res.stamp;   // as this save left them: the next save checks against it
    save.disabled = true;
    save.after(okNote("Saved. Used at once."));
  }));
  return h("section", { class: "card panel" }, intro,
    cmds.length || noun === "flea" ? null : h("p", { class: "warn small" }, "Its spec hasn't been read: Commands, Read its spec, so a step can call the app's own commands."),
    list, h("div", { class: "row-actions" }, addRule, save, box));
}

function testButton(name, out) {
  const btn = h("button", { type: "button" }, "Test");
  btn.addEventListener("click", busy(btn, out, async () => {
    out.textContent = "";
    const r = await api(`/api/integrations/${name}/test`, { method: "POST" });
    out.replaceChildren(h("span", { class: r.ok ? "pill-ok" : "pill-bad" }, r.ok ? "OK: " : "Not working: "), r.detail);
  }));
  return btn;
}

function saveIntegration(name, values, note, box) {
  return async () => {
    box.textContent = "";
    await api(`/api/integrations/${name}`, { method: "PATCH", body: values() });
    note.replaceChildren(okNote("Saved. Restart to use it."));
    session = await api("/api/session");
  };
}

function oreadCard(o, isAdmin, det) {
  // compliant: who spoke is an offer in Oread's Wepwawet section, switched on its Defaults tab
  const offered = ((det || {}).offers || []).some((f) => f.key === "who_spoke");
  const w = o.wyoming || {};
  const enabled = h("input", { type: "checkbox", checked: o.enabled });
  const source = select([{ value: "wyoming", label: "in the audio path (Wyoming)" }, { value: "oread", label: "Oread's API" },
    { value: "home_assistant", label: "the Home Assistant sensor" }], o.source || "wyoming");
  const host = input("text", { value: w.host || "", placeholder: "Oread's address, e.g. 192.168.1.20" });
  const connect = input("number", { step: "0.5", min: "0.5", max: "30", value: w.connect_timeout ?? 3 });
  const ports = input("text", { value: Object.entries(w.devices || {}).map(([a, p]) => `${a}=${p.listen}>${p.oread}`).join(", "),
    placeholder: "iris=10413>10313, felix=10412>10312" });
  const url = input("text", { value: o.url || "" });
  const token = input("text", { value: o.token || "OREAD_TOKEN" });
  const verify = input("text", { value: o.verify_tls === true ? "true" : (o.verify_tls || "false") });
  const timeout = input("number", { step: "0.1", min: "0.1", value: o.timeout ?? 0.8 });
  const age = input("number", { step: "1", min: "1", value: o.max_age_seconds ?? 20 });
  const overlap = input("number", { step: "0.05", min: "0", max: "1", value: o.min_word_overlap ?? 0.5 });
  const devices = input("text", { value: Object.entries(o.devices || {}).map(([a, b]) => `${a}=${b}`).join(", "), placeholder: "iris=iris, felix=felix" });
  const box = errorBox();
  const note = h("span", {});
  const out = h("p", { class: "small" });
  const wyo = h("div", { class: "grid2" },
    field("Oread's address", host, "Where Oread's Wyoming ports are."),
    field("Reach Oread within (seconds)", connect),
    field("Ports", ports, "assistant=router's port>Oread's port. In Home Assistant, point that device's Wyoming speech-to-text at the router's port. The router's ports must be published in docker-compose.yml (10410-10419)."));
  const api_ = h("div", { class: "grid2" },
    field("Oread's address", url, "https://<server>:10311"),
    field("Token name", token, `In the vault or .env: ${o.token_from || "not set yet"}. Make it on Oread (role reviewer).`),
    field("Check Oread's certificate", verify, "false, true, or the path of Oread's ca.crt"),
    field("Wait at most (seconds)", timeout));
  const show = () => { wyo.hidden = source.value !== "wyoming"; api_.hidden = source.value !== "oread" && !offered; };
  source.addEventListener("change", show);
  show();
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  save.addEventListener("click", busy(save, box, saveIntegration("oread", () => {
    const map = {};
    for (const part of devices.value.split(",")) { const [a, b] = part.split("=").map((x) => (x || "").trim()); if (a && b) map[a] = b; }
    const pmap = {};
    for (const part of ports.value.split(",")) {
      const m = part.trim().match(/^([a-z0-9_-]+)\s*=\s*(\d+)\s*>\s*(\d+)$/i);
      if (m) pmap[m[1].toLowerCase()] = { listen: Number(m[2]), oread: Number(m[3]) };
      else if (part.trim()) throw new Error(`"${part.trim()}" isn't assistant=port>port`);
    }
    const v = verify.value.trim();
    return { enabled: enabled.checked, source: source.value, url: url.value.trim(), token: token.value.trim(),
      verify_tls: v === "true" ? true : v === "false" || v === "" ? false : v, timeout: Number(timeout.value),
      max_age_seconds: Number(age.value), min_word_overlap: Number(overlap.value), devices: map,
      wyoming: { host: host.value.trim(), connect_timeout: Number(connect.value), devices: pmap } };
  }, note, box)));
  const listening = (o.listening || []).length ? `Listening now on ${o.listening.join(", ")}.` : "No Wyoming ports open right now.";
  return h("section", { class: "card panel" }, h("h2", {}, offered ? "Oread" : "Oread: who spoke"),
    h("p", { class: "quiet small" }, "Speech-to-text plus speaker ID. With who spoke on, your name can be said now and then, and the firewall can tell people apart."),
    offered ? h("p", { class: "small" }, `Who spoke is ${o.enabled ? "on" : "off"}: switch it and pick its way on the Defaults tab (Oread offers it in its own spec). Here: where Oread is.`)
      : [h("label", { class: "check" }, enabled, " On"),
        h("div", { class: "grid2" }, field("Who spoke comes from", source, "In the audio path is the agreed way: no token, nothing asked afterwards."))],
    wyo, api_,
    h("div", { class: "grid2" },
      field("Fresh within (seconds)", age), field("Words must match", overlap, "Share of the words Oread heard that the router heard too."),
      field("Device names", devices, "assistant=Oread device, where they differ (API and sensor)")),
    h("p", { class: "quiet small" }, listening),
    box, h("div", { class: "row-actions" }, save, testButton("oread", out), note), out);
}

function haCard(o, isAdmin) {
  const url = input("text", { value: o.url || "", placeholder: "http://<home assistant>:8123" });
  const token = input("text", { value: o.token || "HA_TOKEN" });
  const sats = input("text", { value: Object.entries(o.satellites || {}).map(([a, b]) => `${a}=${b}`).join(", "),
    placeholder: "assist_satellite.kitchen=felix" });
  const box = errorBox();
  const note = h("span", {});
  const out = h("p", { class: "small" });
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  save.addEventListener("click", busy(save, box, saveIntegration("home_assistant", () => {
    const map = {};
    for (const part of sats.value.split(",")) { const [a, b] = part.split("=").map((x) => (x || "").trim()); if (a && b) map[a] = b; }
    return { url: url.value.trim(), token: token.value.trim(), satellites: map };
  }, note, box)));
  return h("section", { class: "card panel" }, h("h2", {}, "Home Assistant"),
    h("p", { class: "quiet small" }, "Which assistant each satellite is (Veil Guard Service). A long-lived token from Home Assistant (your profile, Security), saved in the vault as ha_token."),
    h("div", { class: "grid2" }, field("Address", url), field("Token name", token, `In the vault or .env: ${o.token_from || "not set yet"}`),
      field("Satellites", sats, "Only where a satellite's name doesn't say which assistant it is: device or satellite = assistant")),
    box, h("div", { class: "row-actions" }, save, testButton("home_assistant", out), note), out);
}

function serviceCard(name, s, isAdmin) {
  const title = s.title || name;
  const app = s.title || name;
  const enabled = h("input", { type: "checkbox", checked: s.enabled });
  const url = input("text", { value: s.url || "" });
  const timeout = input("number", { step: "1", min: "1", value: s.timeout ?? 8 });
  // only an app the router keeps a copy of (one with a connector) refreshes it on a clock
  const keeps = Boolean(s.keeps_copy);
  const refresh = input("number", { step: "5", min: "5", value: s.cache_refresh_seconds ?? 60 });
  const box = errorBox();
  const note = h("span", {});
  const out = h("p", { class: "small" });
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  const isApp = s.kind === "openapi";
  const prefix = input("text", { value: s.spec_prefix || "", placeholder: "/{domain}/v1" });
  const pages = input("number", { step: "1", min: "1", max: "20", value: s.pages_max ?? 1 });
  const onlyAccepted = input("checkbox", { checked: Boolean(s.send_only_accepted) });
  const testSaid = input("text", { value: s.test_said || "", placeholder: "what's the weather today" });
  const spoken = input("text", { value: s.spoken_name || "", placeholder: `the ${(s.topics[0] || "app").replace("_", " ")}` });
  save.addEventListener("click", busy(save, box, saveIntegration(name, () => Object.assign(
    { enabled: enabled.checked, url: url.value.trim(), timeout: Number(timeout.value) },
    keeps ? { cache_refresh_seconds: Number(refresh.value) } : {}, isApp ? { spec_prefix: prefix.value.trim(), pages_max: Number(pages.value) || 1, send_only_accepted: onlyAccepted.checked } : {},
    s.kind === "contract" ? { test_said: testSaid.value.trim() } : {}, { spoken_name: spoken.value.trim() }), note, box)));
  return h("section", { class: "card panel" }, h("h2", {}, title),
    h("p", { class: "quiet small" }, `${s.kind} service${s.topics.length ? `, answers ${s.topics.join(", ")}` : ""}${s.secret ? `; token ${s.secret}: ${s.secret_from || "not set"}` : ""}.`),
    h("label", { class: "check" }, enabled, " On"),
    h("div", { class: "grid2" }, field("Address", url), field("Wait at most (seconds)", timeout),
      keeps ? field("Read its lists again every (seconds)", refresh, "The router keeps a copy of its things (open chores, people) to decide quickly; a change always reads fresh first.") : null,
      field("Its spoken name", spoken, "How the persona names it in a sentence (\"the feast days\", \"your chores\"), when asking which app you meant; empty: its title."),
      s.kind === "contract" ? field("Its test question", testSaid, "What Test asks it (an app that takes the words as said); empty: Test asks for its spec instead.") : null,
      isApp ? h("label", { class: "check" }, onlyAccepted, " Send only the fields a change accepts (an app that refuses others; its spec lists them)") : null,
      isApp ? field("Pages it reads", pages, "An answer in pages (its next): how many pages to read in all; each is a call (1: the first only).") : null,
      isApp ? field("Its spec's paths start with", prefix, "Only when its address leaves that start out (Wikipedia's spec lists /{domain}/v1/feed/..., served at its address /feed/...); empty for most apps.") : null,
      isApp ? h("p", { class: "quiet small" }, "Its people, its projects and who \"me\" means: the Defaults tab, Lists.") : null),
    box, h("div", { class: "row-actions" }, save, testButton(name, out), note), out);
}

function litellmCard(l, isAdmin) {
  const out = h("p", { class: "small" });
  const model = input("text", { value: l.fallback_model || "" });
  const timeout = input("number", { step: "1", min: "1", value: l.timeout ?? 60 });
  const key = input("text", { value: l.key || "" });
  const self = input("text", { value: l.model_name || "" });
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button", disabled: !isAdmin }, "Save");
  save.addEventListener("click", busy(save, box, saveIntegration("litellm", () => ({ fallback_model: model.value.trim(),
    timeout: Number(timeout.value), key: key.value.trim(), model_name: self.value.trim() }), note, box)));
  return h("section", { class: "card panel" }, h("h2", {}, "LiteLLM (the way Off-Platform)"),
    h("p", { class: "quiet small" }, `Address ${l.url} (OFF_PLATFORM_URL in .env). Running now: ${l.running}.`),
    h("div", { class: "grid2" },
      field("Model for anything not answered at home", model, "The name in LiteLLM's own model list (it decides which models that tries, and in what order)."),
      field("Wait at most (seconds)", timeout, "How long the router waits for LiteLLM's answer."),
      field("Key name", key, `The name of LiteLLM's key in the vault or .env: ${l.key_from || "not set yet"}`),
      field("The router's name in LiteLLM", self, "What the router calls itself in /v1/models. LiteLLM's config must use the same name.")),
    box, h("div", { class: "row-actions" }, save, isAdmin ? testButton("litellm", out) : null, note), out);
}

// ---------- Connect: settings (every knob) ----------

// The parts of settings.yaml shown on a page of their own (shown there, not on Settings): key -> [label, page].
// Each page's Rules tab holds the knobs for what that page shows (Oct 15). Settings keeps the house,
// how requests are heard, memory between requests, any app (the standard), and the engines.
const SEED_RULES = ["Seed Topics: Rules", "topics?tab=rules"];
// in settings.yaml, never on a page (the pages' own port and certificate: nothing to change there)
const SETTINGS_HIDDEN = new Set(["web"]);
const SETTINGS_ELSEWHERE = {
  topics: ["Seed Topics", "topics"], names_in_replies: ["Name Sparkle", "sparkle"],
  integrations: ["Integrations", "integrations"], services: ["Integrations", "integrations"],
  security: ["Security", "security"],
  miss_log_max: ["Misses: Rules", "misses?tab=rules"], capture_keep: ["Tools: Rules", "tools?tab=rules"],
  activity: ["Off-Platform Bank: Rules", "bank?tab=rules"], savings: ["Savings: Rules", "savings?tab=rules"],
  stats: ["Stats: Rules", "stats?tab=rules"],
  // the keyword build and how sure the router must be: everything the build makes, on Seed Topics
  ...Object.fromEntries(["confidence_local", "min_seen", "door_strong_min", "door_near_min", "door_min", "door_min_hits",
    "seed_min", "seed_share", "thin_min", "slot_min", "slot_max", "verb_min_hits", "verb_max", "detail_min",
    "own_words_share", "verb_beats_object"].map((k) => [k, SEED_RULES])),
};

// A small (i) beside a label: pointing at it shows the text, clicking pins it open (works on a phone),
// Esc or a second click closes it.
function infoTip(text) {
  const tip = h("span", { class: "tip", role: "tooltip", hidden: true }, text);
  const btn = h("button", { type: "button", class: "info", "aria-label": "What this is", "aria-expanded": "false", title: text }, "?");
  const show = (on) => { tip.hidden = !on; btn.setAttribute("aria-expanded", on ? "true" : "false"); };
  let pinned = false;
  btn.addEventListener("click", (e) => { e.preventDefault(); pinned = !pinned; show(pinned); });
  btn.addEventListener("mouseenter", () => show(true));
  btn.addEventListener("mouseleave", () => { if (!pinned) show(false); });
  btn.addEventListener("keydown", (e) => { if (e.key === "Escape") { pinned = false; show(false); } });
  btn.removeAttribute("title");          // the tip itself shows the words, not the browser's box too
  return h("span", { class: "info-wrap" }, btn, tip);
}

// Settings knobs, built from settings.yaml's own sections and comments, for any page: rows(path)
// is one knob with its Save; cards(keep) is every section holding a key keep(key) says yes to.
async function settingsKit() {
  const d = await api("/api/settings");
  const own = d.settings || {};
  const defs = d.defaults || {};
  const notes = d.comments || {};
  function value(path) {
    let a = own;
    let b = defs;
    for (const k of path) { a = a && typeof a === "object" ? a[k] : undefined; b = b && typeof b === "object" ? b[k] : undefined; }
    return [a, b];
  }
  function leaves(obj, path, out) {
    for (const [k, v] of Object.entries(obj || {})) {
      const p = path.concat([k]);
      if (v && typeof v === "object" && !Array.isArray(v)) leaves(v, p, out);
      else out.push(p);
    }
    return out;
  }
  const merged = Object.assign({}, defs, own);
  function knobRow(p) {
    const [cur, def] = value(p);
    const v = cur === undefined ? def : cur;
    let el;
    if (typeof v === "boolean") el = h("input", { type: "checkbox", checked: v, "aria-label": p.join(".") });
    else if (typeof v === "number") el = input("number", { step: "any", value: v, class: "num-in", "aria-label": p.join(".") });
    else if (Array.isArray(v)) el = input("text", { value: v.join(", "), "aria-label": p.join(".") });
    else if (p[p.length - 1] === "timezone" && typeof Intl.supportedValuesOf === "function") {
      // a timezone: the standard list every system uses (the browser's), not a typed box
      const zones = Intl.supportedValuesOf("timeZone");
      el = select((v && !zones.includes(v) ? [v] : []).concat(zones), v || "", { "aria-label": p.join(".") });
    } else el = input("text", { value: v ?? "", "aria-label": p.join(".") });
    const read = () => (typeof v === "boolean" ? el.checked : typeof v === "number" ? Number(el.value)
      : Array.isArray(v) ? el.value.split(",").map((x) => x.trim()).filter(Boolean) : el.value);
    const start = JSON.stringify(read());
    const box = h("span", { class: "small" });
    const btn = h("button", { type: "button", disabled: true }, "Save");     // only once something changed
    const changed = () => { btn.disabled = JSON.stringify(read()) === start; };
    el.addEventListener("input", changed);
    el.addEventListener("change", changed);
    btn.addEventListener("click", busy(btn, box, async () => {
      await api("/api/settings", { method: "PATCH", body: { path: p, value: read() } });
      box.replaceChildren(okNote("saved"));
    }));
    const label = p[p.length - 1].replace(/_/g, " ");
    const hint = notes[p.join(".")] || "";
    return h("div", { class: "setting", "data-find": `${p.join(" ")} ${label} ${hint}`.toLowerCase() },
      h("div", {}, h("strong", {}, label[0].toUpperCase() + label.slice(1)), " ", h("code", { class: "quiet small" }, p.join(".")),
        hint ? infoTip(hint) : null,
        cur === undefined ? h("p", { class: "hint" }, "(the default; not in settings.yaml yet)") : null),
      h("div", { class: "setting-value" }, el), h("div", {}, btn, box));
  }
  function rowsFor(k) {
    const v = merged[k];
    const rows = [];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      if (notes[k]) rows.push(h("p", { class: "quiet small group-note-head" }, h("strong", {}, k.replace(/_/g, " ")), " ", infoTip(notes[k])));
      leaves(v, [k], []).forEach((p) => rows.push(knobRow(p)));
    } else rows.push(knobRow([k]));
    return rows;
  }
  function cards(keep, openFirst = true) {
    const placed = new Set();
    const out = [];
    (d.sections || []).forEach((sec) => {
      sec.keys.forEach((k) => placed.add(k));
      const rows = sec.keys.filter(keep).flatMap(rowsFor);
      if (!rows.length) return;                       // nothing of this section on this page
      out.push(h("details", { class: "card panel fold settings-section", open: openFirst && out.length === 0 },
        h("summary", {}, h("h2", {}, sec.title[0].toUpperCase() + sec.title.slice(1)), h("span", { class: "quiet small" }, ` ${rows.filter((r) => r.classList.contains("setting")).length} settings`)),
        ...rows));
    });
    const rest = Object.keys(defs).filter((k) => !placed.has(k) && keep(k));
    if (rest.length) {
      out.push(h("details", { class: "card panel fold settings-section" }, h("summary", {}, h("h2", {}, "Not in settings.yaml yet (defaults)")),
        ...rest.flatMap((k) => (defs[k] && typeof defs[k] === "object" && !Array.isArray(defs[k]) ? leaves(defs[k], [k], []) : [[k]]).map(knobRow))));
    }
    return out;
  }
  // every setting that matches q but is shown on another page: [[path, label, page]]
  function elsewhere(q) {
    const out = [];
    for (const [k, [label, page]] of Object.entries(SETTINGS_ELSEWHERE)) {
      const v = merged[k];
      const paths = v && typeof v === "object" && !Array.isArray(v) ? leaves(v, [k], []) : [[k]];
      for (const pth of paths) {
        const text = `${pth.join(" ")} ${pth[pth.length - 1].replace(/_/g, " ")} ${notes[pth.join(".")] || ""}`.toLowerCase();
        if (text.includes(q)) out.push([pth, label, page]);
      }
    }
    return out;
  }
  return { knobRow, rowsFor, cards, elsewhere };
}

async function settingsPage() {
  const kit = await settingsKit();
  const cards = kit.cards((k) => !SETTINGS_ELSEWHERE[k] && !SETTINGS_HIDDEN.has(k));
  // find a setting by any word of its name or its comment
  const find = input("search", { placeholder: "find a setting: a word of its name or what it does", "aria-label": "Find a setting" });
  const none = h("p", { class: "empty-state", hidden: true }, "No setting on this page matches.");
  const away = h("div", { class: "card panel", hidden: true });
  find.addEventListener("input", () => {
    const q = find.value.trim().toLowerCase();
    let any = false;
    const other = q ? kit.elsewhere(q).slice(0, 12) : [];
    away.hidden = !other.length;
    away.replaceChildren(h("h2", {}, "On other pages"), h("ul", { class: "rows" }, other.map(([pth, label, page]) =>
      h("li", {}, h("code", { class: "small" }, pth.join(".")), h("a", { href: `#/${page}` }, label)))));
    for (const card of cards) {
      let hits = 0;
      for (const row of card.querySelectorAll(".setting")) { const hit = !q || row.dataset.find.includes(q); row.hidden = !hit; hits += hit; }
      card.querySelectorAll(".group-note-head").forEach((n) => { n.hidden = Boolean(q); });
      card.hidden = q && !hits;
      if (q && hits) card.open = true;
      any = any || hits > 0;
    }
    none.hidden = !q || any;
  });
  const pages = [...new Map(Object.values(SETTINGS_ELSEWHERE).map(([label, page]) => [page, label])).entries()];
  return [h("h1", {}, "Settings"),
    h("p", { class: "quiet" }, "Every knob in settings.yaml that has no page of its own, in the file's own sections, each with its comment. Change one and its Save lights up; saving writes the file and keeps your comments, and most knobs are used after a restart (the restart bar appears)."),
    h("p", { class: "quiet small" }, "On their own pages: ", ...pages.map(([page, label], i) => [i ? " · " : "", h("a", { href: `#/${page}` }, label)]), "."),
    h("div", { class: "toolbar filters" }, find), none, away,
    lazyView(holdingView),
    ...cards,
    lazyView(startingView)];
}

// What the router is carrying between requests right now, per device, with how old each piece is
// and whether it still counts: the place to see which memory a request walked into.
async function holdingView() {
  const d = await api("/api/holding");
  const age = (s) => (s < 90 ? `${s} s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`);
  const live = (on) => h("span", { class: on ? "pill-ok" : "quiet small" }, on ? "counts now" : "expired");
  const cards = Object.entries(d.devices).map(([who, x]) => h("div", { class: "card panel" },
    h("h3", {}, who, x.off_platform_conversation ? h("span", { class: "badge" }, " in an Off-Platform conversation") : null),
    h("dl", { class: "kv" },
      h("dt", {}, "Question waiting (path C)"), h("dd", {}, x.pending ? [`${x.pending.kind} · ${age(x.pending.age)} · `, live(x.pending.alive)] : "none"),
      h("dt", {}, "Last topic at home (path B)"), h("dd", {}, x.memory ? [`${x.memory.topic} ("${x.memory.said}") · ${age(x.memory.age)} · `, live(x.memory.alive)] : "none")),
    x.turns.length ? h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, ["Turn record", "Path", "Answered by", "When"].map((t) => h("th", {}, t)))),
      h("tbody", {}, x.turns.map((t) => h("tr", {}, h("td", {}, t.heard || ""), h("td", {}, t.path || ""), h("td", {}, t.engine || ""), h("td", {}, age(t.age))))))) : null));
  return foldBox("holding", "What the router is holding now", false,
    h("p", { class: "quiet small" }, `The last topic at home and the router's own question count for ${Math.round(d.context_window / 60)} min; a sentence goes back Off-Platform for ${Math.round(d.gemini_window / 60)} min after an Off-Platform answer. A follow-up is ${d.followup_max_words} words or fewer (or starts with a cue); a topic in the last ${d.followup_lookback} requests of the front end's history counts only when the last topic at home is the same one.`),
    ...cards);
}

// What an update shipped in the starting copies (defaults/) that the household's own files don't
// have yet: each with Add (into your file, comments kept) or Not for us (hidden for good).
// Nothing about any one file or app: the list comes from comparing the files.
async function startingView() {
  const d = await api("/api/starting");
  if (!d.items.length) return [];
  const show = (v) => (v !== null && typeof v === "object" ? JSON.stringify(v) : String(v));
  const rows = d.items.map((it) => {
    const box = errorBox();
    const add = h("button", { type: "button", class: "primary" }, "Add");
    add.addEventListener("click", busy(add, box, async () => { await api(`/api/starting/${it.id}/add`, { method: "POST" }); route(); }));
    const skip = h("button", { type: "button" }, "Not for us");
    skip.addEventListener("click", busy(skip, box, async () => { await api(`/api/starting/${it.id}/dismiss`, { method: "POST" }); route(); }));
    return h("tr", {},
      h("td", {}, h("code", {}, it.file)),
      h("td", {}, it.path.join(" › ") || "(the top)"),
      h("td", { class: "small" }, it.kind === "key" ? "a setting: " : "a word in the list: ", h("code", {}, show(it.value))),
      h("td", {}, add, " ", skip, box));
  });
  return h("section", { class: "card panel" }, h("h2", {}, "New in the starting copies"),
    h("p", { class: "quiet small" }, "An update shipped these in the starting copies (defaults/), and your own files don't have them. Your files are never changed by an update: Add puts one in (your comments kept; most are used after a restart), Not for us hides it for good. Values you changed aren't listed: yours win."),
    h("div", { class: "table-wrap" }, h("table", { class: "matrix" },
      h("thead", {}, h("tr", {}, ["File", "Where", "What", ""].map((x) => h("th", {}, x)))), h("tbody", {}, rows))));
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

// ---------- Protect: security ----------

async function securityPage() {
  let tab = hashParam("tab") || "users";
  if (tab === "tokens" || tab === "vault") tab = "keys";            // the older tabs, now one
  const tabs = h("div", { class: "tabs", role: "tablist" }, [["users", "Users"], ["keys", "API keys and vault"], ["addresses", "Addresses"], ["audit", "Audit log"]]
    .map(([id, label]) => h("button", { role: "tab", "aria-selected": id === tab ? "true" : "false", onclick: () => { location.hash = `#/security?tab=${id}`; } }, label)));
  const body = await ({ users: usersTab, keys: keysTab, addresses: addressesTab, audit: auditTab }[tab] || usersTab)();
  return [h("h1", {}, "Security"), h("p", { class: "quiet" }, "Who may sign in, programs' tokens, the keys the router sends to other programs, permitted addresses in and out, and who changed what. The same model as Oread's."), tabs, h("div", { class: "gap-top" }, body)];
}

async function usersTab() {
  const d = await api("/api/users");
  const list = h("ul", { class: "rows users" }, d.users.map((u) => {
    const role = select(d.grantable, u.role);
    const pw = input("password", { placeholder: `new password (${minPassword() || "long"}+)`, autocomplete: "new-password" });
    const box = errorBox();
    const save = h("button", { type: "button" }, "Save");
    save.addEventListener("click", busy(save, box, async () => {
      await api(`/api/users/${encodeURIComponent(u.name)}`, { method: "PATCH", body: { role: role.value, password: pw.value || null } });
      route();
    }));
    const del = h("button", { type: "button" }, "Remove");
    del.addEventListener("click", busy(del, box, async () => { if (confirm(`Remove ${u.name}?`)) { await api(`/api/users/${encodeURIComponent(u.name)}`, { method: "DELETE" }); route(); } }));
    return h("li", {}, h("div", {}, h("strong", {}, u.name), " ", h("span", { class: "badge" }, u.role), u.locked ? h("span", { class: "pill-bad" }, " locked") : null,
      h("p", { class: "quiet small" }, `last sign-in ${u.last_sign_in ? when(u.last_sign_in) : "never"}`)),
      u.name === session.user.name ? h("span", { class: "quiet small" }, "you (change your password on Account)") :
        h("div", { class: "row" }, role, pw, save, del), box);
  }));
  const name = input("text", { placeholder: "username" });
  const pw = input("password", { placeholder: `password (${minPassword() || "long"}+)`, autocomplete: "new-password" });
  const role = select(d.grantable, "viewer");
  const box = errorBox();
  const add = h("button", { class: "primary", type: "submit" }, "Add");
  const f = h("form", { class: "card panel" }, h("h2", {}, "Add a person"), h("div", { class: "grid2" }, field("Username", name), field("Password", pw), field("Role", role)), box, add);
  f.addEventListener("submit", busy(add, box, async () => { await api("/api/users", { method: "POST", body: { name: name.value, password: pw.value, role: role.value } }); route(); }));
  // the sign-in rules (security: in settings.yaml), used at once
  const t = await api("/api/tokens");
  const RULES = [["password_min_length", "Shortest password", "characters"], ["lock_after_failures", "Lock an account after", "wrong passwords in a row"],
    ["lock_minutes", "Locked for", "minutes"], ["session_idle_hours", "Sign out after idle", "hours"], ["session_max_days", "Sign in again after", "days at most"]];
  const rules = h("section", { class: "card panel" }, h("h2", {}, "Sign-in rules"),
    h("p", { class: "quiet small" }, "For everyone who signs in to these pages. Saved to settings.yaml (security:) and used at once."),
    RULES.map(([k, label, unit]) => {
      const box = errorBox();
      const n = input("number", { min: "1", step: "1", value: String(t.rules[k] ?? ""), "aria-label": label, class: "num-in" });
      const save = h("button", { type: "button" }, "Save");
      save.addEventListener("click", busy(save, box, async () => {
        await api("/api/settings", { method: "PATCH", body: { path: ["security", k], value: Number(n.value) } });
        if (k === "password_min_length") { session.password_min_length = Number(n.value); }
        save.after(okNote("Saved"));
      }));
      return h("div", { class: "setting" }, h("div", {}, h("strong", {}, label), " ", h("code", { class: "quiet small" }, `security.${k}`)),
        h("div", { class: "row" }, n, h("span", { class: "quiet small" }, unit)), h("div", {}, save, box));
    }));
  return [h("p", { class: "quiet small" }, "Roles: viewer reads; reviewer works the Off-Platform bank, misses and flair choices; administrator changes settings and runs the tools; super manages security."), list, f, rules];
}

// API keys and vault: Grantees (programs the router gave a token, by door) and Grantors (programs
// that gave the router a key, kept in the vault). One picker at the top chooses which.
async function keysTab() {
  const side = hashParam("side") === "grantors" ? "grantors" : "grantees";
  const pick = select([{ value: "grantees", label: "Grantees: programs the router gave a token" },
    { value: "grantors", label: "Grantors: programs that gave the router a key (the vault)" }], side,
    { "aria-label": "Which keys", onchange: (e) => { location.hash = `#/security?tab=keys&side=${e.target.value}`; } });
  const body = side === "grantors" ? await grantorsPart() : await granteesPart();
  return [h("div", { class: "toolbar filters" }, field("Show", pick)), ...body];
}

function tokenMade(out, r) {
  out.replaceChildren(h("div", { class: "card panel" }, h("p", {}, `The ${r.name} token. Copy it now; it won't be shown again:`),
    h("pre", { class: "output" }, r.token)));
}

async function granteesPart() {
  const d = await api("/api/tokens");
  const out = h("div", {});
  const revoke = (t) => h("button", { type: "button", onclick: async () => {
    if (confirm(`Revoke the ${t.name} token? Whatever uses it is refused at a locked door.`)) { await api(`/api/tokens/${encodeURIComponent(t.name)}`, { method: "DELETE" }); route(); } } }, "Revoke");
  const used = (t) => (t.last_used ? when(t.last_used) : "never");
  // one grid: each door with its lock, its tokens, when they were last used, and Revoke
  const grid = h("div", { class: "door-grid", role: "table", "aria-label": "Doors and their tokens" },
    h("div", { class: "dg-head", role: "row" }, ["Locked", "Door", "Token", "Last used", ""].map((x) => h("span", { role: "columnheader" }, x))));
  for (const door of d.doors) {
    const box = errorBox();
    const sw = h("input", { type: "checkbox", checked: door.locked, "aria-label": `Lock the ${door.name} door` });
    sw.addEventListener("change", async () => {
      box.textContent = "";
      try { await api("/api/settings", { method: "PATCH", body: { path: ["security", "doors", door.name, "locked"], value: sw.checked } }); route(); }
      catch (e) { box.textContent = e.message; sw.checked = !sw.checked; }
    });
    const about = h("div", { class: "dg-door" }, h("strong", {}, door.name), " ", h("span", { class: door.locked ? "pill-ok" : "pill-off" }, door.locked ? "locked" : "open"),
      h("span", { class: "hint" }, door.description), h("span", { class: "hint" }, `Who: ${door.who || "-"} · role ${door.role}`),
      h("span", { class: "hint" }, door.paths.map((p, i) => [i ? " " : "", h("code", {}, p)])),
      !door.built_in ? h("button", { type: "button", class: "quiet-button", onclick: async () => {
        if (confirm(`Take out the ${door.name} door?`)) { await api(`/api/doors/${encodeURIComponent(door.name)}`, { method: "DELETE" }); route(); } } }, "Take out this door") : null, box);
    const lock = h("label", { class: "dg-lock check" }, sw);
    // a door can hold several tokens (Home Assistant's beside LiteLLM's): one more, any time
    if (door.tokens.length) {
      const more = h("button", { type: "button", class: "quiet-button" }, "Another token");
      more.addEventListener("click", busy(more, box, async () => {
        const name = prompt(`A name for another ${door.name} door token (who uses it):`, "");
        if (!name) return;
        tokenMade(out, await api("/api/tokens", { method: "POST", body: { name: name, role: door.role, door: door.name } }));
      }));
      about.append(more);
    }
    const tokens = door.tokens.length ? door.tokens : [null];
    tokens.forEach((t, i) => {
      const first = i === 0;
      let tokenCell, usedCell, actCell;
      if (t) {
        tokenCell = h("span", {}, h("strong", {}, t.name), " ", h("span", { class: "badge" }, t.role));
        usedCell = h("span", { class: t.last_used ? "" : "quiet" }, used(t));
        actCell = revoke(t);
      } else {
        const make = h("button", { type: "button" }, "Make its token");
        const mbox = errorBox();
        make.addEventListener("click", busy(make, mbox, async () => {
          const name = prompt(`A name for the ${door.name} door's token (who uses it):`, door.name);
          if (!name) return;
          tokenMade(out, await api("/api/tokens", { method: "POST", body: { name: name, role: door.role, door: door.name } }));
        }));
        tokenCell = h("span", { class: "quiet" }, "no token yet");
        usedCell = h("span", {}, "");
        actCell = h("span", {}, make, mbox);
      }
      grid.append(h("div", { class: "dg-row" + (first ? " dg-first" : ""), role: "row" },
        first ? lock : h("span", {}), first ? about : h("span", {}),
        h("span", { class: "dg-cell", "data-label": "Token" }, tokenCell), h("span", { class: "dg-cell", "data-label": "Last used" }, usedCell), h("span", { class: "dg-cell" }, actCell)));
    });
  }
  // tokens tied to no door: tie one to its door
  const untied = d.untied.length ? h("section", { class: "card panel" }, h("h2", {}, "Tokens not tied to a door"),
    h("p", { class: "quiet small" }, "Tie each to the door its program uses, so it shows on that door's line."),
    h("ul", { class: "rows" }, d.untied.map((t) => {
      const tie = select([{ value: "", label: "tie to a door…" }, ...d.doors.map((x) => ({ value: x.name, label: x.name }))], "", {
        "aria-label": `Tie ${t.name} to a door`,
        onchange: async (e) => { if (e.target.value) { await api(`/api/tokens/${encodeURIComponent(t.name)}`, { method: "PATCH", body: { door: e.target.value } }); route(); } } });
      return h("li", {}, h("span", {}, h("strong", {}, t.name), " ", h("span", { class: "badge" }, t.role), " ", h("span", { class: "quiet small" }, `last used ${used(t)}`)),
        h("span", { class: "row" }, tie, revoke(t)));
    }))) : null;
  // a new door, as it's needed
  const nm = input("text", { placeholder: "a short word, like mealie" });
  const ds = input("text", { placeholder: "what comes through it" });
  const wh = input("text", { placeholder: "who calls it (and so holds the token)" });
  const pa = input("text", { placeholder: "/ask, /hooks/*" });
  const ro = select(d.roles, "viewer");
  const abox = errorBox();
  const abtn = h("button", { class: "primary", type: "submit" }, "Add the door");
  const addForm = h("details", { class: "card panel fold" }, h("summary", {}, h("h2", {}, "Add a door")),
    h("form", {}, h("p", { class: "quiet small" }, "When a new program calls the router: which of the router's paths it uses, and the role its token needs. A new door starts open; give the program its token, then lock it."),
      h("div", { class: "grid2" }, field("Name", nm), field("Role", ro), field("Description", ds), field("Who", wh), field("Paths", pa, "The router's paths, separated by spaces; one ending in * covers everything under it.")), abox, abtn));
  addForm.querySelector("form").addEventListener("submit", busy(abtn, abox, async () => {
    await api("/api/doors", { method: "POST", body: { name: nm.value, description: ds.value, who: wh.value, paths: pa.value, role: ro.value } });
    route();
  }));
  return [h("p", { class: "quiet small" }, "The doors are the router's addresses other programs call. Lock a door only after its program has its token and has used it (Last used shows a time); a lock takes effect at once, and unticking opens it again. Doors are settings (security: doors: in settings.yaml)."),
    out, grid, untied, addForm];
}

async function grantorsPart() {
  const d = await api("/api/vault");
  if (d.off) return [h("p", { class: "warn" }, "The vault isn't available here (it needs the cryptography package).")];
  const stored = {};
  for (const k of d.keys) stored[k.name.toLowerCase()] = k;
  const setKey = (name) => async () => {
    const v = prompt(`The key for ${name} (it's kept encrypted; the router reads it when it starts):`);
    if (v) { await api(`/api/vault/${encodeURIComponent(name.toLowerCase())}`, { method: "PUT", body: { value: v } }); route(); }
  };
  const del = (k) => h("button", { type: "button", onclick: async () => { if (confirm(`Delete ${k.name} from the vault?`)) { await api(`/api/vault/${encodeURIComponent(k.name)}`, { method: "DELETE" }); route(); } } }, "Delete");
  const grid = h("div", { class: "door-grid grantors", role: "table", "aria-label": "Keys the router sends" },
    h("div", { class: "dg-head", role: "row" }, ["Grantor", "Key", "Comes from", "In the vault", ""].map((x) => h("span", { role: "columnheader" }, x))));
  const shown = new Set();
  for (const w of d.wanted || []) {
    const k = stored[w.name.toLowerCase()];
    if (k) shown.add(k.name.toLowerCase());
    grid.append(h("div", { class: "dg-row dg-first", role: "row" },
      h("span", { class: "dg-cell" }, h("strong", {}, w.for)), h("span", { class: "dg-cell" }, h("code", {}, w.name)),
      h("span", { class: "dg-cell", "data-label": "Comes from" }, h("span", { class: w.from ? "pill-ok" : "pill-bad" }, w.from ? w.from : "not set")),
      h("span", { class: "dg-cell quiet small", "data-label": "In the vault" }, k ? `ends with ${k.ends_with}, updated ${when(k.updated)}` : "-",
        k && !k.readable ? h("span", { class: "pill-bad" }, " can't be read: set it again") : null),
      h("span", { class: "dg-cell row" }, h("button", { type: "button", onclick: setKey(w.name) }, k ? "Replace" : "Set"), k ? del(k) : null)));
  }
  const others = d.keys.filter((k) => !shown.has(k.name.toLowerCase()));
  // step 1 of adding an app we didn't write: its key, with the program it's for
  const kName = input("text", { placeholder: "MEALIE_TOKEN" });
  const kFor = input("text", { placeholder: "mealie" });
  const kVal = input("password", { placeholder: "the key, from the app's own settings", autocomplete: "off" });
  const kBox = errorBox();
  const kBtn = h("button", { type: "submit", class: "primary" }, "Add the key");
  const addKey = h("form", {},
    h("p", { class: "quiet small" }, "Step 1 of adding an app: the key the app gave you, kept encrypted. Name the program it's for in one word; Add an app (Integrations) then offers this key and names the app after it."),
    h("div", { class: "grid2" }, field("Key's name", kName, "Capitals, digits and _ (like MEALIE_TOKEN)."), field("For (the program)", kFor), field("The key", kVal)), kBox, kBtn);
  addKey.addEventListener("submit", busy(kBtn, kBox, async () => {
    const n = kName.value.trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9_]{1,40}$/.test(n)) throw new Error("The key's name is capitals, digits and _ (like MEALIE_TOKEN)");
    if (!kFor.value.trim()) throw new Error("Say which program it's for");
    if (stored[n.toLowerCase()]) throw new Error(`There's already a key named ${n}: use Replace`);
    await api(`/api/vault/${encodeURIComponent(n.toLowerCase())}`, { method: "PUT", body: { value: kVal.value, service: kFor.value.trim() } });
    route();
  }));
  return [h("p", { class: "quiet small" }, `The keys other programs gave the router, kept encrypted in the vault and sent when the router calls them. The vault is read before .env; a change is used after a restart. Encryption key: ${d.encryption_key_from || "made on first use"} (back up data/keys/ separately).`),
    grid,
    others.length ? h("section", { class: "card panel" }, h("h2", {}, "Other keys in the vault"), h("p", { class: "quiet small" }, "No setting asks for these now."),
      h("ul", { class: "rows" }, others.map((k) => h("li", {}, h("span", {}, h("strong", {}, k.name), " ", h("span", { class: "quiet small" }, `ends with ${k.ends_with}, updated ${when(k.updated)}`)), del(k))))) : null,
    h("details", { class: "card panel fold" }, h("summary", {}, h("h2", {}, "Add a key")), addKey)];
}

// An address or a range (IPv4 or IPv6, with an optional /bits), or why not. The router checks again on Save.
function addressError(w, namesOk) {
  const name = /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
  if (namesOk && name.test(w)) return null;
  const v4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}(\/([0-9]|[12]\d|3[0-2]))?$/;
  const v6 = /^[0-9a-fA-F:]+:[0-9a-fA-F:]*(\/\d{1,3})?$/;
  return v4.test(w) || v6.test(w) || w.toLowerCase() === "local" ? null : `"${w.length > 40 ? w.slice(0, 40) + "…" : w}" isn't an address or range (like 192.168.1.50 or 192.168.1.0/24), or local${namesOk ? ", or a name like litcal.johnromanodorazio.com" : ""}`;
}

async function addressesTab() {
  const d = await api("/api/access");
  const state = {};
  const info = {
    inbound_allowed: ["Coming in: the chat door (port 8770) and the Wyoming ports",
      "Who may talk to the router: LiteLLM (it brings Home Assistant's requests), Home Assistant itself (Veil Guard Service, and the Wyoming speech-to-text entries), and the tools. Add LiteLLM's and Home Assistant's addresses."],
    admin_allowed: ["These pages (port 8771)",
      "Who may open these pages: the computers and phones you manage the router from. Your own address must stay on it (Save refuses to lock you out)."],
    outbound_allowed: ["Going out: where the router may call",
      "Everything the router calls: the way Off-Platform and every app and program on the Integrations page. A call anywhere else is refused before it's made. An app on the internet can be permitted by its name (litcal.johnromanodorazio.com)."],
  };
  const sections = Object.entries(info).map(([k, [title, about]]) => {
    state[k] = d[k].entries.slice();
    const chipsWrap = h("div", {});
    const drawChips = () => chipsWrap.replaceChildren(chipList(state[k], (v) => { state[k] = v; }, k === "outbound_allowed" ? "192.168.1.50, a range: 192.168.1.0/24, or a name" : "192.168.1.50, or a range: 192.168.1.0/24", (w) => addressError(w, k === "outbound_allowed")));
    drawChips();
    const seen = d[k].recently_allowed || [];
    return h("section", { class: "card panel" }, h("h2", {}, title),
      h("p", { class: "small" }, about),
      h("p", { class: d[k].local_network_only ? "quiet small" : "small" }, d[k].local_network_only
        ? "Now: empty, so the local network is permitted (home, this machine, Tailscale), never the internet. Add addresses to narrow it to just those."
        : `Now: only these ${state[k].length} address${state[k].length === 1 ? "" : "es"} or ranges.`),
      chipsWrap,
      seen.length ? h("details", { open: d[k].local_network_only }, h("summary", {}, `Seen and permitted lately (${seen.length})`),
        h("p", { class: "quiet small" }, "Who actually used this lately. Add the ones you expect, then Save, and anything else on the network is refused."),
        h("ul", { class: "rows" }, seen.map((r) => h("li", {}, h("span", {}, h("strong", {}, r.address), " ", h("span", { class: "quiet small" }, `${r.what || ""} · ${when(r.time)}`)),
          state[k].includes(r.address) ? h("span", { class: "badge pill-ok" }, "on the list")
            : h("button", { type: "button", onclick: (e) => { if (!state[k].includes(r.address)) state[k].push(r.address); drawChips(); e.target.replaceWith(h("span", { class: "badge" }, "added: Save to use it")); } }, "Add"))))) : null,
      d[k].recently_refused.length ? h("details", {}, h("summary", {}, `Recently refused (${d[k].recently_refused.length})`),
        h("p", { class: "quiet small" }, "Add one you expect (an app on the internet you switched on), then Save. Added to an empty list, local comes first, so the local network stays permitted."),
        h("ul", { class: "rows" }, [...new Set(d[k].recently_refused.map((r) => r.address))].map((a) => {
          const r = d[k].recently_refused.find((x) => x.address === a);
          return h("li", {}, h("span", {}, h("strong", {}, a), " ", h("span", { class: "quiet small" }, `${r.what || ""} · ${when(r.time)}`)),
            state[k].includes(a) ? h("span", { class: "badge pill-ok" }, "on the list")
              : h("button", { type: "button", onclick: (e) => { if (!state[k].length) state[k].push("local"); if (!state[k].includes(a)) state[k].push(a); drawChips(); e.target.replaceWith(h("span", { class: "badge" }, "added: Save to use it")); } }, "Add"));
        }))) : null);
  });
  const box = errorBox();
  const note = h("span", {});
  const save = h("button", { class: "primary", type: "button" }, "Save (in use at once)");
  save.addEventListener("click", busy(save, box, async () => { await api("/api/access", { method: "PUT", body: state }); note.replaceChildren(okNote("Saved, and in use")); }));
  return [h("p", { class: "quiet" }, "Three lists of permitted addresses, checked on every connection. Each one: a single address (192.168.1.50) or a range (192.168.1.0/24). Leave a list empty to permit your whole local network but never the internet; that's how it starts. The entry local keeps the local network in a list that also names addresses."),
    ...sections, box, h("div", { class: "row-actions" }, save, note)];
}

async function auditTab() {
  const d = await api("/api/audit");
  return [h("div", { class: "table-wrap" }, h("table", { class: "results audit" },
    h("thead", {}, h("tr", {}, ["When", "Who", "What", "Of", "Detail", "From"].map((x) => h("th", {}, x)))),
    h("tbody", {}, d.events.map((e) => h("tr", {}, [e.time, e.who, e.action, e.target, e.detail, e.client].map((x) => h("td", {}, x || "")))))))];
}

// ---------- You: account and guides ----------

// The five colour schemes (veil.css has their colours, light and dark).
const PALETTES = [["teal", "Teal and amber"], ["ocean", "Ocean"], ["plum", "Plum"], ["forest", "Forest"], ["indigo", "Indigo and teal"]];

async function accountPage() {
  const cur = input("password", { autocomplete: "current-password" });
  const nw = input("password", { autocomplete: "new-password" });
  const box = errorBox();
  const note = h("span", {});
  const btn = h("button", { class: "primary", type: "submit" }, "Change password");
  const f = h("form", { class: "card panel" }, h("h2", {}, "Your password"), field("Current password", cur), field("New password", nw, `${passwordRule()}; signs you out everywhere else.`), box, btn, note);
  f.addEventListener("submit", busy(btn, box, async () => { await api("/api/account/password", { method: "POST", body: { current: cur.value, new: nw.value } }); note.replaceChildren(okNote("Changed")); cur.value = ""; nw.value = ""; }));
  let theme = "auto";
  try { theme = localStorage.getItem("veil-theme") || "auto"; } catch (e) { theme = "auto"; }
  const themes = select([{ value: "auto", label: "follow the device" }, { value: "light", label: "light" }, { value: "dark", label: "dark" }], theme, {
    onchange: (e) => {
      try { if (e.target.value === "auto") localStorage.removeItem("veil-theme"); else localStorage.setItem("veil-theme", e.target.value); } catch (err) { /* private window */ }
      if (e.target.value === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", e.target.value);
    } });
  let palette = "teal";
  try { palette = localStorage.getItem("veil-palette") || "teal"; } catch (e) { palette = "teal"; }
  const schemes = h("div", { class: "palettes", role: "radiogroup", "aria-label": "Colour scheme" },
    PALETTES.map(([id, label]) => {
      const radio = h("input", { type: "radio", name: "palette", value: id, checked: id === palette, onchange: () => {
        try { if (id === "teal") localStorage.removeItem("veil-palette"); else localStorage.setItem("veil-palette", id); } catch (err) { /* private window */ }
        if (id === "teal") document.documentElement.removeAttribute("data-palette"); else document.documentElement.setAttribute("data-palette", id);
      } });
      return h("label", { class: "palette", "data-palette": id }, radio,
        h("span", { class: "swatches", "aria-hidden": "true" }, h("span", { class: "sw p" }), h("span", { class: "sw s" }), h("span", { class: "sw a" })),
        h("span", {}, label));
    }));
  const out = h("button", { type: "button", onclick: async () => { await api("/api/session", { method: "DELETE" }); session = null; route(); } }, "Sign out");
  return [h("h1", {}, "Account"), h("p", {}, `${session.user.name} (${session.user.role}) · ${session.version}`), f,
    h("section", { class: "card panel" }, h("h2", {}, "Look"),
      h("p", { class: "quiet small" }, "Kept in this browser only: another browser or another person keeps their own."),
      field("Light or dark", themes),
      h("fieldset", { class: "plain" }, h("legend", {}, "Colour scheme"),
        h("p", { class: "hint" }, "Each has three colours: the main one (buttons, links, this page in the menu), a second and an accent (charts and marks)."),
        schemes)), out];
}

async function guidePage() {
  const which = (location.hash.split("?g=")[1] || "users");
  const tabs = h("div", { class: "tabs", role: "tablist" }, [["users", "User's guide"], ["guide", "Coder's guide"], ["design", "Design"], ["readme", "README"]]
    .map(([id, label]) => h("button", { role: "tab", "aria-selected": id === which ? "true" : "false", onclick: () => { location.hash = `#/guide?g=${id}`; } }, label)));
  let text = "";
  try { text = await api(`/api/guide/${which}`); } catch (e) { text = e.message; }
  return [h("h1", {}, "Guides"), tabs, h("div", { class: "card guide gap-top" }, h("pre", { class: "guide-text" }, text))];
}

const PAGE_FNS = {
  overview: overviewPage, stats: withRules("stats", "Stats", statsPage), transactions: transactionsList, inbound: transactionsList, outbound: transactionsList, bank: withRules("bank", "Off-Platform Bank", bankPage), savings: withRules("savings", "Savings", savingsPage),
  try: tryPage, topics: withRules("topics", "Seed Topics", topicsPage, { build: ["Build", async () => [
    h("p", { class: "quiet" }, "Build the keyword tiers from the datasets after changing a topic's seeds or the build's settings (Rules), then restart. The utilities look at the datasets and how a topic scores on them."),
    ...(await toolsView("topics"))]] }), tools: withRules("tools", "Tools", toolsPage), misses: withRules("misses", "Misses", missesPage, { tools: ["Tools", async () => [
    h("p", { class: "quiet" }, "Review the misses against today's router, make one a test case, or drop one."), ...(await toolsView("misses"))]] }), flair: flairPage, sparkle: sparklePage,
  integrations: integrationsPage, settings: settingsPage, firewall: firewallPage, security: securityPage,
  account: accountPage, guide: guidePage, fleas: fleasPage, words: wordsPage, people: peoplePage,
};

// People: one row per person, a column per attached app (veil/people.py, settings.yaml people:).
// Any name in a row is the same person inside the router; an app asks for its own column only.
async function peoplePage() {
  const d = await api("/api/people");
  const titles = Object.fromEntries(d.columns.map((c) => [c.id, c.title]));
  let apps = d.apps.slice();
  let rows = d.rows.map((r) => Object.assign({}, r));
  const box = errorBox();
  const wrap = h("div", { class: "table-wrap" });
  const names = (v) => v.split(",").map((x) => x.trim()).filter(Boolean);
  function draw() {
    const cell = (r, key, many, label) => {
      const el = input("text", { value: many ? (r[key] || []).join(", ") : (r[key] || ""), "aria-label": label, class: "grid-in" });
      el.addEventListener("input", () => { r[key] = many ? names(el.value) : el.value; });
      return h("td", {}, el);
    };
    const head = h("tr", {}, h("th", { title: "The router's own name for the person (optional)" }, "Wepwawet"),
      h("th", { title: "What people call them out loud" }, "Called"),
      ...apps.map((a) => h("th", {}, titles[a] || a, " ",
        h("button", { type: "button", class: "plus", "aria-label": `remove the ${titles[a] || a} column`, onclick: () => { apps = apps.filter((x) => x !== a); draw(); } }, "×"))),
      h("th", {}, ""));
    const body = rows.map((r, i) => h("tr", {}, cell(r, "wepwawet", false, "Wepwawet name"), cell(r, "called", true, "called"),
      ...apps.map((a) => cell(r, a, true, `${titles[a] || a} names`)),
      h("td", {}, h("button", { type: "button", onclick: () => { rows.splice(i, 1); draw(); } }, "Remove"))));
    wrap.replaceChildren(h("table", { class: "matrix people-grid" }, h("thead", {}, head), h("tbody", {}, body)));
    const free = d.columns.filter((c) => !apps.includes(c.id));
    addCol.replaceChildren(...(free.length ? [colSel = select(free.map((c) => ({ value: c.id, label: c.title })), free[0].id, { "aria-label": "an app to add as a column" }), addColBtn] : []));
  }
  let colSel = null;
  const addCol = h("span", {});
  const addColBtn = h("button", { type: "button", onclick: () => { if (colSel) { apps.push(colSel.value); draw(); } } }, "Add a column");
  const addRow = h("button", { type: "button", onclick: () => { rows.push({ wepwawet: "", called: [] }); draw(); } }, "Add a person");
  const save = h("button", { type: "button" }, "Save");
  save.addEventListener("click", busy(save, box, async () => {
    const got = await api("/api/people", { method: "PUT", body: { apps: apps, rows: rows } });
    apps = got.apps.slice(); rows = got.rows.map((r) => Object.assign({}, r)); draw();
    save.after(okNote("Saved."));
  }));
  draw();
  return [h("h1", {}, "People"),
    h("p", { class: "quiet small" }, "One row per person, a column per attached app. Names in a cell are separated by commas. Inside the router any name in a row is the same person: the firewall and who may change brain fleas match on all of them. An app asks through its own door (GET /people/<app>) and gets only its own column, beside the Wepwawet name. Kept in settings.yaml (people:); used as soon as it's saved."),
    h("section", { class: "card panel" }, wrap, h("div", { class: "row-actions" }, addRow, addCol, save, box))];
}

// Words understood (Oct 18): the vocab/ files' word lists on a page, what the router understands
// rather than says (yes and no, fillers, dismissals, the learn commands, dates, moods), each list
// with its comment, edited as chips and saved on its own (comments kept). A file's other values
// (numbers, word: value maps) are shown as they are and stay in the file.
async function wordsPage() {
  const d = await api("/api/words");
  const isAdmin = allowed("tools");
  const files = d.files.map((f) => {
    const lists = f.lists.map((l) => {
      let words = l.words.slice();
      const box = errorBox();
      const save = h("button", { type: "button", disabled: true }, "Save");
      const chips = chipList(words, (w) => { words = w; save.disabled = !isAdmin; });
      save.addEventListener("click", busy(save, box, async () => {
        const r = await api(`/api/words/${encodeURIComponent(f.file)}`, { method: "PUT", body: { path: l.path, words: words, stamp: f.stamps[l.path[0]] } });
        f.stamps[l.path[0]] = r.stamp;
        save.disabled = true; save.after(okNote("Saved. Restart to use it."));
      }));
      return h("div", { class: "setting" }, h("div", {}, h("strong", {}, l.path.join(" › ")), " ", h("code", { class: "quiet small" }, `${f.file}.${l.path.join(".")}`),
        l.note ? h("p", { class: "hint" }, l.note) : null), chips, isAdmin ? h("div", {}, save, box) : null);
    });
    const other = f.other.length ? h("details", {}, h("summary", { class: "small" }, `Also in this file, as it is (${f.other.length})`),
      h("div", { class: "table-wrap" }, h("table", { class: "matrix" }, h("thead", {}, h("tr", {}, h("th", {}, "Word"), h("th", {}, "Means"))),
        h("tbody", {}, f.other.map((o) => h("tr", {}, h("td", {}, h("code", {}, o.path.join(" › "))), h("td", {}, typeof o.value === "object" ? JSON.stringify(o.value) : String(o.value)))))))) : null;
    return foldBox(`words-${f.file}`, `${f.file} (${f.lists.length} list${f.lists.length === 1 ? "" : "s"})`, false,
      f.note ? h("p", { class: "quiet small" }, f.note) : null, ...lists, other);
  });
  return [h("h1", {}, "Words understood"),
    h("p", { class: "quiet" }, "The words the router understands rather than says, from the vocab/ files: yes and no, the filler and dismissals, polite words, sentence shapes, the learn commands, dates and numbers, moods, follow-up cues. Each list is used as it's written; type a word and press Enter to add it, × to take one out, then Save (used after a restart). A list changed in the file or on another page since this one opened isn't saved over: reload first. What's said, not understood, is on Persona Flair, Sayings."),
    ...files];
}

// Brain fleas: the household's small true facts, answered at home before the Off-Platform Bank, built
// with the same line-by-line builder as an app's User rules (veil/fleas.py, learn/fleas.yaml).
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

route();
