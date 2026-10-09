"""
Consent platforms met on real sites on 2026-10-09, replayed against a real Chromium.

Each page in tests/site/ reproduces the banner a site actually served that day
(the provenance is in the page's own comment), with the controls recording which
one was clicked in a cookie. No stand-in: the scanner's own session runs against
the page, the browser clicks, and the cookie says what happened.

TrustArc (enel.it, poste.it): the refusal is `#truste-consent-required` or
`#truste-consent-required2`, labelled "Continua senza accettare" or "Non accetto".
CookieRadar knew neither, clicked "Accetta"/"Accetto" in the post-accept session,
and the report said "Accept was applied and no refusal control was found" —
with GDPR art. 4(11) cited against a site that offers refusal in one click.

Usercentrics (zalando.it): the whole banner is in a shadow root, the buttons
have no id, and the refusal is labelled "Solo gli essenziali".

Skipped when Playwright browsers are not installed.
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


# ─── TrustArc ────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_trustarc_continua_senza_accettare_is_the_refusal(browser, site_url):
    """enel.it: the banner's own text says the button leaves only technical
    cookies, and TrustArc's id for it is the one it gives to "required only"."""
    result, clicked = await _session(browser, f"{site_url}/trustarc_enel.html", accept=False)

    assert clicked == "continua-senza-accettare"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_trustarc_accept_still_clicks_accetta_and_not_the_refusal(browser, site_url):
    """The guard for the new labels: "Continua senza accettare" contains no
    "accetta", and must not be taken for it."""
    result, clicked = await _session(browser, f"{site_url}/trustarc_enel.html", accept=True)

    assert clicked == "accetta"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_trustarc_non_accetto_is_the_refusal(browser, site_url):
    """poste.it: the button "Non accetto" comes first in the DOM, before the
    close icon that does the same thing; the button is what a person clicks."""
    result, clicked = await _session(browser, f"{site_url}/trustarc_poste.html", accept=False)

    assert clicked == "non-accetto"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_trustarc_non_accetto_is_not_taken_for_accetto(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/trustarc_poste.html", accept=True)

    assert clicked == "accetto"


# ─── Usercentrics, in a shadow root ──────────────────────────────────────────

@pytest.mark.integration
async def test_usercentrics_solo_gli_essenziali_is_the_refusal(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/usercentrics_zalando.html", accept=False)

    assert clicked == "uc-deny-all-button"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_usercentrics_accept_clicks_accetta_tutti(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/usercentrics_zalando.html", accept=True)

    assert clicked == "uc-accept-all-button"
