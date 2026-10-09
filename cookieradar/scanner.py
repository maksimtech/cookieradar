"""
CookieRadar — Playwright scanner.
Three clean sessions: pre-consent, post-accept, post-reject+reload.
"""
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Cookie, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from cookieradar.trackerdb import Tracker, TrackerDB

DEFAULT_TIMEOUT_MS = 30000


@dataclass
class TrackerRequest:
    url: str
    domain: str
    resource_type: str
    timestamp: float  # epoch seconds when the request was captured


@dataclass
class ExternalRequest:
    """A request to a host outside the site, recognised or not.

    `TrackerRequest` above still holds only the recognised ones, and everything
    consuming it stays as it was. This list is the denominator that was missing:
    without it, "9 trackers" does not say out of how many hosts those nine were
    chosen, and an unknown host disappears like one never contacted.
    """
    url: str
    host: str
    resource_type: str
    timestamp: float
    # The domain from the built-in list that matched, if one did.
    domain: str | None = None
    # The enrichment from a trackerdb, when the operator supplied one. None
    # means "not loaded" or "not present in that database": two different things
    # the summary keeps apart by looking at `domain`.
    tracker: Tracker | None = None


@dataclass
class ExternalSummary:
    hosts: int
    identified: int
    unknown: list[str]
    organizations: dict[str, int]
    categories: dict[str, int]


def is_same_site(page_host: str, request_host: str) -> bool:
    """Does `request_host` belong to the same site as `page_host`?

    Equality counts, and so does the subdomain relation in both directions, so
    that `example.it`, `www.example.it` and `static.cdn.example.it` are one site.
    No public suffix list is needed, which would be a dependency and a data file
    more to cover a case — `x.co.uk` against `y.co.uk` — that this rule already
    treats as external, correctly.

    An empty host — `data:` and `blob:` requests have none — is neither the
    site's nor a third party's, and is counted nowhere.

    A leading `www.` is stripped from the page's host before the comparison.
    Without that, a scan of `www.tim.it` declared `api.tim.it` a stranger:
    neither is a subdomain of the other, both are subdomains of `tim.it`.
    Measured on tim.it on 2026-09-27, where `api.tim.it` appeared among the
    unknown hosts next to the real trackers.

    The case of two sibling subdomains when the page is not on `www.` stays out:
    scanning `shop.example.com`, `blog.example.com` comes out external. Removing
    that would require knowing where the registrable domain ends, that is a
    public suffix list — a dependency and a data file — and getting that boundary
    wrong would produce the opposite and worse error: `x.co.uk` and `y.co.uk`
    declared the same site.
    """
    a = (page_host or "").strip().rstrip(".").lower()
    b = (request_host or "").strip().rstrip(".").lower()
    if not a or not b:
        return False
    if a.startswith("www.") and a.count(".") >= 2:
        a = a[4:]
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _ascii_host(host: str) -> str:
    """`host` spelled the way Chromium writes it in requests: IDNA, not Unicode.

    The address typed is `müller.de` and every request the page makes goes to
    `xn--mller-kva.de`; compared as written, the site's own resources all came
    out as unknown external hosts. A host the codec refuses — a label over 63
    characters, say — is returned as it was: no worse than before.
    """
    host = (host or "").rstrip(".")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def summarise_external(session: "SessionResult") -> ExternalSummary:
    """The summary per host, not per request.

    Twenty requests to the same host are one host: the report speaks of who was
    contacted, not of how many times.
    """
    by_host: dict[str, ExternalRequest] = {}
    for request in session.external:
        by_host.setdefault(request.host, request)

    unknown: list[str] = []
    organizations: dict[str, int] = {}
    categories: dict[str, int] = {}
    identified = 0
    for host, request in by_host.items():
        if request.tracker is None and request.domain is None:
            unknown.append(host)
            continue
        identified += 1
        tracker = request.tracker
        if tracker is None:
            continue
        categories[tracker.category] = categories.get(tracker.category, 0) + 1
        # 437 real patterns carry no organization. Counting them as identified
        # and saying nothing about the company is right; dropping them is not.
        if tracker.organization is not None:
            name = tracker.organization.name
            organizations[name] = organizations.get(name, 0) + 1

    return ExternalSummary(
        hosts=len(by_host),
        identified=identified,
        unknown=sorted(unknown),
        organizations=organizations,
        categories=categories,
    )


