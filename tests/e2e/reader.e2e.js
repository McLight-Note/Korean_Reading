const { chromium } = require("playwright");
// Reader UI in a real browser, with Google Translate mocked. Needs the read-only app on :8768:
//   KR_READ_ONLY=1 KR_DB_PATH=deploy/app.sqlite .venv/bin/uvicorn backend.app.main:app --port 8768
//   node tests/e2e/reader.e2e.js [baseUrl]   (screenshots go to tests/e2e/shots/, which is gitignored)
const BASE = process.argv[2] || "http://localhost:8768";
const SHOTS = __dirname + "/shots";
require("fs").mkdirSync(SHOTS, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errors = [], gtCalls = [];
  page.on("pageerror", e => errors.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text()); });
  await page.route("https://translate.googleapis.com/**", route => {
    const u = new URL(route.request().url());
    gtCalls.push({ tl: u.searchParams.get("tl"), q: u.searchParams.get("q") });
    route.fulfill({ contentType: "application/json", body: JSON.stringify([[["[" + u.searchParams.get("tl") + "] " + u.searchParams.get("q"), u.searchParams.get("q")], [null, null, "romaja"]], [["noun", ["alt1", "alt2"]]]]) });
  });
  const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) process.exitCode = 1; };

  await page.goto(BASE);
  await page.waitForSelector("#stories-list article.story");
  const cards = await page.locator("#stories-list article.story").count();
  ok(cards >= 15, "stories list shows " + cards + " entries");
  await page.screenshot({ path: SHOTS + "/1-list.png" });

  // open first story
  await page.locator("#stories-list button[data-story]").first().click();
  await page.waitForSelector("#text .w");
  ok((await page.locator("#text .h.hv").count()) > 5 && (await page.locator("#text .h.hg").count()) > 2, "vocab and grammar highlight spans present");
  // colour only: no background, border or padding on highlight spans
  const style = await page.evaluate(() => {
    const out = {};
    for (const sel of [".h.hv", ".h.hg"]) {
      const el = document.querySelector("#text " + sel), cs = getComputedStyle(el);
      out[sel] = { color: cs.color, bg: cs.backgroundColor, border: cs.borderTopWidth, pad: cs.paddingLeft, deco: cs.textDecorationLine };
    }
    out.plain = (() => { const cs = getComputedStyle(document.querySelector("#text .w:not(.h)") || document.querySelector("#text")); return cs.color; })();
    return out;
  });
  console.log(JSON.stringify(style));
  ok(style[".h.hv"].bg === "rgba(0, 0, 0, 0)" && style[".h.hg"].bg === "rgba(0, 0, 0, 0)", "no background boxes");
  ok(style[".h.hv"].border === "0px" && style[".h.hg"].pad === "0px", "no borders/padding");
  ok(style[".h.hv"].color !== style[".h.hg"].color, "vocab and grammar have different colours");
  await page.screenshot({ path: SHOTS + "/2-reader.png" });

  // click a vocab word -> side panel with Google translation
  await page.locator("#text .h.hv").first().click();
  await page.waitForFunction(() => /\[en\]/.test(document.querySelector("#detail").innerText), null, { timeout: 5000 }).catch(() => {});
  const panel = await page.locator("#detail").innerText();
  ok(/\[en\]/.test(panel), "side panel shows the (mock) Google translation: " + panel.slice(0, 80).replace(/\n/g, " | "));
  ok(await page.locator("#detail a[href*='translate.google.com']").count() > 0, "fallback link to translate.google.com");
  await page.screenshot({ path: SHOTS + "/3-panel.png" });

  // click a grammar span
  await page.locator("#text .h.hg").first().click();
  await page.waitForTimeout(400);
  const gpanel = await page.locator("#detail").innerText();
  ok(/Grammar|grammar|\+/.test(gpanel), "grammar click shows textbook block: " + gpanel.slice(0, 100).replace(/\n/g, " | "));
  await page.screenshot({ path: SHOTS + "/4-grammar.png" });

  // an unmarked word is also clickable
  await page.locator("#text .w:not(.h)").first().click();
  await page.waitForTimeout(300);
  ok(/\[en\]/.test(await page.locator("#detail").innerText()), "plain word click translates too");

  // language switch -> Uzbek
  await page.selectOption("#lang", "uz");
  await page.locator("#text .h.hv").nth(1).click();
  await page.waitForTimeout(400);
  ok(gtCalls.some(c => c.tl === "uz"), "language selector switches the target language to uz");
  ok(!/\[en\]/.test(await page.locator("#detail").innerText()), "panel now Uzbek");
  await page.selectOption("#lang", "en");

  // story box + questions
  const box = await page.locator("#story-box").innerText();
  ok(box.length > 50, "story box (targets, questions) present");
  await page.screenshot({ path: SHOTS + "/5-storybox.png", fullPage: true });

  // pasted text gets approximate lookup colouring
  await page.click("#tabs [data-tab=reader], #tabs button:has-text('Reader')");
  await page.fill("#new-text", "저는 영화를 봤어요. 친구와 같이 한국어를 공부했어요. 동아리에 가입하고 싶어요.");
  await page.click("#btn-open");
  await page.waitForFunction(() => document.querySelector("#p-title").textContent !== "Pick a story or paste a text" && document.querySelector("#text").textContent.startsWith("저는"));
  await page.waitForTimeout(500);
  const hv = await page.locator("#text .h.hv").count();
  ok(hv >= 2, "pasted text: " + hv + " words coloured by textbook lookup");
  await page.screenshot({ path: SHOTS + "/6-pasted.png" });

  // saving a word, then flashcards
  await page.locator("#text .h.hv").first().click();
  await page.waitForSelector("#detail button:has-text('Save')");
  await page.click("#detail button:has-text('Save')");
  await page.click("#tabs button:has-text('Saved')");
  await page.waitForTimeout(500);
  ok(await page.locator("#s-table tbody tr").count() >= 1, "saved word appears in Saved tab");
  await page.click("#tabs button:has-text('Study')");
  await page.waitForTimeout(400);
  await page.screenshot({ path: SHOTS + "/7-study.png" });

  // other tabs render without JS errors
  for (const t of ["Vocabulary", "Grammar", "Workbook", "Status"]) {
    await page.click(`#tabs button:has-text('${t}')`);
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: SHOTS + "/8-status.png" });
  ok(await page.locator("#tabs button:has-text('Review')").count() === 0 || !(await page.locator("#tabs button:has-text('Review')").isVisible()), "Review tab hidden in read-only");

  // mobile
  await page.setViewportSize({ width: 390, height: 800 });
  await page.click("#tabs button:has-text('Stories')");
  await page.waitForTimeout(300);
  const sw = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  ok(sw <= 1, "no horizontal scroll on phone width (" + sw + ")");

  console.log("GT calls:", gtCalls.length, " errors:", errors.length);
  errors.forEach(e => console.log("  ", e));
  if (errors.length) process.exitCode = 1;
  await browser.close();
})();
