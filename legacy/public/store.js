"use strict";
/* Per-visitor storage, in every mode: passages (title + text), saved items, study progress.

   store.kind === "local"  -> this browser only (localStorage)       [signed out, or Firebase not configured]
   store.kind === "cloud"  -> the visitor's own Firestore space       [signed in with Google]
   The server's database holds only the textbook data; it never holds anything a visitor creates.

   Firebase is optional: with window.KR_FIREBASE unset nothing from Google is loaded and everything stays local.
   Security is enforced by firestore.rules (users/{uid}/... readable and writable only by that uid). */

const LS = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
const SDK_VERSION = "10.14.1";
const SDK_URLS = ["app", "auth", "firestore"].map(n => `https://www.gstatic.com/firebasejs/${SDK_VERSION}/firebase-${n}-compat.js`);
const sameId = (a, b) => String(a) === String(b);
const normalizeText = t => String(t || "").replace(/\r\n?/g, "\n").normalize("NFC");

/* ---------------- backend 1: this browser only ---------------- */
const localBackend = {
  kind: "local",
  passages: {
    async list() { return LS.get("kr.passages", []).map(p => ({ id: p.id, title: p.title, preview: (p.text || "").slice(0, 80) })); },
    async get(id) { return LS.get("kr.passages", []).find(p => sameId(p.id, id)) || null; },
    async create(title, text) {
      const p = { id: Date.now(), title: title || null, text: normalizeText(text), createdAt: Date.now() };
      const all = LS.get("kr.passages", []); all.unshift(p);
      if (!LS.set("kr.passages", all)) alert("Browser storage is full: this passage is shown but could not be saved. Delete old passages to free space.");
      return p;
    },
    async update(id, title, text) {
      const p = { id, title: title || null, text: normalizeText(text) };
      LS.set("kr.passages", LS.get("kr.passages", []).map(x => sameId(x.id, id) ? Object.assign({}, x, p) : x));
      return Object.assign({}, await this.get(id));
    },
    async remove(id) { LS.set("kr.passages", LS.get("kr.passages", []).filter(p => !sameId(p.id, id))); },
  },
  saved: {
    async list() { return LS.get("kr.saved", []); },
    async add(e) {
      const same = x => x.kind === e.kind && (e.kind === "word" ? x.text === e.text : x.ref_id === e.ref_id);
      const all = LS.get("kr.saved", []).filter(x => !same(x));
      all.unshift({ id: Date.now(), kind: e.kind, ref_id: e.ref_id ?? null, text: e.text ?? null, sentence: e.sentence || null, item: e.item || null });
      if (!LS.set("kr.saved", all)) throw new Error("Browser storage is full.");
    },
    async remove(id) { LS.set("kr.saved", LS.get("kr.saved", []).filter(x => !sameId(x.id, id))); },
  },
  study: {
    async load() { return LS.get("kr.study", null); },
    async save(state) { if (!LS.set("kr.study", state)) throw new Error("Browser storage is full: your progress could not be saved."); },
  },
};

/* ---------------- backend 2: the signed-in visitor's Firestore space ---------------- */
function makeCloudBackend(db, uid) {
  const col = name => db.collection(`users/${uid}/${name}`);
  let lastDocs = null;     // splitState() of what is currently stored, to write only what changed

  return {
    kind: "cloud",
    passages: {
      async list() {
        const snap = await col("passages").orderBy("createdAt", "desc").limit(300).get();
        return snap.docs.map(d => ({ id: d.id, title: d.data().title || null, preview: (d.data().text || "").slice(0, 80) }));
      },
      async get(id) {
        const snap = await col("passages").doc(String(id)).get();
        if (!snap.exists) return null;
        const d = snap.data();
        return { id: snap.id, title: d.title || null, text: d.text, createdAt: d.createdAt };
      },
      async create(title, text) {
        const ref = col("passages").doc(), now = Date.now(), t = normalizeText(text);
        await ref.set({ title: title || null, text: t, createdAt: now, updatedAt: now });
        return { id: ref.id, title: title || null, text: t, createdAt: now };
      },
      async update(id, title, text) {
        const t = normalizeText(text);
        await col("passages").doc(String(id)).set({ title: title || null, text: t, updatedAt: Date.now() }, { merge: true });
        return { id: String(id), title: title || null, text: t };
      },
      async remove(id) { await col("passages").doc(String(id)).delete(); },
    },
    saved: {
      async list() {
        const snap = await col("saved").get();
        return snap.docs.map(d => Object.assign({ id: d.id }, d.data())).sort((a, b) => (b.t || 0) - (a.t || 0));
      },
      async add(e) {
        const id = e.kind === "word" ? `word_${StudyDocs.hash(e.text)}` : `${e.kind}_${e.ref_id}`;
        await col("saved").doc(id).set(StudyDocs.clean({ kind: e.kind, ref_id: e.ref_id ?? null, text: e.text ?? null, sentence: e.sentence || null, item: e.item || null, t: Date.now() }));
      },
      async remove(id) { await col("saved").doc(String(id)).delete(); },
    },
    study: {
      async load() {
        const snap = await col("study").get();
        const docs = {};
        snap.docs.forEach(d => { docs[d.id] = d.data(); });
        lastDocs = StudyDocs.splitState(StudyDocs.joinState(docs));    // normalised form, comparable with future splits
        return StudyDocs.joinState(docs);
      },
      async save(state) {
        const next = StudyDocs.splitState(state);
        const prev = lastDocs || {};
        const { set, del } = StudyDocs.diffDocs(prev, next);
        const ops = [...set.map(id => ["set", id]), ...del.map(id => ["del", id])];
        for (let i = 0; i < ops.length; i += 400) {                    // Firestore batches hold at most 500 writes
          const batch = db.batch();
          for (const [op, id] of ops.slice(i, i + 400)) {
            const ref = col("study").doc(id);
            if (op === "set") batch.set(ref, next[id], id.startsWith("cards_") ? { merge: true } : {});   // cards merge per card, so two devices don't erase each other's cards
            else batch.delete(ref);
          }
          await batch.commit();
        }
        lastDocs = next;
      },
    },
  };
}

