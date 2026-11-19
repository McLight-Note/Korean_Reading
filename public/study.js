"use strict";
/* Study: flashcards (SM-2), generated exercises, workbook practice, stats, reading progress, passage questions.
   Uses globals from app.js: $, $$, h, api, RO, LS, LEVELS, cur.
   State is one JSON document: saved on the server locally (/api/study/state), in this browser when deployed (RO).
   All scheduling / exercise generation / answer checking happens in the backend (tested); nothing here calls an AI. */

let ST = null;
const MAX_LOG = 5000;
const todayStr = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const dayShift = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return todayStrOf(d); };
const todayStrOf = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

async function stLoad() {
  if (ST) return ST;
  // A failed load must NOT fall back to an empty state: the next save would overwrite the stored progress.
  const s = RO ? LS.get("kr.study", null) : await api("/study/state");
  ST = Object.assign({ cards: {}, log: [], ex: [], read: {}, questions: {} }, s || {});
  return ST;
}
async function stSave() {
  if (!ST) return;
  ST.log = ST.log.slice(-MAX_LOG); ST.ex = ST.ex.slice(-MAX_LOG);
  try {
    if (RO) { if (!LS.set("kr.study", ST)) alert("Browser storage is full: your progress could not be saved."); }
    else await api("/study/state", { method: "PUT", body: { state: ST } });
  } catch (e) { alert("Could not save study progress: " + e.message); }
}
async function getSavedList() { return RO ? LS.get("kr.saved", []) : await api("/saved"); }
async function addToSaved(kind, ref_id, item, sentence) {
  if (RO) {
    const all = LS.get("kr.saved", []).filter(x => !(x.kind === kind && x.ref_id === ref_id));
    all.unshift({ id: Date.now(), kind, ref_id, sentence: sentence || null, item: { headword: item.headword || item.pattern, meaning_uz: item.meaning_uz, meaning_en: item.meaning_en, level: item.level } });
    LS.set("kr.saved", all);
  } else await api("/saved", { method: "POST", body: { kind, ref_id, sentence: sentence || null } });
}
const itemCache = new Map();
async function getItem(kind, id) {
  const k = kind + ":" + id;
  if (!itemCache.has(k)) itemCache.set(k, await api(`/${kind}/${id}`));
  return itemCache.get(k);
}
const refLine = it => [it.level && `Level ${it.level}`, it.unit && `Unit ${it.unit}`, it.page ? `p.${it.page}` : (it.pdf_page ? `PDF p.${it.pdf_page}` : null)].filter(Boolean).join(" · ") || "no level/unit recorded";
const levelOptions = (sel, any) => (any ? `<option value="">Any level</option>` : "") + LEVELS.map(l => `<option ${l === sel ? "selected" : ""}>${l}</option>`).join("");

/* ---------- navigation ---------- */
let stView = "home";
$$("#st-nav button").forEach(b => b.onclick = () => { stView = b.dataset.v; loadStudyHome(); });
async function loadStudyHome() {
  try { await stLoad(); } catch (e) {
    $("#st-body").innerHTML = `<div class="banner err">Could not load your study progress (${h(e.message)}). Nothing was changed. Reload the page to retry.</div>`;
    return;
  }
  $$("#st-nav button").forEach(b => b.classList.toggle("on", b.dataset.v === stView));
  ({ home: viewHome, cards: viewCards, ex: viewExercises, wb: viewWorkbook }[stView])();
}

