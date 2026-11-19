# Korean Reading — a textbook-based reading and grammar platform

Paste a Korean passage and get its vocabulary and grammar highlighted, each tied to **your own 서울대 한국어 textbooks**. Analysis uses [Kiwi](https://github.com/bab2min/Kiwi) (`kiwipiepy`) locally. There is **no external AI, no API key, and no network call** at runtime. Anything the textbooks don't contain is shown as *not found*, never invented.

```
PDFs → local OCR / text extraction → SQLite knowledge base → Kiwi + rule-based matcher → web reader
```

## What works today

| Area | Status |
|---|---|
| Vocabulary glossary import (1A–5B, ~5,800 entries, Uzbek meanings) | ✅ |
| Scanned grammar-index import (OCR, ~320 patterns, Uzbek glosses) | ✅ needs review |
| Student-book grammar import (3B, 4A, 4B: explanations, examples, unit, page) | ✅ needs review |
| Reader: highlights, click for textbook panel, save words, add English meanings | ✅ |
| Vocabulary / Grammar browse + edit, Review tab (page image next to fields), calibration report | ✅ |
| Workbook import (3A, 3B, 4A, 4B: ~1,150 exercises + listening scripts), Workbook tab, exercises shown under their grammar item | ✅ OCR draft |
| Study tab: flashcards with spaced repetition (SM-2), generated exercises, workbook practice, statistics | ✅ |
| Reader: mark passages as read, your own comprehension questions | ✅ |
| CSV / JSON / DOCX / TXT upload importers | ⏳ not built yet |

## Requirements

- **macOS** for the one-time PDF ingestion. It uses Apple's built-in text extraction and Vision OCR (Korean + English), both offline. The finished database and the web app themselves are not macOS-specific.
- **Python 3.11+** (developed on 3.13)
- **Xcode Command Line Tools** (for the `swift` command): `xcode-select --install`
- Node.js is only used to syntax-check the frontend (optional).

No `brew install` is needed: Tesseract and poppler are not used.

## 1. Install

```bash
cd Korean_Reading
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # requirements.txt alone is the lean runtime set used by Vercel
```

Use the project's own `.venv` as above. A different Python environment already active in your shell can shadow it, which is why every command below spells out `.venv/bin/…`.

Check Kiwi works (it loads its model on first use):

```bash
.venv/bin/python -c "from kiwipiepy import Kiwi; print(Kiwi().tokenize('먹었습니다'))"
```

## 2. Put your textbooks in the project folder

The PDFs stay in the repo folder (they're git-ignored via `*.pdf`). Expected names:

| File | Used for |
|---|---|
| `서울대 책 1a 부터 5b가지.pdf` | vocabulary glossary |
| `서울 대 grammatikka kitob.pdf` | scanned grammar index |
| `3B SB.pdf`, `4A SB.pdf`, `4B SB.pdf` | student books (grammar explanations/examples) |
| `3A WB.pdf`, `3B WB.pdf`, `4A WB.pdf`, `4B WB.pdf` | workbooks (exercises and listening scripts) |

## 3. Build the knowledge base (one time)

The database is created at `data/app.sqlite`. **Run the steps in this order**, because the student-book step joins its explanations to the grammar index.

```bash
# 3a. Vocabulary (fast; the PDF has a clean text layer)
.venv/bin/python -m backend.app.ingest.import_glossary "서울대 책 1a 부터 5b가지.pdf"

# 3b. Scanned grammar index (OCRs 12 pages, about a minute)
.venv/bin/python -m backend.app.ingest.import_grammar_index "서울 대 grammatikka kitob.pdf"

# 3c. Student books: OCR first (slow, resumable), then import
swift backend/app/ingest/vision_ocr.swift "3B SB.pdf" data/ocr/3B_SB
swift backend/app/ingest/vision_ocr.swift "4A SB.pdf" data/ocr/4A_SB
swift backend/app/ingest/vision_ocr.swift "4B SB.pdf" data/ocr/4B_SB

.venv/bin/python -m backend.app.ingest.import_student_book "3B SB.pdf"
.venv/bin/python -m backend.app.ingest.import_student_book "4A SB.pdf"
.venv/bin/python -m backend.app.ingest.import_student_book "4B SB.pdf"

# 3d. Workbooks: OCR (resumable), then import. Run AFTER 3c so exercise headings can join to the grammar items.
for b in "3A WB" "3B WB" "4A WB" "4B WB"; do swift backend/app/ingest/vision_ocr.swift "$b.pdf" "data/ocr/${b// /_}"; done
for b in "3A WB" "3B WB" "4A WB" "4B WB"; do .venv/bin/python -m backend.app.ingest.import_workbook "$b.pdf"; done
```

Notes:

- **OCR takes a while** (roughly 10–15 minutes per book). It is **resumable**: pages that already have a `.json` in `data/ocr/<book>/` are skipped, so you can stop and restart. To OCR only a page range (1-based, inclusive), add two numbers: `swift … "4A SB.pdf" data/ocr/4A_SB 148 247`. The grammar appendix is near the end of each book (about PDF pages 240–260 in 3B, 148–247 in 4A, 134–233 in 4B).
- The first run of `swift …` is slow because it compiles the script.
- **Run the imports in this order, and repeat the later ones after an earlier `--force`.** `import_grammar_index --force` replaces the uncorrected grammar items, which also removes the explanations/examples the student-book import attached to them and detaches the workbook links. After it, re-run steps 3c and 3d.
- A first import refuses to run twice. Re-running needs `--force`:
  - `import_glossary --force` **replaces all vocabulary and discards manual edits to it.**
  - `import_grammar_index --force` and `import_student_book --force` re-import but **keep any item you corrected** (`corrected=1`).
- Everything imported from scans is `needs_review` until you approve it in the **Review** tab.
- **Workbooks** are stored exercise by exercise (`연습 N`, plus numbered questions in listening/reading/review sections) and the listening scripts page by page, all verbatim OCR: blanks stay blank, answers are **not** filled in, and the answer key (`모범 답안`) is not parsed. A grammar exercise is attached to the grammar item whose pattern matches its heading (the import prints any heading it could not join). `import_workbook --force` replaces that workbook's rows.

## 4. Run the app

```bash
.venv/bin/uvicorn backend.app.main:app --port 8765
```

Open http://localhost:8765. Add `--reload` while developing.

> **The local app has no login** (it has edit, delete and re-import endpoints). Keep the default `127.0.0.1` binding. Do not start it with `--host 0.0.0.0` on a shared network. The deployed Vercel edition is read-only, so it has no such endpoints.

## 5. Using it

1. **Reader**: paste a passage and click *Analyze with Kiwi*. Results are saved. Reopening a passage does **not** re-run Kiwi. Editing the text, or clicking *Re-analyze*, does.
   - Shaded = grammar, underlined = vocabulary. Colour shows confidence (green verified, amber likely, orange needs review). Grey dotted = not in the textbook.
   - Click a highlight for the textbook explanation, examples, level/unit/page, and the sentence where you met it. Missing English meanings can be typed in.
2. **Review tab**: work through `needs_review` items with the original page image beside the editable fields. Fix the pattern or explanation, remove examples that don't belong, then *Save & approve*. Only approved items can show as VERIFIED in the reader. After approving, click *Re-analyze* on a passage (the "database changed" banner reminds you).
3. **Workbook tab**: browse and search the exercises by level and section; *Analyze in reader* sends an exercise or a listening script to the reader. Grammar exercises also appear under the grammar item in the reader panel.
4. **Calibration report** (Review tab): runs every stored textbook example through the matcher and lists rules that miss their own examples, a quick way to find rules or notation to fix.
5. **Study tab** (works locally and on the deployed site; progress is stored in your local database, or in the browser when deployed):
   - *Flashcards*: a session = every card that is due + the number of new cards you choose, taken from your saved items or from a level's glossary/grammar. Grade yourself Again / Hard / Good / Easy; the next review date follows SM-2 (`backend/app/services/srs.py`). "Again" brings the card back in the same session.
   - *Exercises* (all labelled **Generated**, each showing the textbook record it was built from and whether that record is still an unreviewed OCR draft):
     grammar recognition (a textbook example sentence with the grammar blanked, pick the pattern; examples where the pattern occurs twice, or where a distractor would also fit, are skipped), and vocabulary Korean → Uzbek or Uzbek → Korean (reviewed glossary entries only). If a level doesn't have enough material you are told so; nothing is invented to fill the gap.
   - *Workbook practice*: an original workbook exercise (OCR draft) with an answer box per item. **Check** reports whether your answer uses the exercise's target grammar, using the same local detector as the reader. It cannot grade the rest of your sentence, and there is no answer key.
   - *Overview*: cards due, saved-but-unstudied items, young/mature cards, 30-day retention, streak, 14-day review chart, exercise accuracy, passages read.
   - *Comprehension questions* are only the ones you write under a passage; none are generated.
6. **Grammar / Vocabulary tabs**: search, edit, add items by hand. A new grammar item needs a `V+`/`A+`/`N+` prefix (for example `V+(으)ㄹ 수 있다`) to be auto-detected; the dialog has a *Test rule* box.

### Status labels

| Label | Meaning |
|---|---|
| FOUND IN TEXTBOOK | unambiguous match of an approved item |
| RELATED FORM | the textbook pattern with something inserted, e.g. a tense marker |
| POSSIBLE MATCH | matches, but the item is unreviewed or several items fit: verify it |
| NOT FOUND IN TEXTBOOK | a grammatical ending with no textbook item. No reference is shown |

## 6. Tests

```bash
.venv/bin/python -m pytest -q
```

Tests use temporary databases and don't touch `data/app.sqlite`. `tests/test_hardening.py` holds regressions for bugs found in code review (paging limits, input validation, UTF-16 offsets for emoji, importer guards, the deploy-DB builder). They also fail if an AI SDK or an outbound network call is added to the code.

## Project layout

```
backend/app/
  main.py  config.py  db.py  schema.sql  deps.py
  services/   korean_analyzer.py  vocabulary_matcher.py  grammar_matcher.py
              pattern_compiler.py  sentence_analyzer.py  calibration.py  srs.py  exercises.py
  routers/    passages  vocab  grammar  admin  workbook  study  misc
  ingest/     glossary_parser  grammar_index_parser  sb_grammar_parser
              import_glossary  import_grammar_index  import_student_book  wb_parser  import_workbook
              vision_ocr.swift  pdf_text.swift
public/       index.html  app.js  study.js  styles.css      (also the CDN root on Vercel)
app.py        Vercel entrypoint
scripts/      build_deploy_db.py
deploy/       app.sqlite — slim read-only DB for Vercel (git-ignored, built by the script)
data/         app.sqlite, OCR JSON + page images   (git-ignored)
tests/
```

## Troubleshooting

- **`ModuleNotFoundError: kiwipiepy`**: you're not using the project venv; run commands as `.venv/bin/python …`.
- **`swift: command not found`**: run `xcode-select --install`.
- **Import says "already imported"**: re-run with `--force` (read the warning in step 3 first).
- **Grammar items have no explanation**: only 3B, 4A and 4B have student books here. Levels 1A–3A, 5A and 5B have just the pattern and Uzbek gloss from the scanned index; add the rest by hand.
- **A grammar item shows "not auto-detectable"**: its notation (often from a handwritten or OCR-damaged index line) couldn't be compiled. Fix the pattern text in the Review tab.
- **Start over**: stop the server, delete `data/app.sqlite`, and repeat step 3. The OCR output in `data/ocr/` is reused, so only the imports re-run.
- **Back up** `data/app.sqlite` before big re-imports. It holds your corrections and saved words.

## 7. Deploy to Vercel (public, read-only)

> The full guide, with verification, rollback and troubleshooting, is in **[DEPLOYMENT.md](DEPLOYMENT.md)**. What follows is the short version.

Vercel can't keep a writable SQLite file, so the deployed site is **read-only**: it serves the textbook data and runs Kiwi on demand, but passages and saved words are kept in each visitor's browser (`localStorage`). All write and admin endpoints return 403. Editing, the Review tab and re-imports stay a local activity.

```bash
.venv/bin/python scripts/build_deploy_db.py     # data/app.sqlite -> deploy/app.sqlite (about 1.5 MB, no OCR pages, no personal data)
                                                 # add --include-workbook to also publish workbook exercises + listening scripts (off by default)
npx vercel@latest link --yes --project korean-reading
npx vercel@latest git disconnect --yes          # `link` connects the GitHub repo; see the warning below
npx vercel@latest deploy --prod --yes
```

- `deploy/app.sqlite` is **git-ignored on purpose** (it contains text extracted from the textbooks), so deploy with the CLI, not from a Git push. A Git-triggered build would have no database. Keep the GitHub integration disconnected.
- **Updating the site:** fix things locally (Review tab), re-run `build_deploy_db.py`, then `deploy --prod` again.
- The CLI must be a recent version (`npx vercel@latest` is fine; FastAPI needs ≥ 48.1.8).
- **Who can open it:** the production URL (e.g. `https://korean-reading-beta.vercel.app`) is **open to anyone** with the link. Vercel's Deployment Protection only covers the per-deployment URLs (`…-<hash>-….vercel.app`). To restrict the site instead: dashboard → project → Settings → Deployment Protection → enable *Vercel Authentication* for Production. To take it down: Settings → Delete project, or `npx vercel@latest remove korean-reading --confirm-name korean-reading`.
- The first request after idle time takes about 6 s while Kiwi loads. Analysis is capped at 8,000 characters per passage.
- Vercel always runs in read-only mode (it sets `VERCEL`). To test the same mode locally: `KR_READ_ONLY=1 .venv/bin/uvicorn backend.app.main:app`.

**Copyright:** the deployed database contains vocabulary and grammar text extracted from your textbooks. A public URL makes that readable by anyone, so check that this is acceptable to you. The PDFs, page images and raw OCR text are not deployed.

## Privacy

Locally, everything runs on your machine. Nothing leaves it except what you commit, push or deploy. The PDFs, database and OCR output are git-ignored.
