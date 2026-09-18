# CookieRadar

**Checks whether a website keeps tracking visitors after they click "Reject".**

CookieRadar opens a website in a real browser (Chromium) three times: without
touching the cookie banner, after clicking "Accept", and after clicking
"Reject". It records which known tracking services (Google Analytics, Meta,
DoubleClick, Hotjar, TikTok and others) the page contacts each time, and tells
you whether any of them is still loaded after the visitor refused consent.

```
$ cookieradar audit example.com
...
⚠️  VIOLATION — 2 tracker(s) loaded after rejection:
  → doubleclick.net (persists from pre-consent)
  → hotjar.com (new after rejection)
```

## Why it matters

Under EU rules (the GDPR together with the ePrivacy Directive), analytics and
advertising trackers may only run after the visitor has given consent, and a
refusal must be respected. A site whose banner says "Reject" but keeps loading
the same trackers is collecting data without a legal basis.

Checking this by hand means opening the browser developer tools, clearing
cookies, clicking through the banner and reading hundreds of network requests.
CookieRadar does it automatically and repeatably, and produces a report you
can keep as evidence of what the site did on a given day.

**Who it is for:** DPOs, privacy lawyers and consultants auditing a site,
agencies checking a consent banner before go-live, and developers verifying
that their tag manager respects the visitor's choice.