/* ---------- overview / statistics ---------- */
function streakOf(days) {
  let t = todayStr(), n = 0;
  if (!days.has(t)) t = dayShift(t, -1);
  while (days.has(t)) { n++; t = dayShift(t, -1); }
  return n;
}
async function viewHome() {
  const today = todayStr(), cards = Object.values(ST.cards);
  const due = cards.filter(c => c.srs && c.srs.due <= today).length;
  const mature = cards.filter(c => c.srs && c.srs.interval >= 21).length;
  const young = cards.length - mature;
  let saved = []; try { saved = await getSavedList(); } catch { /* ignore */ }
  const unreviewed = saved.filter(s => !ST.cards[`${s.kind}:${s.ref_id}`]).length;
  const days = new Set([...ST.log.map(l => l.t), ...ST.ex.map(l => l.t)]);
  const last14 = Array.from({ length: 14 }, (_, i) => dayShift(today, i - 13));
  const perDay = last14.map(d => ST.log.filter(l => l.t === d).length);
  const maxN = Math.max(1, ...perDay);
  const recent = ST.log.filter(l => l.t >= dayShift(today, -29));
  const retention = recent.length ? Math.round(100 * recent.filter(l => l.grade >= 2).length / recent.length) : null;
  const exTypes = { grammar_mcq: "Grammar recognition", vocab_mcq: "Vocabulary: Korean → Uzbek", vocab_rev: "Vocabulary: Uzbek → Korean", wb_check: "Workbook: target grammar used" };
  const exRows = Object.entries(exTypes).map(([k, label]) => { const xs = ST.ex.filter(e => e.type === k); return xs.length ? `<tr><td>${h(label)}</td><td>${xs.length}</td><td>${Math.round(100 * xs.filter(e => e.ok).length / xs.length)}%</td></tr>` : ""; }).join("");
  const read = Object.values(ST.read);
  $("#st-body").innerHTML = `
    <div class="statgrid">
      <div class="stat"><b>${due}</b><span>cards due today</span></div>
      <div class="stat"><b>${unreviewed}</b><span>saved items not yet studied</span></div>
      <div class="stat"><b>${cards.length}</b><span>cards (${young} young · ${mature} mature)</span></div>
      <div class="stat"><b>${retention === null ? "—" : retention + "%"}</b><span>answered good/easy (30 days)</span></div>
      <div class="stat"><b>${streakOf(days)}</b><span>day streak</span></div>
      <div class="stat"><b>${read.length}</b><span>passages read (${read.reduce((a, r) => a + (r.chars || 0), 0)} characters)</span></div>
    </div>
    <h3>Card reviews, last 14 days</h3>
    <div class="bars">${perDay.map((n, i) => `<div title="${last14[i]}: ${n}"><i style="height:${Math.round(100 * n / maxN)}%"></i><small>${last14[i].slice(8)}</small></div>`).join("")}</div>
    <h3>Exercises</h3>
    ${exRows ? `<table class="grid"><thead><tr><th>Type</th><th>Answered</th><th>Correct</th></tr></thead><tbody>${exRows}</tbody></table>` : `<p class="muted">No exercises answered yet.</p>`}
    <p class="muted">Stats are stored ${RO ? "in this browser only" : "in your local database"}. Flashcards come from items you save in the reader, or from a textbook level.</p>`;
}

