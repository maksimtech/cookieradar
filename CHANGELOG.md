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

### Security

- **CVE-2026-88647 in gnutls28 recorded in `SECURITY-EXCEPTIONS.toml`.** A hostname \
  verification bypass with no fix in any Debian suite, found by the scan of the 2026.44 \
  image; same chain as the five gnutls/krb5 entries of 2026-10-09 (libcups2t64, not \
  loaded by the headless shell), reviewed on 2026-11-30.
- **The gnutls28 and krb5 entries now say what was checked, not only what was read.** The \
  six gnutls CVEs of 2026-10-08 were reproduced with the public PoC certificates against \
  Debian's own packages (trixie 3.8.9-3+deb13u4, sid 3.8.13-1) and had no upstream issue \
  anywhere on 2026-10-10; CVE-2026-107778 in krb5 gained Debian bug 1150461, a no-dsa for \
  trixie and a fix on the upstream 1.22 branch the same day.
- **The six gnutls CVEs are now reported, not only recorded.** GnuTLS confidential issue \
  1965 and Debian bug 1150522 (src:gnutls28, found in 3.8.13-1 and 3.8.9-3+deb13u4), both \
  filed on 2026-10-10 with the reproduction transcripts; the exceptions name them.


## [2026.44] - 2026-10-10

### Security

- **`CVE-2026-95210`, `CVE-2026-95209`, `CVE-2026-95184`, `CVE-2026-67693` (gnutls28) and
  `CVE-2026-107778` (krb5) recorded in `SECURITY-EXCEPTIONS.toml`.** Docker Scout opened
  the five against 2026.43 on 2026-10-09, one of them critical; `patchradar debian` the
  same day says open in trixie, no fix in any suite, no Debian bug, and the tracker still
  asks whether the four gnutls reports are valid. Neither library is in the base image:
  `playwright install-deps chromium` brings them in for libcups2t64, which is the only
  package depending on them. Measured in the published image, Playwright's full `chrome`
  links cups and so loads both; the `chrome-headless-shell` that cookieradar runs — the
  only mode that works in an image with no display — maps none of gnutls, krb5 or cups.
  No TLS here goes through gnutls (httpx uses OpenSSL via `_ssl`, Chromium its BoringSSL)
  and nothing uses Kerberos. Reviewed with the other Chromium dependencies by 2026-11-30.

### Fixed

- **The report says when it was made and by what.** The README calls it "evidence of
  what the site did on a given day", and the file saved on 2026-10-09 for
  www.repubblica.it carried no day: the only dates in it were the "Version of:" lines
  under the legal citations, which exist only when something is cited, and nothing
  named the CookieRadar that produced it. Every report now opens with
  `Audited on 2026-10-09 12:37 UTC with CookieRadar 2026.43`, and the HTML file has a
  `<title>` with the site's host — Rich's export template has none, so ten reports
  open side by side were ten tabs called `report.html`.

