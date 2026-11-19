"""Kiwi (kiwipiepy) wrapper: the only place that talks to the morphological analyzer.

Runs fully locally. Produces paragraphs -> sentences -> eojeol words -> morphemes with
character offsets into the (NFC-normalised) passage, plus lexical units with dictionary forms.
Offsets are Python code-point indices (identical to JS string indices for Hangul/BMP text).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

PREDICATE_TAGS = {"VV", "VA", "VX", "VCN"}          # conjugating lexemes (dictionary form = stem + 다)
NOUNISH_TAGS = {"NNG", "NNP", "NP", "NR", "XR"}
OTHER_LEX_TAGS = {"MAG", "MAJ", "MM", "IC"}
DERIV_PREDICATE = {"XSV", "XSA"}                    # noun + 하/되 ... -> 공부하다
PUNCT_PREFIX = "S"                                   # SF, SP, SS*, SO, SW ...


def base_tag(tag: str) -> str:
    """'VV-R' (irregular) -> 'VV'."""
    return tag.split("-")[0]


@dataclass
class Morph:
    form: str
    tag: str          # normalised (no -R/-I suffix)
    start: int
    end: int          # exclusive; zero-length tokens (covert 이) have end == start
    raw_tag: str = ""


@dataclass
class Word:                      # an eojeol (whitespace-delimited chunk)
    start: int
    end: int
    text: str
    morphs: list[Morph] = field(default_factory=list)


@dataclass
class LexUnit:
    """A dictionary-able word found in a sentence (what the vocabulary matcher consumes)."""
    surface: str                 # text covered in the passage (stem + endings for predicates)
    start: int
    end: int
    lemma: str                   # primary dictionary form, e.g. 공부하다
    alt_lemmas: list[str]        # weaker alternatives, e.g. ['공부']
    tag: str                     # VV / VA / NNG / MAG ...
    word_index: int              # index of eojeol within the sentence
    morph_index: int             # index of the lexical morph in sentence.morphs


@dataclass
class Sentence:
    index: int
    paragraph: int
    start: int
    end: int
    text: str
    morphs: list[Morph]
    words: list[Word]
    units: list[LexUnit]


@lru_cache(maxsize=1)
def get_kiwi():
    from kiwipiepy import Kiwi  # imported lazily: heavy model load, only when analysis is requested
    return Kiwi()


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _words_of(sentence_text: str, base: int) -> list[Word]:
    return [Word(base + m.start(), base + m.end(), m.group()) for m in re.finditer(r"\S+", sentence_text)]


def _dict_form(stem: str) -> str:
    return stem if stem.endswith("다") else stem + "다"


def build_units(morphs: list[Morph], words: list[Word]) -> list[LexUnit]:
    """Collapse morphemes into lexical units with dictionary forms and surface spans."""
    units: list[LexUnit] = []
    n = len(morphs)
    word_of: list[int] = []
    for m in morphs:
        wi = next((i for i, w in enumerate(words) if w.start <= m.start < w.end or (m.start == w.end == m.end and i == len(words) - 1)), -1)
        if wi == -1:
            wi = max((i for i, w in enumerate(words) if w.start <= m.start), default=0)
        word_of.append(wi)

    def word_end_excluding_punct(wi: int) -> int:
        ends = [m.end for m, w in zip(morphs, word_of) if w == wi and not m.tag.startswith(PUNCT_PREFIX)]
        return max(ends) if ends else words[wi].end

    i = 0
    while i < n:
        m = morphs[i]
        wi = word_of[i]
        if m.tag in PREDICATE_TAGS:
            end = word_end_excluding_punct(wi)
            units.append(LexUnit(None, m.start, end, _dict_form(m.form), [], m.tag, wi, i))
        elif m.tag in NOUNISH_TAGS or m.tag in OTHER_LEX_TAGS:
            nxt = morphs[i + 1] if i + 1 < n else None
            if nxt is not None and nxt.tag in DERIV_PREDICATE and word_of[i + 1] == wi and m.tag in NOUNISH_TAGS:
                # 공부 + 하 + 고  ->  공부하다 (alt: 공부)
                end = word_end_excluding_punct(wi)
                units.append(LexUnit(None, m.start, end, m.form + _dict_form(nxt.form), [m.form], "V" if nxt.tag == "XSV" else "A", wi, i))
                i += 2
                continue
            units.append(LexUnit(None, m.start, m.end, m.form, [], m.tag, wi, i))
        i += 1
    return units


def analyze_text(text: str) -> tuple[str, list[Sentence]]:
    """Normalise and analyse a passage. Returns (normalised_text, sentences)."""
    text = normalize(text)
    kiwi = get_kiwi()
    sentences: list[Sentence] = []
    para_no = -1
    for pm in re.finditer(r"[^\n]+", text):          # each non-empty line is a paragraph
        chunk, offset = pm.group(), pm.start()
        if not chunk.strip():
            continue
        para_no += 1
        for s in kiwi.split_into_sents(chunk, return_tokens=True):
            raw = s.text
            lead = len(raw) - len(raw.lstrip())     # keep absolute offsets exact
            s_start = offset + s.start + lead
            s_text = raw.strip()
            if not s_text:
                continue
            morphs = [
                Morph(t.form, base_tag(t.tag), offset + t.start, offset + t.start + t.len, t.tag)
                for t in s.tokens
            ]
            words = _words_of(s_text, s_start)
            for mo in morphs:
                for w in words:
                    if w.start <= mo.start < w.end or (mo.start == mo.end == w.end):
                        w.morphs.append(mo)
                        break
            units = build_units(morphs, words)
            for u in units:
                u.surface = text[u.start:u.end]
            sentences.append(Sentence(len(sentences), para_no, s_start, s_start + len(s_text), s_text, morphs, words, units))
    return text, sentences


def headword_lemma_keys(headword: str) -> list[str]:
    """Lookup keys for a textbook headword such as '(이름을)부르다', '나이 /연세', '숙제를 하다'.

    A key is the space-joined sequence of content lemmas Kiwi finds, e.g. '숙제 하다'.
    """
    variants: list[str] = []
    for part in re.split(r"\s*/\s*", headword):
        part = unicodedata.normalize("NFC", part).strip()
        if not part:
            continue
        no_paren = re.sub(r"\([^)]*\)", "", part)       # optional complements: (이름을)부르다 -> 부르다
        unparen = part.replace("(", "").replace(")", "")  # 춤(을) 추다 -> 춤을 추다
        for v in (no_paren, unparen):
            v = re.sub(r"\s+", " ", v).strip(" ,.~-–")
            if v and v not in variants:
                variants.append(v)
    keys: list[str] = []
    kiwi = get_kiwi()
    for v in variants:
        if not re.search(r"[가-힣]", v):
            continue
        morphs = [Morph(t.form, base_tag(t.tag), t.start, t.start + t.len) for t in kiwi.tokenize(v)]
        words = _words_of(v, 0)
        units = build_units(morphs, words)
        lemmas = [u.lemma for u in units]
        if not v.endswith("다") and any(u.tag in PREDICATE_TAGS for u in units):
            lemmas = [v]          # 봄 (spring) is not 보다+ㅁ: a headword without 다 is a noun/adverb, keep it verbatim
        cand = " ".join(lemmas) if lemmas else v
        for k in (cand, v if " " not in v else None):
            if k and k not in keys:
                keys.append(k)
    return keys


def coarse_pos(headword: str) -> str | None:
    """Kiwi-derived coarse part of speech for a headword (labelled as a guess in the DB)."""
    v = re.sub(r"\([^)]*\)", "", headword.split("/")[0]).strip()
    if not v or not re.search(r"[가-힣]", v):
        return None
    toks = [t for t in get_kiwi().tokenize(v) if not t.tag.startswith("S")]
    if not toks:
        return None
    # last content token decides for phrases (숙제를 하다 -> verb)
    for t in reversed(toks):
        tag = base_tag(t.tag)
        if tag in ("VV", "XSV"):
            return "verb"
        if tag in ("VA", "XSA"):
            return "adjective"
        if tag == "VX":
            return "auxiliary verb"
        if tag in ("NNG", "NNP", "NR", "NP", "XR"):
            return "noun" if tag != "NP" else "pronoun"
        if tag in ("MAG", "MAJ"):
            return "adverb"
        if tag == "MM":
            return "determiner"
        if tag == "IC":
            return "interjection"
    return None
