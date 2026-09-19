# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses calendar versioning (YYYY.MM.N).

## [Unreleased]

## [2026.09.9] - 2026-09-19
### Added
- `audit` ends with a "Norme applicate" section, also in the `--output`
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

[Unreleased]: https://github.com/maksimtech/cookieradar/compare/v2026.09.8...HEAD
[2026.09.8]: https://github.com/maksimtech/cookieradar/compare/v2026.09.7...v2026.09.8
[2026.09.7]: https://github.com/maksimtech/cookieradar/compare/v2026.09.6...v2026.09.7
[2026.09.6]: https://github.com/maksimtech/cookieradar/compare/v2026.09.5...v2026.09.6
[2026.09.5]: https://github.com/maksimtech/cookieradar/compare/v2026.09.4...v2026.09.5
[2026.09.4]: https://github.com/maksimtech/cookieradar/compare/v2026.09.3...v2026.09.4
[2026.09.3]: https://github.com/maksimtech/cookieradar/compare/v2026.09.2...v2026.09.3
[2026.09.2]: https://github.com/maksimtech/cookieradar/compare/v2026.09.1...v2026.09.2
[2026.09.1]: https://github.com/maksimtech/cookieradar/releases/tag/v2026.09.1
