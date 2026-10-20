// Light, dark, or follow the device, and one of five colour schemes; remembered in this browser only.
// Runs before the page draws, so it never flashes the wrong one.
(function () {
  var choice = null;
  var palette = null;
  try {
    choice = localStorage.getItem("veil-theme");
    palette = localStorage.getItem("veil-palette");
  } catch (e) { /* private window: the defaults */ }
  if (choice === "light" || choice === "dark") {
    document.documentElement.setAttribute("data-theme", choice);
  }
  if (palette === "ocean" || palette === "plum" || palette === "forest" || palette === "indigo") {
    document.documentElement.setAttribute("data-palette", palette);
  }
})();
