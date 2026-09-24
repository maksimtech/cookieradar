"""Properties, checked against generated input rather than chosen examples.

normalize_url is the first thing a URL from a batch file meets, and the only
guard that stops a scheme other than http(s) reaching the browser: the CLI
tests already pin file:///etc/passwd, but that is one example of a family.

The `normalize_text` block is the most valuable one here, and the reason is not
the parser: its output is hashed, and that hash is what tells an operator "the
law changed". A normalisation that is not idempotent would report a change in a
text that nobody edited.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from cookieradar.cli import normalize_url
from cookieradar.law_fetcher import normalize_text

# ── The gate every URL passes through ───────────────────────────────────────

_HOST = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-/?=&_",
    min_size=1, max_size=40,
).filter(lambda s: s.strip() and ":" not in s)


@given(_HOST)
def test_a_bare_host_is_given_https_not_http(host):
    """The default must be the safe scheme, not the reachable one."""
    assume(not host.strip().startswith(("http://", "https://")))
    assert normalize_url(host).startswith("https://")


@given(st.sampled_from(["http", "https", "HTTP", "HTTPS", "HtTpS"]), _HOST)
def test_a_url_that_already_names_http_or_https_is_left_alone(scheme, host):
    url = f"{scheme}://{host}"
    assert normalize_url(url) == url


@given(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz+.-", min_size=1, max_size=10),
    _HOST,
)
def test_every_other_scheme_is_refused_rather_than_rewritten(scheme, host):
    """file:, javascript:, data: — the point is that the list is not enumerated.

    A refused URL must raise, never come back with https:// bolted on the
    front, which would hand the browser something the caller never wrote.
    """
    assume(scheme.lower() not in ("http", "https"))
    assume(scheme[0].isalpha())
    with pytest.raises(ValueError):
        normalize_url(f"{scheme}://{host}")


@given(st.sampled_from(["", " ", "   ", "\t", "\n", " \t\n "]))
def test_an_empty_url_is_refused(url):
    with pytest.raises(ValueError):
        normalize_url(url)


@given(_HOST)
def test_normalising_twice_says_the_same_as_normalising_once(host):
    """A batch file read twice must not grow a second scheme."""
    once = normalize_url(host)
    assert normalize_url(once) == once


@given(_HOST)
def test_the_result_always_names_http_or_https(host):
    assert normalize_url(host).lower().startswith(("http://", "https://"))


# ── The hash that decides "the law changed" ─────────────────────────────────

_LEGAL_TEXT = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=0x2FFF, blacklist_categories=("Cs",)),
    max_size=400,
)


@given(_LEGAL_TEXT)
@settings(max_examples=300)
def test_normalising_law_text_twice_says_the_same_as_once(text):
    """If this ever failed, the cache would report a change nobody made."""
    once = normalize_text(text)
    assert normalize_text(once) == once


@given(_LEGAL_TEXT)
def test_the_normal_form_holds_no_run_of_spaces_and_no_edges(text):
    result = normalize_text(text)
    assert "  " not in result
    assert result == result.strip()


@given(_LEGAL_TEXT)
def test_the_normal_form_never_leaves_a_space_before_punctuation(text):
    """"Consiglio ;" is what a removed footnote reference leaves behind."""
    result = normalize_text(text)
    for mark in ";,.:":
        assert f" {mark}" not in result
