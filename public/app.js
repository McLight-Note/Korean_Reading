"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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
  const b = document.getElementById("err-banner");
  if (!b) return;
  b.textContent = "Something went wrong: " + msg + "  (click to dismiss)";
  b.hidden = false;
}
window.addEventListener("unhandledrejection", ev => { showError((ev.reason && ev.reason.message) || String(ev.reason)); });
/* Read-only (public) mode: the server keeps no per-user data. Passages and saved words live in this browser. */
let RO = false;
const LS = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
};
async function createLocal(title, text) {
  const a = await api("/analyze", { method: "POST", body: { title, text } });
  a.id = Date.now();
  const all = LS.get("kr.passages", []); all.unshift(a);
  if (!LS.set("kr.passages", all)) alert("Browser storage is full: this passage is shown but could not be saved. Delete old passages to free space.");
  return a;
}
async function updateLocal(id, title, text) {
  const a = await api("/analyze", { method: "POST", body: { title, text } });
  a.id = id;
  LS.set("kr.passages", LS.get("kr.passages", []).map(p => p.id === id ? a : p));
  return a;
}
const LEVELS = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"];

/* ---------- labels (strict wording: never claim more than the data says) ---------- */
function grammarLabel(m) {
  if (m.status === "NOT_FOUND") return "NOT FOUND IN TEXTBOOK";
  if (m.status === "NEEDS_REVIEW") return "POSSIBLE MATCH";
  if (m.match_type === "RELATED") return "RELATED FORM";
  if (m.status === "LIKELY") return "POSSIBLE MATCH";
  return "FOUND IN TEXTBOOK";
}
function vocabLabel(m) {
  if (m.status === "NOT_FOUND") return "Not found in textbook";
  return { EXACT: "Exact dictionary match", CONJUGATED: "Conjugated form", RELATED: "Related word" }[m.match_type] || m.match_type;
}
const badge = (m, text) => `<span class="chip s-${m.status}">${h(text)}</span>`;

/* ---------- tabs ---------- */
$$("#tabs button").forEach(b => b.onclick = () => {
  $$("#tabs button").forEach(x => x.classList.toggle("on", x === b));
  $$(".tab").forEach(t => t.hidden = t.id !== "tab-" + b.dataset.tab);
  const loader = { vocab: loadVocab, grammar: loadGrammar, study: loadStudyHome, workbook: loadWorkbook, review: loadReview, saved: loadSaved, status: loadStatus }[b.dataset.tab];
  if (loader) Promise.resolve().then(loader).catch(e => showError(e.message));      // a failing tab shows the banner instead of failing silently
});

/* ---------- reader ---------- */
let cur = null;          // current analysis payload
let selected = null;     // selected match id

async function loadPassages() {
  const list = RO ? LS.get("kr.passages", []).map(p => ({ id: p.id, title: p.title, preview: (p.text || "").slice(0, 80) })) : await api("/passages");
  $("#passage-list").innerHTML = list.map(p => `<li data-id="${p.id}" class="${cur && cur.id === p.id ? "on" : ""}"><span>${h(p.title || p.preview || "(untitled)")}</span></li>`).join("") || `<li class="muted">No passages yet</li>`;
  $$("#passage-list li[data-id]").forEach(li => li.onclick = () => openPassage(+li.dataset.id));
}
async function openPassage(id, data) {
  cur = data || (RO ? LS.get("kr.passages", []).find(p => p.id === id) : await api("/passages/" + id));
  if (!cur) return;
  selected = null;
  $("#p-title").textContent = cur.title || "(untitled)";
  for (const b of ["#btn-edit", "#btn-reanalyze", "#btn-delete"]) $(b).hidden = false;
  $("#stale").hidden = !cur.stale;
  renderText();
  $("#detail").innerHTML = `<p class="muted">Click a highlighted word or grammar structure.</p>`;
  loadPassages();
  if (typeof onPassageOpened === "function") onPassageOpened();
}
$("#btn-analyze").onclick = async () => {
  const text = $("#new-text").value;
  if (!text.trim()) return;
  $("#btn-analyze").disabled = true; $("#analyze-msg").textContent = "Analysing locally with Kiwi…";
  try {
    const title = $("#new-title").value;
    const a = RO ? await createLocal(title, text) : await api("/passages", { method: "POST", body: { title, text } });
    $("#new-text").value = ""; $("#new-title").value = ""; $("#analyze-msg").textContent = "";
    await openPassage(a.id, RO ? a : undefined);
  } catch (e) { $("#analyze-msg").textContent = "Error: " + e.message; }
  $("#btn-analyze").disabled = false;
};
$("#btn-reanalyze").onclick = async () => { cur = RO ? await updateLocal(cur.id, cur.title, cur.text) : await api(`/passages/${cur.id}/reanalyze`, { method: "POST" }); $("#stale").hidden = true; renderText(); };
$("#btn-delete").onclick = async () => { if (confirm("Delete this passage?")) { const gone = cur.id; if (RO) LS.set("kr.passages", LS.get("kr.passages", []).filter(p => p.id !== gone)); else await api("/passages/" + gone, { method: "DELETE" }); if (typeof onPassageDeleted === "function") await onPassageDeleted(gone); cur = null; $("#text").innerHTML = ""; $("#p-title").textContent = "Select or paste a passage"; loadPassages(); } };
$("#btn-edit").onclick = () => formDialog("Edit passage", [["title", "Title", cur.title || ""], ["text", "Text", cur.text, "area"]], async v => { cur = RO ? await updateLocal(cur.id, v.title, v.text) : await api("/passages/" + cur.id, { method: "PUT", body: v }); selected = null; renderText(); loadPassages(); });
["#t-grammar", "#t-vocab", "#t-unmatched"].forEach(s => $(s).onchange = renderText);

