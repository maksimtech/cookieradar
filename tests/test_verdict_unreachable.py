"""
A page that never loaded is not a measurement.

When the navigation itself fails — the name does not resolve, the connection
is refused or reset, nothing answers before the timeout — the session has an
error, no status and no document. `verdict` read such a session like any
other: no trackers, no tracking cookie, so a site whose pre-consent session
never loaded came out OK, and a host that does not exist came out UNVERIFIED
with "reject button not found". Measured on 2026-11-17: www.gnu.org, whose
pre-consent session got net::ERR_CONNECTION_RESET and the other two loaded,
and an unresolvable host, which exited 2 instead of 3.

The rule now: a session with an error, no status and nothing from a document
(no title, no text, no banner, no click, no request) was not measured. Every
session like that is ERROR, NOT MEASURED, exit 3; pre-consent or post-reject
like that is never OK.
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cookieradar.cli as cli
import cookieradar.scanner as scanner
from cookieradar.law_checker import UNREACHABLE_NOTE, UNVERIFIED_NOTE, findings_of, notes_of
from cookieradar.scanner import ScanResult, SessionResult, TrackerRequest, Verdict, _run_session, verdict

RESET = "Page.goto: net::ERR_CONNECTION_RESET at https://example.com/"
UNRESOLVED = "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://nonexistent.invalid/"
runner = CliRunner()


def _loaded(name: str, *, clicked: bool = True, trackers=()) -> SessionResult:
    return SessionResult(name, status=200, consent_clicked=clicked, title="Example",
                         trackers=[TrackerRequest(f"https://{d}/t.js", d, "script", 0.0) for d in trackers])


def _all_unreachable(error: str = UNRESOLVED) -> ScanResult:
    return ScanResult(
        "https://nonexistent.invalid",
        pre_consent=SessionResult("pre-consent", error=error),
        post_accept=SessionResult("post-accept", error=error),
        post_reject=SessionResult("post-reject", error=error),
    )


# ─── the verdict ─────────────────────────────────────────────────────────────

def test_failed_pre_consent_navigation_is_not_an_ok_verdict():
    result = ScanResult(
        "https://example.com",
        pre_consent=SessionResult("pre-consent", error=RESET),
        post_accept=_loaded("post-accept"),
        post_reject=_loaded("post-reject"),
    )
    assert verdict(result) is not Verdict.OK
    assert verdict(result) is Verdict.UNVERIFIED


def test_failed_post_reject_navigation_is_not_an_ok_verdict():
    result = ScanResult(
        "https://example.com",
        pre_consent=_loaded("pre-consent", clicked=False),
        post_accept=_loaded("post-accept"),
        post_reject=SessionResult("post-reject", error=RESET, consent_clicked=False),
    )
    assert verdict(result) is Verdict.UNVERIFIED


def test_every_session_unreachable_is_error_not_unverified():
    assert verdict(_all_unreachable()) is Verdict.ERROR


def test_a_violation_measured_in_the_sessions_that_loaded_still_stands():
    """What was measured stays measured: trackers after a real rejection are a
    violation whether or not the first session loaded."""
    result = ScanResult(
        "https://example.com",
        pre_consent=SessionResult("pre-consent", error=RESET),
        post_accept=_loaded("post-accept"),
        post_reject=_loaded("post-reject", trackers=["doubleclick.net"]),
    )
    assert verdict(result) is Verdict.VIOLATION


def test_a_failed_accept_session_alone_does_not_change_a_clean_verdict():
    """The verdict does not rest on session 2."""
    result = ScanResult(
        "https://example.com",
        pre_consent=_loaded("pre-consent", clicked=False),
        post_accept=SessionResult("post-accept", error=RESET),
        post_reject=_loaded("post-reject"),
    )
    assert verdict(result) is Verdict.OK


@pytest.mark.parametrize("evidence", [
    {"title": "Example"},
    {"text": "Some page text"},
    {"banner_found": True},
    {"consent_clicked": True},
    {"trackers": [TrackerRequest("https://doubleclick.net/t.js", "doubleclick.net", "script", 0.0)]},
])
def test_a_session_with_a_document_is_not_unreachable(evidence):
    """A timeout after the page had rendered is an incomplete session, not a
    page that never loaded: the existing "may be incomplete" warning covers it."""
    session = SessionResult("pre-consent", error="Timeout 30000ms exceeded.", **evidence)
    assert not scanner.unreachable(session)


def test_an_error_with_a_status_is_not_unreachable():
    assert not scanner.unreachable(SessionResult("pre-consent", error="Timeout 30000ms exceeded.", status=200))


def test_no_error_is_not_unreachable():
    """status None and no error: nothing went wrong that anyone recorded."""
    assert not scanner.unreachable(SessionResult("pre-consent"))


# ─── the law check ───────────────────────────────────────────────────────────

def test_an_unreachable_site_cites_nothing_and_says_why():
    result = _all_unreachable()
    assert findings_of(result) == {}
    assert notes_of(result) == [UNREACHABLE_NOTE]
    assert UNVERIFIED_NOTE not in notes_of(result)


# ─── the command line ────────────────────────────────────────────────────────

def _fake(result: ScanResult):
    async def fake(url, **kwargs):
        return result
    return fake


def test_audit_of_an_unreachable_site_is_not_measured():
    with patch.object(scanner, "scan", _fake(_all_unreachable())), patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["audit", "nonexistent.invalid"])

    assert res.exit_code == 3, res.output
    assert "NOT MEASURED" in res.output
    assert "ERR_NAME_NOT_RESOLVED" in res.output
    assert "No trackers loaded after rejection" not in res.output
    assert "0 before consent" not in res.output


def test_batch_of_an_unreachable_site_is_not_measured(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("nonexistent.invalid\n", encoding="utf-8")
    with patch.object(scanner, "scan", _fake(_all_unreachable())), patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["batch", str(urls)])

    assert res.exit_code == 3, res.output
    assert "NOT MEASURED" in res.output
    assert "reject button not found" not in res.output
    assert "post-reject: 0 trackers" not in res.output


def test_audit_with_pre_consent_unreachable_is_not_ok():
    result = ScanResult(
        "https://example.com",
        pre_consent=SessionResult("pre-consent", error=RESET),
        post_accept=_loaded("post-accept"),
        post_reject=_loaded("post-reject"),
    )
    with patch.object(scanner, "scan", _fake(result)), patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["audit", "example.com"])

    assert res.exit_code == 2, res.output
    assert "No trackers loaded after rejection" not in res.output
    assert "pre-consent" in res.output.split("UNVERIFIED", 1)[1]


# ─── against a real Chromium ─────────────────────────────────────────────────

@pytest.fixture
def closed_port():
    """A port on 127.0.0.1 that nothing listens on: the connection is refused."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port


