"""
CookieRadar — every external host contacted, not only the recognised ones

Until now `handle_request` kept a request only if its host was among the 34
hand-written domains, and dropped everything else. The report therefore said
"9 trackers before consent" without ever saying out of how many hosts those 9
had been chosen — and an unrecognised host disappeared exactly like one never
contacted.

They are two different things and the report has to tell them apart:

    31 external hosts contacted before consent
      23 identified
       8 unknown

The third line does not come from a bigger database: it comes from deciding to
count it. A list of 5,104 domains still leaves something out, and without this
count nobody would know how much.
"""
from cookieradar.scanner import ExternalRequest, SessionResult, is_same_site, summarise_external
from cookieradar.trackerdb import Organization, Tracker

# ── same site or external host ───────────────────────────────────────────────

def test_the_same_host_is_the_same_site():
    assert is_same_site("example.it", "example.it")


def test_www_and_the_bare_domain_are_the_same_site():
    """No public suffix list is needed for this, and it is the case that would
    otherwise fill the report with noise."""
    assert is_same_site("example.it", "www.example.it")
    assert is_same_site("www.example.it", "example.it")


def test_a_subdomain_is_the_same_site():
    assert is_same_site("example.it", "static.cdn.example.it")


def test_sibling_subdomains_of_a_www_page_are_the_same_site():
    """Measured on tim.it on 2026-09-27: scanning `www.tim.it`, `api.tim.it`
    finiva fra gli host sconosciuti insieme ai tracker veri. Nessuno dei due e'
    sottodominio dell'altro - lo sono entrambi di `tim.it`."""
    assert is_same_site("www.tim.it", "api.tim.it")
    assert is_same_site("www.tim.it", "cdn.static.tim.it")


def test_stripping_www_does_not_swallow_a_two_label_host():
    """`www.it` must not become `it`, or every Italian site would be one site."""
    assert not is_same_site("www.it", "example.it")


def test_a_sibling_of_a_non_www_page_is_still_external():
    """A known and accepted limit: without a public suffix list there is no way
    of knowing where the registrable domain ends, and getting that boundary wrong
    would say `x.co.uk` and `y.co.uk` are one site — a worse error than this."""
    assert not is_same_site("shop.example.com", "blog.example.com")


def test_another_domain_is_external():
    assert not is_same_site("example.it", "google-analytics.com")


def test_a_suffix_that_is_not_a_subdomain_is_external():
    """`notexample.it` is not a subdomain of `example.it`."""
    assert not is_same_site("example.it", "notexample.it")


def test_case_and_trailing_dot_do_not_matter():
    assert is_same_site("Example.IT", "WWW.example.it.")


def test_an_empty_host_is_not_the_same_site():
    """A request with no host — `data:` or `blob:` — is neither the site's nor a
    third party's: it is not counted, and nothing pretends to know."""
    assert not is_same_site("example.it", "")
    assert not is_same_site("", "example.it")


# ── il riepilogo, che e' il punto ────────────────────────────────────────────

def _req(host, tracker=None, domain=None):
    return ExternalRequest(url=f"https://{host}/x", host=host, resource_type="script",
                           timestamp=0.0, tracker=tracker, domain=domain)


GOOGLE = Tracker(
    id="google_analytics", name="Google Analytics", category="site_analytics",
    domains=("google-analytics.com",),
    organization=Organization(id="google", name="Google", country="US",
                              privacy_policy_url="https://policies.google.com/privacy"),
)


def test_counts_hosts_not_requests():
    """Twenty requests to the same host are one host, not twenty: the report
    speaks of who was contacted, not of how many times."""
    session = SessionResult("pre-consent")
    session.external = [_req("google-analytics.com", GOOGLE, "google-analytics.com")] * 20
    summary = summarise_external(session)
    assert summary.hosts == 1
    assert summary.identified == 1


def test_separates_identified_from_unknown():
    session = SessionResult("pre-consent")
    session.external = [
        _req("google-analytics.com", GOOGLE, "google-analytics.com"),
        _req("something-we-do-not-know.example", None, None),
        _req("nor-this-one.example", None, None),
    ]
    summary = summarise_external(session)
    assert summary.hosts == 3
    assert summary.identified == 1
    assert sorted(summary.unknown) == ["nor-this-one.example",
                                       "something-we-do-not-know.example"]


def test_an_empty_session_has_no_unknowns_rather_than_an_unknown_number():
    """Zero hosts contacted is a measurement, not the absence of one."""
    summary = summarise_external(SessionResult("pre-consent"))
    assert summary.hosts == 0
    assert summary.identified == 0
    assert summary.unknown == []


def test_groups_identified_hosts_by_organization():
    """The question an auditor asks is not "how many domains" but "how many
    companies", and four Adobe domains are one company."""
    adobe = Organization(id="adobe", name="Adobe", country="US")
    session = SessionResult("pre-consent")
    session.external = [
        _req("demdex.net", Tracker("a", "Adobe Audience Manager", "advertising",
                                   ("demdex.net",), organization=adobe)),
        _req("everesttech.net", Tracker("b", "Adobe Advertising Cloud", "advertising",
                                        ("everesttech.net",), organization=adobe)),
        _req("google-analytics.com", GOOGLE),
    ]
    summary = summarise_external(session)
    assert summary.organizations == {"Adobe": 2, "Google": 1}


def test_categories_are_counted_by_host():
    session = SessionResult("pre-consent")
    session.external = [
        _req("google-analytics.com", GOOGLE),
        _req("doubleclick.net", Tracker("d", "Google Marketing Platform", "advertising",
                                        ("doubleclick.net",))),
    ]
    summary = summarise_external(session)
    assert summary.categories == {"site_analytics": 1, "advertising": 1}


def test_an_identified_host_without_an_organization_is_not_lost():
    """437 real patterns have no organization: they are first-party domains.
    Counting them among the identified and saying nothing about the company is
    right; dropping them because a field is missing is not."""
    session = SessionResult("pre-consent")
    session.external = [_req("1822direkt.de", Tracker("x", "1822direkt.de", "misc",
                                                      ("1822direkt.de",)))]
    summary = summarise_external(session)
    assert summary.identified == 1
    assert summary.organizations == {}
