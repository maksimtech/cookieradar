"""Tests for the law check that `cookieradar audit` runs."""
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cookieradar import law_fetcher
from cookieradar.cli import app
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest

FIXTURES = Path(__file__).parent / "fixtures"
GDPR_PAGE = FIXTURES / "gdpr_it_excerpt.html"
EPRIVACY_PAGE = FIXTURES / "eprivacy_it_consolidated_excerpt.html"
runner = CliRunner()


def _session(name, domains, clicked=True):
    return SessionResult(
        session=name,
        trackers=[TrackerRequest(f"https://{d}/t.js", d, "script", 0.0) for d in domains],
        consent_clicked=clicked,
    )


def scan_result(rejected=(), clicked=True):
    return ScanResult(
        url="https://example.com/",
        pre_consent=_session("pre-consent", ["doubleclick.net"], clicked=False),
        post_accept=_session("post-accept", [], clicked=clicked),
        post_reject=_session("post-reject", rejected, clicked=clicked),
    )


def _sha(page, articles, ref):
    text = law_fetcher.parse_articles(page.read_text(encoding="utf-8"), articles)[ref]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def eurlex(monkeypatch):
    calls = []

    def fake_fetch_html(url, **kwargs):
        calls.append(url)
        page = EPRIVACY_PAGE if "02002L0058" in url else GDPR_PAGE
        return page.read_text(encoding="utf-8")

    monkeypatch.setattr(law_fetcher, "fetch_html", fake_fetch_html)
    return calls


def _audit(result, *args):
    async def fake_scan(url, headless=True):
        return result

    with patch("cookieradar.scanner.scan", fake_scan):
        return runner.invoke(app, ["audit", "https://example.com", *args])


def test_violation_cites_gdpr_eprivacy_and_article_7(eurlex):
    out = _audit(scan_result(rejected=["doubleclick.net"]))

    assert out.exit_code == 1, out.output   # VIOLATION, unchanged
    assert "Norme applicate" in out.output
    assert "Norma applicata: GDPR art. 5(1)(a)" in out.output
    assert f"SHA256: {_sha(GDPR_PAGE, ('5',), '5(1)(a)')}" in out.output
    assert "Norma applicata: ePrivacy dir. 2002/58/CE art. 5(3)" in out.output
    assert f"SHA256: {_sha(EPRIVACY_PAGE, ('5',), '5(3)')}" in out.output
    assert "Norma applicata: GDPR art. 7\n" in out.output
    assert f"SHA256: {_sha(GDPR_PAGE, ('7',), '7')}" in out.output
    assert "testo consolidato al 19.12.2009" in out.output
    assert len(eurlex) == 2


def test_clean_site_cites_nothing(eurlex):
    out = _audit(scan_result(rejected=[]))

    assert out.exit_code == 0
    assert "Norma applicata" not in out.output
    assert eurlex == []


def test_unverified_prints_note_and_cites_nothing(eurlex):
    out = _audit(scan_result(rejected=["doubleclick.net"], clicked=False))

    assert out.exit_code == 2   # UNVERIFIED, unchanged
    assert "banner dei cookie o pulsante di rifiuto non trovato" in out.output
    assert "Norma applicata" not in out.output
    assert eurlex == []


def test_saved_report_contains_the_citations(eurlex, tmp_path):
    report = tmp_path / "report.txt"
    out = _audit(scan_result(rejected=["doubleclick.net"]), "--output", str(report))

    saved = report.read_text(encoding="utf-8")
    assert f"SHA256: {_sha(EPRIVACY_PAGE, ('5',), '5(3)')}" in saved
    # The saved report reuses the audit's check: EUR-Lex is not downloaded again
    assert len(eurlex) == 2
    assert out.exit_code == 1


def test_offline_without_cache():
    # conftest makes every download fail
    out = _audit(scan_result(rejected=["doubleclick.net"]))

    assert out.exit_code == 1
    assert "SHA256: non disponibile" in out.output


def test_law_check_failure_does_not_change_verdict(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("cookieradar.law_checker.check", boom)
    out = _audit(scan_result(rejected=["doubleclick.net"]))

    assert out.exit_code == 1
    assert "unexpected" in out.output