/* ---------- flashcards ---------- */
let FC = null;   // {queue:[{key,kind,id,meta}], done:int, again:int}
function viewCards() {
  $("#st-body").innerHTML = `
    <div class="filters">
      <label>New cards from <select id="fc-deck"><option value="saved">my saved items</option><option value="vocab">a level's glossary</option><option value="grammar">a level's grammar</option></select></label>
      <select id="fc-level">${levelOptions("3B")}</select>
      <label>up to <input id="fc-new" type="number" min="0" max="50" value="10" style="width:70px"> new</label>
      <button id="fc-start" class="primary">Start session</button>
    </div>
    <p class="muted">A session shows every card that is due plus the new cards you ask for. Grade yourself: <b>Again</b> brings the card back today; <b>Hard / Good / Easy</b> set the next review date (SM-2).</p>
    <div id="fc-area"></div>`;
  $("#fc-deck").onchange = () => { $("#fc-level").hidden = $("#fc-deck").value === "saved"; };
  $("#fc-level").hidden = true;
  $("#fc-start").onclick = startFlashcards;
}
async function startFlashcards() {
  try { await startFlashcardsInner(); } catch (e) { $("#fc-area").innerHTML = `<div class="banner err">Could not start the session: ${h(e.message)}</div>`; }
}
async function startFlashcardsInner() {
  const today = todayStr(), deck = $("#fc-deck").value, level = $("#fc-level").value, nNew = Math.max(0, +$("#fc-new").value || 0);
  const queue = Object.entries(ST.cards).filter(([, c]) => c.srs && c.srs.due <= today).map(([key, c]) => ({ key, kind: c.kind, id: c.ref_id, meta: c }));
  let fresh = [];
  if (deck === "saved") {
    fresh = (await getSavedList()).filter(s => !ST.cards[`${s.kind}:${s.ref_id}`]).map(s => ({ key: `${s.kind}:${s.ref_id}`, kind: s.kind, id: s.ref_id, meta: { kind: s.kind, ref_id: s.ref_id, sentence: s.sentence } }));
  } else if (deck === "vocab") {
    const r = await api(`/vocab?level=${level}&status=verified&limit=200`);
    fresh = r.items.filter(e => e.meaning_uz && !ST.cards["vocab:" + e.id]).map(e => ({ key: "vocab:" + e.id, kind: "vocab", id: e.id, meta: { kind: "vocab", ref_id: e.id, level } }));
  } else {
    const r = await api(`/grammar?level=${level}&limit=200`);
    fresh = r.items.filter(e => !ST.cards["grammar:" + e.id]).map(e => ({ key: "grammar:" + e.id, kind: "grammar", id: e.id, meta: { kind: "grammar", ref_id: e.id, level } }));
  }
  FC = { queue: queue.concat(fresh.slice(0, nNew)), total: 0, reviewed: 0, again: 0 };
  FC.total = FC.queue.length;
  if (!FC.total) { $("#fc-area").innerHTML = `<p class="muted">Nothing to study right now: no cards are due${deck === "saved" ? " and you have no unstudied saved items (save words or grammar in the reader)" : ""}.</p>`; return; }
  showCard();
}
async function showCard() {
  const area = $("#fc-area");
  if (!FC.queue.length) { area.innerHTML = `<div class="stat"><b>Session complete</b><span>${FC.reviewed} reviews · ${FC.again} marked “again”</span></div>`; return; }
  const c = FC.queue[0];
  let it;
  try { it = await getItem(c.kind, c.id); } catch { FC.queue.shift(); return showCard(); }   // item deleted since
  const front = c.kind === "vocab" ? it.headword : it.pattern;
  const sent = c.meta.sentence ? `<p class="muted">You met it in: ${h(c.meta.sentence)}</p>` : "";
  const exs = (it.examples || []).slice(0, 2).map(e => `<blockquote>${h(e.sentence)}</blockquote>`).join("");
  const back = c.kind === "vocab"
    ? `<p><b>${h(it.meaning_uz || "—")}</b> <span class="muted">(Uzbek, from the glossary)</span></p>${it.meaning_en ? `<p>${h(it.meaning_en)}</p>` : ""}<p class="muted">${h(refLine(it))}${it.status !== "verified" ? " · unreviewed entry" : ""}</p>${exs}`
    : `<p><b>${h(it.meaning_uz || "—")}</b> ${it.meaning_en ? "· " + h(it.meaning_en) : ""}</p>${it.explanation_original ? `<blockquote>${h(it.explanation_original.slice(0, 500))}</blockquote>` : `<p class="muted">No textbook explanation stored for this item.</p>`}<p class="muted">${h(refLine(it))}${it.status === "needs_review" ? " · unreviewed (OCR draft)" : ""}</p>${exs}`;
  area.innerHTML = `<div class="card"><div class="muted">${FC.total - FC.queue.length + 1} / ${FC.total} · ${c.kind}${c.meta.srs ? " · review" : " · new"}</div>
    <div class="cardfront ko">${h(front)}</div>${sent}
    <div id="fc-back" hidden>${back}</div>
    <div class="grades" id="fc-grades" hidden><button data-g="0">Again</button><button data-g="1">Hard</button><button data-g="2" class="primary">Good</button><button data-g="3">Easy</button></div>
    <button id="fc-show" class="primary">Show answer</button></div>`;
  $("#fc-show").onclick = () => { $("#fc-back").hidden = false; $("#fc-grades").hidden = false; $("#fc-show").hidden = true; };
  $$("#fc-grades button").forEach(b => b.onclick = () => gradeCard(+b.dataset.g));
}
async function gradeCard(grade) {
  const c = FC.queue[0], today = todayStr();
  const meta = ST.cards[c.key] || Object.assign({ kind: c.kind, ref_id: c.id }, c.meta);
  try { meta.srs = await api("/study/schedule", { method: "POST", body: { state: meta.srs || null, grade, today } }); }
  catch (e) { showError("could not schedule the card (" + e.message + "). It stays in your session; try again."); return; }
  FC.queue.shift();
  ST.cards[c.key] = meta;
  ST.log.push({ t: today, kind: c.kind, id: c.id, grade });
  FC.reviewed++;
  if (grade === 0) { FC.again++; FC.queue.push({ key: c.key, kind: c.kind, id: c.id, meta }); }
  await stSave();
  showCard();
}

