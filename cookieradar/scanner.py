"""
CookieRadar — Playwright scanner.
Three clean sessions: pre-consent, post-accept, post-reject+reload.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext


@dataclass
class TrackerRequest:
    url: str
    domain: str
    resource_type: str
    timestamp: float


@dataclass
class SessionResult:
    session: str  # pre-consent, post-accept, post-reject
    trackers: list[TrackerRequest] = field(default_factory=list)
    cookies: list[dict] = field(default_factory=list)
    banner_found: bool = False
    error: Optional[str] = None


@dataclass
class ScanResult:
    url: str
    pre_consent: SessionResult = field(default_factory=lambda: SessionResult("pre-consent"))
    post_accept: SessionResult = field(default_factory=lambda: SessionResult("post-accept"))
    post_reject: SessionResult = field(default_factory=lambda: SessionResult("post-reject"))


TRACKER_DOMAINS = [
    "google-analytics.com",
    "googletagmanager.com",
    "googlesyndication.com",
    "doubleclick.net",
    "facebook.com",
    "facebook.net",
    "adform.net",
    "adobedtm.com",
    "omtrdc.net",
    "demdex.net",
    "everesttech.net",
    "adsrvr.org",
    "casalemedia.com",
    "rubiconproject.com",
    "pubmatic.com",
    "openx.net",
    "3lift.com",
    "tapad.com",
    "id5-sync.com",
    "newrelic.com",
    "nr-data.net",
    "go-mpulse.net",
    "scorecardresearch.com",
    "amazon-adsystem.com",
    "bing.com",
    "linkedin.com",
    "tiktok.com",
    "hotjar.com",
    "clarity.ms",
    "contentsquare.net",
    "tagcommander.com",
    "tiqcdn.com",
    "klaviyo.com",
    "ekonsilio.io",
]


def is_tracker(url: str) -> bool:
    """Check if URL belongs to a known tracker domain."""
    for domain in TRACKER_DOMAINS:
        if domain in url:
            return True
    return False


async def _run_session(
    context: BrowserContext,
    url: str,
    session_name: str,
    accept: Optional[bool] = None,
) -> SessionResult:
    """Run a single browser session and collect trackers."""
    result = SessionResult(session=session_name)
    page = await context.new_page()

    # Intercept requests
    async def handle_request(request):
        if is_tracker(request.url):
            from urllib.parse import urlparse
            domain = urlparse(request.url).netloc
            result.trackers.append(TrackerRequest(
                url=request.url,
                domain=domain,
                resource_type=request.resource_type,
                timestamp=0.0,
            ))

    page.on("request", handle_request)

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)

        # Check for cookie banner
        banner_selectors = [
            "[id*='cookie']", "[class*='cookie']",
            "[id*='consent']", "[class*='consent']",
            "[id*='gdpr']", "[class*='gdpr']",
            "[id*='banner']", "[class*='banner']",
        ]
        for selector in banner_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    result.banner_found = True
                    break
            except:
                pass

        # Interact with banner if needed
        if accept is True:
            accept_selectors = [
                "button[id*='accept']", "button[class*='accept']",
                "button[id*='agree']", "button[class*='agree']",
                "button:has-text('Accetta')", "button:has-text('Accept')",
                "button:has-text('Accetto')", "button:has-text('OK')",
            ]
            for selector in accept_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        break
                except:
                    pass

        elif accept is False:
            reject_selectors = [
                "button[id*='reject']", "button[class*='reject']",
                "button[id*='decline']", "button[class*='decline']",
                "button:has-text('Rifiuta')", "button:has-text('Reject')",
                "button:has-text('Rifiuto')", "button:has-text('Decline')",
                "button:has-text('Non accetto')",
            ]
            for selector in reject_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        # Reload after reject
                        await page.reload(wait_until="networkidle")
                        await page.wait_for_timeout(2000)
                        break
                except:
                    pass

        # Collect cookies
        result.cookies = await context.cookies()

    except Exception as e:
        result.error = str(e)
    finally:
        await page.close()

    return result


async def scan(url: str, headless: bool = True) -> ScanResult:
    """
    Scan a URL with three clean sessions.
    Session 1: pre-consent (no interaction)
    Session 2: post-accept-all
    Session 3: post-reject-all + reload
    """
    result = ScanResult(url=url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)

        # Session 1 — pre-consent
        ctx1 = await browser.new_context()
        result.pre_consent = await _run_session(ctx1, url, "pre-consent", accept=None)
        await ctx1.close()

        # Session 2 — post-accept
        ctx2 = await browser.new_context()
        result.post_accept = await _run_session(ctx2, url, "post-accept", accept=True)
        await ctx2.close()

        # Session 3 — post-reject + reload
        ctx3 = await browser.new_context()
        result.post_reject = await _run_session(ctx3, url, "post-reject", accept=False)
        await ctx3.close()

        await browser.close()

    return result
