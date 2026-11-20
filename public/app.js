"use strict";
/* 서울대 Reader: a list of stories, a reader with click-to-translate, and a "read" list.

   Stories live in Firebase (Firestore collection `stories`, readable by everyone, writable only by the publish script).
   The read list is stored per person: in their own Firestore space once signed in with Google (users/{uid}/read/{storyId}),
   otherwise in this browser. Translations come from Google Translate, requested by the browser (translate.js).
   Uses helpers from core.js and translate.js. */

const SDK_VERSION = "10.14.1";
const SDK_URLS = ["app", "auth", "firestore"].map(n => `https://www.gstatic.com/firebasejs/${SDK_VERSION}/firebase-${n}-compat.js`);

const $ = s => document.querySelector(s);
const h = escapeHtml;

const state = {
  stories: null,        // null while loading, then [{id, level, title, text, highlights, ...}]
  read: {},             // {storyId: timestamp}
  user: null,
  auth: null,
  db: null,
  cur: null,            // the story being read
  ctx: null,            // what the side panel currently shows
  scrolled: false,      // the visitor has scrolled down: only then does reaching the end of the text count as "read"
  openedAt: 0,
};
window.krState = state; // handle for the end-to-end tests

/* ---------------- small UI helpers ---------------- */
function banner(msg, isErr = true) {
  const b = $("#banner");
  b.textContent = msg; b.className = "banner" + (isErr ? " err" : ""); b.hidden = !msg;
}
let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}

/* ---------------- the read list (browser, or the signed-in person's Firestore space) ---------------- */
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
};
const readCol = () => state.db.collection(`users/${state.user.uid}/read`);

async function loadRead() {
  if (!state.user) { state.read = LS.get("kr.read", {}); return; }
  const snap = await readCol().get();
  const cloud = {};
  snap.docs.forEach(d => { cloud[d.id] = d.data().t || 0; });
  const local = LS.get("kr.read", {});
  const up = idsToUpload(local, cloud);                   // what this browser knew before signing in (the browser copy is kept)
  if (up.length) {
    const batch = state.db.batch();
    up.forEach(id => batch.set(readCol().doc(id), { t: local[id] || Date.now() }));
    await batch.commit();
  }
  state.read = mergeRead(local, cloud);
}

async function setRead(id, on, auto = false) {
  const was = !!state.read[id];
  if (on === was) return;
  if (on) state.read[id] = Date.now(); else delete state.read[id];
  try {
    if (state.user) {
      if (on) await readCol().doc(id).set({ t: state.read[id] }); else await readCol().doc(id).delete();
    } else if (!LS.set("kr.read", state.read)) banner("Browser storage is full: your read list could not be saved.");
  } catch (e) {
    if (on) delete state.read[id]; else state.read[id] = Date.now();     // undo the optimistic change
    banner("Could not save your read list: " + e.message);
  }
  if (on) toast(auto ? "You reached the end: added to your read list ✓" : "Added to your read list ✓");
  render();
}

/* ---------------- loading stories ---------------- */
async function loadStories() {
  try {
    const snap = await state.db.collection("stories").get();
    state.stories = sortStories(snap.docs.map(d => ({ ...d.data(), id: d.id })));
  } catch (e) {
    state.stories = [];
    banner(e.code === "permission-denied"
      ? "Firebase refused to send the stories. The security rules have not been installed yet (README, Part 3e)."
      : "Could not load the stories: " + e.message);
  }
}