@dataclass
class SessionResult:
    session: str  # pre-consent, post-accept, post-reject
    trackers: list[TrackerRequest] = field(default_factory=list)
    # playwright's context.cookies() returns list[Cookie], a TypedDict; the
    # annotation said list[dict], which is not the same type.
    cookies: list[Cookie] = field(default_factory=list)
    # Every external host contacted, recognised or not. `trackers` above stays
    # the recognised subset, so nothing that reads it has to change.
    external: list[ExternalRequest] = field(default_factory=list)
    banner_found: bool = False
    # The status of the main document. None when the navigation produced no
    # response at all — a timeout, which the session already reports as an
    # error — and not to be read as a failure in its own right.
    status: int | None = None
    error: str | None = None
    consent_clicked: bool = False  # accept/reject button found and clicked
    # The document's own identity, kept so that `bot_challenge` can tell a
    # challenge page from the site. A challenge answering 200 is invisible to
    # everything that only reads counts: it has no trackers and no banner, which
    # is exactly what a compliant site looks like.
    title: str = ""
    text: str = ""


@dataclass
class ScanResult:
    url: str
    pre_consent: SessionResult = field(default_factory=lambda: SessionResult("pre-consent"))
    post_accept: SessionResult = field(default_factory=lambda: SessionResult("post-accept"))
    post_reject: SessionResult = field(default_factory=lambda: SessionResult("post-reject"))
    # When the audit was made, in UTC. The README calls the report "evidence of
    # what the site did on a given day", and until 2026-10-09 the file saved
    # said no day at all: the only dates in it were the "Version of:" lines
    # under the legal citations, which appear only when something is cited.
    scanned_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Violations:
    persistent: set[str]  # loaded before consent and still loaded after rejection
    new: set[str]  # loaded only after rejection

    @property
    def all(self) -> set[str]:
        return self.persistent | self.new


def page_not_served(result: ScanResult) -> bool:
    """The site answered with an error status, so nothing else describes it.

    Measured on canon.it, 2026-09-26: 403 Access Denied from the Akamai edge,
    364 bytes, identical with and without a browser User-Agent. A headless
    browser loads that page like any other and finds no trackers, no banner and
    one cookie — and every one of those is a fact about an error page.

    Reporting it as "0 trackers before consent" is the strongest claim this
    tool can make, assembled entirely out of never having seen the site.

    A status of None is not a failure: the navigation produced no response,
    which is a timeout, and the session already carries that as an error.

    Any of the three sessions, not the first alone. Measured on www.zalando.it
    on 2026-10-09, in a batch run: the pre-consent session got no response at
    all, the post-reject session got the edge's 403 page with a banner on it,
    and the verdict came out as VIOLATION "new after rejection" — assembled
    from one session that saw nothing and one that saw an error page. The
    verdict rests on session 3; an error page there leaves it nothing to rest on.
    """
    return not_served(result) is not None


def not_served(result: ScanResult) -> tuple[str, int] | None:
    """The first session whose document was an error page, as (name, status)."""
    for session in (result.pre_consent, result.post_accept, result.post_reject):
        if session.status is not None and session.status >= 400:
            return session.session, session.status
    return None


# A bot-management edge refuses in two ways, and only one of them looks like a
# refusal. `page_not_served` catches the status; these catch the other, where the
# challenge answers 200 and the browser loads it like any other page.
#
# 202 is what AWS WAF returns with its JavaScript challenge: a success status
# carrying something that is not the page, which is why it needs naming here.
#
# 429 and 503 are deliberately *not* in this set, although a challenge often uses
# them. They are above 400, so `page_not_served` already reports "this is not the
# site" — which is true — and calling a bare 503 a bot challenge would put a cause
# on it that nobody established. A 503 that also says "Just a moment" is a
# challenge, and the text is what says so.
CHALLENGE_STATUSES = frozenset({202})

# Enough for a challenge's words, which are always in the first screenful, and not
# enough to carry someone else's article around in a report.
_TEXT_SNIFF = 4000

# The page's own words. Deliberately narrow: this tool audits cookie banners, so
# the words "cookies" and "please enable" appear on almost every compliant site
# in the corpus, and a marker that fired on a consent notice would make
# cookieradar refuse to audit exactly the sites doing it right.
CHALLENGE_TEXT = (
    re.compile(r"just a moment", re.I),
    re.compile(r"checking your browser", re.I),
    re.compile(r"attention required.{0,3}\|\s*cloudflare", re.I),
    re.compile(r"verify(ing)? (that )?you are (human|a human)", re.I),
    re.compile(r"review(ing)? the security of your connection", re.I),
    re.compile(r"pardon our interruption", re.I),
    re.compile(r"incapsula incident", re.I),
    re.compile(r"request unsuccessful", re.I),
    re.compile(r"enable javascript and cookies to continue", re.I),
    re.compile(r"ddos protection by", re.I),
    re.compile(r"(cf-browser-verification|__cf_chl|challenge-platform)", re.I),
)

