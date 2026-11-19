"""Build the slim, read-only database that ships with the public deployment.

    python scripts/build_deploy_db.py                      # data/app.sqlite -> deploy/app.sqlite
    python scripts/build_deploy_db.py --include-workbook   # also ship the workbook exercises + listening scripts

Keeps the textbook knowledge (vocabulary, grammar, examples, sources) and drops everything personal or heavy:
saved words, passages, analyses, study progress, and the raw OCR pages (text + line boxes). Workbook exercises and
listening scripts are bulk verbatim textbook text, so they are left out unless --include-workbook is given.
The copy is brought up to the current schema first, so a source DB the app never opened still works. VACUUMs the result.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import db as appdb  # noqa: E402

SRC = ROOT / "data" / "app.sqlite"
DST = ROOT / "deploy" / "app.sqlite"
DROP_ROWS = ["analysis_match", "passage_sentence", "passage", "saved_item", "study_state", "ocr_page"]
COUNT_TABLES = ("vocab_entry", "vocab_key", "grammar_item", "grammar_example", "workbook_item")


def build(src: Path, dst: Path, include_workbook: bool = False) -> dict:
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
    for t in DROP_ROWS + ([] if include_workbook else ["workbook_item"]):
        d.execute(f"DELETE FROM {t}")
    d.commit()
    d.execute("VACUUM")
    counts = {t: d.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
    d.close()
    tmp.replace(dst)                                                # only replace the deploy DB once the new one is complete
    return counts


def main() -> int:
    try:
        counts = build(SRC, DST, "--include-workbook" in sys.argv[1:])
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f"wrote {DST} ({DST.stat().st_size / 1e6:.1f} MB)  {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
