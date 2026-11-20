"use strict";
/* App shell, reader, and the vocabulary / grammar / workbook / review / saved / status tabs.
   Translation = translate.js (Google Translate in the browser). Storage = store.js. Study = study.js. Stories = stories.js. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LEVELS = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"];
const TRIM = /^[\s"'“”‘’.,!?…()\[\]:;~\-–—<>]+|[\s"'“”‘’.,!?…()\[\]:;~\-–—<>]+$/g;
const isKorean = s => /[가-힣]/.test(s);
let RO = false;                       // public deployment: no editing / review

async function api(path, opts = {}) {
  const r = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) {
    let msg = r.statusText || `HTTP ${r.status}`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : j.detail ? JSON.stringify(j.detail) : msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}
function showError(msg) {
  const b = $("#err-banner");
  if (!b) return;
  b.textContent = "Something went wrong: " + msg + "  (click to dismiss)";
  b.hidden = false;
}
window.addEventListener("unhandledrejection", ev => { showError((ev.reason && ev.reason.message) || String(ev.reason)); });

/* ---------- language of the translations ---------- */
$("#lang").innerHTML = Object.entries(TL_LANGS).map(([k, v]) => `<option value="${k}">${h(v)}</option>`).join("");
$("#lang").value = TL.lang;
$("#lang").onchange = () => { TL.lang = $("#lang").value; if (lastPanel) showPanel(lastPanel); };

/* ---------- tabs ---------- */
$$("#tabs button").forEach(b => b.onclick = () => {
  $$("#tabs button").forEach(x => x.classList.toggle("on", x === b));
  $$(".tab").forEach(t => t.hidden = t.id !== "tab-" + b.dataset.tab);
  const loader = { stories: loadStories, study: loadStudyHome, vocab: loadVocab, grammar: loadGrammar, workbook: loadWorkbook, review: loadReview, saved: loadSaved, status: loadStatus }[b.dataset.tab];
  if (loader) Promise.resolve().then(loader).catch(e => showError(e.message));
});

/* =====================================================================================================
   READER
   cur = { id, title, text, highlights: [{start, end, kind: "vocab"|"grammar", ref?, entry?}], storyId?, story? }
   ===================================================================================================== */
let cur = null;
let lastPanel = null;

async function loadPassages() {
  const list = await store.passages.list();
  $("#passage-list").innerHTML = list.map(p => `<li data-id="${h(p.id)}" class="${cur && String(cur.id) === String(p.id) ? "on" : ""}"><span>${h(p.title || p.preview || "(untitled)")}</span></li>`).join("") || `<li class="muted">No passages yet</li>`;
  $$("#passage-list li[data-id]").forEach(li => li.onclick = () => openPassage(li.dataset.id));
}

async function openPassage(id) {
  const p = await store.passages.get(id);
  if (!p) return;
  await withLookupHighlights(p);
  showReading(p);
}

/* Colour the words that are in the textbook word list. Plain rules, no morphology: approximate (see services/lookup.py). */
async function withLookupHighlights(doc) {
  doc.highlights = [];
  const tokens = [...doc.text.matchAll(/\S+/g)];
  const words = [...new Set(tokens.map(m => m[0].replace(TRIM, "")).filter(w => /^[가-힣]+$/.test(w)))].slice(0, 1500);
  if (!words.length) return;
  try {
    const { matches } = await api("/vocab/lookup", { method: "POST", body: { tokens: words } });
    for (const m of tokens) {
      const core = m[0].replace(TRIM, "");
      const hit = matches[core];
      if (!hit) continue;
      const start = m.index + m[0].indexOf(core);
      doc.highlights.push({ start, end: start + core.length, kind: "vocab", entry: hit });
    }
  } catch { /* colours are a nicety: the text stays readable and clickable without them */ }
}

function showReading(doc) {
  cur = doc;
  lastPanel = null;
  $("#p-title").textContent = doc.title || "(untitled)";
  const isStory = !!doc.storyId;
  $("#btn-edit").hidden = isStory; $("#btn-delete").hidden = isStory; $("#btn-read").hidden = false;
  $("#story-box").hidden = !isStory;
  const legend = $("#legend");
  legend.hidden = false;
  legend.innerHTML = isStory
    ? `<span class="dot v"></span> word to learn <span class="dot g"></span> grammar to learn <span class="muted">· click any word for its translation</span>`
    : `<span class="dot v"></span> word found in your textbooks' word list <span class="muted">(approximate matching) · click any word for its translation</span>`;
  renderText();
  $("#detail").innerHTML = `<p class="muted">Click any word. Its translation appears here.</p>`;
  loadPassages();
  if (typeof onPassageOpened === "function") onPassageOpened();
}