# Corroboration only, never a verdict on their own. `__cf_bm` is set on a large
# share of ordinary sites that serve their own pages perfectly well: reading it as
# a block would lose coverage silently, which is the failure that looks like
# caution. Once the page has already said it is a challenge, naming the vendor is
# what lets an operator ask the right party for access.
CHALLENGE_COOKIES = (
    "__cf_bm", "cf_clearance", "__cf_chl",        # Cloudflare
    "aws-waf-token",                               # AWS WAF
    "datadome",                                    # DataDome
    "_px", "_pxhd", "_pxvid",                      # HUMAN / PerimeterX
    "ak_bmsc", "bm_sv", "bm_sz", "bm_mi",          # Akamai Bot Manager
    "incap_ses", "visid_incap", "nlbi_",           # Imperva
    "reese84",                                     # Kasada
)

CHALLENGE_HOSTS = (
    "challenges.cloudflare.com",
    "captcha-delivery.com",
    "perimeterx.net",
    "px-cloud.net",
    "hcaptcha.com",
    "recaptcha.net",
)


@dataclass(frozen=True)
class Challenge:
    """Why the document in hand is not the site, in words a reader can check."""

    signals: tuple[str, ...] = ()

    @property
    def seen(self) -> bool:
        return bool(self.signals)

    def describe(self) -> str:
        return "; ".join(self.signals)


def bot_challenge(result: ScanResult) -> Challenge:
    """Whether a bot-management challenge stood between us and the site.

    Measured on msi.com on 2026-09-29, this is *not* what a headless browser
    normally meets: msi.com answers 403 with a 363-byte Access Denied page, and
    `httpx` with no browser at all gets the identical answer with and without a
    Chrome User-Agent. That is an edge refusing a network address, which
    `page_not_served` already reports, and no browser setting changes it.

    What this catches is the other shape: a challenge served with a status the
    scanner reads as success. The page identity decides — its title or its text —
    or a status that means "not the page you asked for". Cookies and vendor hosts
    are added to the explanation once one of those has fired, and never decide on
    their own.

    An error page is left alone: 403 and a challenge both mean "the site was not
    seen", but they need different actions from whoever reads the report, so
    merging them would tell an operator to change their browser when the answer is
    to ask for access from this address.
    """
    pre = result.pre_consent
    status = pre.status
    signals: list[str] = []
    haystack = f"{pre.title}\n{pre.text}"
    for pattern in CHALLENGE_TEXT:
        found = pattern.search(haystack)
        if found:
            where = "title" if pattern.search(pre.title) else "page text"
            signals.append(f"the {where} says {found.group(0)!r}")
            break
    if status in CHALLENGE_STATUSES:
        signals.append(f"the site answered HTTP {status}, which is a challenge "
                       f"and not a page")
    if not signals:
        return Challenge()

    named = [c["name"] for c in pre.cookies
             if any(str(c.get("name", "")).startswith(p) for p in CHALLENGE_COOKIES)]
    if named:
        signals.append("bot-management cookies set: " + ", ".join(sorted(named)))
    vendors = sorted({r.host for r in pre.external
                      if any(r.host == h or r.host.endswith(f".{h}")
                             for h in CHALLENGE_HOSTS)})
    if vendors:
        signals.append("challenge hosts contacted: " + ", ".join(vendors))
    return Challenge(signals=tuple(signals))


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