/* ---------- generated exercises ---------- */
let EX = null;   // {items, i, correct}
function viewExercises() {
  $("#st-body").innerHTML = `
    <div class="filters">
      <select id="ex-type"><option value="grammar_mcq">Grammar recognition</option><option value="vocab_mcq">Vocabulary: Korean → Uzbek</option><option value="vocab_rev">Vocabulary: Uzbek → Korean</option></select>
      <select id="ex-level">${levelOptions("3B", true)}</select>
      <label>questions <input id="ex-n" type="number" min="3" max="30" value="10" style="width:70px"></label>
      <label><input id="ex-unrev" type="checkbox" checked style="width:auto"> include unreviewed grammar</label>
      <button id="ex-start" class="primary">Start</button>
    </div>
    <p class="muted"><b>Generated</b> exercises are built by this app from stored textbook records, not written by the textbook. Each one shows which record it came from and whether that record has been reviewed.</p>
    <div id="ex-area"></div>`;
  $("#ex-start").onclick = startExercises;
}
async function startExercises() {
  const type = $("#ex-type").value;
  $("#ex-area").innerHTML = `<p class="muted">Generating…</p>`;
  let r;
  try { r = await api(`/study/exercises?type=${type}&level=${$("#ex-level").value}&n=${+$("#ex-n").value || 10}&seed=${Date.now() % 1000000}&include_unreviewed=${$("#ex-unrev").checked}`); }
  catch (e) { $("#ex-area").innerHTML = `<div class="banner err">Could not generate exercises: ${h(e.message)}</div>`; return; }
  if (!r.count) { $("#ex-area").innerHTML = `<p class="muted">Not enough textbook material for this selection (grammar needs items with rules and examples; vocabulary needs at least 4 reviewed glossary entries). Try another level or tick “include unreviewed grammar”. Nothing is made up to fill the gap.</p>`; return; }
  EX = { items: r.items, i: 0, correct: 0 };
  showQuestion();
}
function promptHtml(e) {
  return e.type === "grammar_mcq" ? h(e.prompt).split("____").join(`<span class="blank">_____</span>`) : h(e.prompt);
}
function showQuestion() {
  const area = $("#ex-area");
  if (EX.i >= EX.items.length) { area.innerHTML = `<div class="stat"><b>${EX.correct} / ${EX.items.length}</b><span>correct</span></div><button id="ex-again" class="primary">New set</button>`; $("#ex-again").onclick = startExercises; return; }
  const e = EX.items[EX.i];
  area.innerHTML = `<div class="card"><div class="muted">${EX.i + 1} / ${EX.items.length} · <span class="chip s-LIKELY">Generated</span> ${e.type === "grammar_mcq" ? "Which grammar fits the blank?" : e.type === "vocab_mcq" ? "Choose the Uzbek meaning" : "Choose the Korean word"}</div>
    <div class="cardfront ${e.type === "vocab_rev" ? "" : "ko"}">${promptHtml(e)}</div>
    <div class="choices">${e.choices.map(c => `<button data-id="${c.id}" class="ko">${h(c.pattern || c.text)}</button>`).join("")}</div>
    <div id="ex-fb"></div></div>`;
  $$("#ex-area .choices button").forEach(b => b.onclick = () => answerQuestion(+b.dataset.id));
}
async function answerQuestion(id) {
  const e = EX.items[EX.i], ok = id === e.answer_id;
  EX.correct += ok;
  ST.ex.push({ t: todayStr(), type: e.type, ok, id: e.item_id });
  $$("#ex-area .choices button").forEach(b => { b.disabled = true; b.classList.toggle("right", +b.dataset.id === e.answer_id); if (+b.dataset.id === id && !ok) b.classList.add("wrong"); });
  const src = e.source || {};
  const detail = e.type === "grammar_mcq"
    ? `<p class="ko"><b>${h(e.full_sentence).replace(h(e.blanked), () => `<mark>${h(e.blanked)}</mark>`)}</b></p><p>${h(e.answer_pattern)} — ${h(e.meaning_uz || "")}${e.meaning_en ? " · " + h(e.meaning_en) : ""}</p>${e.explanation ? `<blockquote>${h(e.explanation)}</blockquote>` : ""}<p class="muted">From a textbook example (${h(src.example_ref || "")}) · ${h(src.level || "")} unit ${h(src.unit ?? "?")} p.${h(src.page ?? "?")}${src.item_status === "needs_review" ? " · <b>unreviewed OCR record</b>" : ""}</p>`
    : `<p class="ko"><b>${h(e.headword)}</b> — ${h(e.meaning_uz)}${e.meaning_en ? " · " + h(e.meaning_en) : ""}</p><p class="muted">Glossary ${h(src.level || "")} unit ${h(src.unit ?? "?")}</p>`;
  $("#ex-fb").innerHTML = `<div class="${ok ? "okbox" : "badbox"}">${ok ? "Correct ✓" : "Not quite"}</div>${detail}
    <button id="ex-save">Add to flashcards</button> <button id="ex-next" class="primary">${EX.i + 1 < EX.items.length ? "Next" : "Finish"}</button>`;
  $("#ex-next").onclick = () => { EX.i++; showQuestion(); };
  $("#ex-save").onclick = async ev => {
    const kind = e.type === "grammar_mcq" ? "grammar" : "vocab";
    await addToSaved(kind, e.item_id, kind === "vocab" ? { headword: e.headword, meaning_uz: e.meaning_uz, meaning_en: e.meaning_en, level: src.level } : { pattern: e.answer_pattern, meaning_uz: e.meaning_uz, meaning_en: e.meaning_en, level: src.level }, null);
    ev.target.textContent = "Saved ✓"; ev.target.disabled = true;
  };
  await stSave();
}

