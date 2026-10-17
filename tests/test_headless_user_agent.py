"""
CookieRadar — the browser does not announce that it is headless (audit F-02)

Playwright's headless Chromium says so in its User-Agent ("HeadlessChrome/153…"),
and some consent platforms answer by showing no banner. Measured on subito.it on
2026-10-17, twice: with that User-Agent the Didomi notice was never mounted, with
"Chrome/153…" from the same browser it was, "Continua senza accettare →" first.
`cookieradar audit https://www.subito.it` therefore said UNVERIFIED — "no
refusal could be applied" — about a site that offers one, and that kept
contacting doubleclick.net after it. The README listed it among the limits
("retry with --no-headless"), which is no remedy inside the Docker image.

The sessions now use the browser's own User-Agent with "HeadlessChrome" written
as "Chrome", which is what the same build says when it has a window, and the
report states the User-Agent the site was shown — a report is evidence, and
which browser the site believed it was talking to is part of it.

`tests/site/didomi_subito_ua_gate.html` is the notice captured that day, mounted
only for a browser that does not say it is headless (derived; see its comment).
Skipped when Playwright browsers are not installed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pytest
from rich.console import Console

from cookieradar.cli import _render_report
from cookieradar.scanner import ScanResult, scan


@pytest.mark.integration
async def test_a_banner_shown_only_to_a_browser_that_is_not_headless_is_seen(browser, site_url):
    """Both choices are reached once the notice is mounted. (Whether the "Banner
    found" hint recognises Didomi's markup is audit finding F-03, not this.)"""
    result = await scan(f"{site_url}/didomi_subito_ua_gate.html")

    assert result.post_reject.consent_clicked is True
    assert result.post_accept.consent_clicked is True


@pytest.mark.integration
async def test_the_user_agent_the_site_was_shown_is_kept_and_says_chrome(browser, site_url):
    result = await scan(f"{site_url}/didomi_subito_ua_gate.html")

    assert "Chrome/" in result.user_agent
    assert "Headless" not in result.user_agent


@pytest.mark.integration
async def test_it_is_the_browser_s_own_user_agent_not_an_invented_one(browser, site_url):
    """The version is the build's own: a fixed string would date, and a
    report would then name a browser that never ran."""
    result = await scan(f"{site_url}/didomi_subito_ua_gate.html")

    assert browser.version.split(".")[0] in result.user_agent


def test_the_report_states_the_user_agent():
    result = ScanResult(url="https://www.subito.it")
    result.scanned_at = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
    result.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/153.0.8010.12 Safari/537.36"
    out = Console(file=StringIO(), width=400, color_system=None)

    _render_report(out, result.url, result)

    assert "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/153.0.8010.12" in out.file.getvalue()


def test_a_report_without_one_says_nothing_about_it():
    """A result built before this field, or by a test, has no User-Agent; the
    report must not print an empty one."""
    out = Console(file=StringIO(), width=400, color_system=None)

    _render_report(out, "https://example.com", ScanResult(url="https://example.com"))

    assert "User-Agent" not in out.file.getvalue()