def tracker_domain(url: str) -> str | None:
    """
    Registrable domain of a tracker URL, or None if the host is not a tracker.
    TRACKER_DOMAINS entries are registrable domains, so the matching entry is
    the eTLD+1: region1.google-analytics.com → google-analytics.com.
    """
    host = (urlparse(url).hostname or "").rstrip(".")
    for domain in TRACKER_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def is_tracker(url: str) -> bool:
    """Check if the URL host is a known tracker domain or one of its subdomains."""
    return tracker_domain(url) is not None


ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button[id*='accept-all']",
    "button[class*='accept-all']",
    # A substring match, so "disagree" has to be excluded by name: Didomi puts
    # `didomi-notice-agree-button` and `didomi-notice-disagree-button` side by
    # side, and the selectors are tried before the labels.
    "button[id*='agree']:not([id*='disagree'])",
    # Usercentrics renders its banner inside a shadow root with no ids on the
    # buttons; `data-testid` is the one stable handle. Playwright's selectors
    # pierce open shadow roots. Measured on zalando.it, 2026-10-09.
    "[data-testid='uc-accept-all-button']",
]
REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    ".ot-pc-refuse-all-handler",
    "button[id*='reject-all']",
    "button[class*='refuse-all']",
    # TrustArc's "required cookies only": `#truste-consent-required` on enel.it
    # ("Continua senza accettare"), `#truste-consent-required2` on poste.it ("Non
    # accetto", with the close icon `#truste-consent-required` after it in the
    # DOM, an <a> without href). Prefix match, any tag, first visible in DOM
    # order: the button a person would click comes first on both. Measured
    # 2026-10-09, when both sites were reported as offering no refusal.
    "[id^='truste-consent-required']",
    "[data-testid='uc-deny-all-button']",
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
    # The refusals Italian banners actually carry, measured on 2026-10-09:
    # "Non accetto" (poste.it), "Continua senza accettare" (enel.it, whose
    # banner says it leaves only technical cookies), "Solo gli essenziali"
    # (zalando.it). Whole names, so "accetto" inside "non accetto" cannot be
    # read as acceptance — ACCEPT_LABELS anchor on "accett" at the start.
    re.compile(r"^\s*non\s+accett[ao]\s*$", re.I),
    re.compile(r"^\s*continua\s+senza\s+accettare\s*$", re.I),
    re.compile(r"^\s*continue\s+without\s+accepting\s*$", re.I),
    re.compile(r"^\s*solo\s+(i\s+|gli\s+)?(cookie\s+)?(tecnici|necessari|essenziali)\s*$", re.I),
    re.compile(r"^\s*(only\s+)?(the\s+)?(essential|necessary)(\s+cookies)?(\s+only)?\s*$", re.I),
]


async def _first_visible(page: Page, selector: str):
    """First visible element matching selector (the first match may be hidden)."""
    for element in await page.query_selector_all(selector):
        if await element.is_visible():
            return element
    return None


async def _click_consent_button(page: Page, selectors: list[str], labels: list[re.Pattern]) -> bool:
    """Click the first visible match: CSS selectors first, then buttons by accessible name."""
    for selector in selectors:
        try:
            btn = await _first_visible(page, selector)
            if btn:
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


def _is_main_document(request) -> bool:
    """A navigation of the page itself, as opposed to one of its frames."""
    # `request.frame` raises on a service worker's request, which has no frame,
    # but none gets here: Playwright hands them to the context alone, never to
    # `page.on("request")`, and none is a navigation, so the `and` would stop
    # first anyway. Measured with 1.63 on Windows and Linux; the integration test
    # with a fetching service worker keeps it so.
    return bool(request.is_navigation_request()) and request.frame.parent_frame is None


def _add_error(result: SessionResult, error: Exception) -> None:
    message = str(error).splitlines()[0] if str(error) else type(error).__name__
    result.error = f"{result.error}; {message}" if result.error else message