- **The law section no longer says "no cookie banner was found" under a report that
  says "Banner found".** Measured on 2026-10-09 on it.wikipedia.org, www.subito.it and
  www.muenchen.de: every session printed the tick, neither button was clicked, and the
  UNVERIFIED note denied the banner. Both lines came from one result. The heuristic
  cannot tell a Didomi notice from a footer link called "Dichiarazione sui cookie"
  (Wikipedia's match), and the note now says what it knows: something that looks like
  a banner was found, and no refusal control was recognised on it.

- **A page that never goes idle keeps its HTTP status.** `page.goto(wait_until=
  "networkidle")` returns the response only when the wait succeeds; when the page keeps
  the network busy it raises a timeout and the status, which had arrived in the first
  second, was lost with it. Measured on 2026-10-09: zalando.it answered 403 from its
  edge with a full page whose scripts never went quiet, so the status was None,
  `page_not_served` saw nothing wrong, and the audit said "0 trackers before consent,
  UNVERIFIED" about an error page it never had; enel.it and poste.it, served with 200
  and never idle, showed no status in any session. The status is now taken from the
  main document's response as it arrives, last hop of a redirect, and `goto` only
  confirms it. `tests/site/forbidden_busy.html`, served with 403 by the test server
  under `/forbidden/`, reproduces the zalando.it case.

- **TrustArc and Usercentrics refusals are clicked, and so are "Non accetto",
  "Continua senza accettare" and "Solo gli essenziali".** Measured on 2026-10-09:
  enel.it and poste.it (TrustArc) offer refusal in one click — `#truste-consent-required`
  "Continua senza accettare", whose banner says it leaves only technical cookies, and
  `#truste-consent-required2` "Non accetto" — and the audit clicked "Accetta", found no
  refusal, and reported *"Accept was applied and no refusal control was found"* with
  GDPR art. 4(11) cited against both. zalando.it (Usercentrics) renders its banner in a
  shadow root with no ids; the refusal is `[data-testid="uc-deny-all-button"]` "Solo gli
  essenziali". The three banners are in `tests/site/`, captured from the real pages
  that day, and the sessions now click the refusal on each and the acceptance on none.

- **An error page in any of the three sessions means NOT MEASURED.** `page_not_served`
  read the pre-consent status only. In the batch run of 2026-10-09 www.zalando.it got no
  response at all in the pre-consent session and the edge's 403 page in the post-reject
  one — with a Usercentrics banner over it and Google Tag Manager loading once "Solo gli
  essenziali" was clicked — and the verdict came out as *VIOLATION, 2 trackers new after
  rejection*, assembled from one session that saw nothing and one that saw an error page.
  The verdict rests on session 3; an error page there leaves it nothing to rest on. The
  report now names the session that got the error page, and the other sessions' tables
  say that no verdict rests on them.

### Changed

- **The test matrix runs on `3.15-dev` too, as an experimental row.** 3.15.0 final is
  due 2026-10-09 (PEP 790) and the dependencies the suite stands on already ship
  cp315 wheels; `actions/setup-python` resolves `3.15-dev` to the newest build, rc.3
  today and the final once it is out. The row is an `include` with
  `continue-on-error`, so it may fail without failing the run or the required
  `Tests` check; the classifiers still stop at 3.14 until 3.15 is final. patchradar
  has had the same row since 2026-08-20.

## [2026.43] - 2026-10-08

### Added

- **`CVE-2026-77214` recorded in `SECURITY-EXCEPTIONS.toml`.** Docker Scout and Snyk
  report the heap over-read in expat's `XML_ParseBuffer`; `patchradar debian` on
  2026-10-08 says fixed in sid only (`2.9.0-1`), open in trixie, bookworm and forky, no
  Debian bug yet. Recorded the way the other expat entries are, to be reviewed by
  2026-11-30, with who loads the system `libexpat1` in the image: fontconfig and Mesa,
  for their own configuration files. CPython's `pyexpat` carries its own copy, and
  cookieradar parses no XML.

- **The files the build is told to include are checked to be there.** apkradar lost its
  `LICENSE` out of the working tree on 2026-10-04 and the loss reached `main`: pyproject
  names the file, so `python -m build` failed with `License file does not exist: LICENSE`,
  and the PyPI publish and the image went down with it. cookieradar lost its own a few
  hours later, during a run of the suite. Neither suite noticed, because neither looked.

  What removes them is still not known, and these cases do not explain it. They stop it
  reaching a commit, which is the part that can be fixed without knowing.

  The expectation is read out of the declarations rather than written down as `LICENSE`,
  because the five Radar do not declare it the same way: patchradar states its licence as
  text and only its Dockerfile names the file, the other four name it in pyproject, and of
  those apkradar and mailradar do not copy it into the image. So two cases — every file
  pyproject names, and every path the Dockerfile copies — and between them each repository
  is covered, three of them twice.

  Checked by moving the file aside in all five: it fails where it should and passes where
  the declaration genuinely does not name it, and pointing pyproject at a file that is not
  there fails too.

### Fixed

- **Two defences in `release.sh` that the tests did not actually measure.** Found by
  mutating the script rather than by reading it.

  Replacing the existing-tag check's `fail` with an `echo` of the same words left every
  case green: the script carried on, bumped, **committed**, and only then did `git tag`
  refuse the tag that already existed. The release was still refused — one commit too
  late, which is the opposite of what the script promises, that a refusal leaves the
  version file modified and nothing else. The cases now check that it did not commit on
  its way to refusing.

  And `git push --atomic` was not measured at all; two separate pushes passed. With two
  pushes `main` arrives and the tag does not, so the repository carries a version bump
  that no release and no published artifact corresponds to — and the tag that would
  produce them cannot be pushed afterwards either, because the version it would be
  given is by then "already the current version". A `pre-receive` hook on the test
  remote now refuses tags, which is the way to make the second half fail on demand.

  Both mutations fail now, along with the three that already did.

- **The PyPI wait allows a margin once the index answers.** apkradar's Docker build
  failed on 2026-10-03 with `No matching distribution found` **fifteen seconds after**
  the wait had reported the version available — 16:31:21 against 16:31:36. The poll is
  not wrong and not enough: it establishes that the file is reachable from the runner,
  while the build container, multi-platform through buildx, resolves the index again
  and can reach an edge still serving the old one.

  This is not the `sleep 60` that stood in that step before polling and lost the race
  twice. That was a guess about how long publishing takes, made before knowing
  anything; this waits for the fact first and then allows a bounded margin for it to
  propagate, and says so in the log when it uses one.

  It narrows the window; it does not close it. What closes it is not asking the index
  during the build at all — which is what exeradar's Dockerfile already does, with
  `pip install /app/src`, and why exeradar has no wait script and did not hit this.
  cookieradar and patchradar are one word from that (`_SOURCE=local`); apkradar and
  mailradar would need the build argument added. That is the follow-up.

  Three cases hold the margin, and they were needed twice over. The two cases that
  already drove this script pass the retry interval as zero so they stay fast, and the
  new default made every success wait 45 seconds past their timeout — so the suite was
  red in all four repositories until those two were told to ask for no grace. Telling
  them that alone would have left the margin itself unmeasured, which is the shape of
  defect this script was written to fix in the first place. So: one case times a
  two-second grace and checks the log says why it waited, one checks that no grace
  waits for nothing and claims nothing, and one measures the *default* without the
  suite paying 45 seconds for it — started with no grace argument, the script must
  still be running three seconds after the index answered. All four ways of undoing
  the margin were checked against them: the default set to zero, the wait removed
  while the log still claims it, the log removed while the wait still happens, and the
  guard removed so zero waits anyway.

- **`batch` no longer crashes on a site it could not see.** The verdict was turned into
  a label through a table with no entry for ERROR, so a site answering 403, or a
  bot-management challenge answering 200, ended in `❌ Error: <ExitCode.ERROR: 3>`, and
  the report asked for with `-o` was never written. It now reads `⛔ NOT MEASURED` with
  the reason and no tracker counts — as `audit` already did — and the report is saved.

- **Auditing a site that is itself on the tracker list no longer finds it a tracker of
  itself.** `linkedin.com`, `facebook.com`, `bing.com`, `tiktok.com`: the site's own
  document was counted as the tracker `linkedin.com` in every session, so the verdict
  was always VIOLATION "persists from pre-consent". Requests to the audited site are
  first-party, which the README already put out of scope, and `trackers` is again the
  subset of `external` that its own comment says it is.

- **The accept selector `button[id*='agree']` no longer clicks "disagree".** A substring
  match: Didomi's `didomi-notice-disagree-button` sits next to its agree button, and
  the selectors are tried before the labels, so the post-accept session rejected and
  was recorded as accepted.

- **The site is the one the browser landed on, spelled as the browser spells it.** The
  host compared against every request came from the address typed: `müller.de` against
  requests to `xn--mller-kva.de`, or `example.com` against a redirect to `example.it`,
  and every resource of the site came out as an unknown external host. The typed host
  is now converted to IDNA, and the main frame's navigation — redirects included —
  decides the site, in Chromium's own spelling (which also covers `ß`, where Python's
  IDNA 2003 codec and Chromium disagree). Checked against real Chromium on local pages.

