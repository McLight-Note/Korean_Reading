"""Build the slim, read-only database that ships with the public deployment.

    python scripts/build_deploy_db.py                      # data/app.sqlite -> deploy/app.sqlite (books incl. workbook exercises)
    python scripts/build_deploy_db.py --exclude-workbook   # leave the workbook exercises out

Keeps the textbook knowledge (vocabulary headwords with level/unit, grammar items with the books' own English
explanations and examples, workbook exercises) and drops everything else: the raw OCR pages, any Uzbek gloss or raw
glossary line that might still be in an older database, and every table that only existed for server-side user data.
The copy is brought up to the current schema first. VACUUMs the result.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import db as appdb  # noqa: E402

SRC = ROOT / "data" / "app.sqlite"
DST = ROOT / "deploy" / "app.sqlite"
DROP_ROWS = ["ocr_page"]
LEGACY_TABLES = ["vocab_key", "sentence_pattern", "analysis_match", "passage_sentence", "passage", "saved_item", "study_state"]
SCRUB = {"vocab_entry": ["meaning_uz", "meaning_ko", "raw_text", "pos", "pos_source"], "grammar_item": ["meaning_uz", "raw_text", "rule_json"]}
COUNT_TABLES = ("vocab_entry", "grammar_item", "grammar_example", "workbook_item")


def build(src: Path, dst: Path, include_workbook: bool = True) -> dict:
    if not src.exists():
        raise FileNotFoundError(f"{src} not found; build the knowledge base first (see README step 3)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)           # consistent snapshot even if the app is running
    d = sqlite3.connect(tmp)
    s.backup(d)
    s.close()
    d.row_factory = sqlite3.Row
    appdb.init_db(d)                                                # add tables/columns newer than the source DB
    for t in LEGACY_TABLES:
        d.execute(f"DROP TABLE IF EXISTS {t}")
    for t in DROP_ROWS + ([] if include_workbook else ["workbook_item"]):
        d.execute(f"DELETE FROM {t}")
    for table, cols in SCRUB.items():
        have = {r[1] for r in d.execute(f"PRAGMA table_info({table})")}
        use = [c for c in cols if c in have]
        if use:
            d.execute(f"UPDATE {table} SET " + ", ".join(f"{c}=NULL" for c in use))
    d.commit()
    d.execute("VACUUM")
    counts = {t: d.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
    d.close()
    tmp.replace(dst)                                                # only replace the deploy DB once the new one is complete
    return counts


def main() -> int:
    try:
        counts = build(SRC, DST, "--exclude-workbook" not in sys.argv[1:])
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f"wrote {DST} ({DST.stat().st_size / 1e6:.1f} MB)  {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
