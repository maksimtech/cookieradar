"""
CookieRadar — EU and Italian law provisions for audit findings.

Maps what an audit found to the provisions it concerns, and cites each one
with the SHA-256 of the exact text applied and the date of that wording. The
text is downloaded on every audit (EUR-Lex, or Normattiva for Italian law)
and compared with the local cache; without network the cached copy is cited.

Shared by the Radar tools: only the mapping section is specific to CookieRadar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cookieradar import law_fetcher
from cookieradar.law_cache import Key, LawCache
from cookieradar.law_fetcher import CONSUMER_CODE, DIGITAL_CONTENT, EPRIVACY, GDPR, Act, LawFetchError, Provision

# ─── Mapping: CookieRadar findings → provisions ───────────────────────────────

# Finding → cited provisions, in report order. All four come from the same
# evidence, trackers loaded after rejection, and cite different rules.
FINDING_ARTICLES = {
    "violation": ((GDPR, "5(1)(a)"), (EPRIVACY, "5(3)")),
    "unfair_practice": ((CONSUMER_CODE, "20"), (CONSUMER_CODE, "21")),
    "post_reject": ((GDPR, "7"),),
    "invalid_consent": ((DIGITAL_CONTENT, "3(8)"),),
    # Different evidence from the four above: not what the trackers did, but
    # what the banner offered. Art. 4(11) defines consent as a freely given
    # indication of the data subject's wishes, and a choice with one button is
    # the case that definition exists to exclude; art. 5(3) is what makes
    # consent necessary here in the first place.
    "no_refusal": ((GDPR, "4(11)"), (EPRIVACY, "5(3)")),
}

FINDING_TITLES = {
    "violation": "VIOLATION — trackers without valid consent",
    "unfair_practice": "Unfair commercial practice",
    "post_reject": "Trackers loaded after rejection",
    "invalid_consent": "Consent not valid (personal data in the digital contract)",
    "no_refusal": "Accept was applied and no refusal control was found",
}

# Articles downloaded and cached even when not cited, by act
ALSO_FETCH: dict = {}

UNVERIFIED_NOTE = (
    "UNVERIFIED: no cookie banner was found, so no provision is cited for the "
    "post-reject session"
)

# The same outcome when a session did see something that looked like a banner.
# Measured on 2026-10-09 on it.wikipedia.org, www.subito.it and www.muenchen.de:
# every session printed "Banner found" and this section then said "no cookie
# banner was found", two sentences from one result and one of them false. The
# heuristic cannot tell a Didomi notice from a site notice with "banner" in its
# class name, and the note must not pretend it can: what it knows is that no
# refusal control was recognised.
UNRECOGNISED_BANNER_NOTE = (
    "UNVERIFIED: something that looks like a cookie banner was found, but no "
    "refusal control was recognised on it, so no provision is cited for the "
    "post-reject session"
)

# The other way a session can go unverified, and the one that is not about this
# tool's reach: the banner was there and it was used.
NOT_SERVED_NOTE = (
    "NOT MEASURED: the site answered with an error status, so no provision is "
    "cited — there is nothing here to apply one to"
)

# The same reason in its other shape: a challenge served with 200, which has no
# banner because it is not the site.
CHALLENGED_NOTE = (
    "NOT MEASURED: a bot-management challenge answered instead of the site, so "
    "no provision is cited — there is nothing here to apply one to"
)

NO_REFUSAL_NOTE = (
    "UNVERIFIED: the banner was found and accepted, and no refusal control was "
    "found on it, so no provision is cited for the post-reject session — the "
    "banner is cited instead"
)


def _rejected(result) -> bool:
    return bool(result.post_reject.consent_clicked)


def refusal_not_offered(result) -> bool:
    """Acceptance was exercised, refusal could not be.

    Both halves are required. Without the accept half this is the audit failing
    to locate the banner at all, which is a limitation of the audit and says
    nothing about the site — and the two must not collapse into one outcome,
    because only one of them is evidence.

    What this cannot establish is that no refusal control exists: it reports
    that none was found, which is a different sentence and the only one the
    evidence supports.
    """
    return bool(
        result.post_accept.banner_found
        and result.post_accept.consent_clicked
        and not result.post_reject.consent_clicked
    )


def _not_the_site(result) -> str | None:
    """The note that stands for the whole audit when the site was never seen."""
    from cookieradar.scanner import bot_challenge, page_not_served

    if page_not_served(result):
        return NOT_SERVED_NOTE
    if bot_challenge(result).seen:
        return CHALLENGED_NOTE
    return None


def findings_of(result) -> dict[str, list[str]]:
    """
    Findings in a CookieRadar ScanResult, with the tracker domains.

    A VIOLATION is a tracker loaded after the user rejected cookies: the same
    evidence is a violation of the consent rules (GDPR, ePrivacy), an unfair
    commercial practice (Consumer Code) and invalid consent in a digital
    content contract (directive 2019/770).
    """
    from cookieradar.scanner import find_violations

    if _not_the_site(result):
        # A reject button on an error page, or on a challenge, is not the
        # site's: the report says NOT MEASURED and must not cite a violation.
        return {}
    if not _rejected(result):
        if refusal_not_offered(result):
            accepted = len({t.domain for t in result.post_accept.trackers})
            return {
                "no_refusal": [
                    "accept was applied and no refusal control was found on the banner",
                    f"{accepted} trackers loaded after accepting",
                ]
            }
        return {}
    violations = find_violations(result)
    if not violations.all:
        return {}
    domains = sorted(violations.all)
    persistent = [f"{d} (already present before consent)" for d in sorted(violations.persistent)]
    new = [f"{d} (new after rejection)" for d in sorted(violations.new)]
    summary = [f"{len(domains)} trackers active despite consent being rejected"]
    return {
        "violation": domains,
        "unfair_practice": summary,
        "post_reject": persistent + new,
        "invalid_consent": summary,
    }


def notes_of(result) -> list[str]:
    not_the_site = _not_the_site(result)
    if not_the_site:
        # Before anything else: "no banner was found" is a statement about a
        # site, and on an error page or a challenge there is no site to make
        # it about.
        return [not_the_site]
    if _rejected(result):
        return []
    if refusal_not_offered(result):
        return [NO_REFUSAL_NOTE]
    sessions = (result.pre_consent, result.post_accept, result.post_reject)
    if any(s.banner_found for s in sessions):
        return [UNRECOGNISED_BANNER_NOTE]
    return [UNVERIFIED_NOTE]


# ─── Citations ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Citation:
    finding: str
    law: str                      # act as cited: "GDPR"
    article: str                  # "32(1)(a)"
    sha256: str | None         # None when the text could not be obtained
    version_date: str | None   # YYYY-MM-DD the wording was downloaded


@dataclass(frozen=True)
class ActStatus:
    act: Act
    # "verified": downloaded now from the act's source (EUR-Lex or Normattiva);
    # "cache": source unreachable, cached copy; "unavailable": no text at all
    source: str
    error: str | None = None


@dataclass
class LawCheckResult:
    citations: list[Citation]
    acts: list[ActStatus] = field(default_factory=list)
    # What triggered each finding, e.g. {"critical": ["CVE-2026-1234"]}
    evidence: dict[str, list[str]] = field(default_factory=dict)
    # "GDPR art. 32" → SHA-256 of its previous text, for cited provisions
    # whose text changed since the last audit
    changed: dict[str, str] = field(default_factory=dict)
    # Remarks without a citation, e.g. why no verdict was possible
    notes: list[str] = field(default_factory=list)


def check(
    subject,
    *,
    cache: LawCache | None = None,
    now: datetime | None = None,
    **context,
) -> LawCheckResult:
    """
    Cite the provisions that apply to the findings about `subject`.

    `context` is passed on to findings_of and notes_of: what the audit found
    besides `subject` itself.
    """
    evidence = findings_of(subject, **context)
    notes = notes_of(subject, **context)
    cited = [
        (finding, act, ref)
        for finding in evidence
        for act, ref in FINDING_ARTICLES[finding]
    ]
    if not cited:
        return LawCheckResult(citations=[], notes=notes)

    cache = cache or LawCache()
    now = now or datetime.now(UTC)

    acts = list(dict.fromkeys(act for _, act, _ in cited))
    # Keyed by (celex, article) — the cache's key, not the fetcher's.
    fresh: dict[Key, Provision] = {}
    errors: dict[Act, str] = {}
    for act in acts:
        # The articles cited ("32(1)(a)" is part of article 32) and ALSO_FETCH
        articles = tuple(dict.fromkeys(
            [ref.split("(")[0] for _, a, ref in cited if a == act] + list(ALSO_FETCH.get(act, ()))
        ))
        try:
            by_article = law_fetcher.fetch_provisions(act, articles, now=now)
        except LawFetchError as e:
            errors[act] = str(e)
        else:
            fresh.update({p.key: p for p in by_article.values()})

    changed: dict[Key, str] = {}
    try:
        if fresh:
            provisions, changed = cache.update(fresh, checked_at=law_fetcher.utc_stamp(now))
        else:
            provisions = cache.load()
    except OSError:
        provisions = {**cache.load(), **fresh}   # the text just downloaded can still be cited

    statuses = []
    for act in acts:
        if act not in errors:
            statuses.append(ActStatus(act, "verified"))
        else:
            cached = any((act.celex, ref) in provisions for _, a, ref in cited if a == act)
            statuses.append(ActStatus(act, "cache" if cached else "unavailable", errors[act]))

    citations = []
    for finding, act, ref in cited:
        provision = provisions.get((act.celex, ref))
        citations.append(Citation(
            finding=finding,
            law=act.name,
            article=ref,
            sha256=provision.sha256 if provision else None,
            version_date=provision.fetched_at[:10] if provision else None,
        ))

    names = {act.celex: act.name for act in acts}
    cited_keys = {(act.celex, ref) for _, act, ref in cited}
    return LawCheckResult(
        citations=citations,
        acts=statuses,
        evidence=evidence,
        changed={
            f"{names[celex]} art. {article}": sha
            for (celex, article), sha in changed.items()
            if (celex, article) in cited_keys
        },
        notes=notes,
    )


def format_citation(citation: Citation) -> str:
    return (
        f"Provision applied: {citation.law} art. {citation.article}\n"
        f"SHA256: {citation.sha256 or 'not available'}\n"
        f"Version of: {citation.version_date or 'not available'}"
    )
