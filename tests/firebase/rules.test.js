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
  // stories are written by the publish script (admin SDK, bypasses rules): simulate that here
  await env.withSecurityRulesDisabled(async ctx => {
    await ctx.firestore().doc("stories/s1").set({ level: "3A", title: "t", text: "가나다" });
  });

  await t("stories: signed-out visitors can read the list and a story", async () => {
    await assertSucceeds(anon.doc("stories/s1").get());
    await assertSucceeds(anon.collection("stories").get());
  });
  await t("stories: nobody can create, change or delete them from the website", async () => {
    for (const who of [anon, alice]) {
      await assertFails(who.doc("stories/s2").set({ title: "x" }));
      await assertFails(who.doc("stories/s1").update({ title: "hacked" }));
      await assertFails(who.doc("stories/s1").delete());
    }
  });

  await t("read list: owner can mark, read and unmark", async () => {
    await assertSucceeds(alice.doc("users/alice/read/s1").set({ t: 1700000000000 }));
    await assertSucceeds(alice.doc("users/alice/read/s1").get());
    await assertSucceeds(alice.collection("users/alice/read").get());
    await assertSucceeds(alice.doc("users/alice/read/s1").delete());
  });
  await t("read list: another user cannot read, write or delete it", async () => {
    await assertSucceeds(alice.doc("users/alice/read/s1").set({ t: 1 }));
    await assertFails(bob.doc("users/alice/read/s1").get());
    await assertFails(bob.collection("users/alice/read").get());
    await assertFails(bob.doc("users/alice/read/s9").set({ t: 1 }));
    await assertFails(bob.doc("users/alice/read/s1").delete());
  });
  await t("read list: signed-out visitors cannot read or write", async () => {
    await assertFails(anon.doc("users/alice/read/s1").get());
    await assertFails(anon.doc("users/anon/read/s1").set({ t: 1 }));
  });
  await t("read list: only a numeric timestamp is accepted", async () => {
    await assertFails(alice.doc("users/alice/read/x").set({ t: "yesterday" }));
    await assertFails(alice.doc("users/alice/read/x").set({ t: 1, isAdmin: true }));
    await assertFails(alice.doc("users/alice/read/x").set({}));
  });
  await t("any other path is closed, even for signed-in users", async () => {
    await assertFails(alice.doc("public/anything").set({ a: 1 }));
    await assertFails(alice.doc("users/alice").set({ a: 1 }));
    await assertFails(alice.doc("users/alice/passages/x").set({ a: 1 }));
    await assertFails(alice.doc("users/alice/study/meta").get());
  });

  await env.cleanup();
  console.log(failed ? `${failed} FAILED` : "ALL RULES TESTS PASSED");
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error("ERROR", e); process.exit(1); });
