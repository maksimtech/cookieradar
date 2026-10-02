# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses **CalVer, Apple style**: `YYYY.count[.fix]`, not SemVer.
`YYYY` is the generation, shared by the five Radar; the count belongs to each of
them and moves when its code moves; the third segment is for something urgent on
what has already shipped. The line above said `YYYY.MM.N` until 2026-09-29, which
no version in this file has ever matched — 40 is not a month, and
`tests/test_version_contract.py` has been enforcing the real form all along.

## [Unreleased]


### Added

- **The gate reads FIRST's forecast on the CVEs it already holds.** EPSS is indexed
  by CVE, and `SECURITY-EXCEPTIONS.toml` is the one surface in this repository that
  holds CVE ids: Docker Scout names its alerts by CVE, so every accepted finding
  already has an id, a written reason and a review date. The forecast is what those
  records lacked — "no fix in any suite" accepted until December is comfortable at
  an EPSS of 0.1% and is something else at 40%.

  The forecast changes no verdict. The gate fails on a blocking alert with no entry
  and on an entry past its date, and on nothing else: `exit_code` takes the
  forecasts and ignores them, so the signature says they were available and did not
  decide anything. Only ids that *are* CVE ids are looked up —
  `SNYK-DEBIAN13-GCC14-20386241` is CVE-2026-95619 and says so in its description,
  and reading prose is guessing. A CVE FIRST does not score prints "not scored by
  FIRST" rather than 0.0%, which is a real reading at the floor of the scale; FIRST
  unreachable prints nothing and the report is the one this script produced before.

  The accepted findings are listed on a **passing** run, worst first, because that
  is where somebody decides whether to renew a review date and nothing else prompts
  it.

  Ported from patchradar with its nineteen tests; `tools/security_exceptions.py` is
  shared by copy across the five, and all four copies were byte-identical before
  this.

### Fixed

- **`release.sh` would have refused the version this repository is on.** Its check
  read `YYYY.MM.N` and the scheme has been `YYYY.count[.fix]` since 2026-09-29, so
  the documented release path answered
  `Invalid version: 2026.41 (expected YYYY.MM.N)`. How that went unnoticed is that
  v2026.41 was tagged by hand on 2026-09-30 and the script was never run —
  patchradar's `scripts/bump_version.py` had the same defect in the same week, and
  neither was found by a test, because both tests asserted the old scheme too.

  The check now accepts a count with an optional fix, refuses a leading zero —
  2026.09.5 sorts *below* 2026.10 under PEP 440, and publishing it would be a
  downgrade PyPI never lets anybody take back — and refuses a middle segment of
  twelve or less on its own terms, saying that it reads as a month rather than
  calling the version malformed.

  `tests/test_release_script.py` gained the test that would have caught it: it
  reads the version out of `cookieradar/__init__.py` instead of a literal, so the
  next change of scheme fails there rather than at a release. Measured by mutation:
  the old check fails twelve of the nineteen cases.

### Changed

- **The Italian comments are in English**, in `Dockerfile`, `release.sh`,
  `scanner.py`, `cli.py` and two test files, together with the one line of Italian
  the CLI still printed — the trackerdb size, "domini" and "organizzazioni" in the
  middle of an English report.

## [2026.41] - 2026-09-29

### Added

- **Every external host contacted, not only the recognised ones**, and a reader
  for Ghostery's trackerdb format without shipping Ghostery's data.

- **A bot-management challenge is no longer audited as if it were the site.**
  2026.40.1 closed the honest refusal — a status of 4xx or 5xx. The other shape
  answers **200**: Cloudflare's "Just a moment…", AWS WAF's 202, DataDome's
  interstitial. The browser loads it like any document and finds no trackers and
  no banner, which is also what a compliant site looks like, so the strongest
  claim this tool makes was again available without having seen the site.

  The page's own identity decides — its title or its text — or a status that
  means "not the page you asked for". The verdict is ERROR, as for a page never
  served, and the report says to try `--no-headless`: a challenge is sometimes
  served to a visible browser, and a refused address never is.

  Two things it deliberately does not do. **A bot-management cookie is not a
  challenge**: `__cf_bm` is set on a large share of ordinary sites that serve
  their own pages perfectly well, so cookies and vendor hosts only corroborate a
  page that has already identified itself — reading them as proof would refuse to
  audit compliant sites and look like caution while losing coverage. And **a bare
  429 or 503 is not called a challenge**: both are above 400, so the existing
  check already says "this is not the site", which is all that is known. A 503
  that also says "Just a moment" is a challenge, and the text is what says so.

