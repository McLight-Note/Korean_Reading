const test = require("node:test");
const assert = require("node:assert");
const { wordsHtml, sentenceAround, sortStories, idsToUpload, mergeRead, firstHighlight, escapeHtml, isKorean } = require("../../public/core.js");

test("words become clickable spans; highlights only wrap the coloured part", () => {
  const text = "저는 영화를 봤어요.";
  const html = wordsHtml(text, [{ start: 3, end: 5, kind: "vocab", ref: "영화" }, { start: 7, end: 9, kind: "grammar", ref: "V+았어요" }]);
  assert.match(html, /<span class="w" data-s="3" data-e="6"><span class="h hv" data-h="0">영화<\/span>를<\/span>/);
  assert.match(html, /<span class="h hg" data-h="1">봤어<\/span>요\.<\/span>/);
  assert.equal(html.replace(/<[^>]+>/g, ""), text);                      // nothing is lost or duplicated
});

test("offsets count UTF-16 units like JavaScript strings (emoji before a word)", () => {
  const text = "😀 영화";
  const i = text.indexOf("영화");
  const html = wordsHtml(text, [{ start: i, end: i + 2, kind: "vocab", ref: "영화" }]);
  assert.match(html, /<span class="h hv" data-h="0">영화<\/span>/);
});

test("text is escaped", () => {
  const html = wordsHtml('<b>"x"</b> & 가', []);
  assert.ok(!html.includes("<b>"));
  assert.equal(escapeHtml(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
});

test("sentenceAround finds the right sentence", () => {
  const t = "첫 문장입니다. 둘째 문장이에요! 셋째\n넷째 문장";
  assert.equal(sentenceAround(t, 1), "첫 문장입니다.");
  assert.equal(sentenceAround(t, t.indexOf("둘째") + 1), "둘째 문장이에요!");
  assert.equal(sentenceAround(t, t.indexOf("넷째")), "넷째 문장");
});

test("stories sort by level, then id", () => {
  const ids = sortStories([{ id: "b", level: "4A" }, { id: "z", level: "3B" }, { id: "a", level: "4A" }, { id: "q", level: "3A" }, { id: "x", level: "??" }]).map(s => s.id);
  assert.deepEqual(ids, ["q", "z", "a", "b", "x"]);
});

test("signing in uploads only what the account does not know yet; the merged list is the union", () => {
  assert.deepEqual(idsToUpload({ a: 1, b: 2 }, { b: 5 }), ["a"]);
  assert.deepEqual(idsToUpload({}, { b: 5 }), []);
  assert.deepEqual(idsToUpload(null, null), []);
  assert.deepEqual(mergeRead({ a: 1, b: 2 }, { b: 5, c: 3 }), { a: 1, b: 5, c: 3 });
});

test("finding the first highlight of a target and detecting Korean", () => {
  const hl = [{ kind: "vocab", ref: "a" }, { kind: "grammar", ref: "a" }, { kind: "vocab", ref: "b" }];
  assert.equal(firstHighlight(hl, "grammar", "a"), 1);
  assert.equal(firstHighlight(hl, "vocab", "zzz"), -1);
  assert.ok(isKorean("영화") && !isKorean("movie"));
});
