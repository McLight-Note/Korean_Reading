"use strict";
/* Google Translate, called straight from the visitor's browser (no key, no server involved).

   It uses the same keyless endpoint Google's own widgets use. It is unofficial: Google may rate-limit or change it,
   so every use shows a link to translate.google.com as a fallback. What you click (a word or its sentence) is sent to
   Google; nothing else is. Results are cached in this browser. */

const TL_LANGS = { en: "English", uz: "O'zbek", ru: "Русский", tr: "Türkçe", ko: "한국어 (romanization only)" };
const TL = {
  get lang() { try { return localStorage.getItem("kr.lang") || "en"; } catch { return "en"; } },
  set lang(v) { try { localStorage.setItem("kr.lang", v); } catch { /* ignore */ } },
};
const gtCache = new Map();
const GT_STORE_MAX = 400;

function gtLoadStore() {
  try { return JSON.parse(localStorage.getItem("kr.gt") || "{}"); } catch { return {}; }
}
function gtSaveStore(obj) {
  try {
    const keys = Object.keys(obj);
    if (keys.length > GT_STORE_MAX) for (const k of keys.slice(0, keys.length - GT_STORE_MAX)) delete obj[k];
    localStorage.setItem("kr.gt", JSON.stringify(obj));
  } catch { /* storage full or unavailable: the in-memory cache still works */ }
}

function gtUrl(text, to) {
  return `https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=${encodeURIComponent(to)}&dt=t&dt=bd&dt=rm&q=${encodeURIComponent(text)}`;
}
const gtLink = (text, to = TL.lang) => `https://translate.google.com/?sl=ko&tl=${encodeURIComponent(to)}&text=${encodeURIComponent(text)}&op=translate`;

/* Pure parser for Google's response array (exported for tests):
   j[0] = segments [translated, original, , , ...] plus an optional romanization segment [null, null, targetRoman, sourceRoman]
   j[1] = dictionary entries [[partOfSpeech, [alternatives...], ...], ...] (single words only) */
function gtParse(j) {
  const segs = Array.isArray(j && j[0]) ? j[0] : [];
  const text = segs.map(s => (s && s[0]) || "").join("").trim();
  const roman = segs.map(s => (s && s.length >= 4 && s[3]) || "").join(" ").trim();
  const alts = (Array.isArray(j && j[1]) ? j[1] : []).slice(0, 3).map(e => ({ pos: e[0], words: (e[1] || []).slice(0, 5) }));
  return { text, roman, alts };
}

async function gtranslate(text, to = TL.lang) {
  const t = String(text || "").trim();
  if (!t) return { text: "", roman: "", alts: [] };
  const key = `${to}|${t}`;
  if (gtCache.has(key)) return gtCache.get(key);
  const stored = gtLoadStore();
  if (stored[key]) { gtCache.set(key, stored[key]); return stored[key]; }
  const res = await fetch(gtUrl(t, to));
  if (!res.ok) throw new Error(`Google Translate answered ${res.status}`);
  const out = gtParse(await res.json());
  if (!out.text) throw new Error("empty translation");
  gtCache.set(key, out);
  stored[key] = out; gtSaveStore(stored);
  return out;
}

/* Fill an element with a translation (word or sentence); shows a fallback link if Google is unreachable. */
function gtRender(el, text, opts = {}) {
  const to = TL.lang;
  el.innerHTML = `<span class="muted">translating…</span>`;
  gtranslate(text, to).then(r => {
    const alts = opts.alts && r.alts.length ? `<div class="alts">${r.alts.map(a => `<span class="muted">${escapeHtml(a.pos)}</span> ${a.words.map(escapeHtml).join(", ")}`).join("<br>")}</div>` : "";
    el.innerHTML = `<div class="tr">${escapeHtml(r.text)}</div>${opts.roman && r.roman ? `<div class="roman muted">${escapeHtml(r.roman)}</div>` : ""}${alts}`;
  }).catch(() => {
    el.innerHTML = `<span class="warnline">Couldn't reach Google Translate (offline, blocked or rate-limited).</span> <a href="${gtLink(text, to)}" target="_blank" rel="noopener">Open it in Google Translate ↗</a>`;
  });
}

if (typeof module !== "undefined" && module.exports) module.exports = { gtParse, gtUrl, gtLink };