async def _run_session(
    context: BrowserContext,
    url: str,
    session_name: str,
    accept: bool | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    trackers: TrackerDB | None = None,
) -> SessionResult:
    """
    Run a single browser session and collect trackers.
    Playwright errors are recorded in result.error instead of being raised;
    a navigation timeout does not stop the analysis of the loaded page.
    """
    result = SessionResult(session=session_name)
    page = await context.new_page()
    page_host = _ascii_host(urlparse(url).hostname or "")

    # Intercept requests
    def handle_request(request):
        nonlocal page_host
        now = time.time()
        host = (urlparse(request.url).hostname or "").rstrip(".")
        if host and _is_main_document(request):
            # The site is where the navigation lands, not what was typed: when
            # example.com redirected to example.it, every resource of
            # example.it came out as an unknown external host.
            page_host = host
        if is_same_site(page_host, host):
            # The site's own requests are first-party, which the README puts out
            # of scope. Without this, auditing linkedin.com found linkedin.com a
            # tracker of itself — its own document, in every session, so always
            # a VIOLATION "persists from pre-consent".
            return

        domain = tracker_domain(request.url)
        if domain:
            result.trackers.append(TrackerRequest(
                url=request.url,
                domain=domain,
                resource_type=request.resource_type,
                timestamp=now,
            ))

        # Every external host, recognised or not. Before this line everything
        # that was not among the 34 built-in domains disappeared, and the report
        # could not say out of how many hosts its counts had been chosen.
        if host:
            result.external.append(ExternalRequest(
                url=request.url,
                host=host,
                resource_type=request.resource_type,
                timestamp=now,
                domain=domain,
                tracker=trackers.lookup(host) if trackers is not None else None,
            ))

    page.on("request", handle_request)

    # The main document's status as it arrives, independently of `goto`.
    # `goto` returns the response only when the wait for `networkidle` succeeds;
    # when the page keeps the network busy it raises instead, and the status that
    # had arrived in the first second was lost with it. Measured on 2026-10-09:
    # zalando.it answered 403 from its edge with a page whose scripts never went
    # quiet, so the status was None, `page_not_served` saw nothing wrong, and the
    # audit said "0 trackers before consent, UNVERIFIED" about an error page.
    # enel.it and poste.it, served with 200 and never idle, lost theirs the same
    # way. A redirect answers once per hop, and the document is the last one.
    served: list[int] = []

    def handle_response(response):
        if _is_main_document(response.request):
            served.append(response.status)

    page.on("response", handle_response)

    try:
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            # Kept rather than discarded: everything measured below describes
            # whatever document came back, and on canon.it that is a 364-byte
            # Access Denied page from an edge.
            result.status = response.status if response is not None else None
        except PlaywrightTimeoutError as e:
            _add_error(result, e)
            # None only when no document ever answered: that is the timeout the
            # error already describes. A document that did answer keeps its status.
            result.status = served[-1] if served else None
        await page.wait_for_timeout(3000)

        # The document's own identity, for `bot_challenge`. Taken after the wait
        # above because a challenge either resolves or settles into its final
        # words in the first seconds, and the title before that is often empty.
        #
        # Both are best effort: a page that navigated away mid-read raises, and a
        # missing title is not worth losing a session over. The cap is because
        # only the first screenful ever carries a challenge's words, and a report
        # should not hold a megabyte of someone else's article.
        with suppress(PlaywrightError):
            result.title = await page.title()
        with suppress(PlaywrightError):
            result.text = (await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            ))[:_TEXT_SNIFF]

        # Check for cookie banner
        banner_selectors = [
            "[id*='cookie']", "[class*='cookie']",
            "[id*='consent']", "[class*='consent']",
            "[id*='gdpr']", "[class*='gdpr']",
            "[id*='banner']", "[class*='banner']",
        ]
        for selector in banner_selectors:
            try:
                if await _first_visible(page, selector):
                    result.banner_found = True
                    break
            except PlaywrightError:
                pass

        # Accept all
        if accept is True:
            if await _click_consent_button(page, ACCEPT_SELECTORS, ACCEPT_LABELS):
                result.consent_clicked = True
                await page.wait_for_timeout(2000)

        # Reject all
        elif accept is False:
            # Step 1 — try rejecting outright
            rejected = await _click_consent_button(page, REJECT_SELECTORS, REJECT_LABELS)
            if rejected:
                await page.wait_for_timeout(2000)

            # Step 2 — OneTrust a due step: apri preferenze poi rifiuta
            if not rejected:
                try:
                    pc_btn = await _first_visible(page, "#onetrust-pc-btn-handler")
                    if pc_btn:
                        await pc_btn.click()
                        await page.wait_for_timeout(2000)
                        refuse_btn = await _first_visible(page, ".ot-pc-refuse-all-handler")
                        if refuse_btn:
                            await refuse_btn.click()
                            await page.wait_for_timeout(2000)
                            rejected = True
                except PlaywrightError:
                    pass

            if rejected:
                result.consent_clicked = True
                # Only requests made after the rejection count for this session.
                # `external` is cleared together with `trackers`: keeping it
                # would make every host contacted before the rejection appear
                # among the post-rejection ones, and the count of unknowns would
                # be twice the truth.
                result.trackers.clear()
                result.external.clear()
                try:
                    await page.reload(wait_until="networkidle", timeout=timeout_ms)
                except PlaywrightTimeoutError as e:
                    _add_error(result, e)
                await page.wait_for_timeout(2000)
    except PlaywrightError as e:
        _add_error(result, e)
    finally:
        try:
            result.cookies = await context.cookies()
        except PlaywrightError as e:
            _add_error(result, e)
        await page.close()

    return result


async def scan(url: str, headless: bool = True, timeout_ms: int = DEFAULT_TIMEOUT_MS,
               trackers: TrackerDB | None = None) -> ScanResult:
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
                    session = await _run_session(ctx, url, name, accept=accept,
                                                 timeout_ms=timeout_ms,
                                                 trackers=trackers)
                except Exception as e:
                    session = SessionResult(session=name)
                    _add_error(session, e)
                finally:
                    await ctx.close()
                setattr(result, attr, session)
        finally:
            await browser.close()

    return result
