"""
CookieRadar — EU law provisions for audit findings.

Maps what an audit found to the provisions it concerns, and cites each one
with the SHA-256 of the exact text applied and the date of that wording. The
text is downloaded from EUR-Lex on every audit and compared with the local
cache; without network the cached copy is cited.

Adapted from APKRadar's law_checker: only the mapping section is specific to
CookieRadar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cookieradar import law_fetcher
from cookieradar.law_cache import LawCache
from cookieradar.law_fetcher import EPRIVACY, GDPR, Act, LawFetchError

# ─── Mapping: CookieRadar findings → provisions ───────────────────────────────

# Finding → cited provisions, in report order
FINDING_ARTICLES = {
    "violation": ((GDPR, "5(1)(a)"), (EPRIVACY, "5(3)")),
    "post_reject": ((GDPR, "7"),),
}

FINDING_TITLES = {
    "violation": "VIOLATION — tracker senza consenso valido",
    "post_reject": "Tracker caricati dopo il rifiuto",
}

UNVERIFIED_NOTE = (
    "UNVERIFIED: banner dei cookie o pulsante di rifiuto non trovato, "
    "quindi nessuna norma è citata per la sessione post-rifiuto"
)


def _rejected(result) -> bool:
    return bool(result.post_reject.consent_clicked)


def findings_of(result) -> dict[str, list[str]]:
    """
    Findings in a CookieRadar ScanResult, with the tracker domains.

    A VIOLATION is a tracker loaded after the user rejected cookies, so both
    findings come together; they cite different provisions.
    """
    from cookieradar.scanner import find_violations

    if not _rejected(result):
        return {}
    violations = find_violations(result)
    if not violations.all:
        return {}
    domains = sorted(violations.all)
    persistent = [f"{d} (già presente prima del consenso)" for d in sorted(violations.persistent)]
    new = [f"{d} (nuovo dopo il rifiuto)" for d in sorted(violations.new)]
    return {"violation": domains, "post_reject": persistent + new}


def notes_of(result) -> list[str]:
    return [] if _rejected(result) else [UNVERIFIED_NOTE]


# ─── Citations ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Citation:
    finding: str
    law: str                      # act as cited: "GDPR"
    article: str                  # "32(1)(a)"
    sha256: Optional[str]         # None when the text could not be obtained
    version_date: Optional[str]   # YYYY-MM-DD the wording was downloaded


@dataclass(frozen=True)
class ActStatus:
    act: Act
    # "eur-lex": verified now; "cache": EUR-Lex unreachable, cached copy;
    # "unavailable": no text at all
    source: str
    error: Optional[str] = None


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


def check(subject, *, cache: Optional[LawCache] = None, now: Optional[datetime] = None) -> LawCheckResult:
    """Cite the provisions that apply to the findings about `subject`."""
    evidence = findings_of(subject)
    notes = notes_of(subject)
    cited = [
        (finding, act, ref)
        for finding in evidence
        for act, ref in FINDING_ARTICLES[finding]
    ]
    if not cited:
        return LawCheckResult(citations=[], notes=notes)

    cache = cache or LawCache()
    now = now or datetime.now(timezone.utc)

    acts = list(dict.fromkeys(act for _, act, _ in cited))
    fresh = {}
    errors = {}
    for act in acts:
        # Only the articles cited: "32(1)(a)" is part of article 32
        articles = tuple(dict.fromkeys(ref.split("(")[0] for _, a, ref in cited if a == act))
        try:
            provisions = law_fetcher.fetch_provisions(act, articles, now=now)
        except LawFetchError as e:
            errors[act] = str(e)
        else:
            fresh.update({p.key: p for p in provisions.values()})

    changed = {}
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
            statuses.append(ActStatus(act, "eur-lex"))
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
        f"Norma applicata: {citation.law} art. {citation.article}\n"
        f"SHA256: {citation.sha256 or 'non disponibile'}\n"
        f"Versione del: {citation.version_date or 'non disponibile'}"
    )
