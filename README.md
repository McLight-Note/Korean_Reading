# Korean Reading — read stories, click a word, see the translation

A reading site built on your own 서울대 한국어 textbooks. It opens on **15 original reading stories** (levels 3A–4B) that practise the books' vocabulary and grammar. The words and grammar a story teaches are shown **in colour only** (green = word to learn, orange = grammar to learn). **Click any word** and the side panel shows its **Google Translate** translation, plus the matching glossary/grammar entry from your books when there is one.

```
PDFs → local OCR / text extraction → SQLite (words, grammar, examples, workbook) → web reader + Google Translate in the browser
```

## What it does

| Area | Notes |
|---|---|
| **Stories** (15, levels 3A–4B) | Written for this app, not textbook content. Targets are coloured; summary and comprehension questions under the text; "add all to flashcards". |
| **Reader** | Paste any Korean text. Words found in your textbooks' word list are coloured green (approximate matching, see below). Every word is clickable. |
| **Side panel** | Google translation of the word, of the highlighted phrase and of the whole sentence; the textbook entry (level, unit, examples) when it exists; a Save button. |
| **Study** | Flashcards with spaced repetition (SM-2) from saved words or a level's word list/grammar; reading progress; your own comprehension questions. |
| **Vocabulary / Grammar** | Browse and search the imported glossary (~5,800 words) and grammar (~290 patterns with explanations and ~670 examples from the student books 3B, 4A, 4B). |
| **Workbook** | ~1,150 exercises and listening scripts from the workbooks 3A–4B (OCR draft; blanks stay blank, no answer key). |
| **Review** (local only) | Check OCR results next to the page image and approve them. |
| **Storage** | Your passages, saved words and progress live in your browser, or in your own account with Google sign-in ([FIREBASE.md](FIREBASE.md)). |

### Translation: how it works and what to know

- Translations come from **Google Translate**, requested **from your browser** (`public/translate.js`). There is no API key and the server never calls Google.
- It uses the keyless endpoint Google's own widgets use. It is **unofficial**: Google may rate-limit or change it. When it fails, the panel says so and links to translate.google.com.
- **What is sent to Google:** the word, phrase or sentence you click, and nothing else. Results are cached in your browser (`localStorage`, key `kr.gt`).
- The **Translate to** menu in the header chooses English (default), Uzbek, Russian or Turkish. The Uzbek glosses of the old glossary are no longer stored or shown anywhere; use that menu if you want Uzbek.
- The book data itself is stored as Korean headwords with level and unit only; meanings come from Google, never from the books' Uzbek column.

### What the textbook lookup can and cannot do

Pasted text is matched against the glossary by simple rules (a noun plus a particle, or a regular verb/adjective stem plus a common ending). It has **no morphological analyser**, so irregular forms (`봤어요`, `와요`, `들어요` …) and compounds are not recognised, and the legend says "approximate". Grammar patterns are **not** detected in pasted text. In the stories, the colours come from hand-written markup (below), which is exact.

## Requirements

