// End-to-end in a REAL browser (headless Chromium): the site + the real Firebase SDK + the Auth/Firestore emulators.
// Google Translate is mocked, so this never contacts Google. Run it through the emulators (see the README, "Tests"):
//   npx firebase-tools@13.35.1 emulators:exec --only auth,firestore --project demo-kr "bash tests/e2e/run-site.sh"
// One-time: npm --prefix tests/e2e install && (cd tests/e2e && npx playwright install chromium)
const { chromium } = require("playwright");
const fs = require("fs");
const base = process.argv[2];
const SHOTS = __dirname + "/shots";
fs.mkdirSync(SHOTS, { recursive: true });
const results = [];
const check = (name, ok, extra = "") => { results.push(!!ok); console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "   " + extra : "")); };
const consoleErrors = [];
const gtCalls = [];

const FIREBASE = { apiKey: "fake", authDomain: "localhost", projectId: "demo-kr", appId: "1:1:web:1",
  emulator: { auth: "http://127.0.0.1:9099", firestore: ["127.0.0.1", 8080] } };

async function device(browser, { firebase = true, viewport = { width: 1280, height: 700 } } = {}) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  page.on("pageerror", e => consoleErrors.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error" && !/PERMISSION_DENIED|permission-denied|Missing or insufficient/.test(m.text())) consoleErrors.push("console: " + m.text().slice(0, 160)); });
  await page.route("https://translate.googleapis.com/**", route => {
    const u = new URL(route.request().url());
    gtCalls.push(u.searchParams.get("tl"));
    route.fulfill({ contentType: "application/json", body: JSON.stringify([[["(" + u.searchParams.get("tl") + ") " + u.searchParams.get("q"), u.searchParams.get("q")]], null]) });
  });
  if (firebase) await page.addInitScript(cfg => { window.KR_FIREBASE = cfg; }, FIREBASE);
  await page.goto(base + "/");
  if (firebase) await page.waitForSelector("#stories-list article.story", { timeout: 30000 });
  return page;
}
const signIn = async (page, sub) => {
  await page.evaluate(async sub => {
    const cred = firebase.auth.GoogleAuthProvider.credential(JSON.stringify({ sub, email: sub + "@example.com", email_verified: true }));
    await firebase.auth().signInWithCredential(cred);
  }, sub);
  await page.waitForFunction(() => window.krState.user, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
};
const adminList = async path => {
  const r = await fetch(`http://127.0.0.1:8080/v1/projects/demo-kr/databases/(default)/documents/${path}`, { headers: { Authorization: "Bearer owner" } });
  return ((await r.json()).documents || []).map(d => d.name.split("/").pop());
};
const progress = page => page.textContent("#progress");

(async () => {
  const browser = await chromium.launch();

  // ---- without a Firebase config the page explains what to do ----
  const N = await device(browser, { firebase: false });
  check("no Firebase config: friendly setup message, no crash", /Firebase is not set up yet/.test(await N.textContent("#stories-list")));

  // ---- device A, signed out ----
  const A = await device(browser);
  const nStories = await A.locator("#stories-list article.story").count();
  check("the 15 published stories are listed for a signed-out visitor", nStories === 15, `${nStories}`);
  check("progress starts at 0 read", /^0 of 15/.test(await progress(A)));
  check("only the story reader is on the page (no other tabs)", (await A.locator("nav, #tabs").count()) === 0);
  const order = await A.locator("#stories-list h3.lvl").allTextContents();
  check("stories are grouped by level in order", order.map(t => t.split(" ")[0]).join(",") === "3A,3B,4A,4B", order.join(" | "));
  await A.selectOption("#f-level", "4B");
  check("level filter", (await A.locator("#stories-list article.story").count()) === 4);
  await A.selectOption("#f-level", "");
  await A.screenshot({ path: SHOTS + "/site-1-list.png" });

  await A.locator("#stories-list a.go").first().click();
  await A.waitForSelector("#text .w");
  const storyId = decodeURIComponent((await A.evaluate(() => location.hash)).replace("#/story/", ""));
  check("opening a story shows coloured words and grammar", (await A.locator("#text .h.hv").count()) > 5 && (await A.locator("#text .h.hg").count()) > 2);
  const css = await A.evaluate(() => {
    const out = {};
    for (const sel of [".h.hv", ".h.hg"]) { const cs = getComputedStyle(document.querySelector("#text " + sel)); out[sel] = { bg: cs.backgroundColor, b: cs.borderTopWidth, pad: cs.paddingLeft, color: cs.color }; }
    return out;
  });
  check("colour only: no background, border or padding", css[".h.hv"].bg === "rgba(0, 0, 0, 0)" && css[".h.hg"].bg === "rgba(0, 0, 0, 0)" && css[".h.hv"].b === "0px" && css[".h.hg"].pad === "0px");
  check("word and grammar colours differ", css[".h.hv"].color !== css[".h.hg"].color);

  await A.locator("#text .h.hv").first().click();
  await A.waitForFunction(() => /\(en\)/.test(document.querySelector("#detail").innerText), null, { timeout: 8000 });
  check("click a word: Google translation (mocked) in the side panel", true);
  await A.locator("#text .h.hg").first().click();
  await A.waitForTimeout(300);
  check("click a grammar span: shows the textbook pattern", /Textbook pattern/.test(await A.textContent("#detail")));
  await A.locator("#text .w:not(:has(.h))").first().click();
  await A.waitForTimeout(300);
  check("a plain word translates too", /\(en\)/.test(await A.textContent("#detail")));
  await A.selectOption("#lang", "uz");
  await A.waitForTimeout(600);
  check("language menu re-translates in Uzbek", gtCalls.includes("uz") && /\(uz\)/.test(await A.textContent("#detail")));
  await A.selectOption("#lang", "en");
  await A.screenshot({ path: SHOTS + "/site-2-reader.png" });

  await A.locator("#below .chips button").first().click();
  await A.waitForTimeout(500);
  check("clicking a 'word to learn' chip jumps to it in the story and opens the panel", /Word to learn/.test(await A.textContent("#detail")));
  await A.click('#below [data-ans="0"]');
  check("question answers are hidden until asked", await A.locator("#ans0").isVisible());

  await A.click("#btn-read");
  await A.waitForSelector("#toast:not([hidden])");
  check("mark as read: saved in this browser", await A.evaluate(id => Object.keys(JSON.parse(localStorage.getItem("kr.read") || "{}")).includes(id), storyId));
  await A.click(".back");
  await A.waitForSelector("#view-list:not([hidden])");
  await A.waitForFunction(() => /^1 of 15/.test(document.querySelector("#progress").textContent), null, { timeout: 5000 }).catch(() => { });
  check("list shows 1 of 15 read and a ✓ badge", /^1 of 15/.test(await progress(A)) && (await A.locator("#stories-list .chip.ok").count()) === 1, `${await progress(A)} / badges: ${await A.locator("#stories-list .chip.ok").count()}`);
  await A.selectOption("#f-status", "unread");
  check("'not read yet' filter", (await A.locator("#stories-list article.story").count()) === 14);
  await A.selectOption("#f-status", "read");
  check("'read' filter", (await A.locator("#stories-list article.story").count()) === 1);
  await A.selectOption("#f-status", "");

  // ---- sign in: what this browser already knew is uploaded; the browser copy is kept ----
  await signIn(A, "alice");
  const uid = await A.evaluate(() => window.krState.user.uid);
  check("signed in: email shown", /alice@example.com/.test(await A.textContent("#auth-box")));
  check("the read story was uploaded to the account", (await adminList(`users/${uid}/read`)).join() === storyId);
  check("the browser copy was kept", await A.evaluate(() => Object.keys(JSON.parse(localStorage.getItem("kr.read") || "{}")).length === 1));

  // ---- reading to the end by scrolling adds the story to the read list automatically ----
  const second = await A.locator("#stories-list a.go").nth(1).getAttribute("href");
  const secondId = decodeURIComponent(second.replace("#/story/", ""));
  await A.goto(base + "/" + second);
  await A.waitForSelector("#text .w");
  await A.waitForTimeout(700);
  check("not marked just by opening", !(await A.evaluate(id => id in window.krState.read, secondId)));
  for (let i = 0; i < 12; i++) { await A.mouse.wheel(0, 350); await A.waitForTimeout(150); }
  await A.waitForFunction(id => id in window.krState.read, secondId, { timeout: 8000 }).catch(() => { });
  check("scrolling down to the end adds it to the read list automatically", await A.evaluate(id => id in window.krState.read, secondId));
  await A.waitForTimeout(1200);
  check("…and it is stored in Firestore", (await adminList(`users/${uid}/read`)).length === 2);

  // ---- device B: the same account elsewhere ----
  const B = await device(browser);
  await signIn(B, "alice");
  await B.waitForFunction(() => /^2 of 15/.test(document.querySelector("#progress").textContent), null, { timeout: 15000 }).catch(() => { });
  check("device B sees the same read list", /^2 of 15/.test(await progress(B)), await progress(B));
  await B.goto(base + "/#/story/" + storyId);
  await B.waitForSelector("#text .w");
  await B.waitForFunction(() => /Read \(click to undo\)/.test(document.querySelector("#btn-read").textContent), null, { timeout: 10000 });
  check("a story opened by a direct link shows it is read", true);
  await B.click("#btn-read");
  await B.waitForTimeout(1500);
  check("undo removes it from Firestore", (await adminList(`users/${uid}/read`)).join() === secondId);

  // ---- another account is isolated ----
  const C = await device(browser);
  await signIn(C, "bob");
  check("bob has an empty read list", /^0 of 15/.test(await progress(C)));
  const cross = await C.evaluate(async uid => firebase.firestore().collection(`users/${uid}/read`).get().then(() => "allowed", e => e.code), uid);
  check("security rules stop bob reading alice's read list (real SDK)", cross === "permission-denied", cross);
  const writeStory = await C.evaluate(async () => firebase.firestore().doc("stories/hack").set({ title: "x" }).then(() => "allowed", e => e.code));
  check("nobody can add stories from the website", writeStory === "permission-denied", writeStory);

  // ---- sign out ----
  await A.goto(base + "/");
  await A.waitForSelector("#auth-out");
  await A.click("#auth-out");
  await A.waitForFunction(() => !window.krState.user, null, { timeout: 8000 });
  await A.waitForTimeout(800);
  check("sign-out goes back to this browser's own read list", /^1 of 15/.test(await progress(A)), await progress(A));

  // ---- phone ----
  const P = await device(browser, { viewport: { width: 390, height: 800 } });
  await P.locator("#stories-list a.go").first().click();
  await P.waitForSelector("#text .w");
  const overflow = await P.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  check("phone: no horizontal scroll", overflow <= 1, `${overflow}px`);
  await P.locator("#text .h.hv").first().click();
  await P.waitForFunction(() => /\(en\)/.test(document.querySelector("#detail").innerText), null, { timeout: 8000 });
  const box = await P.locator("#detail").boundingBox();
  check("phone: the translation opens as a bottom sheet that is on screen", box && box.y >= 0 && box.y + box.height <= 801 && box.y > 300, JSON.stringify(box && { y: Math.round(box.y), h: Math.round(box.height) }));
  await P.screenshot({ path: SHOTS + "/site-3-phone.png" });
  await P.click("#p-close");
  check("phone: the sheet can be closed", !(await P.locator("#detail").isVisible()));

  console.log("BROWSER ERRORS:", consoleErrors.length ? consoleErrors : "none");
  check("no browser errors", consoleErrors.length === 0);
  await browser.close();
  console.log(results.every(Boolean) ? "ALL SITE E2E CHECKS PASSED" : "SOME CHECKS FAILED");
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch(e => { console.error("FAILED", e.message.split("\n").slice(0, 5).join(" | ")); process.exit(1); });
