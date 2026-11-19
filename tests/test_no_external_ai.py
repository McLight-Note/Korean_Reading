"""The platform must stay self-contained: no AI SDKs, no network calls in the code base."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(openai|anthropic|google\.generativeai|google\.genai|cohere|mistralai|langchain|ollama|api[_-]?key)\b", re.I)
NETWORK = re.compile(r"\b(requests|urllib\.request|http\.client|aiohttp|httpx)\b|fetch\(\s*[\"']https?:")


def test_no_ai_sdk_or_keys():
    offenders = []
    for p in list((ROOT / "backend").rglob("*.py")) + [ROOT / "requirements.txt", *(ROOT / "frontend").glob("*")]:
        if FORBIDDEN.search(p.read_text(encoding="utf-8")):
            offenders.append(str(p))
    assert not offenders


def test_backend_makes_no_outbound_requests():
    offenders = [str(p) for p in (ROOT / "backend").rglob("*.py") if NETWORK.search(p.read_text(encoding="utf-8"))]
    assert not offenders