- **No provision is cited for a challenge page.** `notes_of` knew that an error page is
  not the site and did not know the same of a challenge served with 200, so the report
  said NOT MEASURED and, under the provisions, "no cookie banner was found". Both now get
  their own NOT MEASURED note, and `findings_of` draws no finding from either: a reject
  button on a page that is not the site no longer leads to citing a violation.

- **`normalize_url` refuses an address with no host.** `https://` passed, the browser
  refused to navigate, and an invalid address exited 2 (UNVERIFIED) instead of 3.

- **An unreadable `--trackers` database exits 3, not 1.** Only `ValueError` was caught,
  so a `.eno` that could not be read escaped as a traceback with exit status 1 — which
  a pipeline reads as VIOLATION.

- **`batch -o` report names no longer collide where the filesystem ignores case.**
  `Example.com.txt` and `example.com.txt` are one file on Windows and macOS, and the
  second report overwrote the first.

- **A trackerdb block left open is kept when another block follows it**, not only at the
  end of the file, as the parser's docstring already promised.

- **Shell scripts are checked out with LF everywhere** (`.gitattributes`). With
  `core.autocrlf=true` a Windows checkout wrote `release.sh` and `wait_for_pypi.sh` with
  CRLF, and bash stopped at `set: pipefail\r: invalid option name`.

