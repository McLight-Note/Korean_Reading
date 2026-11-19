"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
async function api(path, opts = {}) {
  const r = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
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
  ({ vocab: loadVocab, grammar: loadGrammar, saved: loadSaved, status: loadStatus }[b.dataset.tab] || (() => { }))();
});

/* ---------- reader ---------- */
let cur = null;          // current analysis payload
let selected = null;     // selected match id

async function loadPassages() {
  const list = await api("/passages");
  $("#passage-list").innerHTML = list.map(p => `<li data-id="${p.id}" class="${cur && cur.id === p.id ? "on" : ""}"><span>${h(p.title || p.preview || "(untitled)")}</span></li>`).join("") || `<li class="muted">No passages yet</li>`;
  $$("#passage-list li[data-id]").forEach(li => li.onclick = () => openPassage(+li.dataset.id));
}
async function openPassage(id) {
  cur = await api("/passages/" + id);
  selected = null;
  $("#p-title").textContent = cur.title || "(untitled)";
  for (const b of ["#btn-edit", "#btn-reanalyze", "#btn-delete"]) $(b).hidden = false;
  $("#stale").hidden = !cur.stale;
  renderText();
  $("#detail").innerHTML = `<p class="muted">Click a highlighted word or grammar structure.</p>`;
  loadPassages();
}
$("#btn-analyze").onclick = async () => {
  const text = $("#new-text").value;
  if (!text.trim()) return;
  $("#btn-analyze").disabled = true; $("#analyze-msg").textContent = "Analysing locally with Kiwi…";
  try {
    const a = await api("/passages", { method: "POST", body: { title: $("#new-title").value, text } });
    $("#new-text").value = ""; $("#new-title").value = ""; $("#analyze-msg").textContent = "";
    await openPassage(a.id);
  } catch (e) { $("#analyze-msg").textContent = "Error: " + e.message; }
  $("#btn-analyze").disabled = false;
};
$("#btn-reanalyze").onclick = async () => { cur = await api(`/passages/${cur.id}/reanalyze`, { method: "POST" }); $("#stale").hidden = true; renderText(); };
$("#btn-delete").onclick = async () => { if (confirm("Delete this passage?")) { await api("/passages/" + cur.id, { method: "DELETE" }); cur = null; $("#text").innerHTML = ""; $("#p-title").textContent = "Select or paste a passage"; loadPassages(); } };
$("#btn-edit").onclick = () => formDialog("Edit passage", [["title", "Title", cur.title || ""], ["text", "Text", cur.text, "area"]], async v => { cur = await api("/passages/" + cur.id, { method: "PUT", body: v }); renderText(); loadPassages(); });
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

