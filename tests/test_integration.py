"""
Integration tests against a local site with a real Chromium.
Tracker hosts are fulfilled locally via context.route, no network needed.
Skipped when Playwright browsers are not installed.
"""
import http.server
import re
import threading

import pytest

from cookieradar.scanner import ACCEPT_LABELS, ACCEPT_SELECTORS, _click_consent_button, _run_session

TRACKER_HOSTS = re.compile(r"^https?://[^/]*(doubleclick\.net|facebook\.com)/")


async def _context(browser):
    ctx = await browser.new_context()
    await ctx.route(TRACKER_HOSTS, lambda route: route.fulfill(status=200, body="ok"))
    return ctx


@pytest.mark.integration
async def test_compliant_site_has_no_post_reject_trackers(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/reject.html", "post-reject", accept=False)
    await ctx.close()

    assert result.trackers == []


@pytest.mark.integration
async def test_non_compliant_site_reports_trackers_after_reject(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/persist.html", "post-reject", accept=False)
    await ctx.close()

    assert {t.domain for t in result.trackers} == {"doubleclick.net", "facebook.com"}


@pytest.mark.integration
async def test_never_idle_page_times_out_without_raising(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/never_idle.html", "pre-consent", timeout_ms=1500)
    await ctx.close()

    assert "Timeout" in result.error
    assert {t.domain for t in result.trackers} == {"doubleclick.net"}
    assert result.banner_found is True


async def _clicked(ctx):
    return {c["name"]: c["value"] for c in await ctx.cookies()}.get("clicked")


@pytest.mark.integration
async def test_accept_clicks_accept_button_not_substring_matches(browser, site_url):
    ctx = await _context(browser)
    await _run_session(ctx, f"{site_url}/accept.html", "post-accept", accept=True)
    clicked = await _clicked(ctx)
    await ctx.close()

    assert clicked == "accept"


@pytest.mark.integration
async def test_reject_clicks_first_visible_exact_match(browser, site_url):
    ctx = await _context(browser)
    await _run_session(ctx, f"{site_url}/reject_buttons.html", "post-reject", accept=False)
    clicked = await _clicked(ctx)
    await ctx.close()

    assert clicked == "reject"


@pytest.mark.integration
async def test_cookies_are_collected_from_the_browser(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/reject.html", "post-reject", accept=False)
    await ctx.close()

    assert {c["name"]: c["value"] for c in result.cookies} == {"consent": "no"}


@pytest.mark.integration
async def test_banner_and_button_first_visible_match(browser, site_url):
    ctx = await _context(browser)
    result = await _run_session(ctx, f"{site_url}/banner.html", "post-accept", accept=True)
    clicked = await _clicked(ctx)
    await ctx.close()

    assert result.banner_found is True
    assert clicked == "visible"


# ─── a service worker's requests never reach the page's listener ────────────

@pytest.mark.integration
async def test_a_service_worker_that_fetches_does_not_disturb_the_session(browser, site_url):
    """A service worker's request has no frame, and asking for one raises. The
    scanner listens on the page, where Chromium never delivers them — they go to
    the context alone — so the session neither fails on them nor counts them.

    The worker fetches from another host while installing and again to answer a
    request of the page; the title it writes proves both happened."""
    ctx = await browser.new_context()
    result = await _run_session(ctx, f"{site_url}/service_worker.html", "pre-consent")
    await ctx.close()

    assert result.error is None
    assert result.status == 200
    assert result.title == "answered by the service worker (opaque)"
    assert result.external == []


# ─── accept selectors: "agree" without "disagree" ───────────────────────────

_RECORD_CLICKS = (
    "<script>document.querySelectorAll('button').forEach("
    "b => b.onclick = () => window.clicked = b.id)</script>"
)


async def _clicked_id(page):
    """The id of the button the page saw clicked, waited for rather than read
    straight after the click."""
    handle = await page.wait_for_function("() => window.clicked")
    return await handle.json_value()


@pytest.mark.integration
async def test_accept_does_not_click_a_disagree_button(browser):
    """`button[id*='agree']` is a substring match: it also matches
    id="disagree-btn". CSS selectors come before the labels, so the post-accept
    session clicked "Disagree" with "Accept" right next to it."""
    page = await browser.new_page()
    await page.set_content(
        "<div id='cookie-banner'>"
        "<button id='disagree-btn'>Disagree</button>"
        "<button id='btn-ok'>Accept</button></div>" + _RECORD_CLICKS
    )

    clicked = await _click_consent_button(page, ACCEPT_SELECTORS, ACCEPT_LABELS)

    assert clicked is True
    assert await _clicked_id(page) == "btn-ok"
    await page.close()


@pytest.mark.integration
async def test_accept_still_clicks_an_agree_button_by_its_id(browser):
    """The opposite guard: leaving "disagree" out must not lose the selector.
    The label "Agree and close" matches none of ACCEPT_LABELS, so only the
    selector on the id can find it."""
    page = await browser.new_page()
    await page.set_content(
        "<div id='didomi-notice'>"
        "<button id='didomi-notice-disagree-button'>Disagree and close</button>"
        "<button id='didomi-notice-agree-button'>Agree and close</button></div>" + _RECORD_CLICKS
    )

    clicked = await _click_consent_button(page, ACCEPT_SELECTORS, ACCEPT_LABELS)

    assert clicked is True
    assert await _clicked_id(page) == "didomi-notice-agree-button"
    await page.close()


# ─── the site is where the navigation lands, as Chromium spells it ──────────

def _page(*urls):
    """A page that loads one resource from each of `urls`."""
    return "".join(f"<script src='{u}'></script>" for u in urls).encode()


class _LocalSites(http.server.BaseHTTPRequestHandler):
    """Several sites on one local server, told apart by the Host header."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        host = self.headers.get("Host", "").split(":")[0]
        port = self.server.server_address[1]
        if host == "old.test":
            self.send_response(302)
            self.send_header("Location", f"http://www.new.test:{port}/")
            self.end_headers()
            return
        body = b""
        if host in ("www.new.test", "xn--strae-oqa.test"):
            body = (f"<link rel='stylesheet' href='http://{host}:{port}/s.css'>"
                    f"<link rel='stylesheet' href='http://static.new.test:{port}/s.css'>"
                    f"<script src='http://cdn.other.test:{port}/x.js'></script>").encode()
        elif host == "xn--mller-kva.test":
            body = _page(f"http://{host}:{port}/style.js",
                         f"http://static.{host}:{port}/app.js")
        elif host == "www.linkedin.com":
            body = _page(f"http://static.linkedin.com:{port}/app.js",
                         # The guard: a third party's tracker on the same page
                         # is still a tracker.
                         f"http://static.klaviyo.com:{port}/onsite.js")
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if body else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_sites():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LocalSites)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


async def _local_session(url):
    """One pre-consent session with every host resolved to this machine.

    Chromium resolves every name to 127.0.0.1 (`--host-resolver-rules`) and
    `_LocalSites` picks the site from the Host header: nothing leaves the
    machine, not even a host the page was not meant to ask for.

    The navigation gets the scanner's default timeout: "networkidle" on a busy
    machine can take longer than a tight one, and the session then ended with
    no status and nothing to compare.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            b = await p.chromium.launch(args=["--host-resolver-rules=MAP * 127.0.0.1"])
        except Exception as e:  # pragma: no cover - depends on environment
            pytest.skip(f"Chromium not available: {e}")
        context = await b.new_context()
        try:
            result = await _run_session(context, url, "pre-consent")
        finally:
            await context.close()
            await b.close()
    assert result.status == 200, result.error
    return result


async def _external_hosts(url):
    return sorted({r.host for r in (await _local_session(url)).external})


@pytest.mark.integration
async def test_requests_of_the_site_a_redirect_lands_on_are_not_external(local_sites):
    """`page_host` came from the URL asked for, not from the one the navigation
    lands on: when old.test redirected to www.new.test, every resource of
    new.test came out as an unknown external host.

    `route.fulfill` with a 302 is not enough to stage this, because the
    redirected request no longer goes through the route and ends up at DNS."""
    assert await _external_hosts(f"http://old.test:{local_sites}/") == ["cdn.other.test"]


@pytest.mark.integration
async def test_an_idn_the_python_codec_spells_differently_is_still_the_site(local_sites):
    """Python's `idna` codec is IDNA 2003 and spells straße "strasse"; Chromium
    (UTS-46) spells it "xn--strae-oqa". It is the navigation's host, in
    Chromium's spelling, that decides which site this is."""
    hosts = await _external_hosts(f"http://straße.test:{local_sites}/")

    assert hosts == ["cdn.other.test", "static.new.test"]


# ─── the audited site's own requests are first-party ────────────────────────

@pytest.mark.integration
async def test_first_party_requests_of_an_idn_site_are_not_external(local_sites):
    """`page_host` came from the address typed, in Unicode (müller.test), while
    Chromium sends the requests in punycode (xn--mller-kva.test). Every resource
    of the site itself ended up among the unknown "external hosts"."""
    assert await _external_hosts(f"http://müller.test:{local_sites}/") == []


@pytest.mark.integration
async def test_the_audited_sites_own_document_is_not_a_tracker(local_sites):
    """Auditing linkedin.com (or facebook.com, bing.com, tiktok.com…) the main
    document's request was classified as the tracker "linkedin.com": the site
    was always a VIOLATION "persists from pre-consent" for the mere fact of
    being loaded. The README puts first-party tracking out of scope.

    Plain HTTP on purpose, and linkedin.com because Chromium's HSTS preload
    list does not force it to HTTPS (facebook.net and bing.com it does)."""
    result = await _local_session(f"http://www.linkedin.com:{local_sites}/")

    assert [t.domain for t in result.trackers] == ["klaviyo.com"]
    assert [r.host for r in result.external] == ["static.klaviyo.com"]
