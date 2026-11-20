"use strict";
/* Small pure helpers (no DOM, no network) shared by app.js and the unit tests. */

const LEVELS = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"];
const TRIM = /^[\s"'“”‘’()[\]{}<>.,!?…~·:;\-—]+|[\s"'“”‘’()[\]{}<>.,!?…~·:;\-—]+$/g;

const escapeHtml = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isKorean = s => /[가-힣]/.test(s);

/* The story text as HTML: every whitespace-separated word is a <span class="w"> (clickable), and the parts covered by a
   highlight ({start, end, kind, ref}, UTF-16 offsets into `text`) are wrapped in <span class="h hv|hg">. Highlights only
   change the colour of the text; they never add boxes. */
function wordsHtml(text, highlights) {
  const hl = (highlights || []).map((H, i) => ({ ...H, i })).sort((a, b) => a.start - b.start);
  let html = "", pos = 0, hi = 0;
  for (const m of text.matchAll(/\S+/g)) {
    const s = m.index, e = s + m[0].length;
    html += escapeHtml(text.slice(pos, s)) + `<span class="w" data-s="${s}" data-e="${e}">`;
    while (hi < hl.length && hl[hi].end <= s) hi++;
    let p = s, j = hi;
    while (j < hl.length && hl[j].start < e) {
      const H = hl[j], a = Math.max(H.start, s), b = Math.min(H.end, e);
      if (a > p) html += escapeHtml(text.slice(p, a));
      if (b > a) html += `<span class="h ${H.kind === "grammar" ? "hg" : "hv"}" data-h="${H.i}">${escapeHtml(text.slice(a, b))}</span>`;
      p = Math.max(p, b); j++;
    }
    if (p < e) html += escapeHtml(text.slice(p, e));
    html += `</span>`;
    pos = e;
  }
  return html + escapeHtml(text.slice(pos));
}

/* The sentence that contains position `pos`. */
function sentenceAround(text, pos) {
  for (const m of text.matchAll(/[^\n.!?…]+(?:[.!?…]+["'”’)\]]*)?/g)) {
    if (m.index <= pos && pos < m.index + m[0].length) return m[0].trim();
  }
  return "";
}

/* Stories in reading order: by level (3A before 4B), then by id. */
const sortStories = list => [...list].sort((a, b) => {
  const la = LEVELS.indexOf(a.level), lb = LEVELS.indexOf(b.level);
  return (la < 0 ? 99 : la) - (lb < 0 ? 99 : lb) || String(a.id).localeCompare(String(b.id));
});

/* Read lists are {storyId: timestamp}. Which ids exist only in `local`, i.e. must be uploaded when someone signs in? */
const idsToUpload = (local, cloud) => Object.keys(local || {}).filter(id => !(cloud && id in cloud));
const mergeRead = (local, cloud) => ({ ...(local || {}), ...(cloud || {}) });

/* First highlight of a given kind and ref (used by the "words to learn" chips). */
const firstHighlight = (highlights, kind, ref) => (highlights || []).findIndex(H => H.kind === kind && H.ref === ref);

if (typeof module !== "undefined" && module.exports) {
  module.exports = { LEVELS, TRIM, escapeHtml, isKorean, wordsHtml, sentenceAround, sortStories, idsToUpload, mergeRead, firstHighlight };
}