async function showMatch(id, siblings) {
  selected = id; renderText();
  const d = await api("/matches/" + id);
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
    return s + `<h3>${h(m.surface)}</h3><p>${badge(m, "NOT FOUND IN TEXTBOOK")}</p><div class="warn">No matching grammar item in the uploaded textbook database. Detected morpheme: <b>${h(m.dict_form)}</b>. Nothing is invented here — you can add a grammar item in the Grammar tab.</div>
      <div class="row"><span class="lbl">In your passage</span><blockquote>${sentHtml}</blockquote></div>`;
  }
  s += `<h3>${h(it.pattern)}</h3><p class="sub">${badge(m, grammarLabel(m))} <span class="muted">detected: “${h(m.surface)}” · confidence ${Math.round((m.confidence || 0) * 100)}%</span></p>`;
  if (m.note) s += `<div class="warn">${h(m.note)}</div>`;
  if (it.status === "needs_review") s += `<div class="warn">This textbook entry comes from a scan that has not been reviewed. The pattern text may contain OCR errors.</div>`;
  s += provenance(it);
  s += `<div class="row"><span class="lbl">Original textbook explanation</span>${it.explanation_original ? `<blockquote>${h(it.explanation_original)}</blockquote>` : `<div class="empty">Not in the uploaded textbook data yet.</div>`}</div>`;
  if (it.explanation_ko) s += `<div class="row"><span class="lbl">Korean explanation</span><blockquote>${h(it.explanation_ko)}</blockquote></div>`;
  s += `<div class="row"><span class="lbl">Meaning (Uzbek, from the book)</span><br>${h(it.meaning_uz || "—")}</div>`;
  s += `<div class="row"><span class="lbl">Meaning (English)</span><br>${it.meaning_en ? h(it.meaning_en) : `<span class="muted">not provided by the textbook</span>`}<br><input id="en-input" placeholder="Add English meaning…" value="${h(it.meaning_en || "")}"><button id="en-save">Save English</button></div>`;
  s += `<div class="row"><span class="lbl">Textbook examples</span>${it.examples.length ? it.examples.map(e => `<blockquote>${h(e.sentence)}</blockquote>`).join("") : `<div class="empty">No examples stored for this item.</div>`}</div>`;
  s += `<div class="row"><span class="lbl">In your passage</span><blockquote>${sentHtml}</blockquote></div>`;
  if (d.candidate_items.length) s += `<div class="row"><span class="lbl">Other textbook items matching this span</span>${d.candidate_items.map(c => `<div><b>${h(c.pattern)}</b> <span class="muted">${h(c.level || "")}</span> <button data-use="${c.id}">Use this</button></div>`).join("")}</div>`;
  s += `<div class="row"><button id="save-it" class="primary">Save grammar</button> ${it.status !== "verified" ? `<button id="approve">Mark item verified</button>` : ""}</div>`;
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
  s += `<div class="row"><span class="lbl">English</span><br>${it.meaning_en ? h(it.meaning_en) : `<span class="muted">not provided by the textbook</span>`}<br><input id="en-input" placeholder="Add English meaning…" value="${h(it.meaning_en || "")}"><button id="en-save">Save English</button></div>`;
  s += `<div class="row"><span class="lbl">Textbook examples</span>${it.examples && it.examples.length ? it.examples.map(e => `<blockquote>${h(e.sentence)}</blockquote>`).join("") : `<div class="empty">No example sentence in the textbook data.</div>`}</div>`;
  s += `<div class="row"><span class="lbl">Where you met it</span><blockquote>${sentHtml}</blockquote></div>`;
  if (m.candidates.length > 1) s += `<div class="row"><span class="lbl">Other textbook entries for this form</span>${m.candidates.filter(c => c.id !== it.id).map(c => `<div><b>${h(c.headword)}</b> — ${h(c.meaning_uz || "")} <span class="muted">${h(c.level)} u${h(c.unit ?? "")}</span> <button data-use="${c.id}">Use this</button></div>`).join("")}</div>`;
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
    await api("/saved", { method: "POST", body: { kind: m.layer, ref_id: it.id, passage_id: cur.id, sentence } });
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
LEVELS.forEach(l => { $("#v-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); $("#g-level").insertAdjacentHTML("beforeend", `<option>${l}</option>`); });
let vTimer;
["#v-q", "#v-level", "#v-status"].forEach(s => $(s).oninput = () => { clearTimeout(vTimer); vTimer = setTimeout(() => { vPage = 0; loadVocab(); }, 250); });
$("#v-prev").onclick = () => { vPage = Math.max(0, vPage - 1); loadVocab(); };
$("#v-next").onclick = () => { vPage++; loadVocab(); };
async function loadVocab() {
  const lim = 50;
  const r = await api(`/vocab?q=${encodeURIComponent($("#v-q").value)}&level=${$("#v-level").value}&status=${$("#v-status").value}&limit=${lim}&offset=${vPage * lim}`);
  $("#v-table tbody").innerHTML = r.items.map(e => `<tr><td class="ko">${h(e.headword)}</td><td>${h(e.pos || "")}</td><td>${h(e.meaning_uz || "")}</td><td>${h(e.meaning_en || "")}</td><td>${h(e.level || "")}</td><td>${h(e.unit ?? "")}</td><td>${h(e.pdf_page ?? "")}</td><td><span class="chip ${e.status === "verified" ? "s-VERIFIED" : "s-LIKELY"}">${h(e.status)}</span></td><td><button data-e="${e.id}">Edit</button></td></tr>`).join("");
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
  $("#g-table tbody").innerHTML = r.items.map(e => `<tr><td>${h(e.level || "")}</td><td>${h(e.entry_no || "")}</td><td class="ko">${h(e.pattern)}</td><td>${h(e.meaning_uz || "")}</td><td>${e.explanation_original ? "✓" : "—"}</td><td>${e.has_rule ? "✓" : `<span class="s-LIKELY">manual</span>`}</td><td><span class="chip ${e.status === "needs_review" ? "s-LIKELY" : "s-VERIFIED"}">${h(e.status)}</span></td><td><button data-e="${e.id}">Edit</button></td></tr>`).join("");
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

/* ---------- saved + status ---------- */
async function loadSaved() {
  const r = await api("/saved");
  $("#s-table tbody").innerHTML = r.map(s => `<tr><td>${h(s.kind)}</td><td class="ko">${h(s.item ? s.item.headword : "(deleted)")}</td><td>${h(s.item?.meaning_uz || "")}</td><td>${h(s.item?.meaning_en || "")}</td><td>${h(s.item?.level || "")}</td><td>${h(s.sentence || "")}</td><td><button data-d="${s.id}">Remove</button></td></tr>`).join("") || `<tr><td colspan="7" class="muted">Nothing saved yet.</td></tr>`;
  $$("#s-table button[data-d]").forEach(b => b.onclick = async () => { await api("/saved/" + b.dataset.d, { method: "DELETE" }); loadSaved(); });
}
async function loadStatus() {
  const o = await api("/overview");
  $("#status-body").innerHTML = `<div class="kv"><span>Vocabulary entries</span><b>${o.vocab}</b><span>…flagged for review</span><b>${o.vocab_needs_review}</b><span>…with an English meaning</span><b>${o.vocab_with_english}</b>
  <span>Grammar items</span><b>${o.grammar}</b><span>…auto-detectable (compiled rule)</span><b>${o.grammar_detectable}</b><span>…still unreviewed (scan/OCR)</span><b>${o.grammar_needs_review}</b>
  <span>…with an original textbook explanation</span><b>${o.grammar_with_explanation}</b><span>Passages</span><b>${o.passages}</b><span>Saved items</span><b>${o.saved}</b></div>
  <h2>Imported sources</h2><ul>${o.sources.map(s => `<li>${h(s.filename)} — ${h(s.kind)} (${h(s.level || "")})</li>`).join("")}</ul>
  <p class="muted">Student books (3B, 4A, 4B) and workbooks are not imported yet, so grammar items have no original explanations or examples until they are OCR'd or added manually. Levels without a student book (1A–3A, 5A, 5B) will only ever have index entries + Uzbek glosses unless you add that material.</p>`;
}

loadPassages();