### Fixed

- **The report now says which kind of refusal it met.** msi.com answers 403 and
  the report said only "this is an error page, not the site" — true, and it left
  the cause to the reader, who read it as headless Chromium being detected.
  Measured on 2026-09-29: `httpx` with no browser at all gets the identical 403,
  with and without a current Chrome User-Agent, and
  `--disable-blink-features=AutomationControlled` changes nothing. That is an edge
  refusing a network address, and no browser setting will alter it.

  The verdict now says so, and says an audit needs access from an allowed address
  — printed once beneath the verdict rather than inside a 60-column table cell,
  which cut the sentence off and repeated it three times.

- The report stops changing language halfway: the external-host section was
  written in Italian while the rest of the output is English.

## [2026.40.1] - 2026-09-26

### Fixed

- **A page that was never served is no longer reported as a measurement.**
  canon.it answers 403 Access Denied from the Akamai edge — 364 bytes,
  identical with and without a browser User-Agent. The headless browser loads
  that like any other document, finds no trackers, no banner and one cookie,
  and the report said "Trackers measured: 0 before consent": the strongest
  claim this tool can make, assembled out of never having seen the site.

  `page.goto` returns the response and the scanner was discarding it. The
  status is kept now, and a pre-consent document that came back 4xx or 5xx
  means the audit did not happen. The verdict is ERROR rather than UNVERIFIED —
  UNVERIFIED means the site was seen and the refusal could not be exercised,
  and a gate treating it as "inconclusive but fine" would wave through
  something nobody audited. All three session tables say so instead of showing
  a clean result, and no provision is cited, because "no cookie banner was
  found" is a statement about a site and there is no site here to make it
  about.

  A status of None is left alone: the navigation produced no response at all,
  which is a timeout the session already reports as its own error.

## [2026.40] - 2026-09-26
### Changed

- **Baseline: the five Radar restart from a common number.** They had drifted to
  .32, .12, .11, .6 and .3 of the same generation, which left the shared part of
  the version meaning nothing at all. The highest count in the suite was taken,
  rounded up for headroom, and every Radar starts again from 2026.40 — a jump
  for most of them, and a number that means the same thing in all five.

  From here the count belongs to each Radar again, and something urgent gets a
  third segment on top: 2026.40.1 before 2026.41, the way a suite has always
  done it. 2026 is a settling year; from 2027 the count moves when the code
  moves.


### Fixed

- **`SessionResult.cookies` is typed `list[Cookie]`, not `list[dict]`.**
  Playwright's `context.cookies()` returns `Cookie`, a TypedDict, and the
  annotation named a different type. No behaviour changes — the values were
  always whatever Playwright returned — but anyone importing `SessionResult` and
  running a type checker was being told the wrong shape.

  It was invisible locally because mypy ran from an environment without
  playwright installed, where `ignore_missing_imports` makes its types `Any`, and
  `Any` satisfies everything. CI, which installs the project, was right.

- **A session that never took place is no longer reported as a clean one.**
  A site whose reject button is not found never gets a third session, and its
  empty tracker table said "✅ No trackers detected" — under the heading
  "Post-reject", three lines below the warning that no rejection had happened.
  Zero trackers after a refusal that never occurred is not a result. The table
  now says which of the two it is, and the summary names the sessions that did
  run: "0 before consent, 6 after accepting", followed by the sentence that it
  is what the visit established and not a verdict on the site.

