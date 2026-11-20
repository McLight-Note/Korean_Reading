"""The story file format, its checker and the publish script (the Firestore writing itself is covered by the emulator test)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_stories  # noqa: E402
import storylib  # noqa: E402


def make(text, tv, tg, **over):
    plain, hl = storylib.parse_markup(text)
    s = {"id": "3a-99-test", "level": "3A", "title": "제목", "summary_en": "A test.", "marked": text, "text": plain, "highlights": hl,
         "target_vocab": tv, "target_grammar": tg, "questions": [{"q": "질문?", "a": "답"}]}
    s.update(over)
    return s


LONG = "저는 매일 아침에 일찍 일어나서 운동을 합니다. 그리고 학교에 가서 친구들을 만납니다. " * 2


def test_markup_gives_plain_text_and_utf16_spans():
    plain, hl = storylib.parse_markup("😀 [[영화를|영화]] <<봤어요|V+았어요>>")
    assert plain == "😀 영화를 봤어요"
    u = plain.encode("utf-16-le")
    assert [u[2 * h["start"]:2 * h["end"]].decode("utf-16-le") for h in hl] == ["영화를", "봤어요"]
    assert [(h["kind"], h["ref"]) for h in hl] == [("vocab", "영화"), ("grammar", "V+았어요")]


def test_a_good_story_has_no_problems():
    s = make(f"[[동아리|동아리]]에 <<가고 싶지만|V+지만>> 늦었어요. {LONG}", ["동아리"], ["V+지만"])
    assert storylib.problems(s, "3a-99-test") == []


def test_problems_are_reported_in_plain_words():
    s = make(f"[[동아리|동아리]] [[낯선|없는]] <<싶지만|V+지만>> {LONG}", ["동아리", "가입하다"], ["V+지만", "V+고 있다"], id="Bad Id", level="9Z")
    msg = " | ".join(storylib.problems(s, "other-name"))
    assert "id must be lowercase" in msg and "does not match the file name" in msg and "unknown level" in msg
    s = make(f"[[동아리|동아리]] [[낯선|없는]] <<싶지만|V+지만>> {LONG}", ["동아리", "가입하다"], ["V+지만", "V+고 있다"])
    msg = " | ".join(storylib.problems(s, "3a-99-test"))
    assert "vocab target is never marked in the text: 가입하다" in msg
    assert "grammar target is never marked in the text: V+고 있다" in msg
    assert "vocab mark refers to something not in target_vocab: 없는" in msg


def test_marks_may_not_touch_spaces_and_leftover_markup_is_caught():
    s = make(f"[[ 동아리 |동아리]] {LONG}", ["동아리"], ["V+지만"])
    assert any("space at its edge" in p for p in storylib.problems(s))
    s = make(f"[[동아리 {LONG}", ["x"], ["y"])
    assert any("unparsed markup" in p or "never marked" in p for p in storylib.problems(s))


def test_firestore_document_shape():
    s = make(f"[[동아리|동아리]] <<싶지만|V+지만>> {LONG}", ["동아리"], ["V+지만"], theme="Life", units=[1])
    doc = storylib.firestore_doc(s)
    assert set(doc) == {"level", "title", "theme", "units", "summary_en", "text", "highlights", "target_vocab", "target_grammar", "questions", "chars"}
    assert doc["chars"] == len(doc["text"]) and "[[" not in doc["text"] and len(doc["highlights"]) == 2
    json.dumps(doc, ensure_ascii=False)                                   # plain data only: Firestore accepts it as is


def test_all_shipped_stories_pass():
    stories = publish_stories.check("")
    assert len(stories) >= 15 and all(storylib.problems(s) == [] for s in stories)


def test_dry_run_publishes_nothing_and_needs_no_key(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(publish_stories, "client", lambda *a: pytest.fail("a dry run must not connect to Firebase"))
    assert publish_stories.main(["--dry-run"]) == 0


def test_missing_key_gives_instructions(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(SystemExit, match="Service-account key not found"):
        publish_stories.client(str(tmp_path / "nope.json"), None)


def test_broken_story_blocks_publishing(tmp_path, monkeypatch):
    (tmp_path / "x.json").write_text(json.dumps({"id": "x", "level": "3A"}), encoding="utf-8")
    monkeypatch.setattr(storylib, "STORIES_DIR", tmp_path)
    with pytest.raises(SystemExit, match="Nothing was published"):
        publish_stories.check("")


def test_no_secrets_are_deployed_or_committed():
    root = Path(__file__).resolve().parents[1]
    for name in (".gitignore", ".vercelignore"):
        assert "secrets" in (root / name).read_text(encoding="utf-8"), name
    assert not list((root / "public").glob("*.json")), "no key or data files in the deployed folder"
