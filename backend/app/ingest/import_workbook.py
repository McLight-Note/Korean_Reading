"""CLI: import a workbook (WB) from its Vision-OCR output into workbook_item.

    python -m backend.app.ingest.import_workbook "3B WB.pdf" [--level 3B] [--force]

Prerequisite: data/ocr/<name>/page_NNN.json (+ .jpg) made by ingest/vision_ocr.swift.
Exercises are stored verbatim (OCR, unreviewed). Grammar-section exercises are joined to the grammar item whose
pattern is most similar to the workbook heading (same level, similarity >= 0.8); otherwise grammar_id stays NULL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .. import config, db
from .import_student_book import similarity
from .wb_parser import Exercise, parse_ocr_dir

THRESHOLD = 0.8


def store(conn, pdf_name: str, level: str, ocr_dir: Path, items: list[Exercise], sha: str | None = None, force: bool = False) -> dict:
    row = conn.execute("SELECT id FROM source WHERE filename=? AND kind='workbook'", (pdf_name,)).fetchone()
    if row and not force:
        raise SystemExit("already imported; use --force")
    if row:
        sid = row["id"]
        conn.execute("DELETE FROM workbook_item WHERE source_id=?", (sid,))
    else:
        sid = conn.execute("INSERT INTO source(filename, level, kind, sha256, note) VALUES (?,?,?,?,?)",
                           (pdf_name, level, "workbook", sha, "Workbook exercises imported from local OCR; unreviewed")).lastrowid
    for jp in sorted(ocr_dir.glob("page_*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        conn.execute("INSERT OR REPLACE INTO ocr_page(source_id, pdf_page, text, lines_json, image_path) VALUES (?,?,?,?,?)",
                     (sid, d["pdf_page"], "\n".join(l["text"] for l in d["lines"]), json.dumps(d["lines"], ensure_ascii=False),
                      f"{ocr_dir.name}/{jp.stem}.jpg"))
    grammar = conn.execute("SELECT id, pattern, unit FROM grammar_item WHERE level=?", (level,)).fetchall()
    cache: dict[str, tuple[int | None, int | None, float]] = {}

    def join(notation: str):
        if notation in cache:
            return cache[notation]
        best = max(((similarity(notation, g["pattern"]), g) for g in grammar), key=lambda x: x[0], default=(0.0, None))
        res = (best[1]["id"], best[1]["unit"], round(best[0], 2)) if best[1] is not None and best[0] >= THRESHOLD else (None, None, round(best[0], 2))
        cache[notation] = res
        return res

    stats = {"items": 0, "joined": 0, "grammar_headings": 0, "unjoined_headings": []}
    seen_heads = set()
    for ex in items:
        gid = unit = score = None
        if ex.heading_notation:
            gid, unit, score = join(ex.heading_notation)
            if ex.heading_notation not in seen_heads:
                seen_heads.add(ex.heading_notation)
                stats["grammar_headings"] += 1
                if gid is None:
                    stats["unjoined_headings"].append(ex.heading_notation)
        stats["joined"] += gid is not None
        conn.execute(
            """INSERT INTO workbook_item(source_id, level, section, unit, grammar_id, heading, match_score, exercise_no,
                   instruction, body, pdf_page, printed_page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, level, ex.section, unit, gid, ex.heading, score, ex.number, ex.instruction, "\n".join(ex.body), ex.pdf_page, ex.printed_page))
        stats["items"] += 1
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--level")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    pdf = Path(args.pdf)
    level = args.level or pdf.name.split()[0].upper()
    ocr_dir = config.DATA_DIR / "ocr" / pdf.stem.replace(" ", "_")
    if not ocr_dir.is_dir() or not any(ocr_dir.glob("page_*.json")):
        raise SystemExit(f"no OCR output in {ocr_dir}: run vision_ocr.swift on the PDF first (see README)")
    items = parse_ocr_dir(ocr_dir)
    if not items:
        raise SystemExit(f"nothing could be parsed from {ocr_dir}; nothing was imported")
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.exists() else None
    with db.session() as conn:
        stats = store(conn, pdf.name, level, ocr_dir, items, sha, args.force)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