function renderText() {
  if (!cur) return;
  const text = cur.text, el = $("#text");
  const showG = $("#t-grammar").checked, showV = $("#t-vocab").checked, showU = $("#t-unmatched").checked;
  el.classList.toggle("show-g", showG); el.classList.toggle("show-v", showV); el.classList.toggle("show-u", showU);
  const ms = cur.matches.filter(m => m.layer === "grammar" ? (m.status !== "NOT_FOUND" ? showG : showU) : showV);
  const cuts = new Set([0, text.length]);
  ms.forEach(m => { cuts.add(m.start); cuts.add(m.end); });
  const sel = selected && cur.matches.find(m => m.id === selected);
  const sent = sel && cur.sentences.find(s => s.no === sel.sentence_no);
  if (sent) { cuts.add(sent.start); cuts.add(sent.end); }
  const pts = [...cuts].filter(c => c >= 0 && c <= text.length).sort((a, b) => a - b);
  let html = "";
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    const cover = ms.filter(m => m.start <= a && b <= m.end);
    const g = cover.filter(m => m.layer === "grammar" && m.status !== "NOT_FOUND"), v = cover.filter(m => m.layer === "vocab"), u = cover.filter(m => m.layer === "grammar" && m.status === "NOT_FOUND");
    const longest = arr => arr.slice().sort((x, y) => (y.end - y.start) - (x.end - x.start))[0];
    const cls = [];
    if (g.length) cls.push("gs-" + longest(g).status);
    if (v.length) { const found = v.filter(x => x.status !== "NOT_FOUND"); cls.push("vs-" + longest(found.length ? found : v).status); }
    if (sent && a >= sent.start && b <= sent.end) cls.push("sent-on");
    if (sel && a >= sel.start && b <= sel.end) cls.push("sel");
    const attrs = (g.length ? ` data-g="${g.map(x => x.id)}"` : "") + (v.length ? ` data-v="${v.map(x => x.id)}"` : "") + (u.length ? ` data-u="${u.map(x => x.id)}"` : "");
    html += `<span class="${cls.join(" ")}"${attrs}>${h(text.slice(a, b))}</span>`;
  }
  el.innerHTML = html;
  $$("span", el).forEach(sp => sp.onclick = () => clickSpan(sp));
}

function clickSpan(sp) {
  const ids = ["g", "v", "u"].flatMap(k => (sp.dataset[k] || "").split(",").filter(Boolean).map(Number));
  const all = ids.map(id => cur.matches.find(m => m.id === id)).filter(Boolean);
  if (!all.length) return;
  all.sort((a, b) => (a.layer === b.layer ? (a.end - a.start) - (b.end - b.start) : a.layer === "grammar" ? -1 : 1));
  const preferred = all.find(m => m.layer === "grammar" && m.status !== "NOT_FOUND") || all[0];
  showMatch(preferred.id, all);
}

async function loadMatchDetail(m) {
  const base = m.layer === "vocab" ? "/vocab/" : "/grammar/";
  const item = m.ref_id ? await api(base + m.ref_id) : null;
  const others = await Promise.all((m.candidates || []).filter(c => c.id !== m.ref_id).map(c => api(base + c.id).catch(() => null)));
  return { match: m, item, candidate_items: others.filter(Boolean), sentence: cur.sentences.find(x => x.no === m.sentence_no) || null };
}

let matchToken = 0;
async function showMatch(id, siblings) {
  const token = ++matchToken;
  selected = id; renderText();
  const d = await loadMatchDetail(cur.matches.find(x => x.id === id));
  if (token !== matchToken) return;                 // a newer click already replaced this panel
  const m = d.match, it = d.item, box = $("#detail");
  const chips = (siblings || []).filter(x => x.id !== id).map(x => `<button data-m="${x.id}" class="chip s-${x.status}">${x.layer === "grammar" ? "G" : "V"}: ${h(x.layer === "grammar" ? (x.dict_form || x.surface) : x.dict_form || x.surface)}</button>`).join(" ");
  const sentence = d.sentence ? cur.text.slice(d.sentence.start, d.sentence.end) : "";
  const rel = m.start - (d.sentence ? d.sentence.start : 0);
  const sentHtml = sentence ? `${h(sentence.slice(0, rel))}<mark>${h(cur.text.slice(m.start, m.end))}</mark>${h(sentence.slice(rel + (m.end - m.start)))}` : "";
  let body = "";
  if (m.layer === "grammar") body = grammarPanel(m, it, d, sentHtml); else body = vocabPanel(m, it, sentHtml, sentence);
  box.innerHTML = body + (chips ? `<div class="row"><span class="lbl">Also at this position</span><br>${chips}</div>` : "");
  $$("button[data-m]", box).forEach(b => b.onclick = () => showMatch(+b.dataset.m, siblings));
  wirePanel(m, it, d);
}