- **macOS** only for the one-time PDF ingestion (Apple's built-in text extraction and Vision OCR, offline). The finished database and web app are not macOS-specific.
- **Python 3.11+** (developed on 3.13), **Xcode Command Line Tools** (`xcode-select --install`, for `swift`)
- Node.js only for the optional JS/e2e tests.

## 1. Install

```bash
cd Korean_Reading
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # requirements.txt alone (FastAPI) is the lean runtime set used by Vercel
```

Use the project's own `.venv`; every command below spells out `.venv/bin/…` so another active environment can't shadow it.

## 2. Put your textbooks in the project folder

The PDFs stay in the repo folder (git-ignored via `*.pdf`).

| File | Used for |
|---|---|
| `서울대 책 1a 부터 5b가지.pdf` | vocabulary glossary (headwords, level, unit) |
| `서울 대 grammatikka kitob.pdf` | scanned grammar index (patterns, level) |
| `3B SB.pdf`, `4A SB.pdf`, `4B SB.pdf` | student books (grammar explanations/examples) |
| `3A WB.pdf`, `3B WB.pdf`, `4A WB.pdf`, `4B WB.pdf` | workbooks |

## 3. Build the knowledge base (one time)

The database is created at `data/app.sqlite`. **Run the steps in this order**, because the student-book step joins its explanations to the grammar index.

```bash
.venv/bin/python -m backend.app.ingest.import_glossary "서울대 책 1a 부터 5b가지.pdf"
.venv/bin/python -m backend.app.ingest.import_grammar_index "서울 대 grammatikka kitob.pdf"

for b in "3B SB" "4A SB" "4B SB"; do swift backend/app/ingest/vision_ocr.swift "$b.pdf" "data/ocr/${b// /_}"; done   # slow, resumable
for b in "3B SB" "4A SB" "4B SB"; do .venv/bin/python -m backend.app.ingest.import_student_book "$b.pdf"; done

for b in "3A WB" "3B WB" "4A WB" "4B WB"; do swift backend/app/ingest/vision_ocr.swift "$b.pdf" "data/ocr/${b// /_}"; done
for b in "3A WB" "3B WB" "4A WB" "4B WB"; do .venv/bin/python -m backend.app.ingest.import_workbook "$b.pdf"; done
```

- OCR takes roughly 10–15 minutes per book and is **resumable** (pages with a `.json` in `data/ocr/<book>/` are skipped). Add two numbers to OCR a page range: `swift … "4A SB.pdf" data/ocr/4A_SB 148 247`.
- A first import refuses to run twice; re-running needs `--force`. `import_glossary --force` replaces all vocabulary and discards manual edits; `import_grammar_index --force` and `import_student_book --force` keep items you corrected (`corrected=1`). After `import_grammar_index --force`, re-run the student-book and workbook steps.
- Everything imported from scans is `needs_review` until you approve it in the **Review** tab.
- **No Uzbek is kept.** The importers read the Uzbek column only to find where an entry ends and store the Korean headword, level, unit and page.
- **Already have a database from the older (Uzbek/Kiwi) version?** Run `.venv/bin/python scripts/maintenance.py drop-uzbek`. It backs the database up to `data/app.sqlite.before-uzbek-removal`, clears the Uzbek meanings, the OCR text of the glossary and index pages, and the old analysis tables, then vacuums. (The raw OCR JSON under `data/ocr/` still contains the Uzbek source text; it is never served and is git-ignored.)

## 4. Run the app

```bash
.venv/bin/uvicorn backend.app.main:app --port 8765
```

Open http://localhost:8765. Add `--reload` while developing.

> **The local app has no login** (it has edit, delete and re-import endpoints). Keep the default `127.0.0.1` binding; don't use `--host 0.0.0.0` on a shared network. The deployed Vercel edition is read-only.

## 5. Stories

The 15 stories live in `content/stories/*.json` (3 × 3A, 4 × 3B, 4 × 4A, 4 × 4B). Each lists its `target_vocab` and `target_grammar` and marks them **inline in the text**:

```
저는 [[동아리를|동아리]] 찾았지만 <<싶지만|V+고 싶다>> …
```

- `[[shown text|glossary headword]]` colours a word to learn; `<<shown text|grammar pattern>>` colours a grammar point. The marks are removed when the story is loaded, so no analysis runs in the browser or on the server.
- Only whole words are coloured and marks never contain spaces; the checker enforces this.
- **Adding a story:** copy a file, keep the fields (`id` = file name, `level`, `title`, `text`, `target_grammar` = exact pattern strings from the Grammar tab, `target_vocab` = glossary headwords without the bracketed part, `questions`, `summary_en`), then run:

```bash
.venv/bin/python scripts/check_stories.py          # all stories (or: check_stories.py 4b)
```

It prints OK/!! per story: every target must be marked at least once, every mark must refer to a declared target, every target must exist in your database, marks must not overlap and no markup may be left over. `pytest` runs the same check for every story against `data/app.sqlite` (skipped when that file doesn't exist).

## 6. Using the site

1. **Stories** → *Read*. Click any word; the panel shows the Google translation of the word, the phrase it belongs to (for a coloured span) and its sentence, then the textbook entry. Press *Save* to keep a word or grammar point as a flashcard.
2. **Reader** → paste text → *Open to read*. Green words are in your textbooks' word list (approximate). Passages are saved in your browser/account; you can mark them as read and write your own comprehension questions.
3. **Study** → *Flashcards*: a session is every due card plus the number of new cards you choose (from saved items, or a level's word list/grammar). Grade Again / Hard / Good / Easy; the next review follows SM-2 (`backend/app/services/srs.py`). The answer side shows the Google translation of a word, or the book's explanation and examples for grammar.
4. **Grammar / Vocabulary / Workbook** tabs: search and browse; the local app can also edit and add entries by hand.
5. **Review** tab (local only): page image next to the editable fields. Fix, then *Save & approve*.

### What was removed

The earlier version analysed pasted text with the Kiwi morphological analyser. That is gone on purpose, together with what depended on it: automatic grammar detection in pasted text, generated grammar/vocabulary exercises, workbook answer checking, the calibration report, and all Uzbek meanings. The reader now relies on the stories' hand-written colours, Google Translate and the textbooks' own entries.

## 7. Tests

```bash
.venv/bin/python -m pytest -q                       # backend, importers, stories, lookup, deploy-DB builder
node --test tests/js/*.test.js                      # Google-response parser, study-data splitting
npm --prefix tests/firebase install                 # once
npx firebase-tools@13.35.1 emulators:exec --only firestore --project demo-kr "cd tests/firebase && node rules.test.js"
```

Real-browser end-to-end tests (Playwright; Google Translate is **mocked** so they never contact Google):

```bash
npm --prefix tests/e2e install && (cd tests/e2e && npx playwright install chromium)    # once
KR_READ_ONLY=1 KR_DB_PATH=deploy/app.sqlite .venv/bin/uvicorn backend.app.main:app --port 8768 &
node tests/e2e/reader.e2e.js                        # stories, colours-only check, side panel, language menu, lookup, saved words, phone width
npx firebase-tools@13.35.1 emulators:exec --only auth,firestore --project demo-kr "node tests/e2e/firebase.e2e.js http://localhost:8768"
```

`tests/test_no_external_ai.py` fails if an AI SDK or key appears anywhere, if the server makes an outbound request, or if any front-end file other than the Firebase/Google ones names a remote host.

## Project layout

```
backend/app/
  main.py  config.py  db.py  schema.sql  deps.py
  services/   common.py  lookup.py  stories.py  srs.py
  routers/    vocab  grammar  admin  workbook  study  stories  misc
  ingest/     glossary_parser  grammar_index_parser  sb_grammar_parser
              import_glossary  import_grammar_index  import_student_book  wb_parser  import_workbook
              vision_ocr.swift  pdf_text.swift
content/stories/   the 15 stories (JSON with inline markup)
public/       index.html  app.js  stories.js  study.js  store.js  studydocs.js  translate.js  firebase-config.js  styles.css
app.py        Vercel entrypoint
scripts/      build_deploy_db.py  check_stories.py  maintenance.py
deploy/       app.sqlite — slim read-only DB for Vercel (git-ignored, built by the script)
data/         app.sqlite, OCR JSON + page images   (git-ignored)
tests/
```

## Troubleshooting

- **`swift: command not found`**: run `xcode-select --install`.
- **Import says "already imported"**: re-run with `--force` (read the notes in step 3 first).
- **Grammar items have no explanation**: only 3B, 4A and 4B have student books here; other levels have just the pattern from the scanned index.
- **The panel says it couldn't reach Google Translate**: you are offline, a blocker stops the request, or Google rate-limited you. Use the link under the message, or try again later.
- **A pasted word isn't coloured**: the lookup is approximate (irregular forms are missed). It is still clickable and translates.
- **Start over**: stop the server, delete `data/app.sqlite`, repeat step 3. OCR output in `data/ocr/` is reused.
- **Back up** `data/app.sqlite` before big re-imports; it holds your corrections.

## 8. Deploy to Vercel (public, read-only)

> The full guide (verification, rollback, troubleshooting) is **[DEPLOYMENT.md](DEPLOYMENT.md)**. Short version:

The deployed site serves the textbook data and stories read-only; every visitor's passages, saved words and progress stay in their own browser (or their own Google account, see [FIREBASE.md](FIREBASE.md)). Write and admin endpoints return 403.

```bash
.venv/bin/python scripts/build_deploy_db.py     # data/app.sqlite -> deploy/app.sqlite (~1.7 MB: no OCR pages, no Uzbek, no personal data)
npx vercel@latest link --yes --project korean-reading
npx vercel@latest git disconnect --yes          # `link` connects the GitHub repo; keep it disconnected (the DB is git-ignored)
npx vercel@latest deploy --prod --yes
```

- `deploy/app.sqlite` is **git-ignored on purpose** (text extracted from your textbooks), so deploy with the CLI, not from a Git push.
- The production URL is open to anyone with the link; per-deployment URLs sit behind Vercel's Deployment Protection.
- Without Kiwi the function is tiny (FastAPI + SQLite only), so cold starts are fast.
- Test the same mode locally: `KR_READ_ONLY=1 .venv/bin/uvicorn backend.app.main:app`.

**Copyright:** the deployed database contains Korean vocabulary and grammar text extracted from your textbooks. A public URL makes it readable by anyone; check that this is acceptable. PDFs, page images and raw OCR text are not deployed. The stories are your own content.

## Privacy

Locally, everything runs on your machine. The only outside request the site makes is the browser's call to Google Translate for the text you click (and Firebase, if you enable sign-in). The PDFs, database and OCR output are git-ignored.
