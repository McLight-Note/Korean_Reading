// Firestore security rules test. Run against the emulator:
//   npx firebase-tools emulators:exec --only firestore --project demo-kr "node tests/firebase/rules.test.js"
const fs = require("fs");
const path = require("path");
const { initializeTestEnvironment, assertFails, assertSucceeds } = require("@firebase/rules-unit-testing");

let failed = 0;
async function t(name, fn) {
  try { await fn(); console.log("PASS", name); } catch (e) { failed++; console.log("FAIL", name, "-", e.message.split("\n")[0]); }
}

(async () => {
  const env = await initializeTestEnvironment({
    projectId: "demo-kr",
    firestore: { rules: fs.readFileSync(path.join(__dirname, "../../firestore.rules"), "utf8"), host: "127.0.0.1", port: 8080 },
  });
  const alice = env.authenticatedContext("alice").firestore();
  const bob = env.authenticatedContext("bob").firestore();
  const anon = env.unauthenticatedContext().firestore();
  const passage = { title: "t", text: "저는 학생이에요.", createdAt: 1, updatedAt: 1 };

  await t("owner can create and read their passage", async () => {
    await assertSucceeds(alice.doc("users/alice/passages/p1").set(passage));
    await assertSucceeds(alice.doc("users/alice/passages/p1").get());
  });
  await t("another signed-in user cannot read it", () => assertFails(bob.doc("users/alice/passages/p1").get()));
  await t("another user cannot write into someone else's space", () => assertFails(bob.doc("users/alice/passages/p2").set(passage)));
  await t("another user cannot delete it", () => assertFails(bob.doc("users/alice/passages/p1").delete()));
  await t("signed-out visitors cannot read", () => assertFails(anon.doc("users/alice/passages/p1").get()));
  await t("signed-out visitors cannot write", () => assertFails(anon.doc("users/anon/passages/p1").set(passage)));
  await t("passage text over 20,000 characters is rejected", () => assertFails(alice.doc("users/alice/passages/big").set({ ...passage, text: "가".repeat(20001) })));
  await t("passage with an unexpected field is rejected", () => assertFails(alice.doc("users/alice/passages/x").set({ ...passage, isAdmin: true })));
  await t("passage with a non-string text is rejected", () => assertFails(alice.doc("users/alice/passages/x").set({ ...passage, text: 5 })));
  await t("passage with a null title is accepted", () => assertSucceeds(alice.doc("users/alice/passages/n").set({ ...passage, title: null })));
  await t("saved item: valid kind accepted, bad kind rejected", async () => {
    await assertSucceeds(alice.doc("users/alice/saved/vocab_1").set({ kind: "vocab", ref_id: 1, sentence: null, item: { headword: "사과" }, t: 1 }));
    await assertSucceeds(alice.doc("users/alice/saved/word_x").set({ kind: "word", ref_id: null, text: "먹었어요", sentence: "저는 먹었어요.", item: null, t: 1 }));
    await assertFails(alice.doc("users/alice/saved/bad").set({ kind: "weird", ref_id: 1, t: 1 }));
    await assertFails(alice.doc("users/alice/saved/extra").set({ kind: "word", text: "x", surprise: 1, t: 1 }));
  });
  await t("saved item of another user is private", () => assertFails(bob.doc("users/alice/saved/vocab_1").get()));
  await t("study documents: owner read/write ok, others denied", async () => {
    await assertSucceeds(alice.doc("users/alice/study/meta").set({ read: {}, questions: {} }));
    await assertSucceeds(alice.doc("users/alice/study/cards_3").set({ cards: { "vocab:1": { kind: "vocab" } } }, { merge: true }));
    await assertFails(bob.doc("users/alice/study/meta").get());
    await assertFails(anon.doc("users/alice/study/meta").get());
  });
  await t("collection query on one's own space works; on another's does not", async () => {
    await assertSucceeds(alice.collection("users/alice/passages").get());
    await assertFails(bob.collection("users/alice/passages").get());
  });
  await t("any other path is closed, even for signed-in users", async () => {
    await assertFails(alice.doc("public/anything").set({ a: 1 }));
    await assertFails(alice.doc("users/alice").set({ a: 1 }));
    await assertFails(alice.doc("users/alice/other/x").set({ a: 1 }));
  });

  await env.cleanup();
  console.log(failed ? `${failed} FAILED` : "ALL RULES TESTS PASSED");
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error("ERROR", e); process.exit(1); });