function provenance(it) {
  if (!it) return "";
  const bits = [it.level && `Level ${it.level}`, it.unit && `Unit ${it.unit}`, it.page ? `p. ${it.page}` : (it.pdf_page ? `PDF p. ${it.pdf_page}` : null)].filter(Boolean);
  return `<div class="row"><span class="lbl">Textbook reference</span><br>${bits.map(h).join(" · ") || "<em>no level/unit recorded</em>"}${it.source_file ? `<br><span class="muted">${h(it.source_file)}</span>` : ""}${it.corrected ? ` <span class="chip">manually corrected</span>` : ""}</div>`;
}

function grammarPanel(m, it, d, sentHtml) {
  let s = `<h2>Grammar</h2>`;
  if (!it) {
    return s + `<h3>${h(m.surface)}</h3><p>${badge(m, "NOT FOUND IN TEXTBOOK")}</p><div class="warn">No matching grammar item in the uploaded textbook database. Detected morpheme: <b>${h(m.dict_form)}</b>. Nothing is invented here.${RO ? "" : " You can add a grammar item in the Grammar tab."}</div>
      <div class="row"><span class="lbl">In your passage</span><blockquote>${sentHtml}</blockquote></div>`;
  }
  s += `<h3>${h(it.pattern)}</h3><p class="sub">${badge(m, grammarLabel(m))} <span class="muted">detected: “${h(m.surface)}” · confidence ${Math.round((m.confidence || 0) * 100)}%</span></p>`;
  if (m.note) s += `<div class="warn">${h(m.note)}</div>`;
  if (it.status === "needs_review") s += `<div class="warn">This textbook entry comes from a scan that has not been reviewed. The pattern text may contain OCR errors.</div>`;
  s += provenance(it);
  s += `<div class="row"><span class="lbl">Original textbook explanation</span>${it.explanation_original ? `<blockquote>${h(it.explanation_original)}</blockquote>` : `<div class="empty">Not in the uploaded textbook data yet.</div>`}</div>`;
  if (it.explanation_ko) s += `<div class="row"><span class="lbl">Korean explanation</span><blockquote>${h(it.explanation_ko)}</blockquote></div>`;
  s += `<div class="row"><span class="lbl">Meaning (Uzbek, from the book)</span><br>${h(it.meaning_uz || "—")}</div>`;
  s += `<div class="row"><span class="lbl">Meaning (English)</span><br>${it.meaning_en ? h(it.meaning_en) : `<span class="muted">not provided by the textbook</span>`}<span class="edit-only"><br><input id="en-input" placeholder="Add English meaning…" value="${h(it.meaning_en || "")}"><button id="en-save">Save English</button></span></div>`;
  if (it.formation) s += `<details><summary class="lbl">Formation (from the book)</summary><pre class="pre">${h(it.formation)}</pre></details>`;
  s += `<div class="row"><span class="lbl">Textbook examples</span>${it.examples.length ? it.examples.map(e => `<blockquote>${h(e.sentence)}<br><span class="muted">${h(e.source_ref || "")}</span></blockquote>`).join("") : `<div class="empty">No examples stored for this item.</div>`}</div>`;
  if (it.notes) s += `<details><summary class="lbl">Notes &amp; comparisons (verbatim OCR)</summary><pre class="pre">${h(it.notes)}</pre></details>`;
  if (it.workbook && it.workbook.length) s += `<details><summary class="lbl">Workbook exercises (${it.workbook.length}, OCR draft)</summary>${it.workbook.map(w => `<div class="wb"><b>${w.exercise_no ? "연습 " + h(w.exercise_no) + " · " : ""}${h(w.instruction || "")}</b><pre class="pre">${h(w.body || "")}</pre><span class="muted">${h(w.level)} workbook, p.${h(w.printed_page ?? "PDF " + w.pdf_page)}</span></div>`).join("")}</details>`;
  s += `<div class="row"><span class="lbl">In your passage</span><blockquote>${sentHtml}</blockquote></div>`;
  if (d.candidate_items.length) s += `<div class="row"><span class="lbl">Other textbook items matching this span</span>${d.candidate_items.map(c => `<div><b>${h(c.pattern)}</b> <span class="muted">${h(c.level || "")}</span> <button class="edit-only" data-use="${c.id}">Use this</button></div>`).join("")}</div>`;
  s += `<div class="row"><button id="save-it" class="primary">Save grammar</button> ${it.status !== "verified" ? `<button class="edit-only" id="approve">Mark item verified</button>` : ""}</div>`;
  return s;
}

