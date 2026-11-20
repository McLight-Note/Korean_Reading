"""No AI SDKs or keys anywhere. The server makes no outbound requests at all; the only external call is the browser asking
Google Translate for a translation (public/translate.js), and it is the only front-end file allowed to name a remote host."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(openai|anthropic|google\.generativeai|google\.genai|cohere|mistralai|langchain|ollama|api[_-]?key)\b", re.I)
NETWORK = re.compile(r"\b(requests|urllib\.request|http\.client|aiohttp|httpx)\b|fetch\(\s*[\"']https?:")


def test_no_ai_sdk_or_keys():
    offenders = []
    # public/firebase-config.js documents Firebase's public web-app `apiKey` (an identifier, not a secret or an AI key)
    allowed = {ROOT / "public" / "firebase-config.js"}
    for p in list((ROOT / "backend").rglob("*.py")) + [*ROOT.glob("requirements*.txt"), *(ROOT / "public").glob("*")]:
        if p in allowed:
            continue
        if FORBIDDEN.search(p.read_text(encoding="utf-8")):
            offenders.append(str(p))
    assert not offenders


def test_backend_makes_no_outbound_requests():
    offenders = [str(p) for p in (ROOT / "backend").rglob("*.py") if NETWORK.search(p.read_text(encoding="utf-8"))]
    assert not offenders


def test_only_translate_js_talks_to_other_hosts():
    allowed_hosts = re.compile(r"https?://(translate\.googleapis\.com|translate\.google\.com|www\.gstatic\.com|www\.googleapis\.com|www\.google\.com|[a-z0-9-]+\.firebaseapp\.com|[a-z0-9-]+\.firebaseio\.com|firestore\.googleapis\.com|identitytoolkit\.googleapis\.com|securetoken\.googleapis\.com|localhost|127\.0\.0\.1|www\.w3\.org)")
    bad = []
    for p in (ROOT / "public").glob("*.js"):
        for url in re.findall(r"https?://[^\s\"'`)]+", p.read_text(encoding="utf-8")):
            if not allowed_hosts.match(url):
                bad.append((p.name, url))
    assert not bad, bad
    # Google Translate is called from the browser file only, never from the server
    assert "translate.googleapis.com" in (ROOT / "public" / "translate.js").read_text(encoding="utf-8")
    assert not [p for p in (ROOT / "backend").rglob("*.py") if "translate.google" in p.read_text(encoding="utf-8")]
