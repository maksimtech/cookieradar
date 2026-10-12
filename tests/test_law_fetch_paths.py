"""The two paths of the HTTPS-only fetch that no recording reaches.

SonarCloud failed main on 2026-10-11 on the coverage of new code (78.6% against
80%): `fetch_html` without a client of its own, and the limit on redirects, had
no test. Both are exercised here against real servers on 127.0.0.1, not against
answers made up for the occasion.

- A plain HTTP server: asked for an http:// URL with no client given, fetch_html
  builds its own, takes the request over https://, and the server never serves
  anything in clear.
- An HTTPS server whose every answer redirects to itself, with a certificate made
  here with `cryptography` (a test dependency) and trusted only by the client
  passed in: the fetch gives up after MAX_REDIRECTS hops instead of following
  forever.
"""

from __future__ import annotations

import datetime
import ipaddress
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from cookieradar.law_fetcher import MAX_REDIRECTS, LawFetchError, fetch_html


@contextmanager
def _serve(handler: type[BaseHTTPRequestHandler], context: ssl.SSLContext | None = None) -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    if context is not None:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def test_without_a_client_the_fetch_never_goes_out_in_clear():
    served: list[str] = []

    class Plain(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>in clear</html>")

        def log_message(self, *args: object) -> None:
            pass

    with _serve(Plain) as server:
        port = server.server_address[1]
        with pytest.raises(LawFetchError, match="unreachable"):
            fetch_html(f"http://127.0.0.1:{port}/resource/act", timeout=5)
    assert served == []


@pytest.fixture
def certificate(tmp_path: Path) -> tuple[Path, Path]:
    """A certificate for 127.0.0.1, valid for an hour and trusted by nobody but
    the client this test builds."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


def test_a_redirect_loop_stops_after_the_limit(certificate):
    cert, key = certificate
    served: list[str] = []

    class Loop(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served.append(self.path)
            self.send_response(302)
            self.send_header("Location", self.path)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # TLS 1.2 at least: without a floor CodeQL reports the context as allowing
    # insecure protocol versions (py/insecure-protocol, alert #108).
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(cert, key)
    with _serve(Loop, server_context) as server:
        port = server.server_address[1]
        client_context = ssl.create_default_context(cafile=str(cert))
        with (
            httpx.Client(verify=client_context, timeout=5) as client,
            pytest.raises(LawFetchError, match=f"redirected more than {MAX_REDIRECTS} times"),
        ):
            fetch_html(f"https://127.0.0.1:{port}/resource/act", client=client)
    assert served == ["/resource/act"] * (MAX_REDIRECTS + 1)
