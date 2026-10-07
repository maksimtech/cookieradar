"""
CookieRadar — reading a Ghostery trackerdb directory

The reader is ours and ships under MIT. The data is not: `ghostery/trackerdb`
is CC-BY-NC-SA-4.0, which forbids commercial use and forces any derivative to
carry the same restriction — incompatible with an MIT package, and worse,
invisible to whoever installed one. So CookieRadar ships no tracker data from
it and reads a copy the user obtained themselves.

That is also why the fixtures below are written here rather than copied from the
repository: they reproduce the *format*, which is not copyrightable, with
content that is either plain fact (google-analytics.com belongs to Google) or
invented. The format was read from the real files on 2026-09-27, and the shapes
exercised are the ones that actually occur in them:

    3535 patterns        name / category / website_url in all of them
    3098                 have an `organization` — so 437 do NOT
    3458                 have a `domains` block — so 77 do NOT
    2567 empty values    a declared key with nothing after the colon is normal
    up to 46 domains     in a single block
"""
import pytest

from cookieradar.trackerdb import TrackerDB, parse_eno

PATTERN = """\
name: Google Analytics
category: site_analytics
website_url: https://analytics.google.com/
organization: google

--- domains
google-analytics.com
analytics.google.com
--- domains

--- filters
||google-analytics.com^$3p
--- filters
"""

ORGANIZATION = """\
name: Google
website_url: https://www.google.com/
privacy_policy_url: https://policies.google.com/privacy
privacy_contact:
country: US
description: Search and advertising.

--- notes
--- notes

ghostery_id: 1
"""


# ── il formato ───────────────────────────────────────────────────────────────

def test_reads_key_value_pairs():
    doc = parse_eno(PATTERN)
    assert doc["name"] == "Google Analytics"
    assert doc["category"] == "site_analytics"


def test_reads_a_fenced_block_as_a_list():
    doc = parse_eno(PATTERN)
    assert doc["domains"] == ["google-analytics.com", "analytics.google.com"]


def test_reads_several_blocks_independently():
    doc = parse_eno(PATTERN)
    assert doc["filters"] == ["||google-analytics.com^$3p"]


def test_an_empty_value_is_absent_not_empty():
    """`privacy_contact: ` with nothing after it occurs 2567 times in the real
    organizations. A declared key with no value is not an empty answer — it is
    no answer, and returning "" would make the two indistinguishable."""
    doc = parse_eno(ORGANIZATION)
    assert doc.get("privacy_contact") is None
    assert doc["country"] == "US"


def test_an_empty_block_is_an_empty_list():
    """Unlike an empty value: the block IS there and says "nothing here"."""
    doc = parse_eno(ORGANIZATION)
    assert doc["notes"] == []


def test_a_missing_block_is_absent():
    doc = parse_eno("name: x\ncategory: misc\n")
    assert "domains" not in doc


def test_a_colon_inside_a_value_survives():
    """`website_url: https://x/` splits on the first colon only."""
    doc = parse_eno("website_url: https://analytics.google.com/path\n")
    assert doc["website_url"] == "https://analytics.google.com/path"


def test_block_lines_are_not_parsed_as_keys():
    """A filter can contain a colon; inside a block it is content, not a key."""
    doc = parse_eno("--- filters\n||x.com^$3p,domain:y.com\n--- filters\n")
    assert doc["filters"] == ["||x.com^$3p,domain:y.com"]


def test_parse_eno_keeps_an_unclosed_block_followed_by_another_block():
    """The docstring promises not to lose data over someone else's typo, an
    unclosed block, but kept that promise only at the end of the file: when an
    unclosed `--- domains` was followed by `--- filters`, the domains were
    dropped and the tracker no longer matched any host."""
    doc = parse_eno("name: X\n--- domains\na.com\n--- filters\n||x^\n--- filters\n")

    assert doc.get("domains") == ["a.com"]


