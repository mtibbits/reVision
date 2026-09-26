/* reVision engine front end. No network, no framework. Behaviour only; the page is complete without it. */
(function () {
  "use strict";

  const dataEl = document.getElementById("rv-data");
  const data = dataEl ? JSON.parse(dataEl.textContent) : { anchors: {}, start: null, cues: null, variants: [] };
  const body = document.body;
  const $ = (id) => document.getElementById(id);

  /* ---- storage helpers: per-device conveniences only, never required ---- */
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function save(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } }

  /* ---- rail and side panel ---- */
  const panel = $("rv-panel");
  const railButtons = Array.from(document.querySelectorAll(".rv-rail-btn"));
  function openPanel(name) {
    const open = !!name && body.dataset.panel !== name;
    body.dataset.panel = open ? name : "";
    document.documentElement.style.setProperty("--rv-panel-w", open ? "280px" : "0px");
    if (panel) panel.hidden = !open;
    document.querySelectorAll(".rv-panel-view").forEach((v) => { v.hidden = !(open && v.dataset.view === name); });
    railButtons.forEach((b) => b.setAttribute("aria-pressed", String(open && b.dataset.panel === name)));
  }
  railButtons.forEach((b) => b.addEventListener("click", () => openPanel(b.dataset.panel)));

  /* ---- theme ---- */
  function setTheme(mode) {
    if (mode === "light" || mode === "dark") document.documentElement.dataset.theme = mode;
    else delete document.documentElement.dataset.theme;
    save("rv-theme", mode || "auto");
    document.querySelectorAll(".rv-theme").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.theme === (mode || "auto"))));
  }
  document.querySelectorAll(".rv-theme").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.theme)));
  setTheme(load("rv-theme") || "auto");

  /* ---- splitter ---- */
  const splitter = $("rv-splitter");
  const main = document.querySelector(".rv-main");
  function setCodeWidth(px) {
    const min = 240, max = main.clientWidth - 240 - 6;
    const w = Math.max(min, Math.min(max, px));
    document.documentElement.style.setProperty("--rv-code-w", w + "px");
    save("rv-code-w", String(w));
  }
  if (splitter && main) {
    const saved = parseInt(load("rv-code-w") || "", 10);
    if (saved && window.innerWidth > 900) setCodeWidth(saved);
    let dragging = false;
    splitter.addEventListener("pointerdown", (e) => { dragging = true; splitter.setPointerCapture(e.pointerId); });
    splitter.addEventListener("pointermove", (e) => { if (dragging && window.innerWidth > 900) setCodeWidth(e.clientX - main.getBoundingClientRect().left); });
    splitter.addEventListener("pointerup", () => { dragging = false; });
    splitter.addEventListener("keydown", (e) => {
      const cur = $("rv-code").getBoundingClientRect().width;
      if (e.key === "ArrowLeft") setCodeWidth(cur - 24);
      if (e.key === "ArrowRight") setCodeWidth(cur + 24);
    });
  }

  window.RV = { data, openPanel, setTheme };
  /* Tasks 12 and 13 append anchors, variants, fragments, media, and quiz below this line. */
})();
