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


# ─── iubenda: the close X, and a refusal sold with a subscription ────────────
#
# Measured 2026-10-17. On aranzulla.it the refusal is the "×" of the banner,
# whose own text says "Chiudi questa informativa per continuare senza accettare".
# On repubblica.it it is "Rifiuta e abbonati", and the close button is in the
# page but hidden. Both were reported as "no refusal control was found", with
# GDPR art. 4(11) cited.

@pytest.mark.integration
async def test_iubenda_close_x_is_the_refusal(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/iubenda_aranzulla.html", accept=False)

    assert clicked == "close"
    assert result.consent_clicked is True


@pytest.mark.integration
async def test_iubenda_accept_still_clicks_accetta(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/iubenda_aranzulla.html", accept=True)

    assert clicked == "accetta"


@pytest.mark.integration
async def test_a_hidden_close_button_is_not_clicked(browser, site_url):
    """repubblica.it hides its "Continua senza accettare" with display: none.
    A person cannot click it, and a refusal the scanner made through it would
    be one the site never offered."""
    result, clicked = await _session(browser, f"{site_url}/iubenda_repubblica.html", accept=False)

    assert clicked is None
    assert result.consent_clicked is False


@pytest.mark.integration
async def test_a_refusal_that_comes_with_a_subscription_is_seen_and_not_clicked(browser, site_url):
    result, clicked = await _session(browser, f"{site_url}/iubenda_repubblica.html", accept=False)

    assert clicked is None
    assert result.pay_to_refuse == "Rifiuta e abbonati"


# ─── What else the banner offered, counted where Accept was clicked ──────────

@pytest.mark.integration
async def test_the_controls_beside_accept_are_counted(browser, site_url):
    """aranzulla.it: the X, "terze parti", "finalità pubblicitarie", the cookie
    policy link the site marks as a button, and "Scopri di più e personalizza"
    — five things to click besides "Accetta". The hidden counter is not one."""
    result, clicked = await _session(browser, f"{site_url}/iubenda_aranzulla.html", accept=True)

    assert clicked == "accetta"
    assert result.other_controls == 5


@pytest.mark.integration
async def test_a_hidden_control_beside_accept_is_not_counted(browser, site_url):
    """repubblica.it: "Rifiuta e abbonati", the preferences panel, "ACCEDI" —
    and not the close button the site hides."""
    result, _ = await _session(browser, f"{site_url}/iubenda_repubblica.html", accept=True)

    assert result.other_controls == 3


@pytest.mark.integration
async def test_a_link_away_to_the_policy_is_not_a_control(browser, site_url):
    """The one shape the "no refusal" finding is about: Accept, and a link that
    leaves for the cookie policy — which is something to read, not a choice."""
    result, clicked = await _session(browser, f"{site_url}/accept_only.html", accept=True)

    assert clicked == "accetta"
    assert result.other_controls == 0


@pytest.mark.integration
async def test_a_control_inside_another_is_counted_once(browser, site_url):
    """A link that stays on the page around a button: one thing to click."""
    result, clicked = await _session(browser, f"{site_url}/nested_control.html", accept=True)

    assert clicked == "accetta"
    assert result.other_controls == 1


@pytest.mark.integration
async def test_without_a_banner_around_accept_nothing_is_counted(browser, site_url):
    """None, not 0: with no edge to the banner, a count would be a count of the
    page, and 0 would read as "Accept was the only choice"."""
    result, clicked = await _session(browser, f"{site_url}/unmarked_accept.html", accept=True)

    assert clicked == "accetta"
    assert result.other_controls is None


@pytest.mark.integration
async def test_a_banner_that_goes_away_mid_count_is_not_counted(browser, site_url):
    """The page is gone by the time the count runs — a site that navigates on
    its own, a tab closed under the session. None, not an exception that would
    lose the session, and not 0."""
    from cookieradar.scanner import _other_controls

    page = await browser.new_page()
    await page.goto(f"{site_url}/accept_only.html")
    button = await page.query_selector("button:not([style])")
    await page.close()

    assert await _other_controls(button) is None


@pytest.mark.integration
async def test_a_page_that_goes_away_has_no_subscription_label(browser, site_url):
    from cookieradar.scanner import PAY_TO_REFUSE_LABELS, _visible_label

    page = await browser.new_page()
    await page.goto(f"{site_url}/iubenda_repubblica.html")
    await page.close()

    assert await _visible_label(page, PAY_TO_REFUSE_LABELS) == ""


# ─── The whole audit, as `cookieradar audit` runs it ─────────────────────────

@pytest.mark.integration
async def test_no_refusal_is_not_cited_against_a_banner_with_a_close_x(browser, site_url):
    from cookieradar.law_checker import findings_of
    from cookieradar.scanner import scan

    result = await scan(f"{site_url}/iubenda_aranzulla.html")

    assert result.post_reject.consent_clicked is True
    assert "no_refusal" not in findings_of(result)


@pytest.mark.integration
async def test_no_refusal_is_not_cited_against_a_refusal_sold_with_a_subscription(browser, site_url):
    from cookieradar.law_checker import findings_of, notes_of
    from cookieradar.scanner import scan

    result = await scan(f"{site_url}/iubenda_repubblica.html")

    assert "no_refusal" not in findings_of(result)
    assert any("Rifiuta e abbonati" in note for note in notes_of(result))


@pytest.mark.integration
async def test_no_refusal_is_still_cited_against_a_banner_with_only_accept(browser, site_url):
    from cookieradar.law_checker import findings_of
    from cookieradar.scanner import scan

    result = await scan(f"{site_url}/accept_only.html")

    assert "no_refusal" in findings_of(result)
