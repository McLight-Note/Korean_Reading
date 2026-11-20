"""Small shared helpers (no NLP)."""
import re
import unicodedata

LEVELS = [f"{n}{ab}" for n in range(1, 6) for ab in "AB"]
LEVEL_ORDER = {lvl: i for i, lvl in enumerate(LEVELS)}


def plain(headword: str) -> str:
    """Glossary headword without its optional bracketed part and without spaces: '(동아리에)가입하다' -> '가입하다'."""
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", headword or ""))


def same_word(a: str, b: str) -> bool:
    """'예방' and '예방하다' are the same glossary word for our purposes (noun vs its 하다 verb)."""
    return a == b or a + "하다" == b or b + "하다" == a


def pattern_key(pattern: str) -> str:
    """Normalised key to join the same grammar point across the scanned index, the student book and manual entries."""
    s = unicodedata.normalize("NFC", pattern)
    s = re.sub(r"^\d+\s*[.)]\s*", "", s)
    return re.sub(r"[\s\-–—~‘’'\"]", "", s).lower()