- **A banner that accepts and offers no way to refuse is now a finding.**
  Until now it produced the same ending as a banner nobody could find: one
  UNVERIFIED line and nothing else. They are not the same. In the first case
  the mechanism was located and half of it was exercised, and the half that
  could not be is the one that matters. It cites GDPR art. 4(11), which defines
  consent as a freely given indication of the data subject's wishes, and
  ePrivacy art. 5(3), which is what makes consent necessary at all.

  What it does not claim is that no refusal control exists. It reports that
  none was found, because this tool cannot tell a control that is absent from
  one its selectors did not recognise, and two tests exist to keep that
  sentence honest.

- The note that closes an unverified audit used to read "cookie banner or
  reject button not found" in both situations. It now says which one happened.

### Changed

- Coverage now leaves the job log. `--cov` had been measured on every run and
  reported only to the console, where nothing can compare it against the previous
  commit; it goes to Codecov now, once, from one matrix entry.

## [2026.09.11] - 2026-09-24

### Fixed
- **An unverifiable law now says what it costs.** The report warned that an act
  could not be fetched, and separately printed `SHA256: non disponibile` against
  each citation, with nothing joining the two — so a missing hash read as a
  defect in the hashing. It is not: with no verified text there is nothing to
  hash, and printing one anyway would assert a verification that never happened.
  The warning now names the consequence, and the three states are pinned by
  test: `verified` and `cache` both keep the hash, only `unavailable` loses it.
- **`COOKIERADAR_HOME` is no longer taken literally.** `~/cache` made a
  directory actually named `~`, which is what anyone writing that in a
  Dockerfile `ENV` got. A relative value resolved against the working directory,
  so the cache landed somewhere different depending on where the command ran
  from and quietly stopped being one cache. And `"   "` is truthy, so whitespace
  became a directory name.
- CLI error paths raise `typer.Exit` with `from None`. Each had already printed
  a readable message, so chaining would only have put a Python traceback in
  front of a CLI user.

### Changed
- ruff, mypy, hypothesis and mutmut are development dependencies, with a
  `Quality` workflow running ruff and mypy on every push and pull request, and a
  weekly, non-blocking mutation run.
- **The test suite runs on Windows again.** `tests/test_cli.py` called
  `os.geteuid()` at import time inside a `skipif` decorator; `geteuid` exists
  only on POSIX, so on Windows the `AttributeError` aborted collection and pytest
  stopped the whole session — forty-odd unrelated CLI cases were not running, and
  22 failures were hiding behind the abort. All 22 are now fixed or skipped with
  a stated reason.
- Nine new properties checked against generated input, including the family of
  URL schemes `normalize_url` must refuse rather than rewrite, and one that pins
  `normalize_text` as idempotent: its output is hashed, and that hash is what
  says "the law changed".
- A contract test refuses any code in this repository that lets the locale
  choose a text encoding.
- **Every string the tool writes itself is now in English**, which the
  CHANGELOGs already were. The report's section is `Provisions applied` rather
  than `Norme applicate`, and finding titles, scope notes, evidence lines and
  the release script's messages follow. What the tool *quotes* is unchanged: a
  provision's text is fetched from the official Italian version of each act and
  hashed, so translating it would change every SHA-256 in every cache and report
  "the law changed" for every citation on the next run, for nothing.

## [2026.09.10] - 2026-09-21
### Fixed
- Docker image: base moved from `python:3.12-slim-bookworm` to
  `python:3.12-slim-trixie`. Docker Scout reported three critical CVEs against
  Debian 12 packages in the published image: CVE-2026-75803 (openssl
  3.0.20-1~deb12u2), CVE-2026-12087 and CVE-2026-13221 (perl 5.36.0-7+deb12u3).
  Python stays on 3.12, so this changes the distribution only.

### Added
- `docker-build-check.yml`: builds the image from the repository source and runs
  `tests/docker/smoke.py` against it without pushing anything. The release
  workflow publishes to Docker Hub, including `:latest`, so until now there was
  no way to try a Dockerfile change out. Manual dispatch only.

