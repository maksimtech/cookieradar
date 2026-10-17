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

from cookieradar.scanner import ACCEPT_LABELS, REJECT_LABELS


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
