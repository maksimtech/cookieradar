"""
CookieRadar — the challenge detector against a real browser, not a hand-built result.

tests/test_bot_challenge.py builds `ScanResult` objects directly, so all of it
passes even if `_run_session` never records a title or a body. That capture is the
half that has to work in production: without it every field the detector reads is
empty, `bot_challenge` returns nothing, and a challenge page is reported as a site
with no trackers and no banner — which is what a compliant site looks like.

A local server is the whole third party here. It answers 200 with Cloudflare's
wording, which is the shape that matters: a success status carrying something that
is not the site. msi.com, the case that started this, is *not* this shape — it
answers 403 and `page_not_served` has always caught it.

Marked `integration` because it launches Chromium three times, once per session.
"""
from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cookieradar.scanner import bot_challenge, page_not_served, scan

CHALLENGE = b"""<!DOCTYPE html><html><head><title>Just a moment...</title></head>
<body><div id="challenge-running">
<h1>example.com needs to review the security of your connection before proceeding.</h1>
<p>Verifying you are human. This may take a few seconds.</p>
</div></body></html>"""

REAL_SITE = b"""<!DOCTYPE html><html><head><title>Example Shop</title></head>
<body><h1>Our products</h1><p>Browse the catalogue below.</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    page = CHALLENGE
    status = 200
    set_cookie: str | None = None

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.page)))
        if self.set_cookie:
            self.send_header("Set-Cookie", self.set_cookie)
        self.end_headers()
        self.wfile.write(self.page)

    def log_message(self, *_args):
        pass


def serve(page: bytes, *, status: int = 200, cookie: str | None = None):
    handler = type("H", (Handler,), {"page": page, "status": status,
                                     "set_cookie": cookie})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


@pytest.mark.integration
def test_a_challenge_served_with_200_is_caught_end_to_end():
    """The capture in `_run_session` and the detector, together, through the real
    browser. Nothing is stubbed."""
    server, url = serve(CHALLENGE, cookie="__cf_bm=abc; Path=/")
    try:
        result = asyncio.run(scan(url))
    finally:
        server.shutdown()
        server.server_close()

    assert result.pre_consent.status == 200, "the status alone gives nothing away"
    assert not page_not_served(result), "which is exactly why this check exists"

    found = bot_challenge(result)
    assert found.seen is True, f"title={result.pre_consent.title!r}"
    joined = found.describe().lower()
    assert "just a moment" in joined or "verifying you are human" in joined
    # The cookie corroborates once the page has already said it, and naming the
    # vendor is what lets an operator ask the right party for access.
    assert "__cf_bm" in found.describe()


@pytest.mark.integration
def test_an_ordinary_page_served_by_the_same_server_is_not_a_challenge():
    """The other half, and the one that protects coverage: the same harness, the
    same cookie, a page that is the site. A detector that fired here would make
    cookieradar refuse to audit a large share of Cloudflare-fronted sites."""
    server, url = serve(REAL_SITE, cookie="__cf_bm=abc; Path=/")
    try:
        result = asyncio.run(scan(url))
    finally:
        server.shutdown()
        server.server_close()

    assert result.pre_consent.title == "Example Shop"
    assert bot_challenge(result).seen is False


@pytest.mark.integration
def test_the_title_and_text_are_recorded_at_all():
    """The narrow fact everything above rests on. If `_run_session` stopped
    capturing these, the unit tests would stay green and the feature would be
    dead."""
    server, url = serve(REAL_SITE)
    try:
        result = asyncio.run(scan(url))
    finally:
        server.shutdown()
        server.server_close()

    assert result.pre_consent.title == "Example Shop"
    assert "Our products" in result.pre_consent.text
