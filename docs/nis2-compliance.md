# CookieRadar: risposte alle sette domande NIS2 sul software

Revisione 1 · 2026-10-11 · vale per il ramo `main` e per le release successive alla 2026.44

Questo documento risponde alle domande che un cliente soggetto alla direttiva NIS2
(UE 2022/2555, recepita in Italia con il d.lgs. 138/2024) può porre a un fornitore di
software. Ogni affermazione verificabile nel repository è controllata dai test in
`tests/test_nis2_evidence.py`: se il codice cambia e il documento no, la CI fallisce.
Quello che il repository non può dimostrare è indicato con la data in cui è stato
verificato o misurato, oppure dichiarato assente.

La NIS2 non prevede una certificazione di prodotto: gli obblighi della direttiva
ricadono sui soggetti, non sugli strumenti che usano. Quello che segue sono le prove
che il fornitore è in grado di dare, non un attestato di conformità.

## 1. Di cosa è fatto il software

- Dipendenze dichiarate in `pyproject.toml`, con la sola versione minima. Una
  risoluzione completa è in `uv.lock`, e la CI (workflow Quality) fallisce se non
  corrisponde più a `pyproject.toml`. `pip install cookieradar` e la build
  dell'immagine Docker però non lo usano: risolvono le dipendenze al momento
  dell'installazione o della build. Quello che un'immagine contiene davvero è nella
  sua SBOM (punto 6).
- Ogni release su GitHub porta in allegato due SBOM in formato CycloneDX 1.5:
  quella dell'immagine Docker, pacchetti di sistema inclusi, e quella dell'ambiente
  Python del pacchetto installato da sorgente (vedi la tabella al punto 6).
- La SBOM dell'immagine non elenca Chromium, e la scansione Trivy dell'immagine non
  lo controlla: Playwright lo scarica come archivio, senza i metadati di pacchetto
  che Syft e Trivy leggono (verificato il 2026-10-11 sui file allegati alla
  2026.44). Lo identifica la versione del pacchetto `playwright` elencata nella
  SBOM, perché ogni versione di Playwright scarica un build di Chromium fisso: la
  1.63.0, quella dell'immagine 2026.44, il build 1243, Chromium 153.0.8010.12.
- Provenienza: le wheel e i sorgenti su PyPI hanno un'attestazione PEP 740 firmata
  con Sigstore dal workflow di pubblicazione (`publish.yml`, verificato sulla 2026.44);
  le immagini su Docker Hub (`maksimtech/cookieradar`) hanno un'attestazione di
  provenienza SLSA generata da BuildKit al momento del push (presente in
  `maksimtech/cookieradar:v2026.44`), che non è firmata.
- Licenze: il workflow License Check fallisce se una dipendenza Python è sotto GPL,
  AGPL o LGPL. Il controllo non riguarda i pacchetti Debian né il Chromium contenuti
  nell'immagine. CookieRadar non distribuisce i dati di Ghostery (`ghostery/trackerdb`,
  CC-BY-NC-SA-4.0): l'opzione `--trackers` legge una copia che l'operatore si procura
  da sé.

## 2. Chi può vedere cosa, dentro l'applicazione

CookieRadar è uno strumento a riga di comando che gira sul sistema di chi lo esegue.
Non ha account, sessioni, ruoli né un'interfaccia multiutente, quindi non implementa
controlli di accesso: l'accesso al sistema su cui gira è responsabilità
dell'operatore. Una matrice ruoli-permessi non esiste perché non ci sono ruoli.

L'immagine Docker gira come utente non privilegiato `cookieradar`, UID 1000.

CookieRadar apre in Chromium pagine scelte da terzi. Playwright avvia Chromium con
`--no-sandbox`, la sua impostazione predefinita, che CookieRadar non cambia
(verificato il 2026-10-11 sulla riga di comando di chrome-headless-shell): la sandbox
di Chromium non è attiva, e una pagina che sfruttasse una vulnerabilità del browser
avrebbe i permessi dell'utente che esegue CookieRadar, nell'immagine Docker l'utente
`cookieradar`.

