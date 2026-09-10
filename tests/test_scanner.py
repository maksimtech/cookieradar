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

import pytest

@pytest.mark.asyncio
async def test_run_session_pre_consent():
    from cookieradar.scanner import _run_session, SessionResult
    from unittest.mock import AsyncMock, MagicMock

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_context.cookies = AsyncMock(return_value=[])
    mock_page.close = AsyncMock()
    mock_page.on = MagicMock()

    result = await _run_session(mock_context, "https://example.com", "pre-consent", accept=None)
    assert result.session == "pre-consent"
    assert isinstance(result, SessionResult)


@pytest.mark.asyncio
async def test_run_session_post_accept():
    from cookieradar.scanner import _run_session, SessionResult
    from unittest.mock import AsyncMock, MagicMock

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_context.cookies = AsyncMock(return_value=[])
    mock_page.close = AsyncMock()
    mock_page.on = MagicMock()

    result = await _run_session(mock_context, "https://example.com", "post-accept", accept=True)
    assert result.session == "post-accept"


@pytest.mark.asyncio
async def test_run_session_post_reject():
    from cookieradar.scanner import _run_session, SessionResult
    from unittest.mock import AsyncMock, MagicMock

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_context.cookies = AsyncMock(return_value=[])
    mock_page.close = AsyncMock()
    mock_page.on = MagicMock()
    mock_page.reload = AsyncMock()

    result = await _run_session(mock_context, "https://example.com", "post-reject", accept=False)
    assert result.session == "post-reject"
