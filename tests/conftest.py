"""
Shared fixtures: Playwright page mocks and a local HTTP test site.
"""
import http.server
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SITE_DIR = Path(__file__).parent / "site"


def fake_request(url: str, resource_type: str = "script"):
    req = MagicMock()
    req.url = url
    req.resource_type = resource_type
    return req


def make_mock_context(page=None):
    """Return (context, page) mocks; page.on stores handlers in page.handlers."""
    page = page or AsyncMock()
    page.handlers = {}
    page.on = MagicMock(side_effect=lambda ev, fn: page.handlers.setdefault(ev, fn))
    page.query_selector = AsyncMock(return_value=None)
    no_buttons = MagicMock()
    no_buttons.count = AsyncMock(return_value=0)
    page.get_by_role = MagicMock(return_value=no_buttons)
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.cookies = AsyncMock(return_value=[])
    return context, page


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/hang"):
            time.sleep(10)
        if self.path.startswith(("/hang", "/beacon")):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        super().do_GET()


@pytest.fixture(scope="session")
def site_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def browser():
    """Real Chromium; skipped when Playwright browsers are not installed."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            b = await p.chromium.launch()
        except Exception as e:  # pragma: no cover - depends on environment
            pytest.skip(f"Chromium not available: {e}")
        yield b
        await b.close()
