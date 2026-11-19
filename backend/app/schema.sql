PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta(key, value) VALUES ('vocab_version', '1'), ('rules_version', '1');

CREATE TABLE IF NOT EXISTS source (
  id INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  level TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('glossary','grammar_index','student_book','workbook','import')),
  sha256 TEXT,
  note TEXT,
  imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(filename, kind)
);

-- Raw OCR / text-layer output per PDF page. Never edited; extracted records point back here.
CREATE TABLE IF NOT EXISTS ocr_page (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  pdf_page INTEGER NOT NULL,
  printed_page TEXT,
  text TEXT,
  lines_json TEXT,
  image_path TEXT,
  UNIQUE(source_id, pdf_page)
);

CREATE TABLE IF NOT EXISTS vocab_entry (
  id INTEGER PRIMARY KEY,
  headword TEXT NOT NULL,            -- exactly as printed in the textbook
  pos TEXT,                          -- Kiwi-derived guess unless pos_source='manual'
  pos_source TEXT DEFAULT 'kiwi',
  meaning_uz TEXT,                   -- original textbook gloss (glossary is Korean-Uzbek)
  meaning_en TEXT,                   -- manual only; never machine-translated
  meaning_ko TEXT,
  level TEXT, unit INTEGER, unit_title TEXT,
  page INTEGER,                      -- printed page if known
  pdf_page INTEGER,                  -- page in the source PDF
  source_id INTEGER REFERENCES source(id) ON DELETE SET NULL,
  entry_no INTEGER,                  -- number printed in the glossary, if any
  raw_text TEXT,                     -- original line(s)
  status TEXT NOT NULL DEFAULT 'verified' CHECK (status IN ('verified','needs_review','manual')),
  corrected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vocab_headword ON vocab_entry(headword);

-- Lookup keys (lemma sequences) for each vocab entry, produced by Kiwi at import time.
CREATE TABLE IF NOT EXISTS vocab_key (
  entry_id INTEGER NOT NULL REFERENCES vocab_entry(id) ON DELETE CASCADE,
  key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vocab_key ON vocab_key(key);

CREATE TABLE IF NOT EXISTS vocab_example (
  id INTEGER PRIMARY KEY,
  vocab_id INTEGER NOT NULL REFERENCES vocab_entry(id) ON DELETE CASCADE,
  sentence TEXT NOT NULL,
  source_ref TEXT
);

CREATE TABLE IF NOT EXISTS grammar_item (
  id INTEGER PRIMARY KEY,
  pattern TEXT NOT NULL,             -- textbook notation, e.g. V+(으)ㄹ 수 있다
  pattern_key TEXT,                  -- normalised key for joining index <-> student-book entries
  rule_json TEXT,                    -- compiled match rule (NULL => cannot auto-detect)
  explanation_original TEXT,
  explanation_ko TEXT,
  meaning_en TEXT,
  meaning_uz TEXT,
  formation TEXT,
  level TEXT, unit INTEGER, page INTEGER, pdf_page INTEGER,
  source_id INTEGER REFERENCES source(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'needs_review' CHECK (status IN ('verified','needs_review','manual')),
  corrected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  entry_no TEXT,
  raw_text TEXT,
  notes TEXT,
  index_page INTEGER
);

CREATE TABLE IF NOT EXISTS grammar_example (
  id INTEGER PRIMARY KEY,
  grammar_id INTEGER NOT NULL REFERENCES grammar_item(id) ON DELETE CASCADE,
  sentence TEXT NOT NULL,
  source_ref TEXT
);

CREATE TABLE IF NOT EXISTS sentence_pattern (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('connective','particle','conjugation','register')),
  label TEXT NOT NULL,
  rule_json TEXT,
  grammar_id INTEGER REFERENCES grammar_item(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS passage (
  id INTEGER PRIMARY KEY,
  title TEXT,
  text_original TEXT NOT NULL,
  text_norm TEXT NOT NULL,           -- NFC; all stored offsets refer to this text
  text_hash TEXT NOT NULL,
  analyzer_version TEXT,
  rules_version TEXT,
  vocab_version TEXT,
  analysed_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis_match (
  id INTEGER PRIMARY KEY,
  passage_id INTEGER NOT NULL REFERENCES passage(id) ON DELETE CASCADE,
  layer TEXT NOT NULL CHECK (layer IN ('vocab','grammar')),
  surface TEXT NOT NULL,
  start INTEGER NOT NULL,
  "end" INTEGER NOT NULL,
  sentence_no INTEGER, paragraph_no INTEGER,
  dict_form TEXT,
  ref_id INTEGER,                    -- vocab_entry.id or grammar_item.id; NULL => not found
  match_type TEXT NOT NULL CHECK (match_type IN ('EXACT','CONJUGATED','RELATED','NONE')),
  status TEXT NOT NULL CHECK (status IN ('VERIFIED','LIKELY','NEEDS_REVIEW','NOT_FOUND')),
  confidence REAL,
  rule_id TEXT,
  candidates_json TEXT,
  note TEXT,
  manual_override INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_match_passage ON analysis_match(passage_id, layer, start);

CREATE TABLE IF NOT EXISTS saved_item (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('vocab','grammar')),
  ref_id INTEGER NOT NULL,
  passage_id INTEGER REFERENCES passage(id) ON DELETE SET NULL,
  sentence TEXT,
  saved_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(kind, ref_id)
);

-- Single-user learning state (cards, review log, exercise log, reading progress, passage questions) as one JSON document.
CREATE TABLE IF NOT EXISTS study_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  json TEXT NOT NULL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS passage_sentence (
  passage_id INTEGER NOT NULL REFERENCES passage(id) ON DELETE CASCADE,
  no INTEGER NOT NULL,
  paragraph_no INTEGER NOT NULL,
  start INTEGER NOT NULL,
  "end" INTEGER NOT NULL,
  PRIMARY KEY (passage_id, no)
);

-- Workbook exercises / listening scripts, verbatim OCR (draft, unreviewed). One row per 연습 or per script page.
CREATE TABLE IF NOT EXISTS workbook_item (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES source(id) ON DELETE CASCADE,
  level TEXT,
  section TEXT,                      -- vocabulary | grammar | pattern_practice | listening | reading | ... | script
  unit INTEGER,                      -- only when it could be inferred from the joined grammar item
  grammar_id INTEGER REFERENCES grammar_item(id) ON DELETE SET NULL,
  heading TEXT,                      -- grammar heading as printed in the workbook
  match_score REAL,                  -- similarity between heading and the grammar item it was joined to
  exercise_no TEXT,
  instruction TEXT,
  body TEXT,
  pdf_page INTEGER,
  printed_page INTEGER,
  status TEXT NOT NULL DEFAULT 'needs_review'
);
CREATE INDEX IF NOT EXISTS idx_wb_grammar ON workbook_item(grammar_id);
CREATE INDEX IF NOT EXISTS idx_wb_level ON workbook_item(level, section);
