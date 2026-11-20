"""CLI: import the Korean-Uzbek glossary PDF into vocab_entry.

    python -m backend.app.ingest.import_glossary "서울대 책 1a 부터 5b가지.pdf" [--force]

Uses the PDF's embedded text layer (macOS: PDFKit via pdf_text.swift). Re-importing is refused
unless --force, because it would discard manual corrections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import db
from .glossary_parser import parse_pages

SWIFT = Path(__file__).with_name("pdf_text.swift")


def extract_text_pages(pdf: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "text.json"
        res = subprocess.run(["swift", str(SWIFT), str(pdf), str(out)], capture_output=True, text=True)
        if res.returncode:
            raise SystemExit(f"could not read {pdf}: {(res.stderr or 'unknown error').strip()[-500:]}")
        return json.loads(out.read_text(encoding="utf-8"))


def import_entries(conn, entries, source_id: int) -> int:
    n = 0
    for e in entries:
        if e.level is None:
            continue  # cover page etc.
        # only the Korean headword, level, unit and page are kept: the book's Uzbek glosses are deliberately NOT stored
        status = "needs_review" if set(e.flags) - {"no-gloss"} else "verified"
        conn.execute(
            """INSERT INTO vocab_entry (headword, level, unit, unit_title, pdf_page, source_id, entry_no, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (e.headword, e.level, e.unit, e.unit_title, e.pdf_page, source_id, e.entry_no, status),
        )
        n += 1
    db.bump(conn, "vocab_version")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    pdf = Path(args.pdf)
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM source WHERE filename=? AND kind='glossary'", (pdf.name,)).fetchone() and not args.force:
            print("already imported; use --force to replace (manual corrections would be lost)")
            return 1
    if not pdf.is_file():
        raise SystemExit(f"PDF not found: {pdf}. Run this from the project folder with the PDF in it.")
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    pages = extract_text_pages(pdf)
    entries = parse_pages(pages)
    with db.session() as conn:
        row = conn.execute("SELECT id FROM source WHERE filename=? AND kind='glossary'", (pdf.name,)).fetchone()
        if row and not args.force:
            print("already imported; use --force to replace (manual corrections would be lost)")
            return 1
        if row:
            conn.execute("DELETE FROM vocab_entry WHERE source_id=?", (row["id"],))
            conn.execute("DELETE FROM source WHERE id=?", (row["id"],))
        sid = conn.execute(
            "INSERT INTO source(filename, level, kind, sha256, note) VALUES (?,?,?,?,?)",
            (pdf.name, "1A-5B", "glossary", sha, "Korean-Uzbek glossary; page numbers are PDF pages"),
        ).lastrowid
        n = import_entries(conn, entries, sid)
        for pg in pages:
            conn.execute("INSERT INTO ocr_page(source_id, pdf_page) VALUES (?,?)", (sid, pg["pdf_page"]))      # no text: it holds the Uzbek column
    print(f"imported {n} vocabulary entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