## 3. Se succede qualcosa, si può ricostruire chi ha fatto cosa

CookieRadar non tiene un registro proprio: scrive i risultati sul terminale e, se
richiesto, in un file di report; la conservazione dei log è a carico di chi lo
esegue. Non contiene telemetria e non invia nulla al fornitore.

Contatta però servizi esterni, e il cliente deve saperlo per valutarne l'uso.

**Il sito analizzato e le terze parti che carica.** `cookieradar audit` e
`cookieradar batch` aprono l'indirizzo indicato in Chromium tre volte, ogni volta in
un contesto del browser nuovo, senza cookie in comune con gli altri: prima del
consenso, dopo aver cliccato "Accetta", dopo aver cliccato "Rifiuta" e ricaricato la
pagina. Chromium carica tutto quello che la pagina richiede, come per un visitatore:
script, immagini e frame del sito e di ogni terza parte che la pagina include,
tracker compresi. Questi host non hanno un nome fisso: li sceglie il sito
analizzato, e possono essere decine. Ognuno riceve quello che riceve da qualunque
visita con un browser, comprese le risoluzioni DNS del suo nome: l'indirizzo IP da
cui esce la rete di chi esegue l'audit, lo User-Agent di Chromium (in modalità
headless contiene `HeadlessChrome`, misurato il 2026-10-11 con Playwright 1.63.0) e
quello che gli script della pagina decidono di inviare. Nella seconda sessione, se
trova il pulsante, CookieRadar dà davvero il consenso, e i tracker del sito lo
ricevono come da qualunque visitatore.

**Chromium per conto proprio.** Playwright avvia Chromium anche con
`--disable-background-networking` e `--disable-component-update` (letti sulla stessa
riga di comando, il 2026-10-11). Lo stesso giorno un
audit eseguito con `cookieradar audit` non modificato (Playwright 1.63.0,
chrome-headless-shell, su Windows) di una pagina servita su 127.0.0.1 senza risorse
esterne ha aperto connessioni solo verso 127.0.0.1; con una pagina che carica
un'immagine da example.com la stessa misura ha visto la connessione a example.com. Le
connessioni sono state rilevate leggendo all'incirca ogni 65 ms i socket di tutti i
processi dell'audit: una connessione più breve può sfuggire, e la misura non copre la
modalità `--no-headless` né l'immagine Docker.

**Le fonti normative.** Quando il report cita disposizioni di legge, cioè con una
VIOLATION o quando sul banner è stato applicato "Accetta" e non è stato trovato un
comando per rifiutare, `cookieradar audit` scarica il
testo degli atti citati per calcolarne lo SHA-256. `batch` non contatta le fonti
normative. Questi sono gli host fissi che CookieRadar contatta:

<!-- hosts:start -->
| Host | Quando | Cosa riceve |
| --- | --- | --- |
| `publications.europa.eu` | `cookieradar audit`, quando il report cita un atto dell'UE | il numero CELEX dell'atto |
| `eur-lex.europa.eu` | come sopra, solo se publications.europa.eu non restituisce l'atto | il numero CELEX dell'atto |
| `www.normattiva.it` | `cookieradar audit`, quando il report cita il Codice del Consumo | l'URN del Codice del Consumo e il numero dell'articolo |
<!-- hosts:end -->

Queste richieste non contengono l'indirizzo analizzato né i risultati dell'audit, e
si presentano con uno User-Agent che indica la versione di CookieRadar e questo
repository. publications.europa.eu risponde alla richiesta HTTPS con un rinvio a un
indirizzo `http://`, e CookieRadar lo segue: il testo dell'atto arriva quindi in
chiaro, senza TLS (misurato il 2026-10-11). Il riferimento richiesto è pubblico, ma
l'integrità del testo scaricato, e quindi dello SHA-256 citato nel report, non è
protetta dal trasporto.

**Su disco** CookieRadar scrive:

- la cache dei testi di legge citati, in `~/.cookieradar/law_cache.json` (oppure
  nella cartella indicata da `COOKIERADAR_HOME`), solo quando un audit cita
  disposizioni. Contiene i testi delle disposizioni, il loro SHA-256 e le date di
  download e di controllo, non dati sui siti analizzati;
- i report, solo se richiesti con `-o`/`--output`. Il report salvato è lo stesso
  testo stampato sul terminale: indirizzo analizzato, data e versione, domini e URL
  (troncati a 60 caratteri) delle richieste ai tracker, numero degli host esterni
  contattati e nomi di quelli non riconosciuti (fino a otto), nomi, domini e
  scadenze dei cookie, non i loro valori, verdetto e disposizioni citate.

Chromium lavora in un profilo temporaneo che Playwright crea all'avvio e cancella alla
chiusura: dopo i tre audit misurati il 2026-10-11 nella cartella temporanea non è
rimasto nulla. CookieRadar non salva screenshot, registrazioni del traffico né lo
stato del browser. L'opzione `--trackers` legge da disco una copia di
`ghostery/trackerdb` e non scarica nulla.

## 4. Come arrivano gli aggiornamenti, e in quanto tempo

La politica completa è in `SECURITY.md`: fonti di monitoraggio, tempi di risposta,
notifica ai clienti, procedura di rollback. In sintesi:

- le correzioni escono con la release successiva, che può arrivare fino a un mese dopo
  la precedente; per una vulnerabilità con CVSS pari o superiore a 9.0 il cliente che
  ha indicato un contatto di sicurezza viene avvisato entro 48 ore dalla presa in
  carico, anche se la correzione non è ancora pronta;
- le vulnerabilità accettate, con motivazione e data di revisione, sono in
  `SECURITY-EXCEPTIONS.toml`; il 2026-10-11, 20 delle 31 voci riguardavano librerie
  di sistema che Chromium porta nell'immagine;
- ogni versione ha un tag Docker dedicato (es. `maksimtech/cookieradar:v2026.44`) e un
  digest SHA256 immutabile; il rollback consiste nel tornare a quel tag o, meglio, a
  quel digest;
- l'immagine viene costruita quando si pubblica una release, con gli aggiornamenti di
  Debian disponibili in quel momento, e non viene ricostruita tra una release e
  l'altra: le patch di sicurezza di Debian arrivano con la release successiva. Il
  manutentore può ricostruire a mano una versione già pubblicata (`docker.yml`
  avviato manualmente), e in quel caso il tag di quella versione e `latest` vengono
  ripubblicati: per questo il riferimento stabile è il digest;
- Dependabot controlla ogni settimana gli aggiornamenti delle dipendenze Python e
  delle GitHub Actions (`.github/dependabot.yml`) e apre le relative pull request.

Contatto per le segnalazioni: security@maksimtech.com.

## 5. Il codice viene controllato prima di andare in produzione

Analisi automatiche, ciascuna con il proprio workflow in `.github/workflows`:

<!-- scanners:start -->
| Strumento | Cosa controlla | Quando |
| --- | --- | --- |
| `CodeQL` | analisi statica del codice | ogni pull request, ogni push su `main`, ogni settimana |
| `Bandit` | analisi statica di sicurezza Python | ogni pull request, ogni push su `main`, ogni settimana |
| `Trivy` | vulnerabilità note nei file del repository | ogni pull request, ogni push su `main`, ogni settimana |
| `Snyk` | il codice, le dipendenze Python e l'immagine costruita dal sorgente; su una pull request fallisce solo se aggiunge vulnerabilità alte o critiche nelle dipendenze | ogni pull request, ogni push su `main` |
| `SonarCloud` | qualità, duplicazioni e copertura | ogni pull request, ogni push su `main` |
| `Docker Scout` | vulnerabilità note nell'immagine `latest` pubblicata su Docker Hub | ogni push su `main`, ogni settimana |
| `Security Posture` | raccoglie gli avvisi pubblicati dagli altri e fallisce se un avviso alto o critico non ha un'eccezione motivata | ogni pull request, ogni push su `main`, ogni settimana |
| `mutmut` | mutation testing: verifica che i test si accorgano delle modifiche al codice | ogni settimana |
| `CodSpeed` | le prestazioni dei benchmark in `tests/benchmarks`; non è uno strumento di sicurezza e non blocca il merge | ogni push su `main`, ogni pull request che modifica `cookieradar/`, `tests/` o `pyproject.toml`, e a mano |
<!-- scanners:end -->