> CookieRadar produces technical evidence, not a legal assessment. A
> VIOLATION means "these tracking services were contacted after rejection";
> whether that is unlawful in a specific case is for a qualified person to
> decide. See [Known limitations](#known-limitations).

## Installation

Requires Python 3.11 or newer.

```bash
pip install cookieradar
playwright install chromium
```

The second command downloads the Chromium browser that CookieRadar drives
(once). On a fresh Linux machine Chromium may also need system
libraries; install them with:

```bash
playwright install --with-deps chromium
```

Check the installation:

```bash
cookieradar --version
# CookieRadar 2026.09.7
```

Prefer not to install Python? Use the [Docker image](#docker).

## Quick start

### Audit one website

```bash
cookieradar audit https://example.com
```

The `https://` prefix is optional: `cookieradar audit example.com` works too.
Only `http://` and `https://` addresses are accepted.

An audit takes from a few seconds to about a minute, because the site is
loaded three times and CookieRadar waits for each page to settle.

To watch the browser while it works, add `--no-headless`:

```bash
cookieradar audit example.com --no-headless
```

### Save the report

```bash
cookieradar audit https://example.com -o report.html
```

A file ending in `.html` (or `.htm`) is saved as a web page you can open in
any browser, attach to an email or archive. Any other name, for example
`report.txt`, is saved as plain text.

### Audit many websites

Create a text file with one address per line. Empty lines and lines
starting with `#` are ignored:

```text
# urls.txt — client sites, September audit
https://example.com
example.org
shop.example.net
```

Then run:

```bash
cookieradar batch urls.txt
```

For each site you get a one-line verdict:

```
Auditing https://example.com...
  🔴 VIOLATION — pre: 2 trackers, post-reject: 2 trackers
    → doubleclick.net (persists from pre-consent)
    → hotjar.com (new after rejection)

Auditing https://example.org...
  ✅ OK — pre: 0 trackers, post-reject: 0 trackers

Auditing https://shop.example.net...
  ⚠️  UNVERIFIED — pre: 3 trackers, post-reject: 3 trackers
    reject button not found: this session is equivalent to pre-consent
```

To also keep the full report of every site, give a folder with `-o`. One
text file per site is written there (e.g. `example.com.txt`):

```bash
cookieradar batch urls.txt -o reports/
```

An invalid address or a site that fails to load is reported and skipped;
the other sites are still audited.

## Reading the report

### The three sessions

Each session starts from a clean browser: no cookies and no history, like a
first-time visitor.

| Session | What CookieRadar does | What it shows |
|---|---|---|
| 🔴 **1 — Pre-consent** | Opens the page and does not touch the banner. | Trackers loaded **before the visitor has made any choice**. |
| 🟡 **2 — Post-accept** | Opens the page and clicks "Accept". | Trackers the site uses **when consent is given**: the full list, for comparison. |
| 🟢 **3 — Post-reject** | Opens the page, clicks "Reject", then **reloads the page** and records only what is loaded after the reload. | Trackers still loaded **after the visitor refused**. This is what the verdict is based on. |

The reload in session 3 matters: it shows what a visitor who has already
refused gets on every following page, not just the requests that were
already on their way when the button was clicked.

For each session the report lists:

- **Tracker domain, URL and type** of each tracking service contacted
  (one row per service; `script` is JavaScript code, `xhr`/`fetch` is data
  being sent, `image` is often a tracking pixel)
- **Banner found**: whether something that looks like a cookie banner was
  visible on the page
- **Cookies**: every cookie in the browser at the end of the session, with
  its domain and expiry date (`session` means it is deleted when the browser
  closes). This includes the site's own cookies, not only trackers'

Example of a session in the report:

```
🔴 Session 1 — Pre-consent (2 unique trackers)
                                 Pre-consent trackers
╭──────────────────────┬─────────────────────────────────────────────────────┬────────╮
│ Tracker Domain       │ URL                                                 │ Type   │
├──────────────────────┼─────────────────────────────────────────────────────┼────────┤
│ googletagmanager.com │ https://www.googletagmanager.com/gtm.js?id=GTM-XXXX │ script │
│ doubleclick.net      │ https://stats.g.doubleclick.net/g/collect           │ xhr    │
╰──────────────────────┴─────────────────────────────────────────────────────┴────────╯
Banner found: ✅
Cookies: 1

  Cookie   Domain         Expires
 ────────────────────────────────────
  _ga      .example.com   2027-09-19
```

### The verdict

At the end of the report there is one of three outcomes:

| Verdict | Meaning | What to do |
|---|---|---|
| ✅ **OK** — *"No trackers loaded after rejection"* | The "Reject" button was clicked and, after reloading, **none** of the known trackers was contacted. | Nothing, for the trackers CookieRadar knows. Still review session 1 (see below). |
| 🔴 **VIOLATION** | The "Reject" button was clicked, yet after reloading **at least one** known tracker was contacted. The list follows. | Investigate each listed service with whoever manages the site's tags and consent platform. |
| ⚠️ **UNVERIFIED** | CookieRadar **could not click "Reject"**: no banner, or a banner it does not recognise. Session 3 then shows the page without any choice made, so **no verdict is given**. | Check the site by hand, or with `--no-headless` to see what the banner looks like. |

The verdict only looks at session 3. **Trackers in session 1 (pre-consent)
are not part of the verdict**, but they deserve attention on their own:
a tracker that loads before the visitor has chosen anything is loaded
without consent. Read the session 1 table even when the verdict is OK.

If a session hit an error (for example the site took more than 30 seconds
to load), the report shows it in yellow and adds *"Result may be incomplete:
some sessions reported errors"*. Treat that result with caution and run the
audit again.

### "Persists from pre-consent" vs "new after rejection"

Each tracker in a VIOLATION comes with a note that helps find the cause:

- **persists from pre-consent**: the tracker was already loaded before any
  choice (session 1) and is **still loaded after rejection**. Typically the
  tracker is installed directly in the page or in the tag manager without
  any consent condition, so clicking "Reject" has no effect on it.
- **new after rejection**: the tracker did **not** load before the choice
  and appears **only after rejection**. The act of rejecting, or the reload
  after it, activates it: typically a tag configured to fire on "any
  consent decision" instead of "consent granted", or a consent platform
  that treats "reject" as "accept".

In the example above, `doubleclick.net` ignores the refusal entirely and
`hotjar.com` is switched on by it.

## Known limitations

CookieRadar automates what a person would check by hand, with the same blind
spots a quick manual check has. Keep these in mind before relying on a result.

**The banner is not always detected or clicked.**
- Buttons are recognised by the most common consent platform codes
  (e.g. OneTrust, including its two-step "Preferences → Reject all" flow) and
  by labels in **English and Italian** only: "Accept", "Accept all",
  "Accetta tutto", "OK", "Reject", "Reject all", "Decline", "Rifiuta tutto"
  and similar. A banner in another language, or with wording like "Continue
  without accepting", results in **UNVERIFIED**.
- Banners displayed inside an embedded frame (`iframe`), which some consent
  platforms use, are not clicked.
- Banners that only offer "Settings" with individual switches to turn off
  (other than OneTrust) are not handled.
- "Banner found" is a hint, not proof: it means something whose name
  contains `cookie`, `consent`, `gdpr` or `banner` was visible. The verdict
  never depends on it; it depends on whether "Reject" was actually clicked.

**Only known trackers are detected.** CookieRadar recognises a fixed list of
34 tracking and advertising services (and all their subdomains), such
as Google Analytics, Google Tag Manager, DoubleClick, Meta/Facebook,
LinkedIn, TikTok, Microsoft Bing and Clarity, Hotjar, Adobe, Amazon Ads.
It does not detect:
- services that are not on the list;
- tracking through the site's own domain (first-party or server-side
  tracking, e.g. a tag manager proxied through `metrics.example.com`);
- what data a request contains, or whether a cookie is "necessary".

A VIOLATION is therefore reliable for the services listed; an OK means
"none of the listed services", not "no tracking at all".

**One page, one anonymous visitor.** Only the address you give is audited:
CookieRadar does not follow links, fill in forms or log in. Pages behind a
**login or paywall** are audited as an anonymous visitor sees them (usually
the login page or the teaser), and tracking that only happens after login is
not seen. Audit the specific pages that matter (home, product, checkout)
as separate addresses.

**Automated browsers can be treated differently.** Some sites detect
automated or headless browsers and show a CAPTCHA, a different banner or no
banner at all. If the result looks wrong, retry with `--no-headless`.

**Timing.** Each page gets up to 30 seconds to load, plus a few seconds for
the banner and trackers to appear. Trackers that load much later (e.g. after
scrolling or a long delay) are not recorded.

## Docker

The image contains CookieRadar and Chromium, ready to use; nothing else to
install. It runs as a non-root user.

```bash
docker run --rm maksimtech/cookieradar audit https://example.com
```

Images are published for `linux/amd64` and `linux/arm64`, tagged `latest`
and with each version, e.g. `maksimtech/cookieradar:v2026.09.7`.

To save reports or read a URL list, mount a folder from your computer.
The container works in `/home/cookieradar` and runs as user ID 1000, which
must be able to write to the mounted folder:

```bash
# Save an HTML report to ./reports/report.html
mkdir -p reports
docker run --rm -v "$PWD/reports:/home/cookieradar/reports" \
  maksimtech/cookieradar audit https://example.com -o reports/report.html

# Audit every address in ./urls.txt, one report per site in ./reports/
docker run --rm \
  -v "$PWD/urls.txt:/home/cookieradar/urls.txt:ro" \
  -v "$PWD/reports:/home/cookieradar/reports" \
  maksimtech/cookieradar batch urls.txt -o reports/
```

To build the image from this repository instead:

```bash
docker build -t cookieradar .
docker run --rm cookieradar audit https://example.com
```

## Command reference

```
cookieradar --version
cookieradar audit URL [--no-headless] [-o FILE]
cookieradar batch FILE [-o DIRECTORY]
```

| Option | Command | Effect |
|---|---|---|
| `-o`, `--output FILE` | `audit` | Save the report: HTML if the name ends in `.html`/`.htm`, plain text otherwise |
| `--no-headless` | `audit` | Show the browser window while auditing |
| `-o`, `--output DIRECTORY` | `batch` | Save one text report per site in this folder (created if missing) |
| `--help` | any | Show help |

`python -m cookieradar` works the same as `cookieradar`.

### Exit codes

The exit code carries the verdict, so a script or a CI pipeline can act on
it without reading the output:

| Code | `audit` | `batch` |
|---|---|---|
| **0** | OK: no tracker loaded after rejection | Every site is OK |
| **1** | VIOLATION | At least one site has a VIOLATION |
| **2** | UNVERIFIED: "Reject" could not be clicked | At least one site is UNVERIFIED, none has a VIOLATION, none failed |
| **3** | Error: invalid address, browser not starting, report not writable, invalid command-line option | The URL file cannot be read, an invalid command-line option, or at least one site could not be audited (invalid address, scan failed, report not writable) and none has a VIOLATION |

A VIOLATION always wins: if one site violates and another fails, `batch`
exits with 1, and so does `audit` when the verdict is VIOLATION but the
report file cannot be written. The error is still shown in the output.

A site that times out or cannot be reached is not an error for the exit
code: the audit runs, the problem is shown in yellow, and the verdict
follows from what was observed (usually UNVERIFIED, since "Reject" could not
be clicked).

Example: fail a CI job only on violations, and warn when a site could not be
verified:

```bash
cookieradar batch urls.txt -o reports/
case $? in
  0) echo "All sites respect the refusal" ;;
  1) echo "Violations found, see reports/"; exit 1 ;;
  2) echo "::warning::Some sites could not be verified" ;;
  *) echo "CookieRadar could not complete the audit"; exit 1 ;;
esac
```

## Development

```bash
git clone https://github.com/maksimtech/cookieradar
cd cookieradar
pip install -e ".[test]"
playwright install chromium
pytest
```

Changes are listed in [CHANGELOG.md](CHANGELOG.md). To report a security
issue, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 maksimtech. You may use, modify and redistribute
CookieRadar, including commercially, provided the license notice is kept.
