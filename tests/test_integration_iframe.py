"""
CookieRadar — a consent banner rendered inside an iframe (#96)

Sourcepoint renders its message in an iframe: on theguardian.com on 2026-11-27,
`#sp_message_iframe_1533641`, titled "SP Consent Message", holding "Accept all" and
"Reject all and subscribe". The scanner looked for the banner and its buttons in
the page's main frame only, so it saw neither: no banner, no refusal, no note of
the paywall, and the run ended UNVERIFIED where "Reject all and subscribe" should
have given the pay-to-refuse note.

The pages in tests/site/ say where each comes from. Skipped when Playwright
browsers are not installed.
"""
import pytest

from cookieradar.scanner import _run_session


async def _clicked(ctx):
    return {c["name"]: c["value"] for c in await ctx.cookies()}.get("clicked")


async def _session(browser, url, accept):
    ctx = await browser.new_context()
    name = {True: "post-accept", False: "post-reject", None: "pre-consent"}[accept]
    result = await _run_session(ctx, url, name, accept=accept)
    clicked = await _clicked(ctx)
    await ctx.close()
    return result, clicked


@pytest.mark.integration
async def test_the_banner_in_an_iframe_is_found(browser, site_url):
    result, _ = await _session(browser, f"{site_url}/sourcepoint_guardian.html", accept=None)
    assert result.banner_found is True


@pytest.mark.integration
async def test_a_refusal_sold_with_a_subscription_in_an_iframe_is_named_and_not_clicked(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/sourcepoint_guardian.html", accept=False)
    assert clicked is None
    assert result.consent_clicked is False
    assert result.pay_to_refuse == "Reject all and subscribe"


@pytest.mark.integration
async def test_accept_all_in_an_iframe_is_clicked(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/sourcepoint_guardian.html", accept=True)
    assert clicked == "accept-all"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_a_plain_refusal_in_an_iframe_is_clicked(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/sourcepoint_reject_all.html", accept=False)
    assert clicked == "reject-all"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_the_report_names_the_paywall_in_the_iframe(browser, site_url):
    """What #96 asked for: the pay-to-refuse note, and no "no refusal" finding."""
    from cookieradar.law_checker import findings_of, notes_of
    from cookieradar.scanner import scan

    result = await scan(f"{site_url}/sourcepoint_guardian.html")

    assert "no_refusal" not in findings_of(result)
    assert any("Reject all and subscribe" in note for note in notes_of(result))