## [2026.09.9] - 2026-09-19
### Added
- `audit` ends with a "Provisions applied" section, also in the `--output`
  report: each finding cites the legal provisions it concerns, with the
  SHA-256 of the exact text applied and the date of that wording. The text is
  downloaded on every audit and cached in `~/.cookieradar/law_cache.json`
  (`COOKIERADAR_HOME` moves the folder); a changed text is reported with its
  previous hash. Offline the cached copy is cited, or "SHA256: non
  disponibile". A failed law check never changes the verdict or exit code.
  - VIOLATION → GDPR art. 5(1)(a) and ePrivacy directive 2002/58/EC art. 5(3),
    consolidated text of 2009 (prior consent; the 2002 text only required a
    right to refuse).
  - VIOLATION → Italian Consumer Code, D.Lgs. 206/2005, art. 20 and 21, unfair
    commercial practice (Normattiva, text in force).
  - Trackers after rejection → GDPR art. 7.
  - VIOLATION → directive (EU) 2019/770 art. 3(8), invalid consent.
  - UNVERIFIED → a note only: without a reject button no provision is cited.
### Changed
- New dependency: `httpx`, to download the legal texts.

## [2026.09.8] - 2026-09-18
### Changed
- Exit codes now reflect the verdict:
  0=OK, 1=VIOLATION, 2=UNVERIFIED, 3=error
  (previously always 0 on success)
- Batch priority: VIOLATION > error > UNVERIFIED > OK
- CLI usage errors (unknown option, missing argument) → 3
  instead of Click's default 2

## [2026.09.7] - 2026-09-18
### Added
- --version command: cookieradar --version prints
  CookieRadar <version> read from __version__

## [2026.09.6] - 2026-09-18
### Fixed
- Rich FileProxy ImportError on shutdown: _status() context manager
  flushes sys.stdout, sys.stderr and console.file before spinner stops

### Changed
- CI: a single "Tests" summary check now gates branch protection over the
  whole Python matrix and the Docker build, so Dependabot PRs are no longer
  stuck waiting for a check that never runs

## [2026.09.5] - 2026-09-18
This release fixes several problems that made earlier results unreliable.
Before 2026.09.5, audits could report violations on compliant sites, click
the wrong consent button, and the published Docker image did not work.

### Fixed
- **False VIOLATION verdicts removed** (G1): trackers from the pre-consent
  session were not cleared before the post-reject reload, so compliant sites
  were flagged. The report now separates trackers that *persist from
  pre-consent* from trackers that are *new after rejection*
- **Wrong consent button clicked** (L2): `button:has-text('OK')` did a
  case-insensitive substring match, so "OK" matched buttons like
  "Cookie settings". Accept/reject labels are now matched as whole,
  anchored accessible names
- **Click on a hidden button** (L5): the first *visible* matching element is
  clicked, not the first one in the DOM
- **Failed click reported as a verdict** (L3): when the accept or reject
  button is not found or not clicked, the session is marked UNVERIFIED
  instead of producing a false OK or VIOLATION
- **Docker image not working** (G2, W1, W2): Chromium was installed as root
  and was not found by the `cookieradar` user; the image build could also
  start before the package was available on PyPI. Chromium is now installed
  as the runtime user, the Docker build waits for PyPI, the Dockerfile can
  build from the local source, and a smoke test runs before every push
- Docker image built with a `v`-prefixed version that does not exist on PyPI
- **CLI crash on URLs or data containing Rich markup** (G3), e.g. a URL with
  `[/b]`: all external data is now escaped
- **One timeout aborted the whole scan** (G4): timeouts are handled per
  session, the scan continues, and the browser is always closed.
  New `timeout_ms` parameter
- **Wrong tracker matches** (L1): domains are matched on hostname with a
  dot boundary, so `shopbing.com` no longer matches `bing.com`
- **Tracker subdomains counted separately** (L6): trackers are grouped by
  registered domain, e.g. `region1.google-analytics.com` and
  `www.google-analytics.com`
- `batch`: indented comments and blank lines in the URL file are skipped (L8);
  a missing file, a directory, a permission error, a non-UTF-8 file and a
  UTF-8 BOM are handled with a clear message; Ctrl-C exits cleanly without
  leaving orphan Chromium processes (W7)