/* ---------- workbook practice (original textbook exercises, checked with the local grammar detector) ---------- */
let WBP = { last: null };
function viewWorkbook() {
  $("#st-body").innerHTML = `
    <div class="filters"><select id="wp-level">${levelOptions("3B")}</select><button id="wp-load" class="primary">Give me a workbook exercise</button></div>
    <p class="muted">Original workbook exercises (OCR draft). Write your answer in each box; <b>Check</b> only tests whether your answer uses the exercise's <i>target grammar</i> (with the same local detector as the reader). It cannot judge the rest of your sentence, and the workbook's answer key is not available here, so compare with the [보기] model.</p>
    <div id="wp-area"></div>`;
  $("#wp-load").onclick = loadWbExercise;
}
function splitItems(body) {
  const lines = (body || "").split("\n"), model = [], items = [];
  for (const l of lines) {
    const m = l.match(/^\s*\(?(\d{1,2})\)\s*(.*)$/);
    if (m) items.push({ no: m[1], lines: [m[2]] });
    else if (items.length) items[items.length - 1].lines.push(l);
    else model.push(l);
  }
  return { model: model.join("\n"), items };
}
async function loadWbExercise() {
  const level = $("#wp-level").value;
  let r;
  try { r = await api(`/workbook?section=grammar&level=${level}&limit=100`); }
  catch (e) { $("#wp-area").innerHTML = `<div class="banner err">Could not load exercises: ${h(e.message)}</div>`; return; }
  const pool = r.items.filter(w => w.grammar_id && w.body && /\d\)/.test(w.body) && w.id !== WBP.last);
  if (!pool.length) { $("#wp-area").innerHTML = `<p class="muted">No linked workbook exercises for ${h(level)} in this edition.</p>`; return; }
  const w = pool[Math.floor(Math.random() * pool.length)];
  WBP.last = w.id;
  const { model, items } = splitItems(w.body);
  $("#wp-area").innerHTML = `<div class="card"><div class="muted"><span class="chip">Workbook · original (OCR draft)</span> ${h(w.level)} p.${h(w.printed_page ?? "PDF " + w.pdf_page)} · 연습 ${h(w.exercise_no ?? "")}</div>
    <h3 class="ko">${h(w.grammar_pattern || w.heading)}</h3><p>${h(w.instruction || "")}</p>
    ${model.trim() ? `<pre class="pre ko">${h(model)}</pre>` : ""}
    ${items.map((it, i) => `<div class="wpitem"><pre class="pre ko">${h(it.no + ") " + it.lines.join("\n"))}</pre><textarea data-i="${i}" rows="2" placeholder="Your answer…"></textarea><button data-c="${i}">Check</button> <span id="wp-r${i}" class="muted"></span></div>`).join("")}
    <button id="wp-next">Another exercise</button></div>`;
  $("#wp-next").onclick = loadWbExercise;
  $$("#wp-area button[data-c]").forEach(b => b.onclick = async () => {
    const i = +b.dataset.c, text = $(`#wp-area textarea[data-i="${i}"]`).value.trim(), out = $("#wp-r" + i);
    if (!text) { out.textContent = "Write an answer first."; return; }
    let res;
    try { res = await api("/study/check", { method: "POST", body: { grammar_id: w.grammar_id, text } }); }
    catch (e) { out.textContent = "Could not check: " + e.message; return; }
    if (res.checkable === false) out.innerHTML = `This item has no detection rule, so it can't be checked automatically.`;
    else {
      ST.ex.push({ t: todayStr(), type: "wb_check", ok: !!res.target_found, id: w.grammar_id });
      out.innerHTML = res.target_found ? `<span class="s-VERIFIED">✓ uses the target grammar (${h(res.target)})</span>`
        : `<span class="s-REVIEW s-NEEDS_REVIEW">✗ target grammar not detected.</span> ${res.detected.length ? "Detected instead: " + res.detected.map(d => h(d.pattern)).join(", ") : ""}`;
      stSave();
    }
  });
}

