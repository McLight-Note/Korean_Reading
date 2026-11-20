// Run: node --test tests/js
const test = require("node:test");
const assert = require("node:assert/strict");
const D = require("../../public/studydocs.js");

const sample = () => ({
  cards: Object.fromEntries(Array.from({ length: 300 }, (_, i) => [`vocab:${i}`, { kind: "vocab", ref_id: i, srs: { ease: 2.5, interval: i % 9, reps: 1, lapses: 0, due: "2026-11-21", last: "2026-11-20" } }])),
  log: [{ t: "2026-10-30", kind: "vocab", id: 1, grade: 2 }, { t: "2026-11-02", kind: "vocab", id: 2, grade: 0 }, { t: "2026-11-20", kind: "grammar", id: 3, grade: 3 }],
  ex: [{ t: "2026-11-19", type: "grammar_mcq", ok: true, id: 5 }],
  read: { "42": { t: "2026-11-20", chars: 120 } },
  questions: { "42": [{ q: "누가?", a: "내가" }] },
});

test("split then join is lossless", () => {
  const st = sample();
  assert.deepEqual(D.joinState(D.splitState(st)), st);
});

test("cards are spread over at most 16 documents and stay far below the 1 MiB document limit", () => {
  const docs = D.splitState(sample());
  const chunkIds = Object.keys(docs).filter(k => k.startsWith("cards_"));
  assert.ok(chunkIds.length > 1 && chunkIds.length <= D.CHUNKS);
  for (const [id, d] of Object.entries(docs)) assert.ok(Buffer.byteLength(JSON.stringify(d)) < 200_000, id);
});

test("the log is grouped by month and keeps chronological order after a round trip", () => {
  const docs = D.splitState(sample());
  assert.deepEqual(Object.keys(docs).filter(k => k.startsWith("log_")).sort(), ["log_2026-10", "log_2026-11"]);
  assert.deepEqual(D.joinState(docs).log.map(e => e.t), ["2026-10-30", "2026-11-02", "2026-11-20"]);
});

test("chunk assignment is stable", () => {
  assert.equal(D.hash("vocab:12") % D.CHUNKS, D.hash("vocab:12") % D.CHUNKS);
  const a = D.splitState(sample()), st = sample();
  st.cards["vocab:7"].srs.interval = 99;
  const b = D.splitState(st);
  const { set, del } = D.diffDocs(a, b);
  assert.equal(set.length, 1);                      // only the one chunk holding vocab:7 changed
  assert.equal(del.length, 0);
  assert.ok(set[0].startsWith("cards_"));
});

test("diff detects new and removed documents (e.g. a month dropping out of the capped log)", () => {
  const a = D.splitState(sample());
  const st = sample(); st.log = st.log.slice(1);   // the October entry is gone
  const b = D.splitState(st);
  const { set, del } = D.diffDocs(a, b);
  assert.deepEqual(del, ["log_2026-10"]);
  assert.deepEqual(set, []);
  const st2 = sample(); st2.log.push({ t: "2026-12-01", kind: "vocab", id: 9, grade: 2 });
  assert.deepEqual(D.diffDocs(a, D.splitState(st2)).set, ["log_2026-12"]);
});

test("undefined values are dropped (Firestore would reject them) and empty state is recognised", () => {
  const st = D.emptyState(); st.cards["vocab:1"] = { kind: "vocab", ref_id: 1, sentence: undefined, srs: { ease: 2.5, interval: 0, reps: 0, lapses: 0, due: "x", last: undefined } };
  const docs = D.splitState(st);
  assert.ok(!JSON.stringify(docs).includes("undefined"));
  assert.ok(!("sentence" in Object.values(docs).find(d => d.cards).cards["vocab:1"]));
  assert.ok(D.isEmptyState(D.emptyState()) && D.isEmptyState(null) && !D.isEmptyState(st));
});

test("joining tolerates missing or partial documents", () => {
  assert.deepEqual(D.joinState({}), D.emptyState());
  assert.deepEqual(D.joinState({ meta: {} }), D.emptyState());
  assert.deepEqual(D.joinState({ "log_2026-11": {} }).log, []);
});