/* ---------------- routing and rendering ---------------- */
const routeId = () => { const m = location.hash.match(/^#\/story\/(.+)$/); return m ? decodeURIComponent(m[1]) : null; };

function render() {
  const id = routeId();
  const listView = $("#view-list"), readView = $("#view-read");
  if (!id) {
    listView.hidden = false; readView.hidden = true;
    document.body.classList.remove("has-panel");
    renderList();
    return;
  }
  listView.hidden = true; readView.hidden = false;
  if (!state.cur || state.cur.id !== id) openStory(id); else renderReadControls();
}
window.addEventListener("hashchange", render);

function renderList() {
  const box = $("#stories-list");
  if (state.stories === null) { box.innerHTML = `<p class="muted">Loading stories…</p>`; return; }
  const level = $("#f-level").value, status = $("#f-status").value;
  const total = state.stories.length, nread = state.stories.filter(s => state.read[s.id]).length;
  $("#progress").textContent = total ? `${nread} of ${total} read` : "";
  const list = state.stories.filter(s => (!level || s.level === level)
    && (!status || (status === "read") === !!state.read[s.id]));
  if (!total) { box.innerHTML = `<p class="muted">There are no stories yet. Ask Claude to write some and publish them (README, “Adding stories”).</p>`; return; }
  const byLevel = {};
  list.forEach(s => (byLevel[s.level] = byLevel[s.level] || []).push(s));
  box.innerHTML = Object.entries(byLevel).map(([lvl, items]) => `
    <h3 class="lvl">${h(lvl)} <small class="muted">${items.length} ${items.length === 1 ? "story" : "stories"}</small></h3>
    <div class="storygrid">${items.map(s => `
      <article class="story ${state.read[s.id] ? "isread" : ""}">
        <header><span class="ttl ko" lang="ko">${h(s.title)}</span>${state.read[s.id] ? `<span class="chip ok">✓ read</span>` : ""}</header>
        <p class="muted">${h(s.theme || "")}${s.theme ? " · " : ""}${s.text.length} characters · ${(s.target_vocab || []).length} words · ${(s.target_grammar || []).length} grammar points</p>
        <details><summary>English summary</summary><p>${h(s.summary_en || "")}</p></details>
        <a class="btnlink go ${state.read[s.id] ? "" : "primary"}" href="#/story/${encodeURIComponent(s.id)}">${state.read[s.id] ? "Read again" : "Read"}</a>
      </article>`).join("")}</div>`).join("") || `<p class="muted">No stories match these filters.</p>`;
}

function fillLevelFilter() {
  const sel = $("#f-level"), keep = sel.value;
  const levels = [...new Set((state.stories || []).map(s => s.level))];
  sel.innerHTML = `<option value="">All levels</option>` + levels.map(l => `<option>${h(l)}</option>`).join("");
  sel.value = levels.includes(keep) ? keep : "";
}

function openStory(id) {
  if (state.stories === null) return;                                     // render() runs again once the stories have loaded
  const s = state.stories.find(x => x.id === id);
  if (!s) { banner("That story does not exist (any more)."); location.hash = "#/"; return; }
  banner("");
  state.cur = s; state.ctx = null; state.scrolled = false; state.openedAt = performance.now();
  $("#s-title").textContent = s.title;
  $("#s-level").textContent = s.level;
  $("#text").innerHTML = wordsHtml(s.text, s.highlights);
  resetPanel();
  renderBelow(s);
  renderReadControls();
  window.scrollTo({ top: 0 });
  watchEnd();
}

function renderReadControls() {
  const s = state.cur, on = !!state.read[s.id];
  const btn = $("#btn-read");
  btn.textContent = on ? "✓ Read (click to undo)" : "Mark as read";
  btn.className = on ? "" : "primary";
  btn.onclick = () => setRead(s.id, !state.read[s.id]);
  const next = state.stories.find(x => !state.read[x.id] && x.id !== s.id);
  const link = $("#btn-next");
  link.hidden = !(on && next);
  if (next) link.href = "#/story/" + encodeURIComponent(next.id);
}

function renderBelow(s) {
  const chip = (kind, ref, label) => `<button class="${kind === "grammar" ? "cg" : "cv"}" data-kind="${kind}" data-ref="${h(ref)}">${h(label || ref)}</button>`;
  const vocab = (s.target_vocab || []).map(t => chip("vocab", t)).join("");
  const gram = (s.target_grammar || []).map(t => chip("grammar", t)).join("");
  const qs = (s.questions || []).map((q, i) => `<div class="qa"><b class="ko" lang="ko">${h(q.q)}</b>
      ${q.a ? `<button data-ans="${i}">answer</button><span class="ans ko" lang="ko" id="ans${i}" hidden>${h(q.a)}</span>` : ""}</div>`).join("");
  $("#below").innerHTML = `
    <div class="box"><h3>Summary</h3><p>${h(s.summary_en || "")}</p></div>
    ${vocab ? `<div class="box"><h3><span class="vtxt">Words to learn</span> <small class="muted">(click one to find it in the story)</small></h3><div class="chips ko" lang="ko">${vocab}</div></div>` : ""}
    ${gram ? `<div class="box"><h3><span class="gtxt">Grammar to learn</span></h3><div class="chips" lang="ko">${gram}</div></div>` : ""}
    ${qs ? `<div class="box"><h3>Questions</h3>${qs}</div>` : ""}`;
  $("#below").querySelectorAll("[data-ans]").forEach(b => b.onclick = () => { $("#ans" + b.dataset.ans).hidden = false; b.hidden = true; });
  $("#below").querySelectorAll(".chips button").forEach(b => b.onclick = () => {
    const i = firstHighlight(s.highlights, b.dataset.kind, b.dataset.ref);
    const el = i >= 0 ? $(`#text .h[data-h="${i}"]`) : null;
    if (el) { el.click(); el.scrollIntoView({ block: "center", behavior: "smooth" }); }
  });
}

/* Scrolling down to the end of a long story counts as having read it. (A short story that fits on the screen has nothing to
   scroll, so for those the "Mark as read" button is the way.) */
let observer = null;
function maybeAutoRead() {
  const s = state.cur;
  if (!s || state.read[s.id] || $("#view-read").hidden || !state.scrolled) return;
  if ($("#end-sentinel").getBoundingClientRect().top < innerHeight) setRead(s.id, true, true);
}
function watchEnd() {
  if (observer) observer.disconnect();
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) maybeAutoRead(); }, { threshold: 1 });
    observer.observe($("#end-sentinel"));
  }
}
/* Only the visitor's own scrolling (wheel, touch, keyboard) counts: a jump made by the page itself, for example to a word
   that was clicked in the "words to learn" list, does not. */
