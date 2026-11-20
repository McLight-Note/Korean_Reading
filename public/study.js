"use strict";
/* Study: flashcards (SM-2), statistics, reading progress, your own passage questions.
   Uses globals from app.js / store.js / translate.js: $, $$, h, api, store, LEVELS, cur, gtRender, showError.
   State is one JSON document kept by `store` (this browser, or the signed-in visitor's Firestore space). Scheduling
   (SM-2) is the backend's pure /api/study/schedule; nothing here calls an AI. */

let ST = null;
const MAX_LOG = 5000;
const dateStr = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const todayStr = () => dateStr(new Date());
const dayShift = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return dateStr(d); };

async function stLoad() {
  if (ST) return ST;
  // A failed load must NOT fall back to an empty state: the next save would overwrite the stored progress.
  const s = await store.study.load();
  ST = Object.assign({ cards: {}, log: [], ex: [], read: {}, questions: {} }, s || {});
  return ST;
}
async function stSave() {
  if (!ST) return;
  ST.log = ST.log.slice(-MAX_LOG);
  try { await store.study.save(ST); } catch (e) { showError("could not save study progress: " + e.message); }
}
const savedKey = s => s.kind === "word" ? `word:${s.text}` : `${s.kind}:${s.ref_id}`;
const cardLabel = c => c.kind === "word" ? c.text : ((c.item && c.item.headword) || "");
const levelOptions = sel => LEVELS.map(l => `<option ${l === sel ? "selected" : ""}>${l}</option>`).join("");
const refLineShort = it => [it.level && `Level ${it.level}`, it.unit && `Unit ${it.unit}`, it.page ? `p.${it.page}` : null].filter(Boolean).join(" · ");

/* signed in or out: the stored progress is a different document set, so drop the in-memory copy */
function onStoreChanged() {
  ST = null; FC = null;
  if (!$("#tab-study").hidden) loadStudyHome();
}

/* ---------- navigation ---------- */
let stView = "home";
$$("#st-nav button").forEach(b => b.onclick = () => { stView = b.dataset.v; loadStudyHome(); });
async function loadStudyHome() {
  try { await stLoad(); } catch (e) {
    $("#st-body").innerHTML = `<div class="banner err">Could not load your study progress (${h(e.message)}). Nothing was changed. Reload the page to retry.</div>`;
    return;
  }
  $$("#st-nav button").forEach(b => b.classList.toggle("on", b.dataset.v === stView));
  ({ home: viewHome, cards: viewCards }[stView])();
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
  let saved = []; try { saved = await store.saved.list(); } catch { /* ignore */ }
  const unreviewed = saved.filter(s => !ST.cards[savedKey(s)]).length;
  const days = new Set(ST.log.map(l => l.t));
  const last14 = Array.from({ length: 14 }, (_, i) => dayShift(today, i - 13));
  const perDay = last14.map(d => ST.log.filter(l => l.t === d).length);
  const maxN = Math.max(1, ...perDay);
  const recent = ST.log.filter(l => l.t >= dayShift(today, -29));
  const retention = recent.length ? Math.round(100 * recent.filter(l => l.grade >= 2).length / recent.length) : null;
  const read = Object.values(ST.read);
  $("#st-body").innerHTML = `
    <div class="statgrid">
      <div class="stat"><b>${due}</b><span>cards due today</span></div>
      <div class="stat"><b>${unreviewed}</b><span>saved items not yet studied</span></div>
      <div class="stat"><b>${cards.length}</b><span>cards (${cards.length - mature} young · ${mature} mature)</span></div>
      <div class="stat"><b>${retention === null ? "—" : retention + "%"}</b><span>answered good/easy (30 days)</span></div>
      <div class="stat"><b>${streakOf(days)}</b><span>day streak</span></div>
      <div class="stat"><b>${read.length}</b><span>texts read (${read.reduce((a, r) => a + (r.chars || 0), 0)} characters)</span></div>
    </div>
    <h3>Card reviews, last 14 days</h3>
    <div class="bars">${perDay.map((n, i) => `<div title="${last14[i]}: ${n}"><i style="height:${Math.round(100 * n / maxN)}%"></i><small>${last14[i].slice(8)}</small></div>`).join("")}</div>
    <p class="muted">Progress is stored ${store.kind === "cloud" ? "in your account (synced across devices)" : "in this browser only (sign in to sync)"}. Flashcards come from the words and grammar you save while reading, or from a textbook level.</p>`;
}

