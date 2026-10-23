"""A verified text names the source that answered, not the act's publisher.

EU acts are downloaded from Cellar (publications.europa.eu), with EUR-Lex only as the fallback, but the report said
"verified against EUR-Lex" whichever answered (open item of the 2026-10-17 audit). Here the source travels with
the download: fetch_provisions_from returns it and the law check's status carries it.

Answers come from pages already recorded for the other law tests (gdpr_it_excerpt.html, normattiva_privacy_art122.html),
served by httpx.MockTransport at the HTTP boundary, as CLAUDE.md allows: nothing reaches the network, and every
request is seen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cookieradar import law_checker, law_fetcher
from cookieradar.law_cache import LawCache
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest

FIXTURES = Path(__file__).parent / "fixtures"
GDPR_PAGE = (FIXTURES / "gdpr_it_excerpt.html").read_text(encoding="utf-8")
ART_122_PAGE = (FIXTURES / "normattiva_privacy_art122.html").read_text(encoding="utf-8")
GDPR_CELLAR_URL = "https://publications.europa.eu/resource/celex/32016R0679"
GDPR_EURLEX_URL = "https://eur-lex.europa.eu/legal-content/IT/TXT/HTML/?uri=CELEX:32016R0679"
ART_122_URL = law_fetcher.NORMATTIVA_URL.format(urn=law_fetcher.PRIVACY_CODE.celex, article="122")
NOW = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)
REAL_FETCH_HTML = law_fetcher.fetch_html


def _session(name: str, domains: tuple[str, ...], clicked: bool) -> SessionResult:
    return SessionResult(session=name, consent_clicked=clicked,
                         trackers=[TrackerRequest(f"https://{d}/t.js", d, "script", 0.0) for d in domains])


# A tracker loaded after the refusal: a violation, citing the GDPR (from Cellar) among others
TRACKED_AFTER_REFUSAL = ScanResult(
    url="https://example.com",
    pre_consent=_session("pre-consent", (), clicked=False),
    post_accept=_session("post-accept", (), clicked=True),
    post_reject=_session("post-reject", ("google-analytics.com",), clicked=True),
)


@pytest.fixture
def real_fetch(monkeypatch):
    """conftest disables fetch_html so that no test reaches the network; the clients below answer only from the
    recordings, so the real function goes back."""
    monkeypatch.setattr(law_fetcher, "fetch_html", REAL_FETCH_HTML)


def recorded(pages: dict[str, str], seen: list[str]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url) in pages:
            return httpx.Response(200, text=pages[str(request.url)])
        return httpx.Response(503)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_cellar_is_named_when_cellar_answered(real_fetch):
    seen: list[str] = []
    provisions, source = law_fetcher.fetch_provisions_from(
        law_fetcher.GDPR, ("6",), now=NOW, client=recorded({GDPR_CELLAR_URL: GDPR_PAGE}, seen))
    assert source == "Cellar"
    assert "6" in provisions
    assert seen == [GDPR_CELLAR_URL]


def test_eur_lex_is_named_when_only_the_fallback_answered(real_fetch):
    seen: list[str] = []
    _, source = law_fetcher.fetch_provisions_from(
        law_fetcher.GDPR, ("6",), now=NOW, client=recorded({GDPR_EURLEX_URL: GDPR_PAGE}, seen))
    assert source == "EUR-Lex"
    assert seen == [GDPR_CELLAR_URL, GDPR_EURLEX_URL]


def test_normattiva_is_named_for_an_italian_act(real_fetch):
    seen: list[str] = []
    _, source = law_fetcher.fetch_provisions_from(
        law_fetcher.PRIVACY_CODE, ("122",), now=NOW, client=recorded({ART_122_URL: ART_122_PAGE}, seen))
    assert source == "Normattiva"
    assert seen == [ART_122_URL]


def test_the_law_check_status_carries_the_source(real_fetch, tmp_path):
    seen: list[str] = []
    result = TRACKED_AFTER_REFUSAL
    law = law_checker.check(result, cache=LawCache(tmp_path / "law_cache.json"), now=NOW,
                            client=recorded({GDPR_CELLAR_URL: GDPR_PAGE}, seen))
    gdpr = next(status for status in law.acts if status.act == law_fetcher.GDPR)
    assert (gdpr.source, gdpr.origin) == ("verified", "Cellar")


def test_a_text_from_the_cache_names_no_source(real_fetch, tmp_path):
    cache = LawCache(tmp_path / "law_cache.json")
    result = TRACKED_AFTER_REFUSAL
    law_checker.check(result, cache=cache, now=NOW, client=recorded({GDPR_CELLAR_URL: GDPR_PAGE}, []))
    law = law_checker.check(result, cache=cache, now=NOW, client=recorded({}, []))
    gdpr = next(status for status in law.acts if status.act == law_fetcher.GDPR)
    assert (gdpr.source, gdpr.origin) == ("cache", None)
