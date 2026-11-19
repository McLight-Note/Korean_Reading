"""Compile textbook grammar notation (e.g. 'V+(으)ㄹ 수 있다', 'A/V+(으)ㄴ/는데(요)') into match rules.

A rule is JSON-serialisable:
  {"alts": [ {"slots": ["V","A"], "words": [ {"kind":"func","alts":["ᆯ","을"]},
                                              {"kind":"func","alts":["수"]},
                                              {"kind":"lex","morphs":[["있","V"]]} ] } ]}

Words are matched against Kiwi morphemes (see grammar_matcher). Nothing here is learned from an
external model: allomorph expansion is plain rules; lexical words are probed with local Kiwi.
Returns None when the notation can't be compiled reliably -> the item stays manual-only.
"""
from __future__ import annotations

import itertools
import re
import unicodedata

from .korean_analyzer import base_tag, get_kiwi

FINALS = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"      # order of Hangul final jamo / jongseong 1..27
COMPAT_FINAL = {c: chr(0x11A8 + i) for i, c in enumerate(FINALS)}
JONG_INDEX = {c: i + 1 for i, c in enumerate(FINALS)}
SLOT_RE = re.compile(r"^\s*([AVN](?:\s*/\s*[AVN])*)\s*[+=＋]\s*(.*)$")
ALT_SPLIT = re.compile(r"/(?=\s*[AVN](?:\s*/\s*[AVN])*\s*[+=＋])")
LEXICAL_TAGS = ("V", "N", "M", "X")


def _is_syllable(ch: str) -> bool:
    return "가" <= ch <= "힣"


def tag_class(tag: str) -> str:
    t = base_tag(tag)
    if t.startswith("V") or t in ("XSV", "XSA"):
        return "V"
    if t.startswith("N") or t in ("XR", "XSN"):
        return "N"
    return t


def canon(s: str) -> str:
    """Neutralise vowel-harmony allomorphs (아/어/여, 았/었/였) and whitespace; Kiwi emits either."""
    return s.replace(" ", "").replace("아", "어").replace("여", "어").replace("았", "었").replace("였", "었")


def merge_jamo(s: str) -> str:
    """'으ㄹ' -> '을'; a leading/lone consonant jamo -> Kiwi-style final jamo ('ㄹ' -> 'ᆯ')."""
    out: list[str] = []
    for ch in s:
        if ch in JONG_INDEX:
            if out and _is_syllable(out[-1]) and (ord(out[-1]) - 0xAC00) % 28 == 0:
                out[-1] = chr(ord(out[-1]) + JONG_INDEX[ch])
            else:
                out.append(COMPAT_FINAL[ch])
        else:
            out.append(ch)
    return "".join(out)


def _expand_optional(word: str) -> list[str]:
    """'(으)ㄴ데(요)' -> every combination of the parenthesised optional pieces."""
    parts = re.split(r"(\([^)]*\))", word)
    choices = []
    for p in parts:
        if p.startswith("(") and p.endswith(")"):
            choices.append([p[1:-1], ""])
        else:
            choices.append([p])
    return ["".join(c) for c in itertools.product(*choices)]


def _slash_alternatives(word: str) -> list[str]:
    """'ㄴ/는다고' -> ['ㄴ다고','는다고'] by propagating the shared tail of the last part to the others."""
    parts = [p.strip() for p in word.split("/") if p.strip()]
    if len(parts) < 2:
        return parts or [word]
    core_len = len(re.sub(r"\([^)]*\)", "", parts[0]))
    last = parts[-1]
    last_plain = re.sub(r"\([^)]*\)", "", last)
    tail = ""
    if core_len and len(last_plain) > core_len and all(len(re.sub(r"\([^)]*\)", "", p)) <= core_len for p in parts[:-1]):
        units = re.findall(r"\([^)]*\)|.", last)       # keep (optional) groups intact
        seen = 0
        for i, u in enumerate(units):
            if not u.startswith("("):
                seen += 1
            if seen == core_len:
                tail = "".join(units[i + 1:])
                break
    if tail:
        base_last = last[: len(last) - len(tail)]
        return [p + tail for p in parts[:-1]] + [base_last + tail]
    return parts


def word_forms(word: str) -> list[str]:
    forms: list[str] = []
    for alt in _slash_alternatives(word):
        for e in _expand_optional(alt):
            f = canon(merge_jamo(e.strip("-~")))
            if f and f not in forms:
                forms.append(f)
    return forms


def _probe_lexical(word: str):
    """For dictionary-form words (있다, 몰랐다, 하다, 보다) ask local Kiwi for the content morphemes."""
    toks = [(t.form, t.tag) for t in get_kiwi().tokenize(word)]
    while toks and base_tag(toks[-1][1]) in ("EF", "EC") and toks[-1][0] in ("다",):
        toks.pop()
    if not toks or tag_class(toks[0][1]) not in ("V", "N"):
        return None
    if any(base_tag(t).startswith("S") for _, t in toks):
        return None
    return [[canon(f), tag_class(t) if base_tag(t) != "EP" else "EP"] for f, t in toks]


def compile_word(word: str):
    word = word.strip()
    if not word:
        return None
    plain = re.sub(r"\([^)]*\)", "", word)
    if plain.endswith("다") and len(plain) >= 2 and _is_syllable(plain[0]) and "/" not in plain:
        morphs = _probe_lexical(re.sub(r"[()]", "", word))
        if morphs is None:
            return None
        return {"kind": "lex", "morphs": morphs}
    forms = word_forms(word)
    if not forms:
        return None
    return {"kind": "func", "alts": forms}


def compile_pattern(pattern: str) -> dict | None:
    s = unicodedata.normalize("NFC", pattern).strip()
    s = re.sub(r"^\d+\s*[.)]\s*", "", s)
    s = s.replace("＋", "+")
    chunks, last = [], 0
    for m in ALT_SPLIT.finditer(s):
        if re.fullmatch(r"\s*[AVN](?:\s*/\s*[AVN])*\s*", s[last:m.start()]):
            continue                                      # that '/' belongs to the slot itself (A/V+...)
        chunks.append(s[last:m.start()])
        last = m.end()
    chunks.append(s[last:])
    alts = []
    for chunk in chunks:
        m = SLOT_RE.match(chunk)
        if not m:
            return None                                   # no V/A/N+ prefix: can't detect reliably
        slots = sorted(set(re.findall(r"[AVN]", m.group(1))))
        words_src = [w for w in re.split(r"\s+", m.group(2).strip()) if w]
        alts.append((slots, words_src))
    if not alts or any(not w for _, w in alts):
        return None
    # 'A+다고/V+ㄴ다고/N+(이)라고 하다': words after the first one belong to every alternative
    longest = max(alts, key=lambda a: len(a[1]))
    for slots, words in alts:
        if len(words) == 1 and len(longest[1]) > 1 and words is not longest[1]:
            words.extend(longest[1][1:])
    compiled = []
    for slots, words in alts:
        cw = [compile_word(w) for w in words]
        if any(w is None for w in cw):
            return None
        compiled.append({"slots": slots, "words": cw})
    return {"alts": compiled}


def pattern_key(pattern: str) -> str:
    """Normalised key to join the same grammar point across index / student book / manual entries."""
    s = unicodedata.normalize("NFC", pattern)
    s = re.sub(r"^\d+\s*[.)]\s*", "", s)
    return re.sub(r"[\s\-–—~‘’'\"]", "", s).lower()
