"""
Tests for CookieRadar scanner module.
Uses mocks to avoid real browser interactions.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cookieradar.scanner import (
    is_tracker,
    TrackerRequest,
    SessionResult,
    ScanResult,
    TRACKER_DOMAINS,
)


# ─── is_tracker ─────────────────────────────────────────────────────────────

def test_is_tracker_known_domain():
    assert is_tracker("https://www.googletagmanager.com/gtm.js") is True

def test_is_tracker_google_analytics():
    assert is_tracker("https://www.google-analytics.com/analytics.js") is True

def test_is_tracker_facebook():
    assert is_tracker("https://connect.facebook.net/en_US/fbevents.js") is True

def test_is_tracker_adform():
    assert is_tracker("https://track.adform.net/serving/scripts/trackpoint/") is True

def test_is_tracker_unknown_domain():
    assert is_tracker("https://www.tim.it/page.html") is False

def test_is_tracker_legitimate_cdn():
    assert is_tracker("https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js") is False

def test_is_tracker_contentsquare():
    assert is_tracker("https://t.contentsquare.net/uxa/script.js") is True

def test_is_tracker_demdex():
    assert is_tracker("https://dpm.demdex.net/id") is True


# ─── TrackerRequest ──────────────────────────────────────────────────────────

def test_tracker_request_creation():
    t = TrackerRequest(
        url="https://www.googletagmanager.com/gtm.js",
        domain="www.googletagmanager.com",
        resource_type="script",
        timestamp=0.0,
    )
    assert t.domain == "www.googletagmanager.com"
    assert t.resource_type == "script"


# ─── SessionResult ───────────────────────────────────────────────────────────

def test_session_result_default():
    s = SessionResult(session="pre-consent")
    assert s.session == "pre-consent"
    assert s.trackers == []
    assert s.cookies == []
    assert s.banner_found is False
    assert s.error is None

def test_session_result_with_trackers():
    t = TrackerRequest(
        url="https://www.googletagmanager.com/gtm.js",
        domain="www.googletagmanager.com",
        resource_type="script",
        timestamp=0.0,
    )
    s = SessionResult(session="pre-consent", trackers=[t])
    assert len(s.trackers) == 1
    assert s.trackers[0].domain == "www.googletagmanager.com"


# ─── ScanResult ──────────────────────────────────────────────────────────────

def test_scan_result_default():
    r = ScanResult(url="https://tim.it")
    assert r.url == "https://tim.it"
    assert r.pre_consent.session == "pre-consent"
    assert r.post_accept.session == "post-accept"
    assert r.post_reject.session == "post-reject"

def test_scan_result_violation_detection():
    tracker = TrackerRequest(
        url="https://www.googletagmanager.com/gtm.js",
        domain="www.googletagmanager.com",
        resource_type="script",
        timestamp=0.0,
    )
    r = ScanResult(url="https://tim.it")
    r.pre_consent.trackers = [tracker]
    r.post_reject.trackers = [tracker]

    pre_domains = set(t.domain for t in r.pre_consent.trackers)
    rej_domains = set(t.domain for t in r.post_reject.trackers)
    persistent = pre_domains & rej_domains

    assert len(persistent) == 1
    assert "www.googletagmanager.com" in persistent

def test_scan_result_no_violation():
    tracker = TrackerRequest(
        url="https://www.googletagmanager.com/gtm.js",
        domain="www.googletagmanager.com",
        resource_type="script",
        timestamp=0.0,
    )
    r = ScanResult(url="https://tim.it")
    r.pre_consent.trackers = [tracker]
    r.post_reject.trackers = []

    pre_domains = set(t.domain for t in r.pre_consent.trackers)
    rej_domains = set(t.domain for t in r.post_reject.trackers)
    persistent = pre_domains & rej_domains

    assert len(persistent) == 0


# ─── TRACKER_DOMAINS ─────────────────────────────────────────────────────────

def test_tracker_domains_not_empty():
    assert len(TRACKER_DOMAINS) > 0

def test_tracker_domains_contains_gtm():
    assert "googletagmanager.com" in TRACKER_DOMAINS

def test_tracker_domains_contains_facebook():
    assert "facebook.com" in TRACKER_DOMAINS

def test_tracker_domains_contains_adform():
    assert "adform.net" in TRACKER_DOMAINS


# ─── _run_session mock ───────────────────────────────────────────────────────

from tests.conftest import fake_request, make_mock_context


@pytest.mark.parametrize("name,accept", [
    ("pre-consent", None),
    ("post-accept", True),
    ("post-reject", False),
])
async def test_run_session_without_banner(name, accept):
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()

    result = await _run_session(context, "https://example.com", name, accept=accept)

    assert isinstance(result, SessionResult)
    assert result.session == name
    assert result.error is None
    page.close.assert_awaited_once()


# ─── G1: post-reject must not be contaminated by pre-reject requests ─────────


def _visible_button():
    btn = AsyncMock()
    btn.is_visible = AsyncMock(return_value=True)
    return btn


def _reject_page(reload_requests):
    """Page that emits one tracker on goto and `reload_requests` on reload."""
    context, page = make_mock_context()
    btn = _visible_button()

    async def goto(*args, **kwargs):
        page.handlers["request"](fake_request("https://stats.doubleclick.net/pixel", "image"))

    async def reload(*args, **kwargs):
        for url in reload_requests:
            page.handlers["request"](fake_request(url, "image"))

    page.goto = AsyncMock(side_effect=goto)
    page.reload = AsyncMock(side_effect=reload)
    page.query_selector_all = AsyncMock(
        side_effect=lambda sel: [btn] if sel == "#onetrust-reject-all-handler" else []
    )
    return context, page


async def _drain():
    import asyncio
    await asyncio.sleep(0)


async def test_post_reject_ignores_requests_made_before_rejection():
    from cookieradar.scanner import _run_session
    context, page = _reject_page(reload_requests=[])

    result = await _run_session(context, "https://example.com", "post-reject", accept=False)
    await _drain()

    page.reload.assert_awaited_once()
    assert result.trackers == []


async def test_post_reject_keeps_requests_made_after_reload():
    from cookieradar.scanner import _run_session
    context, page = _reject_page(reload_requests=["https://www.facebook.com/tr"])

    result = await _run_session(context, "https://example.com", "post-reject", accept=False)
    await _drain()

    assert [t.domain for t in result.trackers] == ["facebook.com"]


def _tracker(domain):
    return TrackerRequest(url=f"https://{domain}/x", domain=domain, resource_type="script", timestamp=0.0)


def test_find_violations_splits_persistent_and_new():
    from cookieradar.scanner import find_violations
    r = ScanResult(url="https://example.com")
    r.pre_consent.trackers = [_tracker("a.doubleclick.net"), _tracker("b.hotjar.com")]
    r.post_reject.trackers = [_tracker("b.hotjar.com"), _tracker("c.facebook.com")]

    v = find_violations(r)

    assert v.persistent == {"b.hotjar.com"}
    assert v.new == {"c.facebook.com"}
    assert v.all == {"b.hotjar.com", "c.facebook.com"}


def test_find_violations_none_when_post_reject_clean():
    from cookieradar.scanner import find_violations
    r = ScanResult(url="https://example.com")
    r.pre_consent.trackers = [_tracker("a.doubleclick.net")]

    v = find_violations(r)

    assert v.all == set()


# ─── G4: timeouts and Playwright errors are recorded, not raised ────────────

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


async def test_goto_timeout_sets_error_and_continues():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    banner = _visible_button()

    async def goto(*args, **kwargs):
        page.handlers["request"](fake_request("https://stats.doubleclick.net/pixel", "image"))
        raise PlaywrightTimeoutError("Timeout 30000ms exceeded.")

    page.goto = AsyncMock(side_effect=goto)
    page.query_selector_all = AsyncMock(side_effect=lambda sel: [banner] if sel == "[id*='cookie']" else [])

    result = await _run_session(context, "https://example.com", "pre-consent", accept=None)

    assert "Timeout" in result.error
    assert [t.domain for t in result.trackers] == ["doubleclick.net"]
    assert result.banner_found is True  # analysis continued after the timeout
    page.close.assert_awaited_once()


async def test_navigation_error_sets_error_without_raising():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    page.goto = AsyncMock(side_effect=PlaywrightError("net::ERR_NAME_NOT_RESOLVED at https://nope.invalid/"))

    result = await _run_session(context, "https://nope.invalid", "pre-consent", accept=None)

    assert "ERR_NAME_NOT_RESOLVED" in result.error
    page.close.assert_awaited_once()


async def test_reload_timeout_keeps_post_reject_trackers():
    from cookieradar.scanner import _run_session
    context, page = _reject_page(reload_requests=[])

    async def reload(*args, **kwargs):
        page.handlers["request"](fake_request("https://www.facebook.com/tr", "image"))
        raise PlaywrightTimeoutError("Timeout 30000ms exceeded.")

    page.reload = AsyncMock(side_effect=reload)

    result = await _run_session(context, "https://example.com", "post-reject", accept=False)

    assert "Timeout" in result.error
    assert [t.domain for t in result.trackers] == ["facebook.com"]


async def test_timeout_ms_is_passed_to_navigation():
    from cookieradar.scanner import _run_session
    context, page = _reject_page(reload_requests=[])

    await _run_session(context, "https://example.com", "post-reject", accept=False, timeout_ms=1234)

    assert page.goto.await_args.kwargs["timeout"] == 1234
    assert page.reload.await_args.kwargs["timeout"] == 1234


def _mock_playwright(browser):
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=pw)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


async def test_scan_continues_when_a_session_crashes():
    from cookieradar import scanner
    contexts = []

    async def new_context():
        ctx = AsyncMock()
        contexts.append(ctx)
        return ctx

    browser = AsyncMock()
    browser.new_context = AsyncMock(side_effect=new_context)

    async def run_session(ctx, url, name, accept=None, timeout_ms=30000):
        if name == "post-accept":
            raise RuntimeError("Target page, context or browser has been closed")
        return SessionResult(session=name)

    with patch.object(scanner, "async_playwright", _mock_playwright(browser)), \
         patch.object(scanner, "_run_session", run_session):
        result = await scanner.scan("https://example.com")

    assert result.pre_consent.error is None
    assert "has been closed" in result.post_accept.error
    assert result.post_accept.session == "post-accept"
    assert result.post_reject.error is None
    assert len(contexts) == 3
    for ctx in contexts:
        ctx.close.assert_awaited_once()
    browser.close.assert_awaited_once()


# ─── L1: match on hostname with a dot boundary ──────────────────────────────

@pytest.mark.parametrize("url", [
    "https://shopbing.com/",                            # suffix without dot boundary
    "https://www.example.it/?ref=facebook.com",         # domain in query string
    "https://example.com/blog/how-linkedin.com-works",  # domain in path
    "https://notdoubleclick.net.evil.it/",              # domain as a label prefix
    "https://myclarity.ms.example.org/",
    "https://user:facebook.com@example.com/",           # domain in userinfo
    "data:text/html,googletagmanager.com",
    "about:blank",
])
def test_is_tracker_rejects_substring_matches(url):
    assert is_tracker(url) is False


@pytest.mark.parametrize("url", [
    "https://facebook.com/tr",                  # exact domain
    "https://connect.facebook.net/sdk.js",      # subdomain
    "https://a.b.doubleclick.net/x",            # nested subdomain
    "https://WWW.Google-Analytics.COM/g/collect",  # case-insensitive
    "https://www.googletagmanager.com:443/gtm.js",  # explicit port
    "https://stats.doubleclick.net./pixel",     # fully-qualified trailing dot
])
def test_is_tracker_matches_domain_and_subdomains(url):
    assert is_tracker(url) is True


# ─── L2: button labels match whole words, not substrings ────────────────────

def _matches(labels, text):
    return any(rx.search(text) for rx in labels)


@pytest.mark.parametrize("text", [
    "Accetta", "Accetta tutto", "Accetta tutti", "Accetta tutti i cookie", "Accetto",
    "Accept", "Accept All", "ACCEPT ALL COOKIES", "OK", "Ok", "  ok  ",
])
def test_accept_labels_match(text):
    from cookieradar.scanner import ACCEPT_LABELS
    assert _matches(ACCEPT_LABELS, text)


@pytest.mark.parametrize("text", [
    "Cookie settings", "Book now", "Facebook", "Don't accept", "Accept only necessary",
    "Non accetto", "Accettabile", "Okay, show me more", "Rifiuta",
])
def test_accept_labels_do_not_match_substrings(text):
    from cookieradar.scanner import ACCEPT_LABELS
    assert not _matches(ACCEPT_LABELS, text)


@pytest.mark.parametrize("text", [
    "Rifiuta", "Rifiuta tutto", "Rifiuta tutti i cookie", "Reject", "Reject All",
    "Reject all cookies", "Decline", "Decline all",
])
def test_reject_labels_match(text):
    from cookieradar.scanner import REJECT_LABELS
    assert _matches(REJECT_LABELS, text)


@pytest.mark.parametrize("text", [
    "Rejected items", "Non rifiutare", "Declined payments", "Rifiutato", "Accept",
])
def test_reject_labels_do_not_match_substrings(text):
    from cookieradar.scanner import REJECT_LABELS
    assert not _matches(REJECT_LABELS, text)


# ─── L3: sessions record whether the consent button was clicked ─────────────

@pytest.mark.parametrize("name,accept", [("post-accept", True), ("post-reject", False)])
async def test_consent_not_clicked_when_no_button(name, accept):
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()

    result = await _run_session(context, "https://example.com", name, accept=accept)

    assert result.consent_clicked is False


@pytest.mark.parametrize("name,accept,selector", [
    ("post-accept", True, "#onetrust-accept-btn-handler"),
    ("post-reject", False, "#onetrust-reject-all-handler"),
])
async def test_consent_clicked_when_button_found(name, accept, selector):
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    btn = _visible_button()
    page.query_selector_all = AsyncMock(side_effect=lambda sel: [btn] if sel == selector else [])

    result = await _run_session(context, "https://example.com", name, accept=accept)

    assert result.consent_clicked is True
    btn.click.assert_awaited_once()


def test_consent_clicked_defaults_to_false():
    assert SessionResult(session="pre-consent").consent_clicked is False


# ─── L4: real cookies are collected at the end of the session ───────────────

COOKIE = {"name": "_ga", "value": "GA1.1.1", "domain": ".example.com", "path": "/",
          "expires": 1893456000, "httpOnly": False, "secure": False, "sameSite": "Lax"}


async def test_cookies_collected_after_reload():
    from cookieradar.scanner import _run_session
    context, page = _reject_page(reload_requests=[])
    calls = []
    page.reload.side_effect = lambda *a, **k: calls.append("reload")

    async def cookies():
        calls.append("cookies")
        return [COOKIE]

    context.cookies = AsyncMock(side_effect=cookies)

    result = await _run_session(context, "https://example.com", "post-reject", accept=False)

    assert result.cookies == [COOKIE]
    assert calls == ["reload", "cookies"]


async def test_cookies_collected_even_after_navigation_error():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    page.goto = AsyncMock(side_effect=PlaywrightError("net::ERR_CONNECTION_RESET"))
    context.cookies = AsyncMock(return_value=[COOKIE])

    result = await _run_session(context, "https://example.com", "pre-consent")

    assert result.cookies == [COOKIE]
    assert "ERR_CONNECTION_RESET" in result.error


async def test_cookies_error_is_recorded_not_raised():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    context.cookies = AsyncMock(side_effect=PlaywrightError("Target closed"))

    result = await _run_session(context, "https://example.com", "pre-consent")

    assert result.cookies == []
    assert "Target closed" in result.error
    page.close.assert_awaited_once()


# ─── L5: the first *visible* match counts, not the first match ──────────────

def _hidden_element():
    el = AsyncMock()
    el.is_visible = AsyncMock(return_value=False)
    return el


async def test_banner_found_when_first_match_is_hidden():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    matches = [_hidden_element(), _visible_button()]
    page.query_selector_all = AsyncMock(side_effect=lambda sel: matches if sel == "[id*='cookie']" else [])

    result = await _run_session(context, "https://example.com", "pre-consent")

    assert result.banner_found is True


async def test_consent_css_selector_clicks_first_visible_match():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()
    hidden, visible = _hidden_element(), _visible_button()
    page.query_selector_all = AsyncMock(
        side_effect=lambda sel: [hidden, visible] if sel == "button[id*='accept-all']" else []
    )

    result = await _run_session(context, "https://example.com", "post-accept", accept=True)

    assert result.consent_clicked is True
    hidden.click.assert_not_awaited()
    visible.click.assert_awaited_once()


# ─── L6: trackers grouped by registrable domain ─────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://region1.google-analytics.com/g/collect", "google-analytics.com"),
    ("https://www.google-analytics.com/analytics.js", "google-analytics.com"),
    ("https://google-analytics.com/", "google-analytics.com"),
    ("https://A.B.DoubleClick.net:443/x", "doubleclick.net"),
    ("https://www.example.com/", None),
    ("https://shopbing.com/", None),
])
def test_tracker_domain_is_registrable_domain(url, expected):
    from cookieradar.scanner import tracker_domain
    assert tracker_domain(url) == expected


def test_tracker_domains_are_registrable_domains():
    # tracker_domain() relies on every entry being an eTLD+1 (label.tld)
    for domain in TRACKER_DOMAINS:
        assert domain == domain.lower()
        assert domain.count(".") == 1, domain


async def test_session_records_registrable_domain():
    from cookieradar.scanner import _run_session
    context, page = make_mock_context()

    async def goto(*args, **kwargs):
        page.handlers["request"](fake_request("https://region1.google-analytics.com/g/collect"))
        page.handlers["request"](fake_request("https://www.google-analytics.com/analytics.js"))

    page.goto = AsyncMock(side_effect=goto)

    result = await _run_session(context, "https://example.com", "pre-consent")

    assert [t.domain for t in result.trackers] == ["google-analytics.com", "google-analytics.com"]
    assert result.trackers[0].url == "https://region1.google-analytics.com/g/collect"


def test_violation_matches_across_subdomains():
    from cookieradar.scanner import find_violations
    r = ScanResult(url="https://example.com")
    r.pre_consent.trackers = [_tracker("google-analytics.com")]
    r.post_reject.trackers = [_tracker("google-analytics.com")]

    assert find_violations(r).persistent == {"google-analytics.com"}