- **`pytest`, as the README says to run it, no longer ends in three errors.** The
  benchmarks need the CodSpeed runner, which only `codspeed.yml` installs; without it
  they are now skipped with that reason. And `pyproject.toml` no longer sends the reader
  to `tests/test_benchmark_contract.py`, a file that never existed.

- **README:** `audit --trackers` is in the command reference, the version examples use
  the current scheme, and `batch`'s NOT MEASURED is described.

### Changed

- **The race with PyPI is closed rather than narrowed: the released image no longer asks
  the index.** `docker.yml` installed `cookieradar==<the new version>` from PyPI and
  polled the index first to make that work. The poll is not wrong and not enough: it runs
  on the runner, while the multi-platform build resolves the index again, per platform,
  from whichever edge answers — apkradar lost that race on 2026-10-03 **fifteen seconds
  after** its poll had succeeded. Nothing that waits can close it. Not asking does, so the
  image is built from the source the tag points at.

  `local` is also the branch `tests.yml` already builds on every run, with the smoke test
  behind it, so the release moves onto the better exercised of the two paths rather than
  onto an untried one. This repository is the only one of the five where that was already
  true; in the other four the only thing that built the image automatically was the
  workflow that publishes it.

  Two things follow. A dispatched rebuild now checks out the tag it was given: while the
  image installed that version from the index, where the job stood in the tree did not
  matter, and built from the checkout it decides what ships. And that the file on PyPI can
  be installed, which the old arrangement proved by accident, is now checked on purpose in
  `publish.yml` after the upload — where a slow index delays a check instead of failing a
  build that had nothing to do with it, and with no margin, because there is a single
  resolver there.

  Five mutations hold it, and all five fail: the image back on the index, the checkout off
  the tag, a wait returning before the build, the published file unchecked, and a margin
  where there is one resolver.

  Not included, and worth doing separately: neither branch of this Dockerfile passes
  `--only-binary :all:`, so a dependency without an aarch64 wheel would be compiled under
  QEMU. patchradar's `pypi` branch had that guarantee and keeping it was part of its move;
  here there is nothing to keep, and adding it is a change of its own.

