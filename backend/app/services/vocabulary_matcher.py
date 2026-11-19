"""Match Kiwi lexical units against the textbook vocabulary database (lemma-key lookup).

Match types:  EXACT      surface equals the dictionary form
              CONJUGATED lemma matches, surface is an inflected form (먹었습니다 -> 먹다)
              RELATED    only a related lemma matches (공부하고 -> entry 공부)
              NONE       not found in the textbook (no reference is attached)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .korean_analyzer import LexUnit, Sentence

LEVEL_ORDER = {f"{n}{ab}": i for i, (n, ab) in enumerate((n, ab) for n in range(1, 6) for ab in "AB")}
MAX_PHRASE_GAP = 4  # max lexical units allowed between parts of a multi-word headword


@dataclass
class Match:
    layer: str
    surface: str
    start: int
    end: int
    sentence_no: int
    paragraph_no: int
    dict_form: str | None
    ref_id: int | None
    match_type: str
    status: str
    confidence: float
    rule_id: str | None = None
    candidates: list[dict] = field(default_factory=list)
    note: str | None = None
    core_start: int | None = None     # grammar: where the pattern's own morphemes begin (after the stem); used for cloze blanks


class VocabIndex:
    def __init__(self, conn):
        self.entries: dict[int, dict] = {}
        self.by_key: dict[str, list[int]] = defaultdict(list)
        self.phrases: dict[str, list[tuple[list[str], str]]] = defaultdict(list)  # first lemma -> [(parts, key)]
        for r in conn.execute("SELECT * FROM vocab_entry"):
            self.entries[r["id"]] = dict(r)
        for r in conn.execute("SELECT entry_id, key FROM vocab_key"):
            ids = self.by_key[r["key"]]
            if r["entry_id"] not in ids:
                ids.append(r["entry_id"])
            if " " in r["key"]:
                parts = r["key"].split(" ")
                if (parts, r["key"]) not in self.phrases[parts[0]]:
                    self.phrases[parts[0]].append((parts, r["key"]))

    def _distinct(self, ids: list[int]) -> list[dict]:
        """Collapse duplicate textbook entries (same headword+meaning at several levels); earliest level first."""
        seen, out = set(), []
        for e in sorted((self.entries[i] for i in ids), key=lambda e: (LEVEL_ORDER.get(e["level"], 99), e["unit"] or 0, e["id"])):
            sig = (e["headword"], (e["meaning_uz"] or "").strip().lower())
            if sig not in seen:
                seen.add(sig)
                out.append(e)
        return out

    def _make(self, unit_start, unit_end, surface, lemma, via_alt, ids, sent: Sentence) -> Match:
        cands = self._distinct(ids)
        best = cands[0]
        if lemma.replace(" ", "") == surface.replace(" ", ""):
            mtype = "EXACT"
        else:
            mtype = "CONJUGATED"
        if via_alt:
            mtype = "RELATED"
        distinct_meanings = {(c["meaning_uz"] or "").strip().lower() for c in cands}
        if len(cands) > 1 and len(distinct_meanings) > 1:
            status, conf, note = "NEEDS_REVIEW", 0.4, "Several textbook entries share this form; check which meaning applies."
        elif mtype == "RELATED":
            status, conf, note = "LIKELY", 0.6, "Only a related dictionary form was found in the textbook."
        elif best["status"] != "verified":
            status, conf, note = "LIKELY", 0.7, "Textbook entry is flagged for review (parsing was uncertain)."
        else:
            status, conf, note = "VERIFIED", 0.95, None
        return Match("vocab", surface, unit_start, unit_end, sent.index, sent.paragraph, lemma, best["id"], mtype, status, conf,
                     candidates=[{"id": c["id"], "headword": c["headword"], "level": c["level"], "unit": c["unit"],
                                  "meaning_uz": c["meaning_uz"]} for c in cands], note=note)

    def match_sentence(self, sent: Sentence) -> list[Match]:
        out: list[Match] = []
        units = sent.units
        for i, u in enumerate(units):
            # --- multi-word headwords (숙제를 하다) ---
            for parts, key in self.phrases.get(u.lemma, []):
                pos, last = 1, i
                j = i + 1
                while pos < len(parts) and j < len(units) and j - last <= MAX_PHRASE_GAP:
                    if units[j].lemma == parts[pos]:
                        pos += 1
                        last = j
                    j += 1
                if pos == len(parts):
                    s, e = u.start, units[last].end
                    m = self._make(s, e, sent_text(sent, s, e), " ".join(parts), False, self.by_key[key], sent)
                    m.dict_form = key.replace(" ", " ")
                    out.append(m)
            # --- single lexemes ---
            hit = None
            if u.lemma in self.by_key and " " not in u.lemma:
                hit = (u.lemma, False)
            else:
                for alt in u.alt_lemmas:
                    if alt in self.by_key:
                        hit = (alt, True)
                        break
            if hit:
                out.append(self._make(u.start, u.end, u.surface, hit[0], hit[1], self.by_key[hit[0]], sent))
            else:
                out.append(Match("vocab", u.surface, u.start, u.end, sent.index, sent.paragraph, u.lemma, None, "NONE", "NOT_FOUND", 0.0,
                                 note="Not found in the uploaded textbook vocabulary."))
        return out


def sent_text(sent: Sentence, start: int, end: int) -> str:
    return sent.text[start - sent.start:end - sent.start]
