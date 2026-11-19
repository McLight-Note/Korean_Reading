"""Detect textbook grammar items in Kiwi morpheme sequences.

Matching is morphological, never raw substring search:
  * the stem before the pattern must have the right class (V/A -> predicate, N -> noun),
    optionally followed by tense/honorific EP morphemes (었, 겠, 시) -> RELATED FORM;
  * each pattern word must equal the (allomorph-normalised) concatenation of consecutive morphemes,
    so 할/갈/먹을 all satisfy -(으)ㄹ;
  * lexical words (있다, 몰랐다) must match morphemes by lemma + class;
  * only 'JX' particles (도, 은/는, 만) may intervene between words.

Statuses (never overstated):
  VERIFIED     unambiguous match of an approved ('verified'/'manual') textbook item
  LIKELY       form matches but the item is unreviewed OCR data, a very short form, or a related form
  NEEDS_REVIEW several different textbook items match the same span
  NOT_FOUND    a connective/modifier ending (EC, ETM, ETN) with no matching textbook item
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .korean_analyzer import Morph, Sentence
from .pattern_compiler import canon, tag_class
from .vocabulary_matcher import LEVEL_ORDER, Match

MAX_RUN = 4          # max morphemes joined to form one pattern word (e.g. 보+니+까)
UNCOVERED_TAGS = {"EC", "ETM", "ETN"}   # endings reported as NOT_FOUND when no textbook item covers them


@dataclass
class Rule:
    item_id: int
    pattern: str
    pattern_key: str | None
    level: str | None
    status: str
    alts: list[dict]
    specificity: int
    weak: bool


def load_rules(conn) -> list[Rule]:
    rules = []
    for r in conn.execute("SELECT id, pattern, pattern_key, level, status, rule_json FROM grammar_item WHERE rule_json IS NOT NULL"):
        rule = json.loads(r["rule_json"])
        forms = [f for a in rule["alts"] for w in a["words"] for f in (w.get("alts") or [m[0] for m in w.get("morphs", [])])]
        longest = max((len(f) for f in forms), default=0)
        nwords = max(len(a["words"]) for a in rule["alts"])
        rules.append(Rule(r["id"], r["pattern"], r["pattern_key"], r["level"], r["status"], rule["alts"],
                          longest + 3 * nwords, longest <= 1 and nwords == 1))
    return rules


def _slot_ok(m: Morph, slots: list[str]) -> bool:
    cls = tag_class(m.tag)
    if "V" in slots or "A" in slots:
        if cls == "V":
            return True
    if "N" in slots and cls == "N":
        return True
    return False


def _text_slice(sent: Sentence, a: int, b: int) -> str:
    return sent.text[max(0, a - sent.start): max(0, b - sent.start)]


def _run_word(word: dict, sent: Sentence, mi: int) -> list[int]:
    """Return morpheme indices at which matching can continue after consuming `word` from mi."""
    ms = sent.morphs
    n = len(ms)
    if mi >= n:
        return []
    if word["kind"] == "lex":
        out = []
        seq = word["morphs"]
        if mi + len(seq) <= n and all(canon(ms[mi + k].form) == f and ("EP" if ms[mi + k].tag == "EP" else tag_class(ms[mi + k].tag)) == c
                                      for k, (f, c) in enumerate(seq)):
            out.append(mi + len(seq))                        # morpheme-for-morpheme match (handles 모르+았 for 몰랐다)
        stem = word.get("stem")
        if stem:                                             # Kiwi may split a dictionary word differently: 척+하, 만+하
            for L in range(1, MAX_RUN + 1):
                if mi + L > n:
                    break
                run = ms[mi:mi + L]
                if any(m.tag.startswith("S") for m in run):
                    break
                if tag_class(run[-1].tag) == "V" and canon("".join(m.form for m in run)) == stem:
                    out.append(mi + L)                       # last morpheme verb-like: 말/VX yes, 말/NNG (speech) no
        return sorted(set(out))
    out = []
    for L in range(1, MAX_RUN + 1):
        if mi + L > n:
            break
        run = ms[mi:mi + L]
        if any(m.tag.startswith("S") for m in run):
            break
        joined = canon("".join(m.form for m in run))
        surface = canon(_text_slice(sent, run[0].start, run[-1].end))
        if joined in word["alts"] or surface in word["alts"]:
            out.append(mi + L)
    return out


def _word_end_of(sent: Sentence, m: Morph) -> int:
    for w in sent.words:
        if w.start <= m.start < w.end or (m.start == m.end == w.end):
            ends = [x.end for x in w.morphs if not x.tag.startswith("S")]
            return max(ends) if ends else w.end
    return m.end


def _match_alt(alt: dict, sent: Sentence, start_mi: int):
    """Try to match one alternative with its first word at morph index start_mi.
    Returns (last_morph_index, used_ep) or None."""
    ms = sent.morphs
    # stem check (skip tense/honorific EP morphemes)
    j = start_mi - 1
    used_ep = False
    while j >= 0 and ms[j].tag == "EP":
        j -= 1
        used_ep = True
    if j < 0 or not _slot_ok(ms[j], alt["slots"]):
        return None
    pos = [start_mi]
    for wi, word in enumerate(alt["words"]):
        nxt = []
        for p in pos:
            starts = [p]
            if wi > 0 and p < len(ms) and ms[p].tag in ("JX", "MAG"):   # 수(도) 있다, 갈 수(는) 없다, 제대하려면 (아직) 멀었다
                starts.append(p + 1)
            for s in starts:
                nxt.extend(_run_word(word, sent, s))
        pos = sorted(set(nxt))
        if not pos:
            return None
    return j, max(pos) - 1, used_ep


def match_sentence(rules: list[Rule], sent: Sentence) -> list[Match]:
    found: dict[tuple[int, int, int], dict] = {}       # (item, start, end) -> info
    for rule in rules:
        for alt in rule.alts:
            first = alt["words"][0]
            for mi in range(1, len(sent.morphs)):
                if not _run_word(first, sent, mi):
                    continue
                res = _match_alt(alt, sent, mi)
                if res is None:
                    continue
                stem_idx, last_idx, used_ep = res
                start = sent.morphs[stem_idx].start
                if sent.morphs[stem_idx].tag in ("XSV", "XSA") and stem_idx > 0 and tag_class(sent.morphs[stem_idx - 1].tag) == "N":
                    start = min(start, sent.morphs[stem_idx - 1].start)     # 공부|하고 있어요 -> include 공부
                last = sent.morphs[last_idx]
                end = last.end
                if alt["words"][-1]["kind"] == "lex":
                    end = max(end, _word_end_of(sent, last))        # include endings: 있어요, 없었다
                key = (rule.item_id, start, end)
                if key not in found:
                    found[key] = {"rule": rule, "ep": used_ep, "slots": alt["slots"], "core": sent.morphs[mi].start}
    matches = _group(found, sent)
    _flag_nested(matches)
    matches.extend(_uncovered(matches, sent))
    return matches


def _flag_nested(matches: list[Match]) -> None:
    """A match that sits inside a larger one (보니까 inside 먹어 보니까) may be just part of it: never VERIFIED."""
    for m in matches:
        for big in matches:
            if big is m or not (big.start <= m.start and m.end <= big.end and (big.end - big.start) > (m.end - m.start)):
                continue
            if m.start > big.start:
                if m.status == "VERIFIED":
                    m.status, m.confidence = "LIKELY", min(m.confidence, 0.5)
                extra = f"Overlaps the larger structure '{big.dict_form}'; it may only be part of it."
                m.note = f"{m.note} {extra}" if m.note else extra
                break


def _group(found: dict, sent: Sentence) -> list[Match]:
    by_span: dict[tuple[int, int], list[dict]] = {}
    for (item_id, s, e), info in found.items():
        by_span.setdefault((s, e), []).append(info)
    out = []
    for (s, e), infos in by_span.items():
        infos.sort(key=lambda i: (-i["rule"].specificity, LEVEL_ORDER.get(i["rule"].level, 99), i["rule"].item_id))
        best = infos[0]
        rule: Rule = best["rule"]
        distinct = {i["rule"].pattern_key or i["rule"].pattern for i in infos}
        approved = rule.status in ("verified", "manual")
        if len(distinct) > 1:
            status, conf, note = "NEEDS_REVIEW", 0.4, "Several textbook grammar items match this span; check which one applies."
        elif best["ep"]:
            status, conf, note = "LIKELY", 0.7, "Related form: the textbook pattern with a tense/honorific morpheme inserted."
        elif not approved:
            status, conf, note = "LIKELY", 0.7, "Textbook entry has not been reviewed yet (imported from an uncorrected scan)."
        elif rule.weak:
            status, conf, note = "LIKELY", 0.6, "Very short form; the textbook lists several uses, so check the meaning in context."
        else:
            status, conf, note = "VERIFIED", 0.95, None
        mtype = "RELATED" if best["ep"] else "EXACT"
        out.append(Match("grammar", _text_slice(sent, s, e), s, e, sent.index, sent.paragraph, rule.pattern, rule.item_id,
                         mtype, status, conf, rule_id=str(rule.item_id),
                         candidates=[{"id": i["rule"].item_id, "pattern": i["rule"].pattern, "level": i["rule"].level,
                                      "status": i["rule"].status} for i in infos], note=note, core_start=best["core"]))
    return out


def _uncovered(matches: list[Match], sent: Sentence) -> list[Match]:
    out = []
    for m in sent.morphs:
        if m.tag not in UNCOVERED_TAGS:
            continue
        if any(x.start <= m.start and m.end <= x.end and x.status != "NOT_FOUND" for x in matches):
            continue
        a, b = m.start, max(m.end, m.start + 1)
        # fused morphemes (갈 = 가+ᆯ) share the syllable: show the whole syllable
        surface = _text_slice(sent, a, b)
        out.append(Match("grammar", surface, a, b, sent.index, sent.paragraph, m.form, None, "NONE", "NOT_FOUND", 0.0,
                         note="Ending not found in the uploaded textbook grammar database."))
    return out
