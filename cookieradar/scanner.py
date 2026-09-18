"""
CookieRadar — Playwright scanner.
Three clean sessions: pre-consent, post-accept, post-reject+reload.
"""
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DEFAULT_TIMEOUT_MS = 30000


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


@dataclass
class Violations:
    persistent: set[str]  # loaded before consent and still loaded after rejection
    new: set[str]  # loaded only after rejection

    @property
    def all(self) -> set[str]:
        return self.persistent | self.new


def find_violations(result: ScanResult) -> Violations:
    """Every tracker loaded after rejection is a violation."""
    pre = {t.domain for t in result.pre_consent.trackers}
    rej = {t.domain for t in result.post_reject.trackers}
    return Violations(persistent=rej & pre, new=rej - pre)


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
    """Check if the URL host is a known tracker domain or one of its subdomains."""
    host = (urlparse(url).hostname or "").rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in TRACKER_DOMAINS)


ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button[id*='accept-all']",
    "button[class*='accept-all']",
    "button[id*='agree']",
]
REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    ".ot-pc-refuse-all-handler",
    "button[id*='reject-all']",
    "button[class*='refuse-all']",
]

# Whole accessible names, case-insensitive: "OK" must not match "Cookie settings",
# "Accept" must not match "Don't accept".
ACCEPT_LABELS = [
    re.compile(r"^\s*accett[ao](\s+tutt[oi])?(\s+i\s+cookie)?\s*$", re.I),
    re.compile(r"^\s*accept(\s+all)?(\s+cookies)?\s*$", re.I),
    re.compile(r"^\s*ok\s*$", re.I),
]
REJECT_LABELS = [
    re.compile(r"^\s*rifiuta(\s+tutt[oi])?(\s+i\s+cookie)?\s*$", re.I),
    re.compile(r"^\s*reject(\s+all)?(\s+cookies)?\s*$", re.I),
    re.compile(r"^\s*decline(\s+all)?\s*$", re.I),
]


async def _click_consent_button(page: Page, selectors: list[str], labels: list[re.Pattern]) -> bool:
    """Click the first visible match: CSS selectors first, then buttons by accessible name."""
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click()
                return True
        except PlaywrightError:
            pass
    for label in labels:
        try:
            buttons = page.get_by_role("button", name=label)
            for i in range(await buttons.count()):
                btn = buttons.nth(i)
                if await btn.is_visible():
                    await btn.click()
                    return True
        except PlaywrightError:
            pass
    return False


def _add_error(result: SessionResult, error: Exception) -> None:
    message = str(error).splitlines()[0] if str(error) else type(error).__name__
    result.error = f"{result.error}; {message}" if result.error else message


async def _run_session(
    context: BrowserContext,
    url: str,
    session_name: str,
    accept: Optional[bool] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> SessionResult:
    """
    Run a single browser session and collect trackers.
    Playwright errors are recorded in result.error instead of being raised;
    a navigation timeout does not stop the analysis of the loaded page.
    """
    result = SessionResult(session=session_name)
    page = await context.new_page()

    # Intercept requests
    def handle_request(request):
        if is_tracker(request.url):
            domain = urlparse(request.url).netloc
            result.trackers.append(TrackerRequest(
                url=request.url,
                domain=domain,
                resource_type=request.resource_type,
                timestamp=0.0,
            ))

    page.on("request", handle_request)

    try:
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError as e:
            _add_error(result, e)
        await page.wait_for_timeout(3000)

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

        # Accept all
        if accept is True:
            if await _click_consent_button(page, ACCEPT_SELECTORS, ACCEPT_LABELS):
                await page.wait_for_timeout(2000)

        # Reject all
        elif accept is False:
            # Step 1 — prova rifiuto diretto
            rejected = await _click_consent_button(page, REJECT_SELECTORS, REJECT_LABELS)
            if rejected:
                await page.wait_for_timeout(2000)

            # Step 2 — OneTrust a due step: apri preferenze poi rifiuta
            if not rejected:
                try:
                    pc_btn = await page.query_selector("#onetrust-pc-btn-handler")
                    if pc_btn and await pc_btn.is_visible():
                        await pc_btn.click()
                        await page.wait_for_timeout(2000)
                        refuse_btn = await page.query_selector(".ot-pc-refuse-all-handler")
                        if refuse_btn and await refuse_btn.is_visible():
                            await refuse_btn.click()
                            await page.wait_for_timeout(2000)
                            rejected = True
                except:
                    pass

            if rejected:
                # Only requests made after the rejection count for this session
                result.trackers.clear()
                try:
                    await page.reload(wait_until="networkidle", timeout=timeout_ms)
                except PlaywrightTimeoutError as e:
                    _add_error(result, e)
                await page.wait_for_timeout(2000)
    except PlaywrightError as e:
        _add_error(result, e)
    finally:
        await page.close()

    return result


async def scan(url: str, headless: bool = True, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> ScanResult:
    """
    Scan a URL with three clean sessions.
    Session 1: pre-consent (no interaction)
    Session 2: post-accept-all
    Session 3: post-reject-all + reload
    A failing session is recorded in its error field; the others still run.
    """
    result = ScanResult(url=url)
    sessions = [
        ("pre_consent", "pre-consent", None),
        ("post_accept", "post-accept", True),
        ("post_reject", "post-reject", False),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            for attr, name, accept in sessions:
                ctx = await browser.new_context()
                try:
                    session = await _run_session(ctx, url, name, accept=accept, timeout_ms=timeout_ms)
                except Exception as e:
                    session = SessionResult(session=name)
                    _add_error(session, e)
                finally:
                    await ctx.close()
                setattr(result, attr, session)
        finally:
            await browser.close()

    return result