@pytest.mark.integration
async def test_a_refused_connection_leaves_an_unreachable_session(browser, closed_port):
    ctx = await browser.new_context()
    session = await _run_session(ctx, f"http://127.0.0.1:{closed_port}/", "pre-consent", timeout_ms=5000)
    await ctx.close()

    assert session.error and session.status is None
    assert scanner.unreachable(session)
    result = ScanResult(f"http://127.0.0.1:{closed_port}/", pre_consent=session,
                        post_accept=session, post_reject=session)
    assert verdict(result) is Verdict.ERROR


@pytest.mark.integration
async def test_a_page_that_loaded_is_not_unreachable(browser, site_url):
    ctx = await browser.new_context()
    session = await _run_session(ctx, f"{site_url}/banner.html", "pre-consent", timeout_ms=5000)
    await ctx.close()

    assert not scanner.unreachable(session)


def test_batch_says_which_session_was_not_measured(tmp_path):
    result = ScanResult(
        "https://example.com",
        pre_consent=_loaded("pre-consent", clicked=False),
        post_accept=_loaded("post-accept"),
        post_reject=SessionResult("post-reject", error=RESET),
    )
    urls = tmp_path / "urls.txt"
    urls.write_text("example.com\n", encoding="utf-8")
    with patch.object(scanner, "scan", _fake(result)), patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["batch", str(urls)])

    assert res.exit_code == 2, res.output
    assert "pre: 0 trackers, post-reject: not measured" in res.output
    assert "reject button not found" not in res.output
    assert "post-reject: Page.goto: net::ERR_CONNECTION_RESET" in res.output