function vocabPanel(m, it, sentHtml, sentence) {
  let s = `<h2>Vocabulary</h2><h3>${h(m.surface)}</h3>`;
  s += `<p class="sub">${badge(m, vocabLabel(m))} <span class="muted">dictionary form: <b>${h(m.dict_form)}</b></span></p>`;
  if (m.note) s += `<div class="warn">${h(m.note)}</div>`;
  if (!it) return s + `<div class="warn">Not found in the uploaded textbook vocabulary. No definition is shown rather than a made-up one.</div><div class="row"><span class="lbl">In your passage</span><blockquote>${sentHtml}</blockquote></div>`;
  s += `<div class="row"><span class="lbl">Textbook headword</span><br><b style="font-size:18px">${h(it.headword)}</b> <span class="muted">${h(it.pos || "")}${it.pos_source === "kiwi" ? " (POS guessed by Kiwi)" : ""}</span></div>`;
  s += provenance(it);
  s += `<div class="row"><span class="lbl">Textbook definition (Uzbek)</span><br>${h(it.meaning_uz || "—")}</div>`;
  s += `<div class="row"><span class="lbl">English</span><br>${it.meaning_en ? h(it.meaning_en) : `<span class="muted">not provided by the textbook</span>`}<span class="edit-only"><br><input id="en-input" placeholder="Add English meaning…" value="${h(it.meaning_en || "")}"><button id="en-save">Save English</button></span></div>`;
  s += `<div class="row"><span class="lbl">Textbook examples</span>${it.examples && it.examples.length ? it.examples.map(e => `<blockquote>${h(e.sentence)}</blockquote>`).join("") : `<div class="empty">No example sentence in the textbook data.</div>`}</div>`;
  s += `<div class="row"><span class="lbl">Where you met it</span><blockquote>${sentHtml}</blockquote></div>`;
  if (m.candidates.length > 1) s += `<div class="row"><span class="lbl">Other textbook entries for this form</span>${m.candidates.filter(c => c.id !== it.id).map(c => `<div><b>${h(c.headword)}</b> — ${h(c.meaning_uz || "")} <span class="muted">${h(c.level)} u${h(c.unit ?? "")}</span> <button class="edit-only" data-use="${c.id}">Use this</button></div>`).join("")}</div>`;
  s += `<div class="row"><button id="save-it" class="primary">Save word</button></div>`;
  return s;
}

function wirePanel(m, it, d) {
  const en = $("#en-save");
  if (en && it) en.onclick = async () => {
    await api(`/${m.layer === "vocab" ? "vocab" : "grammar"}/${it.id}`, { method: "PATCH", body: { meaning_en: $("#en-input").value } });
    en.textContent = "Saved ✓";
  };
  const sv = $("#save-it");
  if (sv && it) sv.onclick = async () => {
    const sentence = d.sentence ? cur.text.slice(d.sentence.start, d.sentence.end) : null;
    if (RO) {
      const all = LS.get("kr.saved", []).filter(x => !(x.kind === m.layer && x.ref_id === it.id));
      all.unshift({ id: Date.now(), kind: m.layer, ref_id: it.id, sentence, item: { headword: it.headword || it.pattern, meaning_uz: it.meaning_uz, meaning_en: it.meaning_en, level: it.level } });
      if (!LS.set("kr.saved", all)) return alert("Browser storage is full.");
    } else await api("/saved", { method: "POST", body: { kind: m.layer, ref_id: it.id, passage_id: cur.id, sentence } });
    sv.textContent = "Saved ✓";
  };
  const ap = $("#approve");
  if (ap && it) ap.onclick = async () => { await api("/grammar/" + it.id, { method: "PATCH", body: { status: "verified" } }); ap.textContent = "Verified ✓ (re-analyze to update highlights)"; $("#stale").hidden = false; };
  $$("button[data-use]").forEach(b => b.onclick = async () => { await api("/matches/" + m.id, { method: "PATCH", body: { ref_id: +b.dataset.use, status: "LIKELY" } }); cur = await api("/passages/" + cur.id); renderText(); showMatch(m.id); });
}

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

