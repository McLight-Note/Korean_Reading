// End-to-end in a REAL browser (headless Chromium): the app + the real Firebase SDK + the Auth/Firestore emulators.
// Prerequisites: the read-only app running (KR_READ_ONLY=1 .venv/bin/uvicorn backend.app.main:app --port 8768) and, once:
//   npm --prefix tests/e2e install && (cd tests/e2e && npx playwright install chromium)
// Run (the emulators start, the test runs, they stop):
//   npx firebase-tools@13.35.1 emulators:exec --only auth,firestore --project demo-kr "node tests/e2e/firebase.e2e.js http://localhost:8768"
// (firebase-tools 13 needs Java 17; newer releases need Java 21.)
const { chromium } = require("playwright");
const base = process.argv[2];
const results = [];
const check = (name, ok, extra = "") => { results.push(!!ok); console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "   " + extra : "")); };
const consoleErrors = [];

const FIREBASE = { apiKey: "fake", authDomain: "localhost", projectId: "demo-kr", appId: "1:1:web:1",
  emulator: { auth: "http://127.0.0.1:9099", firestore: ["127.0.0.1", 8080] } };

async function device(browser) {
  const ctx = await browser.newContext();          // a separate browser profile = a separate device
  const page = await ctx.newPage();
  page.on("dialog", d => d.accept());
  page.on("pageerror", e => consoleErrors.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error" && !/PERMISSION_DENIED|permission-denied|Missing or insufficient/.test(m.text())) consoleErrors.push("console: " + m.text().slice(0, 160)); });
  await page.addInitScript(cfg => { window.KR_FIREBASE = cfg; }, FIREBASE);
  // Google Translate is mocked: the test must not depend on (or send anything to) the real service
  await page.route("https://translate.googleapis.com/**", route => {
    const q = new URL(route.request().url()).searchParams.get("q");
    route.fulfill({ contentType: "application/json", body: JSON.stringify([[["(en) " + q, q]], null]) });
  });
  await page.goto(base + "/");
  await page.waitForFunction(() => window.krStore && window.krStore.enabled, null, { timeout: 30000 });
  return page;
}
const signIn = async (page, sub) => {
  await page.evaluate(async sub => {
    const cred = firebase.auth.GoogleAuthProvider.credential(JSON.stringify({ sub, email: sub + "@example.com", email_verified: true }));
    await firebase.auth().signInWithCredential(cred);
  }, sub);
  await page.waitForFunction(() => window.krStore.kind === "cloud", null, { timeout: 30000 });
  await page.waitForTimeout(1500);
};
const adminList = async path => {
  const r = await fetch(`http://127.0.0.1:8080/v1/projects/demo-kr/databases/(default)/documents/${path}`, { headers: { Authorization: "Bearer owner" } });
  return (await r.json()).documents || [];
};
const openText = async (page, title, text) => {
  await page.click('#tabs button[data-tab="reader"]');          // the site opens on the Stories tab
  await page.fill("#new-title", title); await page.fill("#new-text", text); await page.click("#btn-open");
  await page.waitForFunction(t => document.querySelector("#p-title").textContent.includes(t) && document.querySelectorAll("#text .w").length > 0, title, { timeout: 30000 });
};
const clickWordAndSave = async page => {
  await page.locator("#text .w").first().click();
  await page.waitForSelector("#p-save"); await page.click("#p-save"); await page.waitForTimeout(800);
};
const tab = (page, name) => page.click(`#tabs button[data-tab="${name}"]`);

(async () => {
  const browser = await chromium.launch();
  const A = await device(browser);
  check("Firebase SDK loaded; signed-out visitors start in browser storage", await A.evaluate(() => krStore.enabled && krStore.kind === "local"));
  await A.waitForSelector("#auth-in", { timeout: 15000 });
  check("sign-in button is visible", await A.locator("#auth-in").isVisible());

  // ---- data created while signed out ----
  await openText(A, "made offline", "저는 어제 영화를 봤어요.");
  await A.locator("#text .w").first().click();
  await A.waitForFunction(() => /\(en\)/.test(document.querySelector("#detail").innerText), null, { timeout: 8000 });
  check("clicking a word shows the (mocked) Google translation in the side panel", true);
  await A.click("#p-save"); await A.waitForTimeout(500);
  check("signed-out data is in localStorage", await A.evaluate(() => JSON.parse(localStorage.getItem("kr.passages")).length === 1 && JSON.parse(localStorage.getItem("kr.saved")).length === 1));

  // ---- sign in as alice: migration of this browser's data ----
  await signIn(A, "alice");
  check("signed in: cloud backend active, email shown", await A.evaluate(() => krStore.kind === "cloud") && /alice@example.com/.test(await A.textContent("#auth-box")));
  const uidA = await A.evaluate(() => krStore.user.uid);
  await A.waitForTimeout(2500);
  const migrated = await adminList(`users/${uidA}/passages`);
  check("this browser's passage was uploaded to Firestore", migrated.length === 1 && /made offline/.test(JSON.stringify(migrated[0])), `${migrated.length} doc(s)`);
  check("saved word uploaded", (await adminList(`users/${uidA}/saved`)).length === 1);
  check("local copy was kept", await A.evaluate(() => JSON.parse(localStorage.getItem("kr.passages")).length === 1));

  // ---- work while signed in ----
  await tab(A, "reader");
  await openText(A, "cloud passage", "한국어를 공부하고 있어요. 비가 오잖아요.");
  const stored = await adminList(`users/${uidA}/passages`);
  check("2 passages stored (title + text only)", stored.length === 2 && !JSON.stringify(stored).includes("highlights"), `${stored.length} docs`);
  await A.locator("#text .w").nth(1).click(); await A.waitForSelector("#p-save"); await A.click("#p-save"); await A.waitForTimeout(800);
  await A.click("#btn-read"); await A.waitForTimeout(1000);
  await A.fill("#q-text", "무엇을 공부해요?"); await A.fill("#q-ans", "한국어"); await A.click("#q-add"); await A.waitForTimeout(1000);
  await tab(A, "study"); await A.click('#st-nav button[data-v="cards"]'); await A.click("#fc-start");
  await A.waitForSelector("#fc-show"); await A.click("#fc-show"); await A.locator("#fc-grades button").nth(2).click(); await A.waitForTimeout(2500);
  const ids = (await adminList(`users/${uidA}/study`)).map(d => d.name.split("/").pop()).sort();
  check("study progress stored as small documents", ids.includes("meta") && ids.some(i => i.startsWith("cards_")) && ids.some(i => i.startsWith("log_")), ids.join(", "));

  // ---- device B: fresh browser profile, same account ----
  const B = await device(browser);
  await signIn(B, "alice");
  check("device B is the same account", (await B.evaluate(() => krStore.user.uid)) === uidA);
  await B.waitForFunction(() => document.querySelectorAll("#passage-list li[data-id]").length === 2, null, { timeout: 15000 }).catch(() => { });
  check("device B lists both passages", (await B.locator("#passage-list li[data-id]").count()) === 2, (await B.locator("#passage-list li").allTextContents()).join(" | "));
  await tab(B, "reader");
  await B.locator("#passage-list li", { hasText: "cloud passage" }).click();
  await B.waitForFunction(() => document.querySelectorAll("#text .w").length > 0, null, { timeout: 30000 });
  check("device B opens the passage stored by device A", /한국어를 공부하고/.test(await B.textContent("#text")));
  check("device B shows read-state and your question", /Read/.test(await B.textContent("#btn-read")) && /무엇을 공부해요/.test(await B.textContent("#q-list")));
  await tab(B, "saved"); await B.waitForTimeout(1500);
  check("device B sees both saved items", (await B.locator("#s-table tbody tr").count()) === 2);
  await tab(B, "study"); await B.waitForTimeout(1500);
  const stats = await B.locator(".stat b").allTextContents();
  check("device B overview shows device A's review and says 'account'", stats[2] === "1" && /account/.test(await B.textContent("#st-body")), stats.join(" | "));

  // ---- two devices add different cards; nothing is lost ----
  await B.click('#st-nav button[data-v="cards"]');
  await B.selectOption("#fc-deck", "vocab"); await B.selectOption("#fc-level", "1A"); await B.fill("#fc-new", "2"); await B.click("#fc-start");
  for (let i = 0; i < 3; i++) { const ok = await B.waitForSelector("#fc-show", { timeout: 6000 }).then(() => true, () => false); if (!ok) break; await B.click("#fc-show"); await B.locator("#fc-grades button").nth(3).click(); await B.waitForTimeout(1500); }
  await A.waitForTimeout(500);
  await tab(A, "study"); await A.click('#st-nav button[data-v="home"]');
  const cardCount = docs => docs.filter(d => /cards_/.test(d.name)).reduce((n, d) => n + Object.keys(d.fields.cards?.mapValue?.fields || {}).length, 0);
  const total = cardCount(await adminList(`users/${uidA}/study`));
  check("cards from both devices coexist in Firestore", total >= 3, `${total} cards`);

  // ---- another account is isolated ----
  const C = await device(browser);
  await signIn(C, "bob");
  check("bob sees none of alice's data", (await C.locator("#passage-list li[data-id]").count()) === 0 && (await C.evaluate(() => krStore.user.uid)) !== uidA);
  const cross = await C.evaluate(async uid => firebase.firestore().collection(`users/${uid}/passages`).get().then(() => "read-allowed", e => e.code), uidA);
  check("security rules stop bob reading alice's passages (real SDK)", cross === "permission-denied", cross);

  // ---- delete + sign out ----
  await tab(A, "reader");
  await A.locator("#passage-list li", { hasText: "cloud passage" }).click();
  await A.waitForFunction(() => document.querySelector("#p-title").textContent.includes("cloud passage") && document.querySelectorAll("#text .w").length > 0, null, { timeout: 30000 });
  await A.click("#btn-delete"); await A.waitForTimeout(2500);
  const left = await adminList(`users/${uidA}/passages`);
  const meta = (await adminList(`users/${uidA}/study`)).find(d => /meta$/.test(d.name));
  check("delete removes the passage and its read-state/questions", left.length === 1 && !JSON.stringify(meta || {}).includes("무엇을 공부해요"));
  await A.click("#auth-out"); await A.waitForTimeout(2000);
  check("sign-out switches back to browser storage and hides cloud data", (await A.evaluate(() => krStore.kind)) === "local" && /made offline/.test(await A.textContent("#passage-list")));

  console.log("BROWSER ERRORS:", consoleErrors.length ? consoleErrors : "none");
  await browser.close();
  console.log(results.every(Boolean) ? "ALL FIREBASE E2E CHECKS PASSED" : "SOME CHECKS FAILED");
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch(e => { console.error("FAILED", e.message.split("\n").slice(0, 4).join(" | ")); process.exit(1); });