- Request timestamps now record the real request time (M3)

### Added
- Cookies set in each session (name, domain, expiry) are shown in the
  report (L4)
- URLs without a scheme get `https://` automatically (L7)
- `--output` / `-o` saves the report as HTML (`.html`) or plain text (M1);
  in `batch`, one report per URL is written to the given directory
- Security scanning in CI: CodeQL, Trivy, Bandit, Docker Scout and a
  license compliance check
- PyPI releases carry PEP 740 attestations via Trusted Publishing (W3, W4)

### Changed
- The spinner names all three sessions: pre-consent, post-accept,
  post-reject (M6)
- Supported and tested on Python 3.11, 3.12, 3.13 and 3.14; integration
  tests with Chromium run in CI (M10)
- `release.sh` checks the branch, sync with `origin/main`, the version format
  and tag uniqueness, then creates an annotated tag and pushes atomically (M12)
- Test suite grew from 24 to 258 tests; coverage from 33% to 94%

### Removed
- `--lang` option, which had no translations behind it (M1)
- Empty modules `analyzer.py`, `legal.py` and `reporter.py` (M2)
- `httpx` dependency, which was unused (M5)
- GPG signing of PyPI releases: PyPI dropped PGP support in 2023 (W3)
- Unused `gnupg` package, `VOLUME` and `.cookieradar` directory from the
  Docker image (M11)

### Security
- Only `http://` and `https://` URLs are accepted; `file://`, `ftp://`,
  `javascript:` and other schemes are rejected (L7, W8)
- No secrets are written to `/tmp` during publishing anymore (W3)
- Trivy action pinned to a commit SHA after GHSA-69fq (W10)
- Workflow inputs are passed through environment variables instead of
  being interpolated in shell commands (W3)

## [2026.09.4] - 2026-09-10
### Changed
- Docker image build is triggered by version tags instead of GitHub Releases

## [2026.09.3] - 2026-09-10
### Changed
- `release.sh` bumps the version, commits, tags and pushes in one step

## [2026.09.2] - 2026-09-10
### Changed
- `release.sh` simplified: it only creates and pushes the version tag

## [2026.09.1] - 2026-09-10
### Added
- `cookieradar audit <url>`: cookie compliance audit (GDPR art. 5/6/7) with
  three Playwright browser sessions: pre-consent, post-accept and
  post-reject + reload
- `cookieradar batch <file>`: audit a list of URLs
- OneTrust two-step reject flow and a 3-second wait for the consent banner
- `python -m cookieradar` entry point
- Dockerfile
- Release automation: `release.sh`, and GitHub workflows for tests,
  releases, PyPI publishing and Docker build/push on version tags
- SonarCloud analysis and CodSpeed benchmarks

[Unreleased]: https://github.com/maksimtech/cookieradar/compare/v2026.09.10...HEAD
[2026.09.10]: https://github.com/maksimtech/cookieradar/compare/v2026.09.9...v2026.09.10
[2026.09.9]: https://github.com/maksimtech/cookieradar/compare/v2026.09.8...v2026.09.9
[2026.09.8]: https://github.com/maksimtech/cookieradar/compare/v2026.09.7...v2026.09.8
[2026.09.7]: https://github.com/maksimtech/cookieradar/compare/v2026.09.6...v2026.09.7
[2026.09.6]: https://github.com/maksimtech/cookieradar/compare/v2026.09.5...v2026.09.6
[2026.09.5]: https://github.com/maksimtech/cookieradar/compare/v2026.09.4...v2026.09.5
[2026.09.4]: https://github.com/maksimtech/cookieradar/compare/v2026.09.3...v2026.09.4
[2026.09.3]: https://github.com/maksimtech/cookieradar/compare/v2026.09.2...v2026.09.3
[2026.09.2]: https://github.com/maksimtech/cookieradar/compare/v2026.09.1...v2026.09.2
[2026.09.1]: https://github.com/maksimtech/cookieradar/releases/tag/v2026.09.1