A questi si aggiungono i test automatici (pytest su Python 3.11, 3.12, 3.13 e 3.14,
con copertura inviata a Codecov, e la costruzione dell'immagine Docker con una prova
di avvio di Chromium come utente non privilegiato), ruff e mypy nel workflow Quality.
Sul repository è attivo il secret scanning di GitHub con push protection; gli avvisi
di sicurezza di Dependabot non sono attivi (entrambi letti dalle impostazioni il
2026-10-11).

Le regole del ramo `main`, lette dalle impostazioni del repository il 2026-10-11:
le modifiche passano da una pull request, che non richiede approvazioni; i controlli
obbligatori per il merge sono Tests e Quality; la cronologia deve restare lineare; il
ramo non può essere cancellato né riscritto con un force push. L'account del
manutentore è configurato come eccezione a queste regole e può scavalcarle. Nessuno
degli strumenti della tabella è tra i controlli obbligatori.

CookieRadar ha un manutentore unico. Non c'è nessuna revisione obbligatoria da parte
di una seconda persona: le pull request vengono unite dal manutentore dopo che la CI è
verde. È un limite noto di un progetto con una sola persona.

## 6. Qualcuno dall'esterno ha provato a entrare

Non è stato eseguito un penetration test. Esiste una scansione automatica continua
delle vulnerabilità note, descritta al punto 5, ma non è un penetration test: non ha un
ambito concordato, non è condotta da un tester indipendente e non produce un rapporto
con vulnerabilità trovate e correzioni datate.

Ogni release porta in allegato i risultati datati di quella scansione, insieme alle
SBOM:

<!-- assets:start -->
| File allegato alla release | Contenuto |
| --- | --- |
| `sbom-image-<versione>.cdx.json` | SBOM CycloneDX 1.5 dell'immagine Docker della versione |
| `sbom-source-<versione>.cdx.json` | SBOM CycloneDX 1.5 dell'ambiente Python del pacchetto |
| `trivy-image-<versione>-<data>.json` | vulnerabilità note nell'immagine, scansione Trivy |
| `trivy-fs-<versione>-<data>.json` | vulnerabilità note nei file del repository al tag, scansione Trivy |
| `EVIDENCE-<versione>.md` | cosa sono questi file, quando e da quale commit e digest dell'immagine sono stati prodotti |
<!-- assets:end -->

Come detto al punto 1, né la SBOM né la scansione dell'immagine coprono Chromium.

Un rapporto Trivy dei file del repository senza risultati vuol dire che Trivy non ha
trovato al tag nessun file che sapesse analizzare, come un file di dipendenze
bloccate: quello allegato alla 2026.44 il 2026-10-11 è vuoto, e un rapporto vuoto non
indica l'assenza di vulnerabilità. Quando succede, la nota `EVIDENCE` lo dice.

## 7. E se il fornitore sparisce

Il codice sorgente è pubblico su <https://github.com/maksimtech/cookieradar> con
licenza MIT, e resta accessibile indipendentemente dalle sorti commerciali del
fornitore. Le versioni pubblicate restano su PyPI e su Docker Hub.

CookieRadar non conserva dati del cliente presso il fornitore: report e cache sono
prodotti sull'infrastruttura di chi lo esegue, quindi non c'è nulla da esportare.

Una clausola contrattuale su questo punto va concordata caso per caso e fatta rivedere
da un legale.