function renderText() {
  if (!cur) return;
  const text = cur.text;
  const hl = (cur.highlights || []).map((H, i) => ({ ...H, i })).sort((a, b) => a.start - b.start);
  let html = "", pos = 0, hi = 0;
  for (const m of text.matchAll(/\S+/g)) {
    const s = m.index, e = s + m[0].length;
    html += h(text.slice(pos, s)) + `<span class="w" data-s="${s}" data-e="${e}">`;
    while (hi < hl.length && hl[hi].end <= s) hi++;
    let p = s, j = hi;
    while (j < hl.length && hl[j].start < e) {
      const H = hl[j], a = Math.max(H.start, s), b = Math.min(H.end, e);
      if (a > p) html += h(text.slice(p, a));
      if (b > a) html += `<span class="h ${H.kind === "grammar" ? "hg" : "hv"}" data-h="${H.i}">${h(text.slice(a, b))}</span>`;
      p = Math.max(p, b); j++;
    }
    if (p < e) html += h(text.slice(p, e));
    html += `</span>`;
    pos = e;
  }
  $("#text").innerHTML = html + h(text.slice(pos));
}

$("#text").onclick = ev => {
  const w = ev.target.closest(".w");
  if (!w) return;
  const hEl = ev.target.closest("[data-h]");
  $$("#text .w.sel").forEach(x => x.classList.remove("sel"));
  w.classList.add("sel");
  openWord(+w.dataset.s, +w.dataset.e, hEl ? +hEl.dataset.h : null);
};

