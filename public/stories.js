"use strict";
/* Reading stories: a list, and a story opened in the reader with its target words/grammar coloured.
   Stories are written for this app (not textbook content); their colouring comes from the markup in the story file and
   their targets are resolved against the textbook database. Uses globals from app.js / study.js. */

let STORIES = null;

async function loadStories() {
  if (!STORIES) STORIES = (await api("/stories")).stories;
  let read = {};
  try { await stLoad(); read = ST.read || {}; } catch { /* progress unavailable: just don't show ticks */ }
  const level = $("#sf-level").value;
  const list = STORIES.filter(s => !level || s.level === level);
  const byLevel = {};
  list.forEach(s => (byLevel[s.level] = byLevel[s.level] || []).push(s));
  $("#stories-list").innerHTML = Object.entries(byLevel).map(([lvl, items]) => `
    <h3 class="lvl">${h(lvl)} <small class="muted">${items.length} stories</small></h3>
    <div class="storygrid">${items.map(s => `
      <article class="story">
        <header><b class="ko">${h(s.title)}</b>${read["story:" + s.id] ? ` <span class="chip s-VERIFIED">✓ read</span>` : ""}</header>
        <p class="muted">${h(s.theme || "")} · units ${h((s.units || []).join(", "))} · ${s.chars} characters</p>
        <p class="muted">${s.n_grammar} grammar patterns · ${s.n_vocab} words to learn</p>
        <details><summary class="lbl">English summary</summary><p>${h(s.summary_en)}</p></details>
        <button class="primary" data-story="${h(s.id)}">Read</button>
      </article>`).join("")}</div>`).join("") || `<p class="muted">No stories for this level.</p>`;
  $$("#stories-list button[data-story]").forEach(b => b.onclick = () => openStory(b.dataset.story));
}
$("#sf-level").onchange = () => loadStories().catch(e => showError(e.message));

async function openStory(id) {
  let d;
  try { d = await api("/stories/" + id); } catch (e) { return showError("could not open the story: " + e.message); }
  $('#tabs button[data-tab="reader"]').click();
  showReading({ id: "story:" + id, storyId: id, title: d.title, text: d.text, highlights: d.highlights, story: d });
  renderStoryBox(d);
  window.scrollTo({ top: 0 });
}

function renderStoryBox(d) {
  const box = $("#story-box");
  const vocabRows = d.target_vocab.map((t, i) => {
    const e = t.entry;
    return e ? `<tr class="clickable" data-v="${i}"><td class="ko"><b>${h(e.headword.replace(/\([^)]*\)/g, ""))}</b></td><td class="muted">${h(e.level)} u${h(e.unit ?? "?")}</td></tr>`
      : `<tr><td class="ko">${h(t.target)}</td><td class="muted">not in the glossary</td></tr>`;
  }).join("");
  const gramRows = d.target_grammar.map((t, i) => {
    const g = t.item;
    return g ? `<tr class="clickable" data-g="${i}"><td class="ko">${h(g.pattern)}</td><td class="muted">${h(g.level)}${g.unit ? " u" + g.unit : ""}${g.status === "needs_review" ? " · unreviewed" : ""}</td></tr>`
      : `<tr><td class="ko">${h(t.target)}</td><td class="muted">not in the grammar database</td></tr>`;
  }).join("");
  box.innerHTML = `
    <h3>📖 ${h(d.title)} <span class="chip">${h(d.level)}</span></h3>
    <p class="muted">Written for this app to practise the words and grammar below; it is not textbook content. <span class="vtxt">Green</span> = a word to learn, <span class="gtxt">orange</span> = grammar to learn. Click any word in the text for its translation, or click a row below.</p>
    <details><summary class="lbl">English summary</summary><p>${h(d.summary_en)}</p></details>
    <div class="twocol">
      <div><h4>Words to learn (${d.target_vocab.length})</h4><table class="grid"><tbody>${vocabRows}</tbody></table></div>
      <div><h4>Grammar to learn (${d.target_grammar.length})</h4><table class="grid"><tbody>${gramRows}</tbody></table></div>
    </div>
    <p><button id="story-add-all" class="primary">Add all to my flashcards</button> <span id="story-add-msg" class="muted"></span></p>
    <h4>Questions</h4>
    <ol class="qa-list">${d.questions.map((q, i) => `<li><span class="ko">${h(q.q)}</span> <button data-qa="${i}">Show answer</button><div class="qa-ans ko" id="sqa${i}" hidden>${h(q.a)}</div></li>`).join("")}</ol>`;
  box.hidden = false;
  $$("#story-box button[data-qa]").forEach(b => b.onclick = () => { $("#sqa" + b.dataset.qa).hidden = false; b.hidden = true; });
  $$("#story-box tr[data-v]").forEach(tr => tr.onclick = () => {
    const e = d.target_vocab[+tr.dataset.v].entry, word = e.headword.replace(/\([^)]*\)/g, "");
    const hl = d.highlights.find(x => x.kind === "vocab" && x.ref === d.target_vocab[+tr.dataset.v].target);
    showPanel({ word, sentence: hl ? sentenceAround(d.text, hl.start) : "", kind: "vocab", entry: e, item: null, phrase: null });
  });
  $$("#story-box tr[data-g]").forEach(tr => tr.onclick = () => {
    const t = d.target_grammar[+tr.dataset.g];
    const hl = d.highlights.find(x => x.kind === "grammar" && x.ref === t.target);
    showPanel({ word: t.item.pattern, sentence: hl ? sentenceAround(d.text, hl.start) : "", kind: "grammar", item: t.item, entry: null, target: t.target, phrase: null, noTranslate: true });
  });
  $("#story-add-all").onclick = async ev => {
    ev.target.disabled = true;
    let n = 0;
    try {
      for (const t of d.target_vocab) if (t.entry) { await store.saved.add({ kind: "vocab", ref_id: t.entry.id, item: { headword: t.entry.headword, level: t.entry.level, unit: t.entry.unit } }); n++; }
      for (const t of d.target_grammar) if (t.item) { await store.saved.add({ kind: "grammar", ref_id: t.item.id, item: { headword: t.item.pattern, level: t.item.level, unit: t.item.unit } }); n++; }
      $("#story-add-msg").textContent = `${n} items added. Open Study → Flashcards to review them.`;
    } catch (e) { showError(e.message); ev.target.disabled = false; }
  };
}
