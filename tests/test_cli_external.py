"""
CookieRadar — the external-host summary in the report

The count does not depend on Ghostery: with the 34 built-in domains alone the
report can already say out of how many hosts those counts were chosen, and how
many got away. A trackerdb moves the boundary between "identified" and "unknown";
it does not create the distinction.

The path given with --trackers has to fail loudly when it is not a trackerdb: a
scan that carries on silently without the enrichment that was asked for delivers
a poorer report than expected, and nobody notices.
"""
from io import StringIO

import pytest
from rich.console import Console

from cookieradar.cli import _print_external
from cookieradar.scanner import ExternalRequest, SessionResult
from cookieradar.trackerdb import Organization, Tracker


def _out():
    return Console(file=StringIO(), width=200, force_terminal=False)


def _req(host, tracker=None, domain=None):
    return ExternalRequest(url=f"https://{host}/x", host=host, resource_type="script",
                           timestamp=0.0, tracker=tracker, domain=domain)


def _session(*requests):
    session = SessionResult("pre-consent")
    session.external = list(requests)
    return session


def test_counts_appear_without_any_trackerdb():
    """Con i soli 34 domini interni: due riconosciuti, uno no."""
    out = _out()
    _print_external(out, _session(
        _req("google-analytics.com", domain="google-analytics.com"),
        _req("doubleclick.net", domain="doubleclick.net"),
        _req("sconosciuto.example"),
    ))
    text = out.file.getvalue()
    assert "3" in text and "2" in text and "1" in text


def test_the_unknown_hosts_are_named_not_just_counted():
    """Un numero non si puo' indagare; un nome si."""
    out = _out()
    _print_external(out, _session(_req("qualcosa.example"), _req("altro.example")))
    text = out.file.getvalue()
    assert "qualcosa.example" in text
    assert "altro.example" in text


def test_nothing_is_printed_when_no_external_host_was_contacted():
    """Zero host non merita una tabella vuota: il resto del report lo dice gia'."""
    out = _out()
    _print_external(out, _session())
    assert out.file.getvalue().strip() == ""


def test_the_organization_is_shown_when_a_trackerdb_supplied_one():
    out = _out()
    _print_external(out, _session(_req(
        "demdex.net",
        Tracker("a", "Adobe Audience Manager", "advertising", ("demdex.net",),
                organization=Organization(id="adobe", name="Adobe", country="US")),
        "demdex.net",
    )))
    text = out.file.getvalue()
    assert "Adobe" in text
    assert "advertising" in text


def test_a_long_list_of_unknown_hosts_is_truncated_with_the_count():
    """Ottanta host sconosciuti non si stampano tutti, ma quanti sono va detto:
    troncare in silenzio nasconde proprio la misura che serve."""
    out = _out()
    _print_external(out, _session(*[_req(f"h{i}.example") for i in range(80)]))
    text = out.file.getvalue()
    assert "80" in text


# ── the --trackers path ─────────────────────────────────────────────────────

def test_a_bad_trackers_path_is_an_error_not_a_silent_downgrade(tmp_path):
    """Asking for the enrichment and not getting it, without knowing, produces a
    report poorer than expected and indistinguishable from a complete one."""
    from cookieradar.cli import _load_trackers

    with pytest.raises(ValueError):
        _load_trackers(tmp_path / "does-not-exist")


def test_no_path_means_no_trackerdb_and_that_is_not_an_error():
    from cookieradar.cli import _load_trackers

    assert _load_trackers(None) is None
