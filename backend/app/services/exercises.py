"""Locally generated exercises built ONLY from stored textbook material. No AI, no network.

Every exercise is labelled generated (never textbook-original) and carries the source reference of the textbook
record it was built from, plus that record's review status, so the learner can see how trustworthy it is.

  grammar_mcq  textbook example sentence with the grammar blanked -> pick the grammar pattern
  vocab_mcq    glossary headword -> pick the Uzbek gloss        (vocab_rev: the other direction)
  check_answer workbook practice: does the learner's answer contain the target grammar? (local detector only)
"""
from __future__ import annotations

import json
import random

from . import grammar_matcher
from . import sentence_analyzer as sa
from .korean_analyzer import analyze_text, normalize

BLANK = "____"
MAX_SENTENCE = 160


def _rule(row) -> grammar_matcher.Rule:
    return grammar_matcher.Rule(row["id"], row["pattern"], None, row["level"], "verified", json.loads(row["rule_json"])["alts"], 1, False)


def _blank_of(conn_row, text: str):
    """(blanked_text, blanked_span, norm_text) for the first exact match of this item's rule in `text`, else None."""
    norm, sents = analyze_text(text)
    rule = _rule(conn_row)
    hits = [m for s in sents for m in grammar_matcher.match_sentence([rule], s) if m.layer == "grammar" and m.status != "NOT_FOUND"]
    if len(hits) != 1:                                    # a second occurrence elsewhere in the text would give the answer away
        return None
    m = hits[0]
    if m.match_type != "EXACT" or m.core_start is None or m.core_start >= m.end:
        return None
    return norm[:m.core_start] + BLANK + norm[m.end:], norm[m.core_start:m.end], norm


def _matches_in(row, norm: str) -> bool:
    _, sents = analyze_text(norm)
    rule = _rule(row)
    return any(m.layer == "grammar" and m.status != "NOT_FOUND" for s in sents for m in grammar_matcher.match_sentence([rule], s))


def grammar_mcq(conn, level: str, n: int, rng: random.Random, include_unreviewed: bool = True) -> list[dict]:
    where = "rule_json IS NOT NULL" + (" AND level=?" if level else "") + ("" if include_unreviewed else " AND status IN ('verified','manual')")
    items = conn.execute(f"SELECT id, pattern, level, unit, page, status, rule_json, meaning_uz, meaning_en, explanation_original FROM grammar_item WHERE {where}",
                         (level,) if level else ()).fetchall()
    pool = conn.execute("SELECT id, pattern, level, rule_json FROM grammar_item WHERE rule_json IS NOT NULL" + (" AND level=?" if level else ""),
                        (level,) if level else ()).fetchall()
    items = list(items)
    rng.shuffle(items)
    out: list[dict] = []
    for it in items:
        if len(out) >= n:
            break
        exs = [r for r in conn.execute("SELECT id, sentence, source_ref FROM grammar_example WHERE grammar_id=?", (it["id"],)) if len(r["sentence"]) <= MAX_SENTENCE]
        rng.shuffle(exs)
        for ex in exs[:4]:
            res = _blank_of(it, ex["sentence"])
            if not res:
                continue
            prompt, answer_span, norm = res
            cands = [p for p in pool if p["id"] != it["id"] and p["pattern"] != it["pattern"]]
            rng.shuffle(cands)
            distractors = []
            for c in cands:                                   # drop any distractor that would ALSO fit the sentence
                if len(distractors) == 3:
                    break
                if not _matches_in(c, norm):
                    distractors.append(c)
            if len(distractors) < 3:
                continue
            choices = [{"id": it["id"], "pattern": it["pattern"]}] + [{"id": d["id"], "pattern": d["pattern"]} for d in distractors]
            rng.shuffle(choices)
            out.append({
                "type": "grammar_mcq", "label": "Generated exercise (built from a textbook example; not original textbook content)",
                "prompt": prompt, "full_sentence": norm, "blanked": answer_span, "choices": choices,
                "answer_id": it["id"], "answer_pattern": it["pattern"], "item_id": it["id"],
                "meaning_uz": it["meaning_uz"], "meaning_en": it["meaning_en"], "explanation": (it["explanation_original"] or "")[:400],
                "source": {"level": it["level"], "unit": it["unit"], "page": it["page"], "item_status": it["status"], "example_ref": ex["source_ref"]},
            })
            break
    return out


def vocab_mcq(conn, level: str, n: int, rng: random.Random, reverse: bool = False) -> list[dict]:
    where = "status='verified' AND meaning_uz IS NOT NULL AND length(meaning_uz) BETWEEN 2 AND 60 AND length(headword) <= 20" + (" AND level=?" if level else "")
    rows = conn.execute(f"SELECT id, headword, meaning_uz, meaning_en, level, unit, pdf_page FROM vocab_entry WHERE {where}", (level,) if level else ()).fetchall()
    rows = [r for r in rows if r["headword"].strip() and r["meaning_uz"].strip()]
    seen, uniq = set(), []
    for r in rows:
        key = r["headword"].strip()
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    if len(uniq) < 4:
        return []
    rng.shuffle(uniq)
    out = []
    for r in uniq[:n]:
        field = "headword" if reverse else "meaning_uz"
        seen_text, others = {r[field].strip().lower()}, []
        for o in uniq:                                     # distractors must differ from the answer AND from each other in what is displayed
            t = o[field].strip().lower()
            if o["id"] != r["id"] and o["meaning_uz"].strip().lower() != r["meaning_uz"].strip().lower() and t not in seen_text:
                seen_text.add(t)
                others.append(o)
        if len(others) < 3:
            continue                                       # not enough distinct choices: skip rather than show duplicates
        picks = rng.sample(others, 3)
        opts = [r] + picks
        rng.shuffle(opts)
        out.append({
            "type": "vocab_rev" if reverse else "vocab_mcq", "label": "Generated exercise (built from the glossary)",
            "prompt": r["meaning_uz"] if reverse else r["headword"], "prompt_lang": "uz" if reverse else "ko",
            "choices": [{"id": o["id"], "text": o[field]} for o in opts], "answer_id": r["id"], "item_id": r["id"],
            "headword": r["headword"], "meaning_uz": r["meaning_uz"], "meaning_en": r["meaning_en"],
            "source": {"level": r["level"], "unit": r["unit"], "glossary_pdf_page": r["pdf_page"], "item_status": "verified"},
        })
    return out


def check_answer(conn, grammar_id: int, text: str) -> dict:
    """Workbook practice: is the target grammar present in what the learner wrote? Says nothing about anything else."""
    row = conn.execute("SELECT id, pattern, rule_json FROM grammar_item WHERE id=?", (grammar_id,)).fetchone()
    if row is None:
        return {"error": "unknown grammar item"}
    if row["rule_json"] is None:
        return {"target": row["pattern"], "checkable": False, "target_found": None, "detected": []}
    sentences, matches = sa.compute(conn, normalize(text))
    detected, target_found = [], False
    for m in matches:
        if m.layer != "grammar" or m.status == "NOT_FOUND":
            continue
        ids = {c["id"] for c in m.candidates}
        hit = grammar_id in ids
        target_found = target_found or hit
        detected.append({"surface": m.surface, "pattern": m.dict_form, "status": m.status, "is_target": hit})
    return {"target": row["pattern"], "checkable": True, "target_found": target_found, "detected": detected}