/* ---------------- the facade the app uses ---------------- */
let active = localBackend;
const store = {
  get kind() { return active.kind; },
  user: null,
  enabled: false,                       // Firebase configured and loaded
  onChange: null,                       // called after the backend switches (sign-in / sign-out)
  passages: new Proxy({}, { get: (_, k) => (...a) => active.passages[k](...a) }),
  saved: new Proxy({}, { get: (_, k) => (...a) => active.saved[k](...a) }),
  study: new Proxy({}, { get: (_, k) => (...a) => active.study[k](...a) }),
};

window.krStore = store;               // handle for debugging and the end-to-end tests

function loadScripts(urls) {
  return urls.reduce((p, src) => p.then(() => new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = () => rej(new Error("could not load " + src));
    document.head.appendChild(s);
  })), Promise.resolve());
}

const localHasData = () => LS.get("kr.passages", []).length || LS.get("kr.saved", []).length || !StudyDocs.isEmptyState(LS.get("kr.study", null));

async function migrateLocalToCloud(cloud) {
  // One-time, only when the account is empty and this browser has data. The local copy is left untouched.
  const [ps, sv, st] = await Promise.all([cloud.passages.list(), cloud.saved.list(), cloud.study.load()]);
  if (ps.length || sv.length || !StudyDocs.isEmptyState(st) || !localHasData()) return;
  if (!confirm("Upload the passages, saved words and study progress from this browser to your account? (This browser's copy is kept.)")) return;
  for (const p of [...LS.get("kr.passages", [])].reverse()) await cloud.passages.create(p.title || null, p.text);   // order is preserved by createdAt
  for (const s of [...LS.get("kr.saved", [])].reverse()) await cloud.saved.add({ kind: s.kind, ref_id: s.ref_id, text: s.text, sentence: s.sentence, item: s.item });
  const local = LS.get("kr.study", null);
  if (local) await cloud.study.save(Object.assign(StudyDocs.emptyState(), local));
}

function renderAuth() {
  const box = document.getElementById("auth-box");
  if (!box) return;
  if (!store.enabled) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = store.user
    ? `<span class="muted" title="Your passages, saved words and progress sync to this account">☁ ${escapeHtml(store.user.email || "signed in")}</span> <button id="auth-out">Sign out</button>`
    : `<span class="muted">Data stays in this browser</span> <button id="auth-in" class="primary">Sign in with Google to sync</button>`;
  const inBtn = document.getElementById("auth-in"), outBtn = document.getElementById("auth-out");
  if (inBtn) inBtn.onclick = signIn;
  if (outBtn) outBtn.onclick = () => store._auth.signOut();
}
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function signIn() {
  try { await store._auth.signInWithPopup(new firebase.auth.GoogleAuthProvider()); }
  catch (e) {
    const hint = {
      "auth/unauthorized-domain": "This site's domain is not authorised yet: add it under Firebase console → Authentication → Settings → Authorized domains.",
      "auth/operation-not-allowed": "Google sign-in is not enabled: Firebase console → Authentication → Sign-in method → Google.",
      "auth/popup-blocked": "Your browser blocked the sign-in popup. Allow popups for this site and try again.",
    }[e.code];
    if (e.code !== "auth/popup-closed-by-user" && e.code !== "auth/cancelled-popup-request") showError(hint || e.message);
  }
}

/* Called once by app.js at start-up. Resolves when the first auth state is known. */
store.init = async function () {
  const cfg = window.KR_FIREBASE;
  if (!cfg) { renderAuth(); return; }
  try {
    await loadScripts(SDK_URLS);
    firebase.initializeApp(cfg);
    const auth = firebase.auth(), db = firebase.firestore();
    if (cfg.emulator) {                                                // local development / tests only
      auth.useEmulator(cfg.emulator.auth, { disableWarnings: true });
      if (cfg.emulator.longPolling) db.settings({ experimentalForceLongPolling: true, experimentalAutoDetectLongPolling: false, merge: true });
      db.useEmulator(cfg.emulator.firestore[0], cfg.emulator.firestore[1]);
    }
    store._auth = auth; store._db = db; store.enabled = true;
  } catch (e) {                                                        // offline / blocked: stay local, don't break the app
    console.warn("Firebase unavailable, using browser storage:", e.message);
    store.enabled = false; renderAuth(); return;
  }
  let first = true;
  await new Promise(resolve => {
    store._auth.onAuthStateChanged(async user => {
      store.user = user;
      try {
        if (user) {
          const cloud = makeCloudBackend(store._db, user.uid);
          await migrateLocalToCloud(cloud).catch(e => showError("could not upload this browser's data: " + e.message));
          active = cloud;
        } else active = localBackend;
      } catch (e) { active = localBackend; showError("cloud storage unavailable: " + e.message); }
      renderAuth();
      if (!first && store.onChange) store.onChange();
      first = false;
      resolve();
    });
  });
};
