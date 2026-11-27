"""
CookieRadar — the labels a banner's buttons carry, as measured on real sites (audit F-03)

Whole accessible names, case-insensitive: a label is added when a site was seen
using it, with the site and the day. "Deny" and "Allow all" are Cookiebot's on
cookiebot.com (2026-10-17, the scanner's en-US locale); "ACCETTA E CONTINUA" is
corriere.it's acceptance as the audit recorded it that day. The guards are the
labels that must not be read as the opposite choice.
"""
from __future__ import annotations

import pytest

from cookieradar.scanner import ACCEPT_LABELS, PAY_TO_REFUSE_LABELS, REJECT_LABELS


def _matches(labels, name: str) -> bool:
    return any(label.search(name) for label in labels)


@pytest.mark.parametrize("name", ["Deny", "DENY"])
def test_cookiebot_s_deny_is_a_refusal(name):
    assert _matches(REJECT_LABELS, name)
    assert not _matches(ACCEPT_LABELS, name)


@pytest.mark.parametrize("name", ["Allow all", "ALLOW ALL"])
def test_cookiebot_s_allow_all_is_an_acceptance(name):
    assert _matches(ACCEPT_LABELS, name)
    assert not _matches(REJECT_LABELS, name)


def test_allow_selection_is_neither():
    """Cookiebot's "Allow selection" accepts what the switches say — on a fresh
    visit, nothing beyond the necessary — so it is not an acceptance of all."""
    assert not _matches(ACCEPT_LABELS, "Allow selection")
    assert not _matches(REJECT_LABELS, "Allow selection")


@pytest.mark.parametrize("name", ["ACCETTA E CONTINUA", "Accetta e continua"])
def test_accetta_e_continua_is_an_acceptance(name):
    assert _matches(ACCEPT_LABELS, name)


def test_continua_senza_accettare_is_still_the_refusal_and_not_accetta_e_continua():
    assert _matches(REJECT_LABELS, "Continua senza accettare")
    assert not _matches(ACCEPT_LABELS, "Continua senza accettare")


@pytest.mark.parametrize("name", [
    "Rifiuta e abbonati", "RIFIUTA E ABBONATI",
    "Reject all and subscribe", "REJECT AND SUBSCRIBE", "Decline and subscribe", "Refuse and subscribe",
])
def test_a_refusal_sold_with_a_subscription_is_named_as_such(name):
    """The English form of repubblica.it's "Rifiuta e abbonati", the label the
    same walls carry in an English locale."""
    assert _matches(PAY_TO_REFUSE_LABELS, name)


@pytest.mark.parametrize("name", ["Reject all", "Subscribe", "Accept and subscribe", "Rifiuta", "Abbonati"])
def test_a_plain_refusal_or_a_plain_subscription_is_not_pay_to_refuse(name):
    assert not _matches(PAY_TO_REFUSE_LABELS, name)


# ─── measured on 2026-11-27 (#97), the scanner's Chromium, locale it-IT ─────

@pytest.mark.parametrize("name", [
    "Rifiuta i cookie non tecnici",   # inps.it, #refuseAnalyticsBtn
    "Reject additional cookies",      # gov.uk
])
def test_the_refusals_measured_on_2026_11_27_are_refusals(name):
    assert _matches(REJECT_LABELS, name)
    assert not _matches(ACCEPT_LABELS, name)


@pytest.mark.parametrize("name", [
    "Accept additional cookies",      # gov.uk
    "Accetta e chiudi",               # giallozafferano.it, iubenda
    "TILLAD ALLE",                    # dr.dk, Danish for "allow all"
])
def test_the_acceptances_measured_on_2026_11_27_are_acceptances(name):
    assert _matches(ACCEPT_LABELS, name)
    assert not _matches(REJECT_LABELS, name)


@pytest.mark.parametrize("name", ["TILLAD UDVALGTE", "Rifiuta i cookie tecnici", "Accetta e abbonati"])
def test_what_they_must_not_be_taken_for(name):
    """dr.dk's "allow selected" is Cookiebot's "Allow selection" again: neither. The
    technical cookies need no consent, so refusing them is not a label anyone uses.
    And an acceptance that subscribes is not a plain acceptance."""
    assert not _matches(REJECT_LABELS, name)
    assert not _matches(ACCEPT_LABELS, name)


def test_google_funding_choices_is_reached_by_its_classes():
    """ilmeteo.it, 2026-11-27: Funding Choices labels its buttons as the publisher
    chooses ("accetta", "continua senza accettare"; "Non acconsento" elsewhere), and
    the classes `fc-cta-consent` and `fc-cta-do-not-consent` stay the same."""
    from cookieradar.scanner import ACCEPT_SELECTORS, REJECT_SELECTORS

    assert any("fc-cta-do-not-consent" in selector for selector in REJECT_SELECTORS)
    assert any("fc-cta-consent" in selector and "do-not" not in selector for selector in ACCEPT_SELECTORS)
