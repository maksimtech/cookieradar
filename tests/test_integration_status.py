"""
The status of a document that never goes idle, against a real Chromium.

`page.goto(wait_until="networkidle")` returns the response only when the wait
succeeds. When the page keeps the network busy the call raises a timeout and
returns nothing, and the status — which had arrived in the first second — was
lost with it. Measured on 2026-10-09 (the demo audits in _analisi/demo/cookieradar):

- zalando.it answered 403 from its edge with a full page whose scripts never went
  quiet. Status None, so `page_not_served` saw nothing wrong, and the audit said
  "0 trackers before consent, UNVERIFIED" about an error page it never had.
- enel.it and poste.it were served with 200 and never went idle either: status
  None in every session, reported alongside the trackers that were measured.

tests/site/forbidden_busy.html reproduces the first; the test server serves it
with 403 under /forbidden/. never_idle.html is the second.
"""
import pytest

from cookieradar.scanner import ScanResult, _run_session, page_not_served


@pytest.mark.integration
async def test_a_403_page_that_never_goes_idle_keeps_its_status(browser, site_url):
    ctx = await browser.new_context()
    result = await _run_session(ctx, f"{site_url}/forbidden/forbidden_busy.html", "pre-consent", timeout_ms=1500)
    await ctx.close()

    assert "Timeout" in result.error
    assert result.status == 403
    assert page_not_served(ScanResult(url=site_url, pre_consent=result))


@pytest.mark.integration
async def test_a_served_page_that_never_goes_idle_keeps_its_status(browser, site_url):
    ctx = await browser.new_context()
    result = await _run_session(ctx, f"{site_url}/never_idle.html", "pre-consent", timeout_ms=1500)
    await ctx.close()

    assert "Timeout" in result.error
    assert result.status == 200


@pytest.mark.integration
async def test_the_status_is_the_last_hop_of_a_redirect(browser, site_url):
    """A redirect answers twice. The document is the second answer."""
    ctx = await browser.new_context()
    await ctx.route(f"{site_url}/moved", lambda route: route.fulfill(
        status=302, headers={"Location": f"{site_url}/never_idle.html"}, body=""))
    result = await _run_session(ctx, f"{site_url}/moved", "pre-consent", timeout_ms=1500)
    await ctx.close()

    assert "Timeout" in result.error
    assert result.status == 200
