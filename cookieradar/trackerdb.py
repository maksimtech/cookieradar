"""Reads a copy of `ghostery/trackerdb` the operator obtained themselves.

**This module is a reader, not the data.** The code is ours and ships under MIT
like the rest of CookieRadar; `ghostery/trackerdb` is CC-BY-NC-SA-4.0, which
forbids commercial use and binds every derivative to carry the same prohibition.
Packing it inside an MIT package would put anyone using CookieRadar at work out
of compliance without their noticing — the label would say one thing and the
contents another.

So CookieRadar distributes none of Ghostery's data. Whoever wants that enrichment
clones the repository and passes the path; the non-commercial clause binds their
use, and that is their own informed decision.

The format, read off the real files on 2026-09-27:

    name: Google Analytics          key: value pairs
    category: site_analytics
    organization: google

    --- domains                     blocks delimited by a --- name line,
    google-analytics.com            closed by an identical line
    --- domains

The shapes that actually recur, counted across 3,535 patterns and 2,608
organizations: 3,535 have name/category/website_url, 3,098 an organization (437
do not), 3,458 a domains block (77 do not), and 2,567 values are declared and
left blank.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The `filters` block is not read. It is ad blocker syntax (`||mmtro.com^$3p`),
# a second language inside the same file, and CookieRadar has to recognise who was
# contacted rather than block them. The 77 patterns that identify only by filter
# stay loaded and never match: a limit of our coverage, counted rather than
# hidden.
_BLOCK_PREFIX = "--- "


def parse_eno(text: str) -> dict[str, str | list[str]]:
    """The document as a dictionary: values for keys, lists for blocks.

    A key declared and left blank does NOT reach the result: in the real files
    that happens 2,567 times, and returning "" would make "not filled in"
    indistinguishable from "filled in with nothing". An empty block does stay, as
    an empty list: the block is there and says there is nothing inside it.
    """
    doc: dict[str, str | list[str]] = {}
    block: str | None = None
    lines: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith(_BLOCK_PREFIX):
            name = line[len(_BLOCK_PREFIX):].strip()
            if block == name:
                doc[name] = lines
                block, lines = None, []
            else:
                # Another block opening while one is still open: the open one
                # is kept, for the same reason as at the end of the file.
                if block is not None:
                    doc[block] = lines
                block, lines = name, []
            continue
        if block is not None:
            if line.strip():
                lines.append(line.strip())
            continue
        if ":" in line:
            # On the first colon only: the URLs contain one.
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if key and value:
                doc[key] = value

    # A block opened and never closed: what was read is kept, because discarding
    # it would lose real data over somebody else's typo.
    if block is not None:
        doc[block] = lines
    return doc


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    country: str | None = None
    website_url: str | None = None
    privacy_policy_url: str | None = None


@dataclass(frozen=True)
class Tracker:
    id: str
    name: str
    category: str
    domains: tuple[str, ...]
    website_url: str | None = None
    organization: Organization | None = None


def _text(doc: dict, key: str) -> str | None:
    value = doc.get(key)
    return value if isinstance(value, str) else None


def _list(doc: dict, key: str) -> list[str]:
    value = doc.get(key)
    return value if isinstance(value, list) else []


class TrackerDB:
    """Lookup by host, with the same semantics as `scanner.tracker_domain`."""

    def __init__(self, trackers: list[Tracker], organizations: dict[str, Organization]):
        self._organizations = organizations
        self._by_domain: dict[str, Tracker] = {}
        self._without_domains = 0
        for tracker in trackers:
            if not tracker.domains:
                self._without_domains += 1
            for domain in tracker.domains:
                # The first to claim a domain keeps it: two patterns claiming
                # the same one are a fact about Ghostery's data, not a decision
                # of ours, and picking one at random each time would make the
                # report irreproducible.
                self._by_domain.setdefault(domain.lower(), tracker)
        self._trackers = len(trackers)

    @property
    def trackers(self) -> int:
        return self._trackers

    @property
    def organizations(self) -> int:
        return len(self._organizations)

    @property
    def domains(self) -> int:
        return len(self._by_domain)

    @property
    def without_domains(self) -> int:
        """Patterns that identify only by filter rule: they never match."""
        return self._without_domains

    def lookup(self, host: str) -> Tracker | None:
        """The tracker that claims `host`, or None.

        Matches the exact domain and its subdomains — `region1.google-
        analytics.com` is Google Analytics — and not any old suffix:
        `notgoogle-analytics.com` is a different domain.
        """
        host = (host or "").strip().rstrip(".").lower()
        if not host:
            return None
        parts = host.split(".")
        for i in range(len(parts) - 1):
            found = self._by_domain.get(".".join(parts[i:]))
            if found is not None:
                return found
        return None

    @classmethod
    def from_directory(cls, path: str | Path) -> TrackerDB:
        """Load from a `db/` directory, or from the clone root that holds it."""
        root = Path(path)
        if not (root / "patterns").is_dir() and (root / "db" / "patterns").is_dir():
            root = root / "db"
        if not (root / "patterns").is_dir():
            raise ValueError(
                f"{path} non sembra un trackerdb: manca la cartella 'patterns'"
            )

        organizations: dict[str, Organization] = {}
        org_dir = root / "organizations"
        if org_dir.is_dir():
            for file in sorted(org_dir.glob("*.eno")):
                doc = parse_eno(file.read_text(encoding="utf-8"))
                organizations[file.stem] = Organization(
                    id=file.stem,
                    name=_text(doc, "name") or file.stem,
                    country=_text(doc, "country"),
                    website_url=_text(doc, "website_url"),
                    privacy_policy_url=_text(doc, "privacy_policy_url"),
                )

        trackers: list[Tracker] = []
        for file in sorted((root / "patterns").glob("*.eno")):
            doc = parse_eno(file.read_text(encoding="utf-8"))
            org_id = _text(doc, "organization")
            trackers.append(Tracker(
                id=file.stem,
                name=_text(doc, "name") or file.stem,
                # `category` is present in all 3,535 real files; if it ever went
                # missing, "unknown" says we do not know instead of attributing
                # some purpose at random.
                category=_text(doc, "category") or "unknown",
                domains=tuple(_list(doc, "domains")),
                website_url=_text(doc, "website_url"),
                organization=organizations.get(org_id) if org_id else None,
            ))
        return cls(trackers, organizations)