const SCROLL_KEYS = ["PageDown", "End", " ", "ArrowDown", "Spacebar"];
function userScrolled() {
  if (state.scrolled || performance.now() - state.openedAt < 400) return;
  state.scrolled = true;
}
window.addEventListener("wheel", e => { if (e.deltaY > 0) userScrolled(); }, { passive: true });
window.addEventListener("touchmove", userScrolled, { passive: true });
window.addEventListener("keydown", e => { if (SCROLL_KEYS.includes(e.key)) userScrolled(); });
window.addEventListener("scroll", maybeAutoRead, { passive: true });

/* ---------------- clicking a word: the side panel ---------------- */
$("#text").onclick = ev => {
  const w = ev.target.closest(".w");
  if (!w) return;
  const hEl = ev.target.closest("[data-h]");
  document.querySelectorAll("#text .w.sel").forEach(x => x.classList.remove("sel"));
  w.classList.add("sel");
  const s = state.cur, st = +w.dataset.s, en = +w.dataset.e;
  const raw = s.text.slice(st, en), word = raw.replace(TRIM, "") || raw;
  const H = hEl ? s.highlights[+hEl.dataset.h] : null;
  const ctx = { word, sentence: sentenceAround(s.text, st), kind: H ? H.kind : null, ref: H ? H.ref : null, phrase: null };
  if (H) { const shown = s.text.slice(H.start, H.end).replace(TRIM, ""); if (shown !== word) ctx.phrase = shown; }
  showPanel(ctx);
};

function resetPanel() {
  const d = $("#detail");
  d.innerHTML = `<p class="muted">Click any word. Its translation appears here.</p>`;
  d.classList.add("idle");
  document.body.classList.remove("has-panel");
}

function showPanel(ctx) {
  state.ctx = ctx;
  const d = $("#detail");
  d.classList.remove("idle");
  document.body.classList.add("has-panel");
  const label = ctx.kind === "grammar" ? "Grammar to learn" : ctx.kind === "vocab" ? "Word to learn" : "Word";
  d.innerHTML = `
    <button class="pclose" id="p-close" aria-label="Close">✕</button>
    <div class="lbl">${label}</div>
    <div class="kword ko" lang="ko">${h(ctx.word)}</div>
    <div id="tr-word" class="trbox"></div>
    ${ctx.kind === "grammar" ? `<div class="lbl">Textbook pattern</div><div class="ko" lang="ko"><b>${h(ctx.ref)}</b></div>` : ""}
    ${ctx.phrase ? `<div class="lbl">Highlighted part</div><div class="ko" lang="ko"><b>${h(ctx.phrase)}</b></div><div id="tr-phrase" class="trbox"></div>` : ""}
    ${ctx.sentence ? `<div class="lbl">Sentence</div><blockquote class="ko" lang="ko">${h(ctx.sentence)}</blockquote><div id="tr-sent" class="trbox"></div>` : ""}
    <p><a href="${gtLink(ctx.sentence || ctx.word, TL.lang)}" target="_blank" rel="noopener">Open in Google Translate ↗</a></p>`;
  if (isKorean(ctx.word)) gtRender($("#tr-word"), ctx.word, { roman: true, alts: true });
  else $("#tr-word").innerHTML = `<span class="muted">(not Korean text)</span>`;
  if (ctx.phrase) gtRender($("#tr-phrase"), ctx.phrase);
  if (ctx.sentence) gtRender($("#tr-sent"), ctx.sentence);
  $("#p-close").onclick = () => { resetPanel(); document.querySelectorAll("#text .w.sel").forEach(x => x.classList.remove("sel")); };
}