/* ---------- vocabulary tab ---------- */
let vPage = 0, gPage = 0;
LEVELS.forEach(l => { $("#w-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); $("#r-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); $("#v-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); $("#g-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); });
let vTimer;
["#v-q", "#v-level", "#v-status"].forEach(s => $(s).oninput = () => { clearTimeout(vTimer); vTimer = setTimeout(() => { vPage = 0; loadVocab(); }, 250); });
$("#v-prev").onclick = () => { vPage = Math.max(0, vPage - 1); loadVocab(); };
$("#v-next").onclick = () => { vPage++; loadVocab(); };
async function loadVocab() {
  const lim = 50;
  const r = await api(`/vocab?q=${encodeURIComponent($("#v-q").value)}&level=${$("#v-level").value}&status=${$("#v-status").value}&limit=${lim}&offset=${vPage * lim}`);
  $("#v-table tbody").innerHTML = r.items.map(e => `<tr><td class="ko">${h(e.headword)}</td><td>${h(e.pos || "")}</td><td>${h(e.meaning_uz || "")}</td><td>${h(e.meaning_en || "")}</td><td>${h(e.level || "")}</td><td>${h(e.unit ?? "")}</td><td>${h(e.pdf_page ?? "")}</td><td><span class="chip ${e.status === "verified" ? "s-VERIFIED" : "s-LIKELY"}">${h(e.status)}</span></td><td><button class="edit-only" data-e="${e.id}">Edit</button></td></tr>`).join("");
  $("#v-info").textContent = `${Math.min(r.total, vPage * lim + 1)}–${Math.min(r.total, (vPage + 1) * lim)} of ${r.total}`;
  $$("#v-table button[data-e]").forEach(b => b.onclick = () => editVocab(r.items.find(x => x.id === +b.dataset.e)));
}
function editVocab(e) {
  const isNew = !e; e = e || {};
  formDialog(isNew ? "Add vocabulary (manual entry)" : "Edit vocabulary", [
    ["headword", "Korean headword", e.headword], ["meaning_uz", "Uzbek (textbook)", e.meaning_uz], ["meaning_en", "English", e.meaning_en],
    ["meaning_ko", "Korean definition", e.meaning_ko], ["pos", "Part of speech", e.pos], ["level", "Level", e.level], ["unit", "Unit", e.unit],
    ...(isNew || true ? [["example", "Add example sentence (optional)", ""]] : []),
    ["status", "Status", e.status || "manual", "select", ["verified", "needs_review", "manual"]],
  ], async v => {
    v.unit = v.unit ? +v.unit : null;
    Object.keys(v).forEach(k => v[k] === "" && delete v[k]);
    await api(isNew ? "/vocab" : "/vocab/" + e.id, { method: isNew ? "POST" : "PATCH", body: v });
    loadVocab();
  });
}
$("#v-add").onclick = () => editVocab(null);

/* ---------- grammar tab ---------- */
let gTimer;
["#g-q", "#g-level", "#g-status", "#g-compiled"].forEach(s => $(s).oninput = () => { clearTimeout(gTimer); gTimer = setTimeout(() => { gPage = 0; loadGrammar(); }, 250); });
$("#g-prev").onclick = () => { gPage = Math.max(0, gPage - 1); loadGrammar(); };
$("#g-next").onclick = () => { gPage++; loadGrammar(); };
async function loadGrammar() {
  const lim = 100;
  const r = await api(`/grammar?q=${encodeURIComponent($("#g-q").value)}&level=${$("#g-level").value}&status=${$("#g-status").value}&compiled=${$("#g-compiled").value}&limit=${lim}&offset=${gPage * lim}`);
  $("#g-table tbody").innerHTML = r.items.map(e => `<tr><td>${h(e.level || "")}</td><td>${h(e.entry_no || "")}</td><td class="ko">${h(e.pattern)}</td><td>${h(e.meaning_uz || "")}</td><td>${e.explanation_original ? "✓" : "—"}</td><td>${e.has_rule ? "✓" : `<span class="s-LIKELY">manual</span>`}</td><td><span class="chip ${e.status === "needs_review" ? "s-LIKELY" : "s-VERIFIED"}">${h(e.status)}</span></td><td><button class="edit-only" data-e="${e.id}">Edit</button></td></tr>`).join("");
  $("#g-info").textContent = `${Math.min(r.total, gPage * lim + 1)}–${Math.min(r.total, (gPage + 1) * lim)} of ${r.total}`;
  $$("#g-table button[data-e]").forEach(b => b.onclick = async () => editGrammar(await api("/grammar/" + b.dataset.e)));
}
function editGrammar(e) {
  const isNew = !e; e = e || {};
  const f = formDialog(isNew ? "Add grammar item (manual entry)" : `Edit grammar item ${e.level || ""} #${e.entry_no || ""}`, [
    ["pattern", "Pattern (e.g. V+(으)ㄹ 수 있다)", e.pattern], ["meaning_uz", "Uzbek gloss (textbook)", e.meaning_uz], ["meaning_en", "English meaning", e.meaning_en],
    ["explanation_original", "Original textbook explanation", e.explanation_original, "area"], ["explanation_ko", "Korean explanation", e.explanation_ko],
    ["formation", "Formation rule", e.formation], ["level", "Level", e.level], ["unit", "Unit", e.unit],
    ["example", "Add textbook example sentence (optional)", ""],
    ["status", "Status", e.status || "manual", "select", ["verified", "needs_review", "manual"]],
  ], async v => {
    v.unit = v.unit ? +v.unit : null;
    Object.keys(v).forEach(k => v[k] === "" && delete v[k]);
    const r = await api(isNew ? "/grammar" : "/grammar/" + e.id, { method: isNew ? "POST" : "PATCH", body: v });
    if (r.compiled === false) alert("Saved, but this notation could not be compiled into a detection rule (it needs a V/A/N+ prefix). It will not be auto-detected.");
    loadGrammar();
  }, `<div class="row"><label>Test rule on a sentence<input id="rt-sent" placeholder="e.g. 내일 갈 수 있어요"></label><button type="button" id="rt-go">Test</button> <span id="rt-out" class="muted"></span></div>`);
  $("#rt-go", f).onclick = async () => {
    const r = await api("/grammar/test-rule", { method: "POST", body: { pattern: f.elements.pattern.value, sentence: $("#rt-sent").value } });
    $("#rt-out").textContent = !r.compiled ? "Cannot compile this notation." : r.matches.length ? "Matches: " + r.matches.map(m => `“${m.surface}” (${m.match_type})`).join(", ") : "No match. Forms tried: " + r.forms.join(" · ");
  };
}
$("#g-add").onclick = () => editGrammar(null);

/* ---------- workbook tab ---------- */
let wPage = 0, wTimer, wSections = null;
["#w-level", "#w-section", "#w-q"].forEach(s => $(s).oninput = () => { clearTimeout(wTimer); wTimer = setTimeout(() => { wPage = 0; loadWorkbook(); }, 250); });
$("#w-prev").onclick = () => { wPage = Math.max(0, wPage - 1); loadWorkbook(); };
$("#w-next").onclick = () => { wPage++; loadWorkbook(); };
async function loadWorkbook() {
  const lim = 30;
  const r = await api(`/workbook?level=${$("#w-level").value}&section=${$("#w-section").value}&q=${encodeURIComponent($("#w-q").value)}&limit=${lim}&offset=${wPage * lim}`);
  if (!wSections) { wSections = r.sections; $("#w-section").insertAdjacentHTML("beforeend", Object.entries(r.sections).map(([k, v]) => `<option value="${k}">${h(v)}</option>`).join("")); }
  $("#w-list").innerHTML = r.items.map(w => `<article class="wbcard"><header><b>${h(r.sections[w.section] || w.section)}</b> · ${h(w.level)}${w.heading ? ` · <span class="ko">${h(w.heading)}</span>` : ""}${w.exercise_no && w.section !== "script" ? ` · 연습 ${h(w.exercise_no)}` : ""} <span class="muted">p.${h(w.printed_page ?? "PDF " + w.pdf_page)}</span></header>
    <p>${h(w.instruction || "")}</p><pre class="pre ko">${h(w.body || "")}</pre><button data-read="${w.id}">Analyze in reader</button></article>`).join("") || `<p class="muted">Nothing matches.</p>`;
  $("#w-info").textContent = `${Math.min(r.total, wPage * lim + 1)}–${Math.min(r.total, (wPage + 1) * lim)} of ${r.total}`;
  $$("#w-list button[data-read]").forEach(b => b.onclick = () => {
    const w = r.items.find(x => x.id === +b.dataset.read);
    $("#new-title").value = `${w.level} WB ${r.sections[w.section] || w.section}${w.exercise_no && w.section !== "script" ? " " + w.exercise_no : ""}`;
    $("#new-text").value = (w.section === "script" ? "" : (w.instruction || "") + "\n") + (w.body || "");
    $('#tabs button[data-tab="reader"]').click();
  });
}

/* ---------- saved + status ---------- */
async function loadSaved() {
  const r = RO ? LS.get("kr.saved", []) : await api("/saved");
  $("#s-table tbody").innerHTML = r.map(s => `<tr><td>${h(s.kind)}</td><td class="ko">${h(s.item ? s.item.headword : "(deleted)")}</td><td>${h(s.item?.meaning_uz || "")}</td><td>${h(s.item?.meaning_en || "")}</td><td>${h(s.item?.level || "")}</td><td>${h(s.sentence || "")}</td><td><button data-d="${s.id}">Remove</button></td></tr>`).join("") || `<tr><td colspan="7" class="muted">Nothing saved yet.</td></tr>`;
  $$("#s-table button[data-d]").forEach(b => b.onclick = async () => { if (RO) LS.set("kr.saved", LS.get("kr.saved", []).filter(x => x.id !== +b.dataset.d)); else await api("/saved/" + b.dataset.d, { method: "DELETE" }); loadSaved(); });
}
async function loadStatus() {
  const o = await api("/overview");
  $("#status-body").innerHTML = `<div class="kv"><span>Vocabulary entries</span><b>${o.vocab}</b><span>…flagged for review</span><b>${o.vocab_needs_review}</b><span>…with an English meaning</span><b>${o.vocab_with_english}</b>
  <span>Grammar items</span><b>${o.grammar}</b><span>…auto-detectable (compiled rule)</span><b>${o.grammar_detectable}</b><span>…still unreviewed (scan/OCR)</span><b>${o.grammar_needs_review}</b>
  <span>…with an original textbook explanation</span><b>${o.grammar_with_explanation}</b><span>Passages</span><b>${o.passages}</b><span>Saved items</span><b>${o.saved}</b><span>Workbook exercises / scripts</span><b>${o.workbook_items}</b></div>
  <h2>Imported sources</h2><ul>${o.sources.map(s => `<li>${h(s.filename)} — ${h(s.kind)} (${h(s.level || "")})</li>`).join("")}</ul>
  <p class="muted">Original explanations and examples exist only where a student book was imported (3B, 4A, 4B — Grammar Extension sections). Levels 1A–3A, 5A and 5B have no student book here, so their grammar items carry only the pattern and Uzbek gloss from the scanned index until you add material. Workbook exercises (3A–4B) are shown as OCR drafts in the Workbook tab.${RO ? " Items marked possible match come from unreviewed scans and may contain OCR errors." : " Everything OCR'd stays needs_review until you approve it in the Review tab."}</p>`;
}

/* ---------- review tab (manual correction of OCR'd textbook data) ---------- */
let rPage = 0, rSel = null, rTimer;
["#r-kind", "#r-level", "#r-status", "#r-expl", "#r-q"].forEach(s => $(s).oninput = () => { clearTimeout(rTimer); rTimer = setTimeout(() => { rPage = 0; loadReview(); }, 250); });
$("#r-prev").onclick = () => { rPage = Math.max(0, rPage - 1); loadReview(); };
$("#r-next").onclick = () => { rPage++; loadReview(); };
async function loadReview() {
  const lim = 60, kind = $("#r-kind").value;
  $("#r-expl").hidden = kind !== "grammar"; $("#r-bulk").hidden = kind !== "grammar";
  const r = await api(`/admin/queue?kind=${kind}&status=${$("#r-status").value}&level=${$("#r-level").value}&has_explanation=${$("#r-expl").value}&q=${encodeURIComponent($("#r-q").value)}&limit=${lim}&offset=${rPage * lim}`);
  $("#r-list").innerHTML = r.items.map(i => `<li data-id="${i.id}" class="${rSel === i.id ? "on" : ""}"><span class="ko">${h(i.label)}</span><small>${h(i.level || "")}${i.unit ? " · u" + i.unit : ""}${i.page ? " · p" + i.page : ""} · ${h(i.status)}${kind === "grammar" ? (i.has_expl ? " · explained" : " · no explanation") + (i.has_rule ? "" : " · not detectable") : ""}</small></li>`).join("") || `<li class="muted">Nothing here.</li>`;
  $("#r-info").textContent = `${Math.min(r.total, rPage * lim + 1)}–${Math.min(r.total, (rPage + 1) * lim)} of ${r.total}`;
  $$("#r-list li[data-id]").forEach(li => li.onclick = () => openReview(+li.dataset.id));
}
$("#r-bulk").onclick = async () => {
  const level = $("#r-level").value;
  if (!level) return alert("Choose a level first.");
  if (!confirm(`Mark every unreviewed ${level} grammar item that has a textbook explanation as VERIFIED? Only do this after checking a sample against the page images.`)) return;
  const r = await api("/admin/approve", { method: "POST", body: { kind: "grammar", level, only_with_explanation: true } });
  alert(`${r.approved} items approved. Re-analyze passages to refresh highlights.`); loadReview();
};
$("#r-calib").onclick = async () => {
  const level = $("#r-level").value;
  $("#r-detail").innerHTML = `<p class="muted">Running every textbook example through Kiwi + the matcher…</p>`;
  const r = await api("/admin/calibration" + (level ? "?level=" + level : ""));
  $("#r-detail").innerHTML = `<h3>Calibration${level ? " · " + level : ""}</h3><p>${r.totals.hits}/${r.totals.examples} textbook examples are detected by their own item's rule (recall ${Math.round((r.totals.recall || 0) * 100)}%) across ${r.totals.items} items. Low scores usually mean either a rule that needs fixing, or "examples" that really belong to a different pattern (comparison notes).</p>
  <table class="grid"><thead><tr><th>Recall</th><th>Item</th><th>Level</th><th>Misses</th></tr></thead><tbody>${r.items.map(i => `<tr><td>${i.hits}/${i.examples}</td><td class="ko"><a href="#" data-g="${i.id}">${h(i.pattern)}</a></td><td>${h(i.level)}</td><td>${i.misses.slice(0, 2).map(m => h(m.sentence)).join("<br>")}</td></tr>`).join("")}</tbody></table>`;
  $$("#r-detail a[data-g]").forEach(a => a.onclick = ev => { ev.preventDefault(); $("#r-kind").value = "grammar"; openReview(+a.dataset.g); });
};
async function openReview(id) {
  rSel = id; $$("#r-list li").forEach(li => li.classList.toggle("on", +li.dataset.id === id));
  const kind = $("#r-kind").value, box = $("#r-detail");
  if (kind === "vocab") {
    const d = await api("/admin/vocab/" + id), it = d.item;
    box.innerHTML = `<h3>${h(it.headword)}</h3><p class="muted">${h(it.level)} · unit ${h(it.unit ?? "?")} · glossary PDF p.${h(it.pdf_page ?? "?")} · ${h(it.status)}</p>
    <div class="rform"><label>Headword<input id="f-headword" value="${h(it.headword)}"></label><label>Uzbek (book)<input id="f-meaning_uz" value="${h(it.meaning_uz || "")}"></label>
    <label>English<input id="f-meaning_en" value="${h(it.meaning_en || "")}"></label><label>Part of speech<input id="f-pos" value="${h(it.pos || "")}"></label></div>
    <details><summary class="lbl">Original line(s)</summary><pre class="pre">${h(it.raw_text || "")}</pre></details>
    <div class="row"><button id="rv-save" class="primary">Save &amp; approve</button> <button id="rv-del">Delete</button></div>`;
    $("#rv-save").onclick = async () => { await api("/vocab/" + id, { method: "PATCH", body: { headword: $("#f-headword").value, meaning_uz: $("#f-meaning_uz").value, meaning_en: $("#f-meaning_en").value, pos: $("#f-pos").value, status: "verified" } }); loadReview(); box.innerHTML = `<p class="muted">Saved.</p>`; };
    $("#rv-del").onclick = async () => { if (confirm("Delete this entry?")) { await api("/vocab/" + id, { method: "DELETE" }); loadReview(); box.innerHTML = ""; } };
    return;
  }
  const d = await api("/admin/grammar/" + id), it = d.item;
  const fld = (k, label, wide, area) => `<label class="${wide ? "wide" : ""}">${label}${area ? `<textarea id="f-${k}" rows="4">${h(it[k] || "")}</textarea>` : `<input id="f-${k}" value="${h(it[k] ?? "")}">`}</label>`;
  const img = (pg, cap) => pg && pg.image_url ? `<figure><a href="${pg.image_url}" target="_blank"><img loading="lazy" src="${pg.image_url}" alt=""></a><figcaption>${h(cap)} (PDF p.${pg.pdf_page})</figcaption></figure>` : "";
  box.innerHTML = `<h3>${h(it.pattern)}</h3><p class="muted">${h(it.level)} · unit ${h(it.unit ?? "?")} · book p.${h(it.page ?? "?")} · ${h(it.status)} · ${it.has_rule ? "auto-detectable" : "<b>not auto-detectable</b> (notation can't be compiled — fix the pattern)"}</p>
  <div class="pages">${img(d.book_page, "Student book – Grammar Extension")}${img(d.index_page, "Scanned grammar index")}</div>
  <div class="rform">${fld("pattern", "Pattern (V/A/N+ notation)", true)}${fld("meaning_uz", "Uzbek gloss (book)")}${fld("meaning_en", "English meaning")}${fld("level", "Level")}${fld("unit", "Unit")}${fld("page", "Book page")}
  ${fld("explanation_original", "Original textbook explanation (verbatim)", true, true)}${fld("formation", "Formation (verbatim)", true, true)}${fld("notes", "Notes", true, true)}</div>
  <div class="row"><b>Examples</b> <span class="muted">(only genuine examples of this pattern should stay)</span><div id="ex-list">${it.examples.map(e => `<div class="ex-row"><span>${h(e.sentence)}</span><button data-e="${e.id}">✕</button></div>`).join("") || `<div class="empty">none</div>`}</div>
  <input id="ex-new" placeholder="Add example sentence…"><button id="ex-add">Add</button></div>
  <details><summary class="lbl">Raw OCR text of the index entry</summary><pre class="pre">${h(it.raw_text || "")}</pre></details>
  <div class="row"><button id="rg-save" class="primary">Save &amp; approve</button> <button id="rg-save-only">Save (keep needs_review)</button> <button id="rg-del">Delete</button>
  <input id="mg-id" placeholder="merge into item #id" style="width:150px"><button id="mg-go">Merge</button></div><p id="rg-msg" class="muted"></p>`;
  const body = approve => { const v = {}; for (const k of ["pattern", "meaning_uz", "meaning_en", "level", "unit", "page", "explanation_original", "formation", "notes"]) { const x = $("#f-" + k).value; v[k] = ["unit", "page"].includes(k) ? (x ? +x : null) : (x || null); } v.status = approve ? "verified" : "needs_review"; return v; };
  const save = async approve => { const r = await api("/grammar/" + id, { method: "PATCH", body: body(approve) }); $("#rg-msg").textContent = "Saved." + (r.compiled === false ? " ⚠ notation still can't be compiled." : ""); loadReview(); };
  $("#rg-save").onclick = () => save(true); $("#rg-save-only").onclick = () => save(false);
  $("#rg-del").onclick = async () => { if (confirm("Delete this grammar item?")) { await api("/grammar/" + id, { method: "DELETE" }); loadReview(); box.innerHTML = `<p class="muted">Deleted.</p>`; } };
  $("#mg-go").onclick = async () => { const to = +$("#mg-id").value; if (to && confirm(`Merge into #${to}? This item is deleted and its examples move over.`)) { await api("/admin/grammar/merge", { method: "POST", body: { from_id: id, into_id: to } }); loadReview(); openReview(to); } };
  $("#ex-add").onclick = async () => { const t = $("#ex-new").value.trim(); if (t) { await api(`/admin/grammar/${id}/examples`, { method: "POST", body: { sentence: t } }); openReview(id); } };
  $$("#ex-list button[data-e]").forEach(b => b.onclick = async () => { await api("/admin/grammar-examples/" + b.dataset.e, { method: "DELETE" }); openReview(id); });
}

function applyMode() {
  document.body.classList.toggle("ro", RO);
  if (!RO) return;
  $('#tabs button[data-tab="review"]').remove(); $("#tab-review").remove();
  $("#ro-banner").hidden = false;
}
(async () => {
  try { RO = !!(await api("/config")).read_only; } catch { /* old server: stay writable */ }
  applyMode();
  try { if (!(await api("/overview")).workbook_items) { $('#tabs button[data-tab="workbook"]').remove(); $("#tab-workbook").remove(); } } catch { /* keep the tab */ }
  loadPassages();
})();
