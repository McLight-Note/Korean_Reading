"""Rule-quality report: does each compiled rule detect the grammar in its OWN textbook examples?

An example "hits" when the item's rule matches somewhere in the example sentence. Examples that are not
sentences of the pattern (notes, comparison fragments) can lower recall, so the report is a triage list
for the admin, not a verdict. Runs locally (Kiwi); nothing is stored.
"""
from __future__ import annotations

import json

from . import grammar_matcher
from .korean_analyzer import analyze_text


def run(conn, level: str | None = None) -> dict:
    where = "WHERE rule_json IS NOT NULL" + (" AND level=?" if level else "")
    items = conn.execute(f"SELECT id, pattern, level, status, rule_json FROM grammar_item {where} ORDER BY level, id", (level,) if level else ()).fetchall()
    report = []
    totals = {"items": 0, "examples": 0, "hits": 0}
    for it in items:
        exs = conn.execute("SELECT id, sentence FROM grammar_example WHERE grammar_id=?", (it["id"],)).fetchall()
        if not exs:
            continue
        rule_alts = json.loads(it["rule_json"])["alts"]
        rule = grammar_matcher.Rule(it["id"], it["pattern"], None, it["level"], "verified", rule_alts, 1, False)
        misses, hits = [], 0
        for ex in exs:
            _, sents = analyze_text(ex["sentence"])
            ok = any(m.layer == "grammar" and m.status != "NOT_FOUND" for s in sents for m in grammar_matcher.match_sentence([rule], s))
            hits += ok
            if not ok:
                misses.append({"id": ex["id"], "sentence": ex["sentence"]})
        report.append({"id": it["id"], "pattern": it["pattern"], "level": it["level"], "status": it["status"],
                       "examples": len(exs), "hits": hits, "recall": round(hits / len(exs), 2), "misses": misses})
        totals["items"] += 1; totals["examples"] += len(exs); totals["hits"] += hits
    totals["recall"] = round(totals["hits"] / totals["examples"], 3) if totals["examples"] else None
    report.sort(key=lambda r: (r["recall"], -r["examples"]))
    return {"totals": totals, "items": report}
