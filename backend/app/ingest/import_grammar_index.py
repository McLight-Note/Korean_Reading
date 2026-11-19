"""CLI: OCR (macOS Vision) + import the scanned grammar index into grammar_item (status=needs_review).

    python -m backend.app.ingest.import_grammar_index "서울 대 grammatikka kitob.pdf" [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .. import config, db
from ..services.pattern_compiler import compile_pattern, pattern_key
from .grammar_index_parser import parse_ocr_dir

SWIFT = Path(__file__).with_name("vision_ocr.swift")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    pdf = Path(args.pdf)
    ocr_dir = config.DATA_DIR / "ocr" / "grammar_book"
    subprocess.run(["swift", str(SWIFT), str(pdf), str(ocr_dir)], check=True, capture_output=True)   # resumable
    items = parse_ocr_dir(ocr_dir)
    with db.session() as conn:
        row = conn.execute("SELECT id FROM source WHERE filename=? AND kind='grammar_index'", (pdf.name,)).fetchone()
        if row and not args.force:
            print("already imported; use --force (manual corrections would be lost)")
            return 1
        if row:
            conn.execute("DELETE FROM grammar_item WHERE source_id=?", (row["id"],))
            conn.execute("DELETE FROM source WHERE id=?", (row["id"],))
        sid = conn.execute("INSERT INTO source(filename, level, kind, sha256, note) VALUES (?,?,?,?,?)",
                           (pdf.name, "1A-4B", "grammar_index", hashlib.sha256(pdf.read_bytes()).hexdigest(),
                            "Scanned, handwriting-annotated pattern index with Uzbek glosses")).lastrowid
        ok = 0
        for it in items:
            rule = compile_pattern(it.pattern)
            ok += rule is not None
            conn.execute(
                """INSERT INTO grammar_item(pattern, pattern_key, rule_json, meaning_uz, level, pdf_page, source_id,
                       status, entry_no, raw_text) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (it.pattern, pattern_key(it.pattern), json.dumps(rule, ensure_ascii=False) if rule else None,
                 it.gloss or None, it.level, it.pdf_page, sid, "needs_review", it.entry_no, it.raw))
        db.bump(conn, "rules_version")
    print(f"imported {len(items)} grammar index items; {ok} compiled into detection rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
