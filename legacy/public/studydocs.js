/* Pure helpers (no DOM, no Firebase) that map the study state onto Firestore-sized documents and back.
   Firestore documents are limited to 1 MiB, so the state is split into:
     meta            {read, questions}
     cards_<0..15>   {cards: {"vocab:12": {...}}}     cards spread over 16 documents by a stable hash of their key
     log_<YYYY-MM>   {entries: [...]}                   card reviews, one document per month
     ex_<YYYY-MM>    {entries: [...]}                   exercise answers, one document per month
   Loaded as a classic script in the browser and with require() in the Node tests. */
(function (root) {
  const CHUNKS = 16;
  const hash = s => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return h; };
  const month = t => (String(t || "").slice(0, 7) || "0000-00");
  const clean = o => JSON.parse(JSON.stringify(o));          // Firestore rejects `undefined`; this drops it

  function emptyState() { return { cards: {}, log: [], ex: [], read: {}, questions: {} }; }

  function splitState(st) {
    const docs = { meta: { read: st.read || {}, questions: st.questions || {} } };
    for (const [key, card] of Object.entries(st.cards || {})) {
      const id = "cards_" + (hash(key) % CHUNKS);
      (docs[id] = docs[id] || { cards: {} }).cards[key] = card;
    }
    for (const [kind, arr] of [["log", st.log || []], ["ex", st.ex || []]]) {
      for (const e of arr) {
        const id = `${kind}_${month(e.t)}`;
        (docs[id] = docs[id] || { entries: [] }).entries.push(e);
      }
    }
    return clean(docs);
  }

  function joinState(docs) {
    const st = emptyState();
    const ids = Object.keys(docs || {}).sort();                // month ids sort chronologically
    for (const id of ids) {
      const d = docs[id] || {};
      if (id === "meta") { st.read = d.read || {}; st.questions = d.questions || {}; }
      else if (id.startsWith("cards_")) Object.assign(st.cards, d.cards || {});
      else if (id.startsWith("log_")) st.log.push(...(d.entries || []));
      else if (id.startsWith("ex_")) st.ex.push(...(d.entries || []));
    }
    return st;
  }

  /* Which documents changed between two splitState() results: {set: [ids to write], del: [ids to delete]} */
  function diffDocs(prev, next) {
    const set = [], del = [];
    for (const id of Object.keys(next)) if (JSON.stringify(next[id]) !== JSON.stringify(prev[id])) set.push(id);
    for (const id of Object.keys(prev)) if (!(id in next)) del.push(id);
    return { set, del };
  }

  const isEmptyState = st => !st || (!Object.keys(st.cards || {}).length && !(st.log || []).length && !(st.ex || []).length
    && !Object.keys(st.read || {}).length && !Object.keys(st.questions || {}).length);

  const api = { CHUNKS, hash, emptyState, splitState, joinState, diffDocs, isEmptyState, clean };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.StudyDocs = api;
})(typeof window !== "undefined" ? window : globalThis);