- **The scanner no longer guards against a service-worker request it never receives.**
  `_is_main_document` caught the error that `request.frame` raises for a service
  worker's request, which has no frame. Playwright hands those to the context alone,
  never to `page.on("request")`, the scanner's only listener, and none is a navigation,
  so the check stopped before asking for the frame anyway. Measured with Playwright 1.63
  on Windows and Linux; an integration test with a fetching service worker, on real
  Chromium, keeps it so. The tests that #23 had written against mocks of the scanner,
  Playwright and the law fetcher run on real inputs now as well: local sites scanned by
  Chromium with the host resolver mapped to `127.0.0.1`.

- **`release.sh` runs the suite after the bump, and refuses before committing.**
  The version is written as the script's first act, so a suite run *before* a
  release cannot see what the bump breaks. Twice — apkradar 2026.42 on 2026-10-03
  and 2026.43 on 2026-10-04 — `test_the_readme_states_the_version_it_was_captured_with`
  failed in CI, on `main`, with the tag already pushed, and was fixed by hand after
  the fact.

  The gate sits between writing the version and committing it, not after: a refusal
  then leaves the version file modified and nothing else touched, which is what
  somebody needs to see, and `git checkout` undoes it. A gate after the commit would
  have to undo a commit, and undoing is worse than not doing. A repository with no
  `tests/` is not held up by a suite it does not have.

  Three cases hold it, and the first was checked against the script without the gate:
  a failing suite stops the release with nothing committed, tagged or pushed; a
  passing one lets it through; and no `tests/` is not a failure.


## [2026.42] - 2026-10-04

### Removed

- **`CVE-2026-84782` out of `SECURITY-EXCEPTIONS.toml`; `CVE-2026-82560` kept on
  purpose.** The openssl entry was never an acceptance — it said so — but a
  rebuild: `patchradar debian CVE-2026-84782` reports it resolved in trixie at
  `3.5.7-1~deb13u3`, which the Dockerfile's `apt-get upgrade` picks up at the next
  build. GitHub closed the alert at **2026-09-30T18:32:11Z**, this repository's
  republish, so the rebuild happened and the entry goes. Its return would mean the
  upgrade stopped taking, which is worth a build failing over.

  `CVE-2026-82560` stays, and not because its silence is shorter — it is longer.
  Docker Scout stopped reporting it at 2026-09-29T15:29:03Z, earlier and on its
  own, with nothing done to the image in between, while
  `patchradar debian CVE-2026-82560` on 2026-10-02 still reports perl no-dsa in
  trixie at `5.40.1-6+deb13u1`, no fix in any suite, Debian bug 1148455. perl-base
  is still installed and still unfixed; only the reporting changed, and Scout has
  already changed its mind about this exact id once — which is why the gate reads
  closed alerts at all.

  Checked by running `tools/security_exceptions.py` against this repository's live
  open and closed alerts rather than by inference: exit 0, with `CVE-2026-82560` the
  one settled entry it names. Twenty-four entries down to twenty-three. The same
  decision was taken in exeradar and apkradar the same day.


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

- **Mutation testing runs again: `also_copy` in `[tool.mutmut]`.** The Saturday
  run died in all five Radar on 2026-10-03, before a single mutant was tried, and
  the cause was the same one each time with a different victim — here, `tests/test_ci_scripts.py` could not read `Dockerfile`.

  mutmut copies `source_paths` into `mutants/` and runs the suite from there,
  adding only `tests/`, `test/`, `setup.cfg`, `pyproject.toml` and `uv.lock` of its
  own accord. So every test that imports from `tools/` or `scripts/`, or reads a
  file at the repository root, found nothing — and since the stats phase runs the
  suite rather than merely collecting it, one such test killed the whole run.

  The list was verified rather than guessed. mutmut 3.8 refuses to run on Windows,
  so the `mutants/` tree was rebuilt by hand from mutmut's own copy rules —
  `configuration.py:184` and `utils/file_utils.py:66` — and the suite run inside it
  until it passed: **584 passed, 22 skipped**.

  This is *not* the previous day's move to `ubuntu-26.04`: the failures are
  Python-level, inside a copied tree, and patchradar's instance dates from
  2026-09-26. The weekly cron is only what surfaced them all at once — the first
  firing since the tests that trip it were written.

