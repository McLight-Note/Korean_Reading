const test = require("node:test");
const assert = require("node:assert");
const { gtParse, gtUrl, gtLink } = require("../../public/translate.js");

test("parses text, romanization and dictionary alternatives", () => {
  const r = gtParse([[["I ate", "먹었어요"], [null, null, "meogeosseoyo", "meogeosseoyo"]], [["verb", ["eat", "have", "consume", "a", "b", "c"]]]]);
  assert.equal(r.text, "I ate");
  assert.equal(r.roman, "meogeosseoyo");
  assert.deepEqual(r.alts[0], { pos: "verb", words: ["eat", "have", "consume", "a", "b"] });
});
test("joins multi-segment sentences and survives junk", () => {
  assert.equal(gtParse([[["Hello. ", "안녕. "], ["World", "세상"]]]).text, "Hello. World");
  assert.deepEqual(gtParse(null), { text: "", roman: "", alts: [] });
  assert.deepEqual(gtParse([]), { text: "", roman: "", alts: [] });
});
test("urls are encoded and point at the keyless endpoint / the public site", () => {
  assert.match(gtUrl("a b&c", "uz"), /^https:\/\/translate\.googleapis\.com\/translate_a\/single\?.*tl=uz.*q=a%20b%26c$/);
  assert.match(gtLink("한국어", "en"), /^https:\/\/translate\.google\.com\/\?sl=ko&tl=en&text=%ED/);
});
