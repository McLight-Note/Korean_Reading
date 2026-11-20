"""Housekeeping for the local database.

    python scripts/maintenance.py drop-uzbek     # remove the book's Uzbek glosses (and everything derived from Kiwi) from data/app.sqlite

`drop-uzbek` first copies data/app.sqlite to data/app.sqlite.before-uzbek-removal (kept, so nothing is lost), then:
  * sets vocab_entry.meaning_uz / meaning_ko / raw_text / pos / pos_source to NULL (raw_text held each original line with its Uzbek gloss)
  * sets grammar_item.meaning_uz / raw_text / rule_json to NULL
  * clears the OCR'd text of the glossary and grammar-index pages (the page images stay for the Review tab)
  * drops tables that only existed for Kiwi analysis or server-side user data (vocab_key, passage, analysis_match, ...)
  * VACUUMs the file.
Headwords, levels, units, pages, the grammar explanations/examples and the workbook text are untouched.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "app.sqlite"
OLD_TABLES = ["vocab_key", "sentence_pattern", "analysis_match", "passage_sentence", "passage", "saved_item", "study_state"]


def drop_uzbek(path: Path = DB, backup: bool = True) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    if backup:
        shutil.copy2(path, path.with_name(path.name + ".before-uzbek-removal"))
    c = sqlite3.connect(path)
    cols = lambda t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
    done = {}
    for table, wanted in (("vocab_entry", ["meaning_uz", "meaning_ko", "raw_text", "pos", "pos_source"]),
                          ("grammar_item", ["meaning_uz", "raw_text", "rule_json"])):
        have = [col for col in wanted if col in cols(table)]
        if have:
            c.execute(f"UPDATE {table} SET " + ", ".join(f"{col}=NULL" for col in have))
        done[table] = have
    # the OCR'd text of the glossary and of the scanned grammar index contains the Uzbek glosses too
    if "ocr_page" in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        c.execute("""UPDATE ocr_page SET text=NULL, lines_json=NULL
                     WHERE source_id IN (SELECT id FROM source WHERE kind IN ('glossary','grammar_index'))""")
    for t in OLD_TABLES:
        c.execute(f"DROP TABLE IF EXISTS {t}")
    c.commit()
    c.execute("VACUUM")
    left = {
        "vocab_with_uzbek": c.execute("SELECT COUNT(*) FROM vocab_entry WHERE meaning_uz IS NOT NULL OR raw_text IS NOT NULL").fetchone()[0],
        "grammar_with_uzbek": c.execute("SELECT COUNT(*) FROM grammar_item WHERE meaning_uz IS NOT NULL OR raw_text IS NOT NULL").fetchone()[0],
    }
    c.close()
    return {"cleared": done, "remaining": left}


def main(argv) -> int:
    what = argv[0] if argv else ""
    if what == "drop-uzbek":
        print(drop_uzbek())
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