# ── la base dati ─────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    (tmp_path / "patterns").mkdir()
    (tmp_path / "organizations").mkdir()
    (tmp_path / "categories").mkdir()
    (tmp_path / "patterns" / "google_analytics.eno").write_text(PATTERN, encoding="utf-8")
    (tmp_path / "organizations" / "google.eno").write_text(ORGANIZATION, encoding="utf-8")
    return TrackerDB.from_directory(tmp_path)


def test_finds_a_tracker_by_its_domain(db):
    t = db.lookup("google-analytics.com")
    assert t is not None
    assert t.name == "Google Analytics"
    assert t.category == "site_analytics"


def test_finds_a_tracker_on_a_subdomain(db):
    """`region1.google-analytics.com` is the same tracker, and the scanner sees
    subdomains far more often than bare ones."""
    assert db.lookup("region1.google-analytics.com").name == "Google Analytics"


def test_does_not_match_a_suffix_that_is_not_a_subdomain(db):
    """notgoogle-analytics.com is a different domain entirely."""
    assert db.lookup("notgoogle-analytics.com") is None


def test_an_unknown_host_is_none(db):
    assert db.lookup("example.org") is None


def test_the_organization_is_joined_in(db):
    org = db.lookup("google-analytics.com").organization
    assert org is not None
    assert org.name == "Google"
    assert org.country == "US"
    assert org.privacy_policy_url == "https://policies.google.com/privacy"


def test_a_pattern_without_an_organization_still_loads(tmp_path):
    """437 of the real patterns have none: they are first-party domains such as
    `1822direkt.de`. Refusing them would drop an eighth of the database."""
    (tmp_path / "patterns").mkdir()
    (tmp_path / "organizations").mkdir()
    (tmp_path / "patterns" / "x.eno").write_text(
        "name: 1822direkt.de\ncategory: misc\n\n--- domains\n1822direkt.de\n--- domains\n",
        encoding="utf-8")
    db = TrackerDB.from_directory(tmp_path)
    t = db.lookup("1822direkt.de")
    assert t.name == "1822direkt.de"
    assert t.organization is None


def test_a_pattern_with_no_domains_is_kept_but_matches_nothing(tmp_path):
    """77 of the real patterns identify only by filter rule. CookieRadar does
    not read filters, so they can never match — and that is a fact about our
    coverage, not a reason to pretend they do not exist."""
    (tmp_path / "patterns").mkdir()
    (tmp_path / "organizations").mkdir()
    (tmp_path / "patterns" / "t.eno").write_text(
        "name: Adobe Target\ncategory: advertising\n\n--- filters\n/mbox.js\n--- filters\n",
        encoding="utf-8")
    db = TrackerDB.from_directory(tmp_path)
    assert db.lookup("mbox.js") is None
    assert db.without_domains == 1


def test_counts_say_what_was_loaded(db):
    """A database that loaded nothing must not look like one that matched
    nothing."""
    assert db.trackers == 1
    assert db.organizations == 1
    assert db.domains == 2


def test_a_directory_that_is_not_a_trackerdb_is_refused(tmp_path):
    with pytest.raises(ValueError, match="patterns"):
        TrackerDB.from_directory(tmp_path)


def test_the_db_directory_may_be_given_instead_of_its_parent(tmp_path):
    """A user will point at the clone, at its `db/`, or at either with a
    trailing separator. All three are the same intent."""
    root = tmp_path / "trackerdb"
    (root / "db" / "patterns").mkdir(parents=True)
    (root / "db" / "organizations").mkdir(parents=True)
    (root / "db" / "patterns" / "g.eno").write_text(PATTERN, encoding="utf-8")
    (root / "db" / "organizations" / "google.eno").write_text(ORGANIZATION, encoding="utf-8")
    assert TrackerDB.from_directory(root).lookup("google-analytics.com") is not None
    assert TrackerDB.from_directory(root / "db").lookup("google-analytics.com") is not None