- **The image Snyk scans has a fixed tag, so code scanning keeps one
  configuration for it.** It was built as `snyk-scan:${GITHUB_SHA}`, and Snyk
  Container writes its own automation id into the SARIF from the image reference it
  scanned — overriding the `category:` given to `upload-sarif`. So every commit
  minted a new code-scanning configuration that nothing could ever find again, and a
  pull request was told *"configurations present on refs/heads/main were not
  found"* and could no longer be shown which alerts it had introduced.

  Measured on 2026-10-02 in apkradar, which had reached **32** of them and whose
  pull request #16 could not be diffed. This repository shows one, because its image
  does not carry the extra target Snyk names the image in. The tag is the same in
  all five, so the fix is too: the defect is there whether or not it has surfaced.

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

- **The CI runners are pinned to `ubuntu-26.04`, and the benchmarks job is pinned
  to `ubuntu-24.04` because CodSpeed cannot run on 26.04.** `ubuntu-latest` was
  Ubuntu 24.04 — read off a live run on 2026-10-02, image `ubuntu24/20260927.320` —
  and GitHub moves that label on its own schedule, so the choice was between finding
  out what breaks on a branch or finding out later on `main` at a moment nobody
  picked.

  Something did break, which is the whole value of having asked: `CodSpeedHQ/action`
  v5 fails on 26.04 with `##[error]Unsupported system`. `mode: simulation` was
  already set and the action was pinned, so it is the image and nothing else. Every
  one of the five Radar runs CodSpeed, so every one of them would have broken the
  same way the day the label moved by itself.

  That job is pinned to **24.04 rather than left on `ubuntu-latest`**: left there it
  keeps working right up to the day the label moves and then fails on `main`. 24.04
  is supported until April 2029, and a comment beside it says to try 26.04 again now
  and then, because nothing here will notice when CodSpeed adds support.

  The risk surface was measured before anything changed — no `apt-get` and no `sudo`
  in any workflow, Python from `actions/setup-python` at explicit versions, no
  `container:` or `services:` jobs — and the Docker path was checked on its own by
  dispatching `docker-build-check.yml` against the branch, which succeeded on image
  `ubuntu26/20260927.149`.

  What pinning costs: nothing bumps it for you. Dependabot updates action versions,
  not `runs-on`.

- **ruff now lints `tools/` as well, because it never did.** Every one of the five
  Radar lints its package and its tests and stops there, which left
  `tools/security_exceptions.py` outside the check — the script that refuses a build
  over an unexplained alert had never been seen by the linter that gates the build.
  Found on 2026-10-02 by running ruff over the whole tree by hand while working on
  something else, which is not a way of finding things that scales.

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

[Unreleased]: https://github.com/maksimtech/cookieradar/compare/v2026.44...HEAD
[2026.44]: https://github.com/maksimtech/cookieradar/compare/v2026.43...v2026.44
[2026.43]: https://github.com/maksimtech/cookieradar/compare/v2026.42...v2026.43
[2026.42]: https://github.com/maksimtech/cookieradar/compare/v2026.41...v2026.42
[2026.41]: https://github.com/maksimtech/cookieradar/compare/v2026.40.1...v2026.41
[2026.40.1]: https://github.com/maksimtech/cookieradar/compare/v2026.40...v2026.40.1
[2026.40]: https://github.com/maksimtech/cookieradar/compare/v2026.09.11...v2026.40
[2026.09.11]: https://github.com/maksimtech/cookieradar/compare/v2026.09.10...v2026.09.11
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
