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

  /* ---- media and cues ---- */
  const mediaEl = $("rv-media-el");
  const segEls = Array.from(document.querySelectorAll(".rv-seg"));
  const cues = Array.isArray(data.cues) ? data.cues : [];
  let activeIndex = -1;

  function unionRange(names) {
    let start = Infinity, end = -Infinity;
    names.forEach((n) => { const r = anchorRange(n); if (r) { start = Math.min(start, r.start); end = Math.max(end, r.end); } });
    return start === Infinity ? null : { start, end };
  }
  function applyCue(index) {
    segEls.forEach((el, i) => el.classList.toggle("rv-active", i === index));
    document.querySelectorAll(".rv-node-active").forEach((el) => el.classList.remove("rv-node-active"));
    activeIndex = index;
    const seg = cues[index];
    if (!seg) { cueBox = null; return; }
    const range = seg.show ? unionRange(seg.show) : null;
    cueBox = range;
    if (range) boxLines(range.start, range.end);
    if (seg.diagram) {
      const fig = document.querySelector('.rv-diagram[data-diagram="' + seg.diagram + '"]');
      if (fig) {
        fig.scrollIntoView({ block: "center", behavior: "smooth" });
        if (seg.node) { const node = fig.querySelector('[data-node="' + seg.node + '"]'); if (node) node.classList.add("rv-node-active"); }
      }
    }
    const el = segEls[index];
    if (el) el.scrollIntoView({ block: "nearest" });
  }
  function segmentAt(t) {
    for (let i = cues.length - 1; i >= 0; i--) if (t >= cues[i].start) return i;
    return -1;
  }
  function activeSegment() { return activeIndex; }
  /* A seek before metadata has loaded is dropped by the browser and may echo a timeupdate at 0,
     so the target is parked until loadedmetadata and timeupdate is ignored meanwhile. */
  let pendingSeekTo = null;
  function seek(seconds) {
    if (!mediaEl) return;
    const i = segmentAt(seconds);
    if (i !== activeIndex) applyCue(i);
    if (mediaEl.readyState >= 1) mediaEl.currentTime = seconds;
    else pendingSeekTo = seconds;
  }
  if (mediaEl) {
    mediaEl.addEventListener("loadedmetadata", () => {
      if (pendingSeekTo !== null) { mediaEl.currentTime = pendingSeekTo; pendingSeekTo = null; }
    });
    mediaEl.addEventListener("timeupdate", () => {
      if (pendingSeekTo !== null || mediaEl.seeking) return;
      const i = segmentAt(mediaEl.currentTime);
      if (i !== activeIndex) applyCue(i);
    });
    mediaEl.addEventListener("error", () => {
      const err = document.querySelector(".rv-media-error");
      if (err) err.hidden = false;
      mediaEl.hidden = true;
    });
    segEls.forEach((el) => {
      const go = () => seek(parseFloat(el.dataset.start));
      el.addEventListener("click", go);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    const mediaPane = $("rv-media");
    if (mediaPane) mediaPane.addEventListener("keydown", (e) => {
      if (e.key === " " && e.target === mediaPane) { e.preventDefault(); if (mediaEl.paused) mediaEl.play(); else mediaEl.pause(); }
    });
    if (pendingSeek !== null) mediaEl.addEventListener("loadedmetadata", () => seek(pendingSeek), { once: true });
  }

  /* ---- quiz: page-local, nothing stored ---- */
  document.querySelectorAll(".rv-quiz form").forEach((form) => {
    const questions = Array.from(form.querySelectorAll(".rv-q"));
    function grade(q) {
      const chosen = q.querySelector("input:checked");
      const fb = q.querySelector(".rv-q-feedback");
      if (!chosen) { q.classList.remove("rv-right", "rv-wrong"); fb.hidden = true; return null; }
      const right = chosen.value === q.dataset.answer;
      q.classList.toggle("rv-right", right);
      q.classList.toggle("rv-wrong", !right);
      fb.textContent = right ? "Correct." : "Not quite. Try another answer.";
      fb.hidden = false;
      return right;
    }
    questions.forEach((q) => q.addEventListener("change", () => grade(q)));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const results = questions.map(grade);
      const answered = results.filter((r) => r !== null).length;
      const correct = results.filter((r) => r === true).length;
      const score = form.querySelector(".rv-quiz-score");
      score.textContent = answered < questions.length
        ? correct + " of " + questions.length + " correct so far; " + (questions.length - answered) + " unanswered."
        : correct + " of " + questions.length + " correct.";
      score.hidden = false;
    });
  });

  window.RV = { data, openPanel, setTheme, boxLines, clearBox, pin, showAnchor, applyHash, applyCue, seek, activeSegment,
                get pinned() { return pinned; }, get boxed() { return boxed; },
                setCueBox(r) { cueBox = r; }, get pendingSeek() { return pendingSeek; } };
})();
