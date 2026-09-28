"""
CookieRadar — ogni host esterno contattato, non solo quelli riconosciuti

Finora `handle_request` teneva una richiesta solo se il suo host era fra i 34
domini scritti a mano, e scartava tutto il resto. Il report diceva quindi
"9 tracker prima del consenso" senza mai dire su quanti host quei 9 fossero
stati scelti - e un host non riconosciuto spariva esattamente come uno non
contattato.

Sono due cose diverse e il report deve saperle distinguere:

    31 host esterni contattati prima del consenso
      23 identificati
       8 sconosciuti

La terza riga non arriva da un database piu' grande: arriva dal decidere di
contarla. Un elenco da 5104 domini lascia comunque qualcosa fuori, e senza
questo conteggio nessuno saprebbe quanto.
"""
from cookieradar.scanner import ExternalRequest, SessionResult, is_same_site, summarise_external
from cookieradar.trackerdb import Organization, Tracker

# ── stesso sito o host esterno ───────────────────────────────────────────────

def test_the_same_host_is_the_same_site():
    assert is_same_site("example.it", "example.it")


def test_www_and_the_bare_domain_are_the_same_site():
    """Nessuna lista di suffissi pubblici e' necessaria per questo, ed e' il
    caso che altrimenti riempirebbe il report di rumore."""
    assert is_same_site("example.it", "www.example.it")
    assert is_same_site("www.example.it", "example.it")


def test_a_subdomain_is_the_same_site():
    assert is_same_site("example.it", "static.cdn.example.it")


def test_sibling_subdomains_of_a_www_page_are_the_same_site():
    """Misurato su tim.it il 27/09/2026: scansionando `www.tim.it`, `api.tim.it`
    finiva fra gli host sconosciuti insieme ai tracker veri. Nessuno dei due e'
    sottodominio dell'altro - lo sono entrambi di `tim.it`."""
    assert is_same_site("www.tim.it", "api.tim.it")
    assert is_same_site("www.tim.it", "cdn.static.tim.it")


def test_stripping_www_does_not_swallow_a_two_label_host():
    """`www.it` non deve diventare `it`, o ogni sito italiano sarebbe lo stesso."""
    assert not is_same_site("www.it", "example.it")


def test_a_sibling_of_a_non_www_page_is_still_external():
    """Limite noto e accettato: senza una lista di suffissi pubblici non si sa
    dove finisce il dominio registrabile, e sbagliare quel confine direbbe che
    `x.co.uk` e `y.co.uk` sono lo stesso sito - errore peggiore di questo."""
    assert not is_same_site("shop.example.com", "blog.example.com")


def test_another_domain_is_external():
    assert not is_same_site("example.it", "google-analytics.com")


def test_a_suffix_that_is_not_a_subdomain_is_external():
    """`notexample.it` non e' un sottodominio di `example.it`."""
    assert not is_same_site("example.it", "notexample.it")


def test_case_and_trailing_dot_do_not_matter():
    assert is_same_site("Example.IT", "WWW.example.it.")


def test_an_empty_host_is_not_the_same_site():
    """Una richiesta senza host - `data:` o `blob:` - non e' del sito ne' di
    un terzo: non si conta, e non si finge di saperlo."""
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
    """Venti richieste allo stesso host sono un host, non venti: il report
    parla di chi e' stato contattato, non di quante volte."""
    session = SessionResult("pre-consent")
    session.external = [_req("google-analytics.com", GOOGLE, "google-analytics.com")] * 20
    summary = summarise_external(session)
    assert summary.hosts == 1
    assert summary.identified == 1


def test_separates_identified_from_unknown():
    session = SessionResult("pre-consent")
    session.external = [
        _req("google-analytics.com", GOOGLE, "google-analytics.com"),
        _req("qualcosa-che-non-conosciamo.example", None, None),
        _req("neanche-questo.example", None, None),
    ]
    summary = summarise_external(session)
    assert summary.hosts == 3
    assert summary.identified == 1
    assert sorted(summary.unknown) == ["neanche-questo.example",
                                       "qualcosa-che-non-conosciamo.example"]


def test_an_empty_session_has_no_unknowns_rather_than_an_unknown_number():
    """Zero host contattati e' una misura, non un'assenza di misura."""
    summary = summarise_external(SessionResult("pre-consent"))
    assert summary.hosts == 0
    assert summary.identified == 0
    assert summary.unknown == []


def test_groups_identified_hosts_by_organization():
    """La domanda che un revisore pone non e' "quanti domini" ma "quante
    aziende", e quattro domini di Adobe sono una azienda sola."""
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
    """437 pattern reali non hanno una organization: sono domini di prima parte.
    Contarli fra gli identificati e tacerne l'azienda e' corretto; scartarli
    perche' manca un campo no."""
    session = SessionResult("pre-consent")
    session.external = [_req("1822direkt.de", Tracker("x", "1822direkt.de", "misc",
                                                      ("1822direkt.de",)))]
    summary = summarise_external(session)
    assert summary.identified == 1
    assert summary.organizations == {}