/* ---------------- header: language menu and sign-in ---------------- */
function initHeader() {
  $("#lang").innerHTML = Object.entries(TL_LANGS).map(([k, v]) => `<option value="${k}">${h(v)}</option>`).join("");
  $("#lang").value = TL.lang;
  $("#lang").onchange = () => { TL.lang = $("#lang").value; if (state.ctx) showPanel(state.ctx); };
  $("#f-level").onchange = renderList;
  $("#f-status").onchange = renderList;
}

function renderAuth() {
  const box = $("#auth-box");
  if (!state.auth) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = state.user
    ? `<span class="muted" title="Your read list is saved to this Google account">☁ ${h(state.user.email || "signed in")}</span> <button id="auth-out">Sign out</button>`
    : `<span class="muted">Read list: this browser only</span> <button id="auth-in" class="primary">Sign in with Google</button>`;
  const i = $("#auth-in"), o = $("#auth-out");
  if (i) i.onclick = signIn;
  if (o) o.onclick = () => state.auth.signOut();
}

async function signIn() {
  try { await state.auth.signInWithPopup(new firebase.auth.GoogleAuthProvider()); }
  catch (e) {
    const hint = {
      "auth/unauthorized-domain": "This web address is not authorised yet: Firebase console → Authentication → Settings → Authorized domains → add it.",
      "auth/operation-not-allowed": "Google sign-in is not turned on: Firebase console → Authentication → Sign-in method → Google.",
      "auth/popup-blocked": "Your browser blocked the sign-in popup. Allow popups for this site and try again.",
    }[e.code];
    if (e.code !== "auth/popup-closed-by-user" && e.code !== "auth/cancelled-popup-request") banner(hint || e.message);
  }
}

/* ---------------- start-up ---------------- */
function loadScripts(urls) {
  return urls.reduce((p, src) => p.then(() => new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = () => rej(new Error("could not load " + src));
    document.head.appendChild(s);
  })), Promise.resolve());
}

async function boot() {
  initHeader();
  const cfg = window.KR_FIREBASE;
  if (!cfg) {
    $("#stories-list").innerHTML = `<div class="box"><h3>Firebase is not set up yet</h3>
      <p>The stories are stored in Firebase. Follow the README (Part 3, “Set up Firebase”), paste your settings into <code>public/firebase-config.js</code>, and reload this page.</p></div>`;
    return;
  }
  try {
    await loadScripts(SDK_URLS);
    firebase.initializeApp(cfg);
    state.auth = firebase.auth(); state.db = firebase.firestore();
    if (cfg.emulator) {                                                   // local development and the automatic tests only
      state.auth.useEmulator(cfg.emulator.auth, { disableWarnings: true });
      if (cfg.emulator.longPolling) state.db.settings({ experimentalForceLongPolling: true, experimentalAutoDetectLongPolling: false, merge: true });
      state.db.useEmulator(cfg.emulator.firestore[0], cfg.emulator.firestore[1]);
    }
  } catch (e) {
    $("#stories-list").innerHTML = `<p class="muted">Could not load Firebase (are you offline?): ${h(e.message)}</p>`;
    return;
  }
  const storiesLoaded = loadStories().then(() => { fillLevelFilter(); render(); });
  let first = true;
  state.auth.onAuthStateChanged(async user => {
    state.user = user;
    try { await loadRead(); } catch (e) { state.read = LS.get("kr.read", {}); banner("Could not load your read list from your account: " + e.message); }
    renderAuth();
    if (!first) { await storiesLoaded; render(); }
    first = false;
  });
  await storiesLoaded;
  render();
}
boot();
