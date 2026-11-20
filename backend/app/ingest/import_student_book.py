"""CLI: import the Grammar Extension (문법 해설) of a student book from its Vision-OCR output.

    python -m backend.app.ingest.import_student_book "3B SB.pdf" [--level 3B] [--force]

Prerequisite: data/ocr/<name>/page_NNN.json (+ .jpg) made by ingest/vision_ocr.swift.
Everything written here is status 'needs_review' (OCR + layout heuristics). Items that join an entry of the
scanned grammar index (same level, similar pattern) get its explanation/examples/unit/page; the rest are added
as new items. Records with corrected=1 are never overwritten. Nothing is translated or invented.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

from .. import config, db
from ..services.common import pattern_key
from .sb_grammar_parser import Item, parse_ocr_dir

SLOT_PREFIX = re.compile(r"[AVN](?:/[AVN])*\s*[+=-]")
JOIN_THRESHOLD = 0.8


def join_norm(pattern: str) -> str:
    s = re.sub(r"\(요\)", "", pattern)
    s = SLOT_PREFIX.sub("", s)
    s = re.sub(r"[A-Za-z0-9]+", "", s)                        # Latin/digits are slot letters or Uzbek-gloss noise in OCR
    return re.sub(r"[\s+\-–—/()\[\],.?~‘’'\"]", "", s)


def similarity(a: str, b: str) -> float:
    na, nb = join_norm(a), join_norm(b)
    best = difflib.SequenceMatcher(None, na, nb).ratio()
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 3 and short in long_:                   # one pattern is contained in the other (OCR noise / sub-entries)
        best = max(best, 0.85)
    for part in re.split(r"/(?=[AVN])", a):                  # one alternative of a multi-form heading
        best = max(best, difflib.SequenceMatcher(None, join_norm(part), nb).ratio())
    return best


def assign(items: list[Item], index_rows: list) -> dict[int, int]:
    """Greedy one-to-one join: item position -> grammar_item id (best similarity first)."""
    scored = []
    for i, it in enumerate(items):
        for r in index_rows:
            sc = similarity(it.pattern, r["pattern"])
            if sc >= JOIN_THRESHOLD:
                scored.append((sc, i, r["id"]))
    out, used_i, used_r = {}, set(), set()
    for sc, i, rid in sorted(scored, reverse=True):
        if i not in used_i and rid not in used_r:
            out[i] = rid
            used_i.add(i); used_r.add(rid)
    return out


def store(conn, pdf_name: str, level: str, ocr_dir: Path, items: list[Item], sha: str | None = None, force: bool = False) -> dict:
    row = conn.execute("SELECT id FROM source WHERE filename=? AND kind='student_book'", (pdf_name,)).fetchone()
    if row and not force:
        raise SystemExit("already imported; use --force (rows with corrected=1 are kept)")
    if row:
        sid = row["id"]
        conn.execute("DELETE FROM grammar_item WHERE source_id=? AND entry_no IS NULL AND corrected=0", (sid,))
    else:
        sid = conn.execute("INSERT INTO source(filename, level, kind, sha256, note) VALUES (?,?,?,?,?)",
                           (pdf_name, level, "student_book", sha, "Grammar Extension imported from local OCR; unreviewed")).lastrowid
    # raw OCR pages (kept for the review UI)
    for jp in sorted(ocr_dir.glob("page_*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        conn.execute("INSERT OR REPLACE INTO ocr_page(source_id, pdf_page, text, lines_json, image_path) VALUES (?,?,?,?,?)",
                     (sid, d["pdf_page"], "\n".join(l["text"] for l in d["lines"]), json.dumps(d["lines"], ensure_ascii=False),
                      f"{ocr_dir.name}/{jp.stem}.jpg"))
    index_rows = conn.execute(
        "SELECT id, pattern FROM grammar_item WHERE level=? AND entry_no IS NOT NULL", (level,)).fetchall()   # entry_no => came from the scanned index
    joined = assign(items, index_rows)
    stats = {"items": len(items), "joined": 0, "new": 0, "merged_index_fragments": 0, "kept_corrected": 0, "with_examples": 0}
    gid_of: dict[int, int] = {}
    for i, it in enumerate(items):
        stats["with_examples"] += bool(it.examples)
        explanation = "\n".join(it.meaning_lines) or None
        formation = "\n".join(it.formation_lines) or None
        notes = "\n".join(it.note_lines) or None
        vals = dict(pattern=it.pattern, pattern_key=pattern_key(it.pattern),
                    explanation_original=explanation, formation=formation, notes=notes, level=level, unit=it.unit, page=it.lesson_page,
                    pdf_page=it.appendix_pdf_page, source_id=sid)
        gid = joined.get(i)
        if gid is not None:
            if conn.execute("SELECT corrected FROM grammar_item WHERE id=?", (gid,)).fetchone()["corrected"]:
                stats["kept_corrected"] += 1
                continue
            sets = ", ".join(f"{k}=?" for k in vals)
            conn.execute(f"UPDATE grammar_item SET {sets}, status='needs_review' WHERE id=?", (*vals.values(), gid))
            stats["joined"] += 1
        else:
            cols = ", ".join(vals)
            gid = conn.execute(f"INSERT INTO grammar_item({cols}, status) VALUES ({','.join('?' * len(vals))}, 'needs_review')", tuple(vals.values())).lastrowid
            stats["new"] += 1
        gid_of[i] = gid
        conn.execute("DELETE FROM grammar_example WHERE grammar_id=? AND source_ref LIKE ?", (gid, f"{pdf_name}%"))
        for ex in it.examples:
            conn.execute("INSERT INTO grammar_example(grammar_id, sentence, source_ref) VALUES (?,?,?)",
                         (gid, ex.text, f"{pdf_name} · Grammar Extension (PDF p.{ex.pdf_page})"))
    # leftover index rows that are sub-entries of an imported heading (e.g. 'A+다면' + 'V+ㄴ다면' under 'A+다면/V+ㄴ다면/...')
    for r in index_rows:
        if r["id"] in joined.values():
            continue
        cands = [(similarity(it.pattern, r["pattern"]), i) for i, it in enumerate(items) if i in gid_of]
        if not cands:
            continue
        sc, i = max(cands)
        if sc < 0.85 or conn.execute("SELECT corrected FROM grammar_item WHERE id=?", (r["id"],)).fetchone() is None:
            continue
        frag = conn.execute("SELECT * FROM grammar_item WHERE id=?", (r["id"],)).fetchone()
        if frag["corrected"]:
            continue
        conn.execute("DELETE FROM grammar_item WHERE id=?", (r["id"],))
        stats["merged_index_fragments"] += 1
    db.bump(conn, "rules_version")
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
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