function sentenceAround(text, pos) {
  for (const m of text.matchAll(/[^\n.!?…]+(?:[.!?…]+["'”’)\]]*)?/g)) {
    if (m.index <= pos && pos < m.index + m[0].length) return m[0].trim();
  }
  return "";
}

function openWord(s, e, hi) {
  const text = cur.text, raw = text.slice(s, e), word = raw.replace(TRIM, "") || raw;
  const H = hi != null ? cur.highlights[hi] : null;
  const ctx = { word, sentence: sentenceAround(text, s), kind: H ? H.kind : null, ref: H ? H.ref : null, entry: null, item: null, phrase: null };
  if (H) {
    const shown = text.slice(H.start, H.end).replace(TRIM, "");
    if (shown !== word) ctx.phrase = shown;
    if (H.entry) ctx.entry = H.entry;
    if (cur.story && H.ref) {
      if (H.kind === "vocab") ctx.entry = (cur.story.target_vocab.find(t => t.target === H.ref) || {}).entry || null;
      else ctx.item = (cur.story.target_grammar.find(t => t.target === H.ref) || {}).item || null;
      ctx.target = H.ref;
    }
  }
  showPanel(ctx);
}

/* ---------- the side panel ---------- */
function showPanel(ctx) {
  lastPanel = ctx;
  const box = $("#detail");
  const lang = TL.lang;
  box.innerHTML = `
    <h2>${ctx.kind === "grammar" ? "Grammar" : "Word"}</h2>
    <div class="kword ko">${h(ctx.word)}</div>
    <div id="tr-word" class="trbox"></div>
    ${ctx.phrase ? `<div class="lbl">Highlighted phrase</div><div class="ko"><b>${h(ctx.phrase)}</b></div><div id="tr-phrase" class="trbox"></div>` : ""}
    <div id="textbook"></div>
    ${ctx.sentence ? `<div class="lbl">Sentence</div><blockquote class="ko">${h(ctx.sentence)}</blockquote><div id="tr-sent" class="trbox"></div>` : ""}
    <div class="row actions">
      <button id="p-save" class="primary">${ctx.entry || ctx.item ? "Save to my flashcards" : `Save “${h(ctx.word)}”`}</button>
      ${ctx.noTranslate ? "" : `<a href="${gtLink(ctx.word, lang)}" target="_blank" rel="noopener">Google Translate ↗</a>`}
    </div>`;
  if (ctx.noTranslate) $("#tr-word").innerHTML = "";                       // a grammar pattern like V+아/어 보니(까) is not translatable text
  else if (isKorean(ctx.word)) gtRender($("#tr-word"), ctx.word, { roman: true, alts: true });
  else $("#tr-word").innerHTML = `<span class="muted">(not Korean text)</span>`;
  if (ctx.phrase) gtRender($("#tr-phrase"), ctx.phrase);
  if (ctx.sentence) gtRender($("#tr-sent"), ctx.sentence);
  renderTextbookBlock(ctx);
  $("#p-save").onclick = async ev => {
    try {
      if (ctx.entry) await store.saved.add({ kind: "vocab", ref_id: ctx.entry.id, sentence: ctx.sentence, item: { headword: ctx.entry.headword, level: ctx.entry.level, unit: ctx.entry.unit } });
      else if (ctx.item) await store.saved.add({ kind: "grammar", ref_id: ctx.item.id, sentence: ctx.sentence, item: { headword: ctx.item.pattern, level: ctx.item.level, unit: ctx.item.unit } });
      else await store.saved.add({ kind: "word", text: ctx.word, sentence: ctx.sentence });
      ev.target.textContent = "Saved ✓"; ev.target.disabled = true;
    } catch (e) { showError(e.message); }
  };
}

const refLine = it => [it.level && `Level ${it.level}`, it.unit && `Unit ${it.unit}`, it.page ? `p. ${it.page}` : (it.pdf_page ? `PDF p. ${it.pdf_page}` : null)].filter(Boolean).join(" · ") || "no level/unit recorded";

async function renderTextbookBlock(ctx) {
  const el = $("#textbook");
  if (ctx.entry) {
    const e = ctx.entry;
    el.innerHTML = `<div class="lbl">In your textbooks</div><div class="tbcard"><b class="ko">${h(e.headword.replace(/\([^)]*\)/g, ""))}</b> <span class="muted">${h(refLine(e))}</span>${e.match === "stem" || e.match === "noun" ? ` <span class="muted">(approximate match)</span>` : ""}<div id="tb-extra"></div></div>`;
    try {
      const d = await api("/vocab/" + e.id);
      if (lastPanel !== ctx) return;
      $("#tb-extra").innerHTML = (d.meaning_en ? `<div>${h(d.meaning_en)}</div>` : "") + (d.examples.length ? d.examples.slice(0, 3).map(x => `<blockquote class="ko">${h(x.sentence)}</blockquote>`).join("") : "");
    } catch { /* optional detail */ }
  } else if (ctx.item || (ctx.kind === "grammar" && ctx.target)) {
    const g = ctx.item;
    if (!g) { el.innerHTML = `<div class="warn">“${h(ctx.target)}” is not in the grammar database.</div>`; return; }
    el.innerHTML = `<div class="lbl">Grammar in your textbooks</div><div class="tbcard"><b class="ko">${h(g.pattern)}</b> <span class="muted">${h(refLine(g))}</span>
      ${g.status === "needs_review" ? `<div class="warn">This entry was read from a scan and has not been reviewed: the pattern may contain OCR errors.</div>` : ""}
      <div id="tb-extra"></div></div>`;
    try {
      const d = await api("/grammar/" + g.id);
      if (lastPanel !== ctx) return;
      $("#tb-extra").innerHTML = grammarBody(d, true);
      wireTranslateButtons($("#tb-extra"));
    } catch { /* optional detail */ }
  }
}

function grammarBody(g, compact) {
  let s = "";
  s += g.explanation_original ? `<div class="lbl">Explanation (from the book)</div><blockquote>${h(g.explanation_original)}</blockquote>` : `<div class="empty">No explanation stored for this item.</div>`;
  if (g.explanation_ko) s += `<blockquote class="ko">${h(g.explanation_ko)}</blockquote>`;
  if (g.meaning_en) s += `<div>${h(g.meaning_en)}</div>`;
  if (g.formation) s += `<details><summary class="lbl">Formation (from the book)</summary><pre class="pre">${h(g.formation)}</pre></details>`;
  const exs = compact ? g.examples.slice(0, 3) : g.examples;
  if (exs.length) s += `<div class="lbl">Examples from the book</div>` + exs.map(x => `<div class="exrow"><span class="ko">${h(x.sentence)}</span> <button class="mini" data-trans="${h(x.sentence)}">translate</button><div class="trbox"></div></div>`).join("");
  if (!compact && g.notes) s += `<details><summary class="lbl">Notes &amp; comparisons (verbatim OCR)</summary><pre class="pre">${h(g.notes)}</pre></details>`;
  if (!compact && g.workbook && g.workbook.length) s += `<details><summary class="lbl">Workbook exercises (${g.workbook.length}, OCR draft)</summary>${g.workbook.map(w => `<div class="wb"><b>${w.exercise_no ? "연습 " + h(w.exercise_no) + " · " : ""}${h(w.instruction || "")}</b><pre class="pre">${h(w.body || "")}</pre><span class="muted">${h(w.level)} workbook, p.${h(w.printed_page ?? "PDF " + w.pdf_page)}</span></div>`).join("")}</details>`;
  return s;
}
function wireTranslateButtons(root) {
  $$("button[data-trans]", root).forEach(b => b.onclick = () => { const box = b.parentElement.querySelector(".trbox"); gtRender(box, b.dataset.trans); b.hidden = true; });
}

/* ---------- reader actions ---------- */
$("#btn-open").onclick = async () => {
  const text = $("#new-text").value;
  if (!text.trim()) return;
  $("#btn-open").disabled = true; $("#open-msg").textContent = "";
  try {
    const p = await store.passages.create($("#new-title").value, text);
    $("#new-text").value = ""; $("#new-title").value = "";
    await withLookupHighlights(p);
    showReading(p);
  } catch (e) { $("#open-msg").textContent = "Error: " + e.message; }
  $("#btn-open").disabled = false;
};
$("#btn-delete").onclick = async () => {
  if (!cur || !confirm("Delete this passage?")) return;
  const gone = cur.id;
  await store.passages.remove(gone);
  if (typeof onPassageDeleted === "function") await onPassageDeleted(gone);
  cur = null; lastPanel = null;
  $("#text").innerHTML = ""; $("#p-title").textContent = "Pick a story or paste a text";
  for (const b of ["#btn-edit", "#btn-delete", "#btn-read"]) $(b).hidden = true;
  $("#questions").hidden = true; $("#legend").hidden = true;
  loadPassages();
};
$("#btn-edit").onclick = () => formDialog("Edit passage", [["title", "Title", cur.title || ""], ["text", "Text", cur.text, "area"]], async v => {
  const p = await store.passages.update(cur.id, v.title, v.text);
  await withLookupHighlights(p);
  showReading(p);
});

/* ---------- generic form dialog ---------- */
function formDialog(title, fields, onSave, extra) {
  const dlg = $("#dlg"), f = $("#dlg-form");
  f.innerHTML = `<h3>${h(title)}</h3>` + fields.map(([k, label, val, kind, opts]) => kind === "area"
    ? `<label>${h(label)}<textarea name="${k}" rows="6">${h(val)}</textarea></label>`
    : kind === "select" ? `<label>${h(label)}<select name="${k}">${opts.map(o => `<option ${o === val ? "selected" : ""}>${h(o)}</option>`).join("")}</select></label>`
      : `<label>${h(label)}<input name="${k}" value="${h(val ?? "")}"></label>`).join("") + (extra || "") +
    `<menu><button value="cancel" formnovalidate>Cancel</button><button value="ok" class="primary">Save</button></menu>`;
  f.onsubmit = async ev => {
    if (ev.submitter && ev.submitter.value !== "ok") return;
    const v = Object.fromEntries(new FormData(f).entries());
    try { await onSave(v); } catch (e) { alert(e.message); }
  };
  dlg.showModal();
  return f;
}

/* ---------- level selects ---------- */
LEVELS.forEach(l => ["#v-level", "#g-level", "#w-level", "#r-level"].forEach(s => $(s).insertAdjacentHTML("beforeend", `<option>${l}</option>`)));
const pager = (infoSel, total, page, lim) => $(infoSel).textContent = `${total ? Math.min(total, page * lim + 1) : 0}–${Math.min(total, (page + 1) * lim)} of ${total}`;
const debounced = fn => { let t; return () => { clearTimeout(t); t = setTimeout(fn, 250); }; };

/* =====================================================================================================
   VOCABULARY
   ===================================================================================================== */
let vPage = 0;
const vReload = debounced(() => { vPage = 0; loadVocab().catch(e => showError(e.message)); });
["#v-q", "#v-level", "#v-status"].forEach(s => $(s).oninput = vReload);
$("#v-prev").onclick = () => { vPage = Math.max(0, vPage - 1); loadVocab(); };
$("#v-next").onclick = () => { vPage++; loadVocab(); };
async function loadVocab() {
  const lim = 50;
  const r = await api(`/vocab?q=${encodeURIComponent($("#v-q").value)}&level=${$("#v-level").value}&status=${$("#v-status").value}&limit=${lim}&offset=${vPage * lim}`);
  $("#v-table tbody").innerHTML = r.items.map(e => `<tr><td class="ko">${h(e.headword)}</td><td>${h(e.level || "")}</td><td>${h(e.unit ?? "")}</td>
    <td><button class="mini" data-tr="${e.id}">Translate</button><div class="trbox" id="vt-${e.id}"></div></td>
    <td><span class="chip ${e.status === "verified" ? "s-VERIFIED" : "s-LIKELY"}">${h(e.status)}</span></td><td class="edit-only"><button data-e="${e.id}">Edit</button></td></tr>`).join("");
  pager("#v-info", r.total, vPage, lim);
  $$("#v-table button[data-tr]").forEach(b => b.onclick = () => {
    const e = r.items.find(x => x.id === +b.dataset.tr);
    gtRender($("#vt-" + e.id), e.headword.replace(/\([^)]*\)/g, ""), { roman: true }); b.hidden = true;
  });
  $$("#v-table button[data-e]").forEach(b => b.onclick = () => editVocab(r.items.find(x => x.id === +b.dataset.e)));
}
function editVocab(e) {
  const isNew = !e; e = e || {};
  formDialog(isNew ? "Add vocabulary (manual entry)" : "Edit vocabulary", [
    ["headword", "Korean headword", e.headword], ["meaning_en", "English meaning (optional)", e.meaning_en], ["level", "Level", e.level], ["unit", "Unit", e.unit],
    ["example", "Add example sentence (optional)", ""], ["status", "Status", e.status || "manual", "select", ["verified", "needs_review", "manual"]],
  ], async v => {
    v.unit = v.unit ? +v.unit : null;
    Object.keys(v).forEach(k => v[k] === "" && delete v[k]);
    await api(isNew ? "/vocab" : "/vocab/" + e.id, { method: isNew ? "POST" : "PATCH", body: v });
    loadVocab();
  });
}
$("#v-add").onclick = () => editVocab(null);

/* =====================================================================================================
   GRAMMAR
   ===================================================================================================== */
let gPage = 0;
const gReload = debounced(() => { gPage = 0; loadGrammar().catch(e => showError(e.message)); });
["#g-q", "#g-level", "#g-status"].forEach(s => $(s).oninput = gReload);
$("#g-prev").onclick = () => { gPage = Math.max(0, gPage - 1); loadGrammar(); };
$("#g-next").onclick = () => { gPage++; loadGrammar(); };
async function loadGrammar() {
  const lim = 100;
  const r = await api(`/grammar?q=${encodeURIComponent($("#g-q").value)}&level=${$("#g-level").value}&status=${$("#g-status").value}&limit=${lim}&offset=${gPage * lim}`);
  $("#g-table tbody").innerHTML = r.items.map(e => `<tr class="clickable" data-g="${e.id}"><td>${h(e.level || "")}</td><td>${h(e.entry_no || "")}</td><td class="ko">${h(e.pattern)}</td>
    <td>${e.explanation_original ? "✓ explained" : '<span class="muted">pattern only</span>'}</td>
    <td><span class="chip ${e.status === "needs_review" ? "s-LIKELY" : "s-VERIFIED"}">${h(e.status)}</span></td><td class="edit-only"><button data-e="${e.id}">Edit</button></td></tr>`).join("");
  pager("#g-info", r.total, gPage, lim);
  $$("#g-table tr[data-g]").forEach(tr => tr.onclick = ev => { if (ev.target.closest("button")) return; showGrammar(+tr.dataset.g); });
  $$("#g-table button[data-e]").forEach(b => b.onclick = async () => editGrammar(await api("/grammar/" + b.dataset.e)));
}
async function showGrammar(id) {
  const g = await api("/grammar/" + id), box = $("#g-detail");
  $$("#g-table tr.sel").forEach(t => t.classList.remove("sel"));
  const row = $(`#g-table tr[data-g="${id}"]`); if (row) row.classList.add("sel");
  box.innerHTML = `<h2>Grammar</h2><div class="kword ko">${h(g.pattern)}</div><p class="muted">${h(refLine(g))} · ${h(g.status)}</p>
    ${g.status === "needs_review" ? `<div class="warn">Read from a scan and not yet reviewed: the pattern text may contain OCR errors.</div>` : ""}${grammarBody(g, false)}`;
  wireTranslateButtons(box);
}
function editGrammar(e) {
  const isNew = !e; e = e || {};
  formDialog(isNew ? "Add grammar item (manual entry)" : `Edit grammar item ${e.level || ""} #${e.entry_no || ""}`, [
    ["pattern", "Pattern (e.g. V+(으)ㄹ 수 있다)", e.pattern], ["meaning_en", "English meaning (optional)", e.meaning_en],
    ["explanation_original", "Original textbook explanation", e.explanation_original, "area"], ["formation", "Formation rule", e.formation],
    ["level", "Level", e.level], ["unit", "Unit", e.unit], ["page", "Book page", e.page], ["example", "Add textbook example sentence (optional)", ""],
    ["status", "Status", e.status || "manual", "select", ["verified", "needs_review", "manual"]],
  ], async v => {
    ["unit", "page"].forEach(k => v[k] = v[k] ? +v[k] : null);
    Object.keys(v).forEach(k => v[k] === "" && delete v[k]);
    await api(isNew ? "/grammar" : "/grammar/" + e.id, { method: isNew ? "POST" : "PATCH", body: v });
    loadGrammar();
  });
}
$("#g-add").onclick = () => editGrammar(null);

/* =====================================================================================================
   WORKBOOK
   ===================================================================================================== */
let wPage = 0, wSections = null;
const wReload = debounced(() => { wPage = 0; loadWorkbook().catch(e => showError(e.message)); });
["#w-level", "#w-section", "#w-q"].forEach(s => $(s).oninput = wReload);
$("#w-prev").onclick = () => { wPage = Math.max(0, wPage - 1); loadWorkbook(); };
$("#w-next").onclick = () => { wPage++; loadWorkbook(); };
async function loadWorkbook() {
  const lim = 30;
  const r = await api(`/workbook?level=${$("#w-level").value}&section=${$("#w-section").value}&q=${encodeURIComponent($("#w-q").value)}&limit=${lim}&offset=${wPage * lim}`);
  if (!wSections) { wSections = r.sections; $("#w-section").insertAdjacentHTML("beforeend", Object.entries(r.sections).map(([k, v]) => `<option value="${k}">${h(v)}</option>`).join("")); }
  $("#w-list").innerHTML = r.items.map(w => `<article class="wbcard"><header><b>${h(r.sections[w.section] || w.section)}</b> · ${h(w.level)}${w.heading ? ` · <span class="ko">${h(w.heading)}</span>` : ""}${w.exercise_no && w.section !== "script" ? ` · 연습 ${h(w.exercise_no)}` : ""} <span class="muted">p.${h(w.printed_page ?? "PDF " + w.pdf_page)}</span></header>
    <p>${h(w.instruction || "")}</p><pre class="pre ko">${h(w.body || "")}</pre><button data-read="${w.id}">Open in the reader</button></article>`).join("") || `<p class="muted">Nothing matches.</p>`;
  pager("#w-info", r.total, wPage, lim);
  $$("#w-list button[data-read]").forEach(b => b.onclick = () => {
    const w = r.items.find(x => x.id === +b.dataset.read);
    $("#new-title").value = `${w.level} WB ${r.sections[w.section] || w.section}${w.exercise_no && w.section !== "script" ? " " + w.exercise_no : ""}`;
    $("#new-text").value = (w.section === "script" ? "" : (w.instruction || "") + "\n") + (w.body || "");
    $('#tabs button[data-tab="reader"]').click();
  });
}

/* =====================================================================================================
   REVIEW (local only): fix OCR'd records beside the page image
   ===================================================================================================== */
let rPage = 0, rSel = null;
const rReload = debounced(() => { rPage = 0; loadReview().catch(e => showError(e.message)); });
["#r-kind", "#r-level", "#r-status", "#r-expl", "#r-q"].forEach(s => { const el = $(s); if (el) el.oninput = rReload; });
if ($("#r-prev")) { $("#r-prev").onclick = () => { rPage = Math.max(0, rPage - 1); loadReview(); }; $("#r-next").onclick = () => { rPage++; loadReview(); }; }
async function loadReview() {
  const lim = 60, kind = $("#r-kind").value;
  $("#r-expl").hidden = kind !== "grammar"; $("#r-bulk").hidden = kind !== "grammar";
  const r = await api(`/admin/queue?kind=${kind}&status=${$("#r-status").value}&level=${$("#r-level").value}&has_explanation=${$("#r-expl").value}&q=${encodeURIComponent($("#r-q").value)}&limit=${lim}&offset=${rPage * lim}`);
  $("#r-list").innerHTML = r.items.map(i => `<li data-id="${i.id}" class="${rSel === i.id ? "on" : ""}"><span class="ko">${h(i.label)}</span><small>${h(i.level || "")}${i.unit ? " · u" + i.unit : ""}${i.page ? " · p" + i.page : ""} · ${h(i.status)}${kind === "grammar" ? (i.has_expl ? " · explained" : " · no explanation") : ""}</small></li>`).join("") || `<li class="muted">Nothing here.</li>`;
  pager("#r-info", r.total, rPage, lim);
  $$("#r-list li[data-id]").forEach(li => li.onclick = () => openReview(+li.dataset.id));
}
if ($("#r-bulk")) $("#r-bulk").onclick = async () => {
  const level = $("#r-level").value;
  if (!level) return alert("Choose a level first.");
  if (!confirm(`Mark every unreviewed ${level} grammar item that has a textbook explanation as VERIFIED? Only do this after checking a sample against the page images.`)) return;
  const r = await api("/admin/approve", { method: "POST", body: { kind: "grammar", level, only_with_explanation: true } });
  alert(`${r.approved} items approved.`); loadReview();
};
async function openReview(id) {
  rSel = id; $$("#r-list li").forEach(li => li.classList.toggle("on", +li.dataset.id === id));
  const kind = $("#r-kind").value, box = $("#r-detail");
  if (kind === "vocab") {
    const it = (await api("/admin/vocab/" + id)).item;
    box.innerHTML = `<h3>${h(it.headword)}</h3><p class="muted">${h(it.level)} · unit ${h(it.unit ?? "?")} · glossary PDF p.${h(it.pdf_page ?? "?")} · ${h(it.status)}</p>
    <div class="rform"><label>Headword<input id="f-headword" value="${h(it.headword)}"></label><label>English meaning (optional)<input id="f-meaning_en" value="${h(it.meaning_en || "")}"></label>
    <label>Level<input id="f-level" value="${h(it.level || "")}"></label><label>Unit<input id="f-unit" value="${h(it.unit ?? "")}"></label></div>
    <div class="row"><button id="rv-save" class="primary">Save &amp; approve</button> <button id="rv-del">Delete</button></div>`;
    $("#rv-save").onclick = async () => { await api("/vocab/" + id, { method: "PATCH", body: { headword: $("#f-headword").value, meaning_en: $("#f-meaning_en").value || null, level: $("#f-level").value || null, unit: $("#f-unit").value ? +$("#f-unit").value : null, status: "verified" } }); loadReview(); box.innerHTML = `<p class="muted">Saved.</p>`; };
    $("#rv-del").onclick = async () => { if (confirm("Delete this entry?")) { await api("/vocab/" + id, { method: "DELETE" }); loadReview(); box.innerHTML = ""; } };
    return;
  }
  const d = await api("/admin/grammar/" + id), it = d.item;
  const fld = (k, label, wide, area) => `<label class="${wide ? "wide" : ""}">${label}${area ? `<textarea id="f-${k}" rows="4">${h(it[k] || "")}</textarea>` : `<input id="f-${k}" value="${h(it[k] ?? "")}">`}</label>`;
  const img = (pg, cap) => pg && pg.image_url ? `<figure><a href="${pg.image_url}" target="_blank"><img loading="lazy" src="${pg.image_url}" alt=""></a><figcaption>${h(cap)} (PDF p.${pg.pdf_page})</figcaption></figure>` : "";
  box.innerHTML = `<h3>${h(it.pattern)}</h3><p class="muted">${h(it.level)} · unit ${h(it.unit ?? "?")} · book p.${h(it.page ?? "?")} · ${h(it.status)}</p>
  <div class="pages">${img(d.book_page, "Student book – Grammar Extension")}${img(d.index_page, "Scanned grammar index")}</div>
  <div class="rform">${fld("pattern", "Pattern (V/A/N+ notation)", true)}${fld("meaning_en", "English meaning (optional)")}${fld("level", "Level")}${fld("unit", "Unit")}${fld("page", "Book page")}
  ${fld("explanation_original", "Original textbook explanation (verbatim)", true, true)}${fld("formation", "Formation (verbatim)", true, true)}${fld("notes", "Notes", true, true)}</div>
  <div class="row"><b>Examples</b> <span class="muted">(only genuine examples of this pattern should stay)</span><div id="ex-list">${it.examples.map(e => `<div class="ex-row"><span>${h(e.sentence)}</span><button data-e="${e.id}">✕</button></div>`).join("") || `<div class="empty">none</div>`}</div>
  <input id="ex-new" placeholder="Add example sentence…"><button id="ex-add">Add</button></div>
  <div class="row"><button id="rg-save" class="primary">Save &amp; approve</button> <button id="rg-save-only">Save (keep needs_review)</button> <button id="rg-del">Delete</button>
  <input id="mg-id" placeholder="merge into item #id" style="width:150px"><button id="mg-go">Merge</button></div><p id="rg-msg" class="muted"></p>`;
  const body = approve => { const v = {}; for (const k of ["pattern", "meaning_en", "level", "unit", "page", "explanation_original", "formation", "notes"]) { const x = $("#f-" + k).value; v[k] = ["unit", "page"].includes(k) ? (x ? +x : null) : (x || null); } v.status = approve ? "verified" : "needs_review"; return v; };
  const save = async approve => { await api("/grammar/" + id, { method: "PATCH", body: body(approve) }); $("#rg-msg").textContent = "Saved."; loadReview(); };
  $("#rg-save").onclick = () => save(true); $("#rg-save-only").onclick = () => save(false);
  $("#rg-del").onclick = async () => { if (confirm("Delete this grammar item?")) { await api("/grammar/" + id, { method: "DELETE" }); loadReview(); box.innerHTML = `<p class="muted">Deleted.</p>`; } };
  $("#mg-go").onclick = async () => { const to = +$("#mg-id").value; if (to && confirm(`Merge into #${to}? This item is deleted and its examples move over.`)) { await api("/admin/grammar/merge", { method: "POST", body: { from_id: id, into_id: to } }); loadReview(); openReview(to); } };
  $("#ex-add").onclick = async () => { const t = $("#ex-new").value.trim(); if (t) { await api(`/admin/grammar/${id}/examples`, { method: "POST", body: { sentence: t } }); openReview(id); } };
  $$("#ex-list button[data-e]").forEach(b => b.onclick = async () => { await api("/admin/grammar-examples/" + b.dataset.e, { method: "DELETE" }); openReview(id); });
}

/* =====================================================================================================
   SAVED + STATUS
   ===================================================================================================== */
const savedLabel = s => s.kind === "word" ? s.text : (s.item && s.item.headword) || "(deleted)";
async function loadSaved() {
  const r = await store.saved.list();
  $("#s-table tbody").innerHTML = r.map(s => `<tr><td>${h(s.kind)}</td><td class="ko">${h(savedLabel(s).replace(/\([^)]*\)/g, ""))}</td><td>${h(s.item?.level || "")}</td><td class="ko">${h(s.sentence || "")}</td>
    <td>${s.kind === "grammar" ? '<span class="muted">—</span>' : `<button class="mini" data-tr="${h(s.id)}">Translate</button><div class="trbox" id="st-${h(s.id)}"></div>`}</td><td><button data-d="${h(s.id)}">Remove</button></td></tr>`).join("") || `<tr><td colspan="6" class="muted">Nothing saved yet. Click a word in a story and press “Save”.</td></tr>`;
  $$("#s-table button[data-tr]").forEach(b => b.onclick = () => {
    const s = r.find(x => String(x.id) === b.dataset.tr);
    gtRender($(`[id="st-${s.id}"]`), savedLabel(s).replace(/\([^)]*\)/g, ""), { roman: true }); b.hidden = true;
  });
  $$("#s-table button[data-d]").forEach(b => b.onclick = async () => { await store.saved.remove(b.dataset.d); loadSaved(); });
}
async function loadStatus() {
  const o = await api("/overview");
  $("#status-body").innerHTML = `<div class="kv"><span>Vocabulary entries</span><b>${o.vocab}</b><span>…flagged for review</span><b>${o.vocab_needs_review}</b>
  <span>Grammar items</span><b>${o.grammar}</b><span>…with the book's original explanation</span><b>${o.grammar_with_explanation}</b><span>…still unreviewed (scan/OCR)</span><b>${o.grammar_needs_review}</b>
  <span>Workbook exercises / scripts</span><b>${o.workbook_items}</b></div>
  <h2>Imported sources</h2><ul>${o.sources.map(s => `<li>${h(s.filename)} — ${h(s.kind)} (${h(s.level || "")})</li>`).join("")}</ul>
  <p class="muted">Translations come from Google Translate in your browser; nothing is translated or analysed on the server. Words are coloured only where a story marks them, or (for pasted text) where they match the textbook word list by simple rules.
  Original grammar explanations exist only where a student book was imported (3B, 4A, 4B); other levels have just the pattern. Everything read from a scan is "needs_review" until approved${RO ? "" : " in the Review tab"}.</p>`;
}

/* =====================================================================================================
   BOOT
   ===================================================================================================== */
(async () => {
  try { RO = !!(await api("/config")).read_only; } catch { /* old server: stay editable */ }
  document.body.classList.toggle("ro", RO);
  if (RO) { $('#tabs button[data-tab="review"]').remove(); $("#tab-review").remove(); $("#ro-banner").hidden = false; }
  store.onChange = () => {                         // signed in or out: show that backend's data
    cur = null; lastPanel = null; $("#text").innerHTML = ""; $("#p-title").textContent = "Pick a story or paste a text";
    for (const b of ["#btn-edit", "#btn-delete", "#btn-read"]) $(b).hidden = true;
    for (const s of ["#questions", "#story-box", "#legend"]) $(s).hidden = true;
    if (typeof onStoreChanged === "function") onStoreChanged();
    loadPassages();
    if (!$("#tab-stories").hidden) loadStories().catch(e => showError(e.message));
  };
  try { await store.init(); } catch (e) { showError("sync unavailable: " + e.message); }
  loadPassages().catch(e => showError(e.message));
  loadStories().catch(e => showError(e.message));
  try { if (!(await api("/overview")).workbook_items) { $('#tabs button[data-tab="workbook"]').remove(); $("#tab-workbook").remove(); } } catch { /* keep the tab */ }
})();