/* ---------- flashcards ---------- */
let FC = null;   // {queue:[{key, card}], total, reviewed, again}
function viewCards() {
  $("#st-body").innerHTML = `
    <div class="filters">
      <label>New cards from <select id="fc-deck"><option value="saved">my saved items</option><option value="vocab">a level's word list</option><option value="grammar">a level's grammar</option></select></label>
      <select id="fc-level">${levelOptions("3B")}</select>
      <label>up to <input id="fc-new" type="number" min="0" max="50" value="10" style="width:70px"> new</label>
      <button id="fc-start" class="primary">Start session</button>
    </div>
    <p class="muted">A session shows every card that is due plus the new cards you ask for. Press “Show answer” to see the Google translation. Grade yourself: <b>Again</b> brings the card back today; <b>Hard / Good / Easy</b> set the next review date (SM-2).</p>
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
  const queue = Object.entries(ST.cards).filter(([, c]) => c.srs && c.srs.due <= today).map(([key, card]) => ({ key, card }));
  let fresh = [];
  if (deck === "saved") {
    fresh = (await store.saved.list()).filter(s => !ST.cards[savedKey(s)]).map(s => ({ key: savedKey(s), card: { kind: s.kind, ref_id: s.ref_id, text: s.text, sentence: s.sentence, item: s.item } }));
  } else if (deck === "vocab") {
    const r = await api(`/vocab?level=${level}&status=verified&limit=200`);
    fresh = r.items.filter(e => !ST.cards["vocab:" + e.id]).map(e => ({ key: "vocab:" + e.id, card: { kind: "vocab", ref_id: e.id, item: { headword: e.headword, level: e.level, unit: e.unit } } }));
  } else {
    const r = await api(`/grammar?level=${level}&limit=200`);
    fresh = r.items.filter(e => !ST.cards["grammar:" + e.id]).map(e => ({ key: "grammar:" + e.id, card: { kind: "grammar", ref_id: e.id, item: { headword: e.pattern, level: e.level, unit: e.unit } } }));
  }
  FC = { queue: queue.concat(fresh.slice(0, nNew)), total: 0, reviewed: 0, again: 0 };
  FC.total = FC.queue.length;
  if (!FC.total) { $("#fc-area").innerHTML = `<p class="muted">Nothing to study right now: no cards are due${deck === "saved" ? " and you have no unstudied saved items (click a word while reading and press Save)" : ""}.</p>`; return; }
  showCard();
}
async function showCard() {
  const area = $("#fc-area");
  if (!FC.queue.length) { area.innerHTML = `<div class="stat"><b>Session complete</b><span>${FC.reviewed} reviews · ${FC.again} marked “again”</span></div>`; return; }
  const { key, card } = FC.queue[0];
  let detail = null;
  try {
    if (card.kind === "vocab") detail = await api("/vocab/" + card.ref_id);
    else if (card.kind === "grammar") detail = await api("/grammar/" + card.ref_id);
  } catch { FC.queue.shift(); return showCard(); }            // item deleted since it was saved
  const front = card.kind === "word" ? card.text : card.kind === "vocab" ? detail.headword.replace(/\([^)]*\)/g, "") : detail.pattern;
  const sent = card.sentence ? `<p class="muted ko">You met it in: ${h(card.sentence)}</p>` : "";
  let back = "";
  if (card.kind === "grammar") {
    const exs = (detail.examples || []).slice(0, 2).map(x => `<blockquote class="ko">${h(x.sentence)}</blockquote>`).join("");
    back = `${detail.explanation_original ? `<blockquote>${h(detail.explanation_original.slice(0, 600))}</blockquote>` : `<p class="muted">No textbook explanation stored for this item.</p>`}<p class="muted">${h(refLineShort(detail))}${detail.status === "needs_review" ? " · unreviewed (OCR draft)" : ""}</p>${exs}`;
  } else {
    back = `<div id="fc-tr" class="trbox"></div>${detail ? `<p class="muted">${h(refLineShort(detail))}</p>` : ""}${card.sentence ? `<div id="fc-sent" class="trbox"></div>` : ""}`;
  }
  area.innerHTML = `<div class="card"><div class="muted">${FC.total - FC.queue.length + 1} / ${FC.total} · ${h(card.kind)}${ST.cards[key] ? " · review" : " · new"}</div>
    <div class="cardfront ko">${h(front)}</div>${sent}
    <div id="fc-back" hidden>${back}</div>
    <div class="grades" id="fc-grades" hidden><button data-g="0">Again</button><button data-g="1">Hard</button><button data-g="2" class="primary">Good</button><button data-g="3">Easy</button></div>
    <button id="fc-show" class="primary">Show answer</button></div>`;
  $("#fc-show").onclick = () => {
    $("#fc-back").hidden = false; $("#fc-grades").hidden = false; $("#fc-show").hidden = true;
    if (card.kind !== "grammar") { gtRender($("#fc-tr"), front, { roman: true, alts: true }); if (card.sentence) gtRender($("#fc-sent"), card.sentence); }
  };
  $$("#fc-grades button").forEach(b => b.onclick = () => gradeCard(+b.dataset.g));
}
async function gradeCard(grade) {
  const { key, card } = FC.queue[0], today = todayStr();
  const meta = ST.cards[key] || Object.assign({}, card);
  try { meta.srs = await api("/study/schedule", { method: "POST", body: { state: meta.srs || null, grade, today } }); }
  catch (e) { showError("could not schedule the card (" + e.message + "). It stays in your session; try again."); return; }
  FC.queue.shift();
  ST.cards[key] = meta;
  ST.log.push({ t: today, kind: card.kind, id: card.ref_id ?? card.text, grade });
  FC.reviewed++;
  if (grade === 0) { FC.again++; FC.queue.push({ key, card: meta }); }
  await stSave();
  showCard();
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
  if (typeof loadStories === "function" && !$("#tab-stories").hidden) loadStories();
};
function renderQuestions() {
  const qs = ST.questions[pidKey()] || [];
  $("#questions").hidden = false;
  $("#q-list").innerHTML = qs.map((q, i) => `<li><b>${h(q.q)}</b>${q.a ? ` <button data-sa="${i}">answer</button><span class="qa" id="qa${i}" hidden> — ${h(q.a)}</span>` : ""} <button data-qd="${i}" title="delete">✕</button></li>`).join("") || `<li class="muted">No questions yet. Questions are written by you.</li>`;
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
