"""
A refusal whose reload failed measured nothing after the refusal.

Session 3 clicks "Reject", then reloads the page and records what the reloaded
page contacts. When the reload fails with anything but a timeout — the
connection reset or aborted, the name gone — Playwright raises, the session
records the error and stops. The status of the first load is still there and
the click happened, so the session looked like any measured one: no trackers
after the refusal, verdict OK, "No trackers loaded after rejection". It had
measured the two seconds after the click and nothing of the page it exists to
measure.

persist.html loads doubleclick.net on every load, refusal or not: a reload that
worked finds it. Here the reload is aborted with ERR_CONNECTION_RESET by
`context.route`, against the conftest site, so nothing leaves the machine.
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cookieradar.cli as cli
import cookieradar.scanner as scanner
from cookieradar.law_checker import RELOAD_FAILED_NOTE, findings_of, notes_of
from cookieradar.scanner import ScanResult, SessionResult, Verdict, _run_session, verdict

TRACKERS = re.compile(r"^https?://[^/]*(doubleclick\.net|facebook\.com)/")
RESET = "Page.reload: net::ERR_CONNECTION_RESET at http://127.0.0.1/persist.html"
runner = CliRunner()


async def _post_reject_with_failed_reload(browser, url):
    """Session 3 against `url`, whose second load (the reload) is reset."""
    ctx = await browser.new_context()
    await ctx.route(TRACKERS, lambda route: route.fulfill(status=200, body="ok"))
    loads = []

    async def first_load_only(route):
        loads.append(route.request.url)
        if len(loads) == 1:
            await route.continue_()
        else:
            await route.abort("connectionreset")

    await ctx.route(url, first_load_only)
    session = await _run_session(ctx, url, "post-reject", accept=False, timeout_ms=5000)
    await ctx.close()
    return session, loads


def _with_post_reject(session: SessionResult) -> ScanResult:
    return ScanResult(
        "https://example.com",
        pre_consent=SessionResult("pre-consent", status=200, title="Example", banner_found=True),
        post_accept=SessionResult("post-accept", status=200, consent_clicked=True, banner_found=True),
        post_reject=session,
    )


def _failed_reload() -> SessionResult:
    """What the real session below records: clicked, status of the first load,
    the reload's error, nothing after the click."""
    return SessionResult("post-reject", status=200, title="Example", banner_found=True,
                         consent_clicked=True, error=RESET, reload_failed=True)


@pytest.mark.integration
async def test_the_session_records_that_the_reload_failed(browser, site_url):
    session, loads = await _post_reject_with_failed_reload(browser, f"{site_url}/persist.html")

    assert len(loads) == 2, loads                      # the reload was attempted
    assert session.consent_clicked is True
    assert session.status == 200                       # the first load's
    assert "ERR_CONNECTION_RESET" in (session.error or "")
    assert session.trackers == []                      # nothing measured after the click
    assert session.reload_failed is True


@pytest.mark.integration
async def test_a_failed_reload_is_not_an_ok_verdict(browser, site_url):
    session, _ = await _post_reject_with_failed_reload(browser, f"{site_url}/persist.html")

    assert verdict(_with_post_reject(session)) is Verdict.UNVERIFIED


@pytest.mark.integration
async def test_a_reload_that_worked_is_unchanged(browser, site_url):
    ctx = await browser.new_context()
    await ctx.route(TRACKERS, lambda route: route.fulfill(status=200, body="ok"))
    session = await _run_session(ctx, f"{site_url}/persist.html", "post-reject", accept=False, timeout_ms=5000)
    await ctx.close()

    assert session.reload_failed is False
    assert verdict(_with_post_reject(session)) is Verdict.VIOLATION


def test_trackers_seen_after_the_click_before_the_failure_are_still_a_violation():
    """What was measured after the refusal stays measured."""
    session = _failed_reload()
    session.trackers = [scanner.TrackerRequest("https://connect.facebook.net/tr", "facebook.net", "image", 0.0)]

    assert verdict(_with_post_reject(session)) is Verdict.VIOLATION


def test_the_law_check_cites_nothing_and_says_why():
    result = _with_post_reject(_failed_reload())

    assert findings_of(result) == {}
    assert notes_of(result) == [RELOAD_FAILED_NOTE]


def _fake(result):
    async def fake(url, **kwargs):
        return result
    return fake


def test_audit_says_session_3_measured_nothing_after_the_refusal():
    with patch.object(scanner, "scan", _fake(_with_post_reject(_failed_reload()))), \
            patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["audit", "example.com"])

    text = " ".join(res.output.split())
    assert res.exit_code == 2, res.output
    assert "No trackers loaded after rejection" not in text
    assert "Nothing cited after rejection" not in text
    assert "UNVERIFIED — the post-reject session could not reload the page after the refusal" in text
    assert "ERR_CONNECTION_RESET" in text
    # Session 3's own table does not tick a page it never saw
    session_3 = text.split("Session 3", 1)[1].split("UNVERIFIED", 1)[0]
    assert "No trackers detected" not in session_3
    assert "the page could not be reloaded after the refusal" in session_3


def test_batch_says_session_3_measured_nothing_after_the_refusal(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("example.com\n", encoding="utf-8")
    with patch.object(scanner, "scan", _fake(_with_post_reject(_failed_reload()))), \
            patch.object(cli, "console", Console(width=250)):
        res = runner.invoke(cli.app, ["batch", str(urls)])

    text = " ".join(res.output.split())
    assert res.exit_code == 2, res.output
    assert "OK" not in text.split("Auditing", 1)[1].split("post-reject:", 1)[0]
    assert "post-reject: not measured" in text
    assert "the page could not be reloaded after the refusal" in text