/* ---------- reader: reading progress + your own comprehension questions ---------- */
const pidKey = () => String(cur.id);
async function onPassageOpened() {
  try { await stLoad(); } catch { $("#btn-read").hidden = true; $("#questions").hidden = true; return; }
  $("#btn-read").hidden = false;
  renderReadState();
  renderQuestions();
}
function renderReadState() {
  const r = ST.read[pidKey()];
  $("#btn-read").textContent = r ? "✓ Read" : "Mark as read";
  $("#btn-read").classList.toggle("primary", !!r);
}
async function onPassageDeleted(id) {
  try { await stLoad(); } catch { return; }
  delete ST.read[String(id)]; delete ST.questions[String(id)];
  await stSave();
  $("#btn-read").hidden = true; $("#questions").hidden = true;
}
$("#btn-read").onclick = async () => {
  if (!cur) return;
  try { await stLoad(); } catch (e) { showError("study progress is unavailable (" + e.message + ")"); return; }
  if (ST.read[pidKey()]) delete ST.read[pidKey()]; else ST.read[pidKey()] = { t: todayStr(), chars: (cur.text || "").length };
  renderReadState(); await stSave();
};
function renderQuestions() {
  const qs = ST.questions[pidKey()] || [];
  $("#questions").hidden = false;
  $("#q-list").innerHTML = qs.map((q, i) => `<li><b>${h(q.q)}</b>${q.a ? ` <button data-sa="${i}">answer</button><span class="qa" id="qa${i}" hidden> — ${h(q.a)}</span>` : ""} <button data-qd="${i}" title="delete">✕</button></li>`).join("") || `<li class="muted">No questions yet. Questions are written by you; none are generated.</li>`;
  $$("#q-list button[data-sa]").forEach(b => b.onclick = () => { $("#qa" + b.dataset.sa).hidden = false; b.hidden = true; });
  $$("#q-list button[data-qd]").forEach(b => b.onclick = async () => { qs.splice(+b.dataset.qd, 1); ST.questions[pidKey()] = qs; renderQuestions(); await stSave(); });
}
$("#q-add").onclick = async () => {
  const q = $("#q-text").value.trim(), a = $("#q-ans").value.trim();
  if (!q || !cur) return;
  try { await stLoad(); } catch (e) { showError("study progress is unavailable (" + e.message + ")"); return; }
  (ST.questions[pidKey()] = ST.questions[pidKey()] || []).push({ q, a });
  $("#q-text").value = ""; $("#q-ans").value = "";
  renderQuestions(); await stSave();
};
