"""
The test site's 403 route cannot read outside tests/site/.

CodeQL alert #99 (py/path-injection) on PR #28: `/forbidden/<name>` joined the
request path to SITE_DIR without a containment check, so `GET
/forbidden/../conftest.py` would have read this very suite's conftest. The
server listens on 127.0.0.1 and lives for one pytest session, so the risk was
small; the policy is to fix it or to argue it, and fixing is shorter.

Real requests against the real fixture server, through urllib. `http.client`
sends the path as written, dots included, which is the point.
"""
import urllib.error
import urllib.request

import pytest

from tests.conftest import SITE_DIR

CONFTEST_MARK = b"Shared fixtures: Playwright page mocks and a local HTTP test site."


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - local test server
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_the_route_serves_the_page_with_403(site_url):
    status, body = _get(f"{site_url}/forbidden/forbidden_busy.html")

    assert status == 403
    assert body == (SITE_DIR / "forbidden_busy.html").read_bytes()


@pytest.mark.parametrize("path", [
    "/forbidden/../conftest.py",
    "/forbidden/%2e%2e/conftest.py",
    "/forbidden/..%2fconftest.py",
    "/forbidden/../../pyproject.toml",
])
def test_the_route_does_not_read_outside_the_site(site_url, path):
    status, body = _get(f"{site_url}{path}")

    assert status == 404
    assert CONFTEST_MARK not in body
    assert b"[project]" not in body


def test_a_missing_page_is_404_not_a_crash(site_url):
    status, _ = _get(f"{site_url}/forbidden/no-such-page.html")

    assert status == 404
