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

  /* ---- code boxes ---- */
  const codeBody = $("rv-code-body");
  const lines = codeBody ? Array.from(codeBody.querySelectorAll(".rv-line")) : [];
  let boxed = null;          // {start, end} currently drawn
  let pinned = null;         // anchor name pinned by click, or null
  let cueBox = null;         // {start, end} from the active narration segment, or null

  function clearBox() {
    lines.forEach((l) => l.classList.remove("rv-boxed", "rv-box-start", "rv-box-end"));
    boxed = null;
  }
  function boxLines(start, end, opts) {
    clearBox();
    for (let n = start; n <= end; n++) {
      const el = lines[n - 1];
      if (!el) continue;
      el.classList.add("rv-boxed");
      if (n === start) el.classList.add("rv-box-start");
      if (n === end) el.classList.add("rv-box-end");
    }
    boxed = { start, end };
    if (!opts || opts.scroll !== false) {
      const first = lines[start - 1];
      if (first && codeBody) {
        const top = first.offsetTop - codeBody.clientHeight * 0.3;
        codeBody.scrollTo({ top: Math.max(0, top), behavior: opts && opts.instant ? "auto" : "smooth" });
      }
    }
  }
  function anchorRange(name) { return data.anchors[name] || null; }
  function showAnchor(name, opts) {
    const r = anchorRange(name);
    if (r) boxLines(r.start, r.end, opts);
    return !!r;
  }
  function restore() {
    if (pinned && showAnchor(pinned, { scroll: false })) return;
    if (cueBox) { boxLines(cueBox.start, cueBox.end, { scroll: false }); return; }
    clearBox();
  }
  function pin(name) {
    pinned = name;
    document.querySelectorAll(".rv-anchor.rv-pinned, .rv-svg-anchor.rv-pinned").forEach((el) => el.classList.remove("rv-pinned"));
    body.classList.toggle("rv-pinned", !!name);
    if (name) {
      document.querySelectorAll('[data-anchor="' + name + '"]').forEach((el) => el.classList.add("rv-pinned"));
      showAnchor(name);
      if (history.replaceState) history.replaceState(null, "", "#" + name);
    } else {
      if (history.replaceState) history.replaceState(null, "", location.pathname + location.search);
      restore();
    }
  }

  /* anchor phrases in the lesson and anchor nodes in diagrams */
  document.querySelectorAll("[data-anchor]").forEach((el) => {
    const name = el.dataset.anchor;
    el.addEventListener("mouseenter", () => showAnchor(name));
    el.addEventListener("focus", () => showAnchor(name));
    el.addEventListener("mouseleave", restore);
    el.addEventListener("blur", restore);
    el.addEventListener("click", (e) => { e.preventDefault(); pin(pinned === name ? null : name); });
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pin(pinned === name ? null : name); } });
  });

  /* variants jump list */
  document.querySelectorAll(".rv-variant").forEach((b) => b.addEventListener("click", () => pin(b.dataset.anchor)));

  /* URL fragment: #anchor-name pins, #t=12.5 seeks (Task 13 reads pendingSeek) */
  let pendingSeek = null;
  function applyHash() {
    const h = decodeURIComponent(location.hash.replace(/^#/, ""));
    if (!h) return;
    if (/^t=/.test(h)) { pendingSeek = parseFloat(h.slice(2)) || 0; return; }
    if (anchorRange(h)) pin(h);
  }

  /* keyboard */
  document.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if (e.key === "Escape") { pin(null); return; }
    if (e.key === "[") { const a = document.querySelector(".rv-prev"); if (a) location.href = a.href; }
    if (e.key === "]") { const a = document.querySelector(".rv-next"); if (a) location.href = a.href; }
  });

  /* initial state: fragment wins, else the lesson's start anchor */
  applyHash();
  if (!pinned && data.start) showAnchor(data.start, { instant: true });
  window.addEventListener("hashchange", applyHash);

  window.RV = { data, openPanel, setTheme, boxLines, clearBox, pin, showAnchor, applyHash,
                get pinned() { return pinned; }, get boxed() { return boxed; },
                setCueBox(r) { cueBox = r; }, get pendingSeek() { return pendingSeek; } };
  /* Task 13 appends media and quiz below this line. */
})();
