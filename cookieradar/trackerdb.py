"""Legge una copia di `ghostery/trackerdb` che l'utente si e' procurato.

**Questo modulo e' un lettore, non dei dati.** Il codice e' nostro e viaggia
sotto MIT come il resto di CookieRadar; `ghostery/trackerdb` e' CC-BY-NC-SA-4.0,
che vieta l'uso commerciale e obbliga ogni derivato a portarsi dietro lo stesso
divieto. Impacchettarlo dentro un pacchetto MIT metterebbe fuori regola
chiunque usi CookieRadar al lavoro, senza che se ne accorga - l'etichetta
direbbe una cosa e il contenuto un'altra.

Quindi CookieRadar non distribuisce nessun dato di Ghostery. Chi vuole
quell'arricchimento clona il repository e indica il percorso; la clausola non
commerciale vincola il suo uso, ed e' una sua decisione informata.

Il formato, letto dai file veri il 27/09/2026:

    name: Google Analytics          coppie chiave: valore
    category: site_analytics
    organization: google

    --- domains                     blocchi delimitati da una riga --- nome,
    google-analytics.com            chiusi da una riga identica
    --- domains

Le forme che ricorrono davvero, contate su 3535 pattern e 2608 organizzazioni:
3535 hanno name/category/website_url, 3098 una organization (437 no), 3458 un
blocco domains (77 no), e 2567 valori sono dichiarati e lasciati in bianco.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Il blocco `filters` non viene letto. E' sintassi da ad blocker
# (`||mmtro.com^$3p`), cioe' un secondo linguaggio dentro lo stesso file, e
# CookieRadar deve riconoscere chi e' stato contattato, non bloccarlo. I 77
# pattern che identificano solo per filtro restano caricati e non combaciano
# mai: e' un limite della nostra copertura, ed e' contato invece che nascosto.
_BLOCK_PREFIX = "--- "


def parse_eno(text: str) -> dict[str, str | list[str]]:
    """Il documento come dizionario: valori per le chiavi, liste per i blocchi.

    Una chiave dichiarata e lasciata in bianco NON finisce nel risultato: nei
    file veri succede 2567 volte, e restituire "" renderebbe "non compilato"
    indistinguibile da "compilato con niente". Un blocco vuoto invece resta,
    come lista vuota: il blocco c'e' e dice che non c'e' nulla dentro.
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
                block, lines = name, []
            continue
        if block is not None:
            if line.strip():
                lines.append(line.strip())
            continue
        if ":" in line:
            # Solo sul primo due punti: gli URL ne contengono uno.
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if key and value:
                doc[key] = value

    # Un blocco aperto e mai chiuso: si tiene quello che si e' letto, perche'
    # scartarlo perderebbe dati veri per un errore di battitura altrui.
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
    """Ricerca per host, con la stessa semantica di `scanner.tracker_domain`."""

    def __init__(self, trackers: list[Tracker], organizations: dict[str, Organization]):
        self._organizations = organizations
        self._by_domain: dict[str, Tracker] = {}
        self._without_domains = 0
        for tracker in trackers:
            if not tracker.domains:
                self._without_domains += 1
            for domain in tracker.domains:
                # Il primo che rivendica un dominio se lo tiene: due pattern
                # che rivendicano lo stesso sono un dato di Ghostery, non una
                # decisione nostra, e sceglierne uno a caso ogni volta
                # renderebbe il report non riproducibile.
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
        """Pattern che identificano solo per regola di filtro: non combaciano mai."""
        return self._without_domains

    def lookup(self, host: str) -> Tracker | None:
        """Il tracker che rivendica `host`, o None.

        Combacia il dominio esatto e i suoi sottodomini - `region1.google-
        analytics.com` e' Google Analytics - e non un suffisso qualunque:
        `notgoogle-analytics.com` e' un dominio diverso.
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
        """Carica da una cartella `db/`, o dalla radice del clone che la contiene."""
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
                # `category` c'e' in tutti i 3535 file veri; se un giorno
                # mancasse, "unknown" dice che non lo sappiamo invece di
                # attribuire una finalita' a caso.
                category=_text(doc, "category") or "unknown",
                domains=tuple(_list(doc, "domains")),
                website_url=_text(doc, "website_url"),
                organization=organizations.get(org_id) if org_id else None,
            ))
        return cls(trackers, organizations)
