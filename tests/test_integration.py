"""
Integration tests against a local site with a real Chromium.
Tracker hosts are fulfilled locally via context.route, no network needed.
Skipped when Playwright browsers are not installed.
"""
import re

import pytest

from cookieradar.scanner import _run_session

TRACKER_HOSTS = re.compile(r"^https?://[^/]*(doubleclick\.net|facebook\.com)/")


async def _context(browser):
    ctx = await browser.new_context()
    await ctx.route(TRACKER_HOSTS, lambda route: route.fulfill(status=200, body="ok"))
    return ctx


@pytest.mark.integration
async def test_compliant_site_has_no_post_reject_trackers(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/reject.html", "post-reject", accept=False)
    await ctx.close()

    assert result.trackers == []


@pytest.mark.integration
async def test_non_compliant_site_reports_trackers_after_reject(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/persist.html", "post-reject", accept=False)
    await ctx.close()

    assert {t.domain for t in result.trackers} == {"stats.doubleclick.net", "www.facebook.com"}


@pytest.mark.integration
async def test_never_idle_page_times_out_without_raising(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/never_idle.html", "pre-consent", timeout_ms=1500)
    await ctx.close()

    assert "Timeout" in result.error
    assert {t.domain for t in result.trackers} == {"stats.doubleclick.net"}
    assert result.banner_found is True


async def _clicked(ctx):
    return {c["name"]: c["value"] for c in await ctx.cookies()}.get("clicked")


@pytest.mark.integration
async def test_accept_clicks_accept_button_not_substring_matches(browser, site_url):
    ctx = await _context(browser)
    await _run_session(ctx, f"{site_url}/accept.html", "post-accept", accept=True)
    clicked = await _clicked(ctx)
    await ctx.close()

    assert clicked == "accept"


@pytest.mark.integration
async def test_reject_clicks_first_visible_exact_match(browser, site_url):
    ctx = await _context(browser)
    await _run_session(ctx, f"{site_url}/reject_buttons.html", "post-reject", accept=False)
    clicked = await _clicked(ctx)
    await ctx.close()

    assert clicked == "reject"
