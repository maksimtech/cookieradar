"""What docs/nis2-compliance.md tells a customer has to stay true of this code.

The document answers the seven questions a customer subject to NIS2 (directive
2022/2555, in Italy d.lgs. 138/2024) can ask a software supplier, and a customer
reads it as evidence. Every statement in it that the repository can prove is
checked here, so that the document goes red when the code moves away from it
instead of quietly turning false: the hosts the tool contacts, what the browser
keeps, the user the image runs as, the cache it writes, the files each release
carries, the scanners it names, and the words a supplier cannot honestly use.

What the repository cannot prove is not claimed as proven. The required status
checks live in GitHub's settings, so the document gives the date they were read
on; what Chromium connects to on its own was measured, so the document gives the
date and the conditions; there is no penetration test, so the document says
there is none.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

import pytest
import yaml

from cookieradar import law_cache, law_checker, law_fetcher
from cookieradar.law_cache import LawCache
from cookieradar.law_fetcher import Provision
from cookieradar.scanner import ScanResult

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "cookieradar"
DOC = ROOT / "docs" / "nis2-compliance.md"
SECURITY = ROOT / "SECURITY.md"
README = ROOT / "README.md"
DOCKERFILE = ROOT / "Dockerfile"
WORKFLOWS = ROOT / ".github" / "workflows"
EVIDENCE = WORKFLOWS / "sbom.yml"
DOCKER = WORKFLOWS / "docker.yml"

# A module that imports one of these can reach the network; one that does not
# cannot, whatever URLs its constants mention (cli.py shows https://tim.it as an
# example in its help text and never contacts it). Playwright is the network
# layer of scanner.py: it drives the Chromium that loads the audited page.
NETWORK_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(?:httpx|playwright|smtplib|dns|requests|urllib\.request|socket)\b", re.M
)
URL_HOST = re.compile(r"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# The contact URL every request to the law sources carries in its User-Agent. It
# names this repository; nothing is sent to it.
USER_AGENT_LINK = re.compile(r"\(\+https://github\.com/maksimtech/")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def network_modules() -> list[Path]:
    return [
        path
        for path in sorted(PACKAGE.rglob("*.py"))
        if NETWORK_IMPORT.search(path.read_text(encoding="utf-8"))
    ]


def hosts_in_code() -> dict[str, set[str]]:
    """Fixed hosts named in string constants of the modules that can reach the network.

    The audited site, and every third party its page loads, has no fixed name:
    those hosts are declared in prose, not in the table this is compared with.
    """
    found: dict[str, set[str]] = {}
    for path in network_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in skip or USER_AGENT_LINK.search(node.value):
                continue
            for host in URL_HOST.findall(node.value):
                found.setdefault(host.lower().rstrip("."), set()).add(path.name)
    return found


def section(text: str, name: str) -> str:
    """The text between `<!-- name:start -->` and `<!-- name:end -->`."""
    match = re.search(rf"<!-- {name}:start -->(.*?)<!-- {name}:end -->", text, re.S)
    assert match, f"docs/nis2-compliance.md has no {name} section between its markers"
    return match.group(1)


def table_first_column(block: str) -> set[str]:
    """The backticked value in the first cell of every row of a markdown table."""
    values = set()
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells and cells[0].startswith("`"):
            values.add(cells[0].strip("`"))
    return values


def prose(text: str) -> str:
    return " ".join(text.split())


def function(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def called_names(node: ast.AST) -> set[str]:
    """`f` for every `f(...)` and `x.f(...)` inside node."""
    names = set()
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            if isinstance(call.func, ast.Name):
                names.add(call.func.id)
            elif isinstance(call.func, ast.Attribute):
                names.add(call.func.attr)
    return names


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


# --- Question 3: what leaves the machine ------------------------------------


def test_every_host_the_code_contacts_is_declared_and_no_other(doc):
    declared = table_first_column(section(doc, "hosts"))
    in_code = set(hosts_in_code())
    assert declared == in_code, (
        f"declared but not in the code: {sorted(declared - in_code)}; "
        f"in the code but not declared: {sorted(in_code - declared)}"
    )


def test_the_host_rule_looks_at_something():
    """A rule that found no host, or never read the browser's module, would pass
    for the wrong reason."""
    assert len(hosts_in_code()) >= 3
    assert {p.name for p in network_modules()} >= {"scanner.py", "law_fetcher.py"}


def test_the_host_rule_skips_what_is_only_cited():
    """Every request to the law sources names github.com/maksimtech/cookieradar in
    its User-Agent; cli.py shows https://tim.it in its help text and
    https://a.com in a docstring. None of them is a host the tool talks to."""
    hosts = hosts_in_code()
    for cited in ("github.com", "tim.it", "a.com"):
        assert cited not in hosts


def test_the_audited_site_and_its_third_parties_are_declared(doc):
    """The hosts that matter most have no fixed name: the audited page chooses
    them. Both commands load it, three times, so the document has to say so."""
    text = prose(doc)
    assert "cookieradar audit" in text and "cookieradar batch" in text
    assert "tre volte" in text
    assert "terza parte" in text or "terze parti" in text


def test_the_cache_declared_is_the_one_written(doc, monkeypatch, tmp_path):
    monkeypatch.delenv("COOKIERADAR_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    written = law_cache.default_cache_path().relative_to(tmp_path).as_posix()
    assert f"~/{written}" in doc
    assert "COOKIERADAR_HOME" in doc


def test_the_cache_holds_law_text_and_nothing_about_the_sites(tmp_path):
    """The document says the cache holds the cited provisions and no data about
    the audited sites: this is what the real cache writes."""
    cache = LawCache(tmp_path / "law_cache.json")
    provision = Provision.from_text("7", "testo", "2026-10-11T00:00:00Z", "32016R0679")
    cache.update({provision.key: provision}, checked_at="2026-10-11T00:00:00Z")

    data = json.loads((tmp_path / "law_cache.json").read_text(encoding="utf-8"))
    assert set(data) == {"checked_at", "entries"}
    assert [set(entry) for entry in data["entries"]] == [{"article", "text", "sha256", "fetched_at", "celex"}]


def test_nothing_is_fetched_or_cached_when_nothing_is_cited(tmp_path):
    """The law sources are contacted, and the cache written, only when the report
    cites a provision. A site that respected the refusal cites nothing."""
    result = ScanResult(url="https://example.com")
    result.post_reject.consent_clicked = True
    cache_file = tmp_path / "law_cache.json"

    law = law_checker.check(result, cache=LawCache(cache_file))

    assert law.citations == [] and law.acts == []
    assert not cache_file.exists()


def test_the_law_sources_are_given_the_act_and_never_the_site():
    """The URLs of the law sources are built inside fetch_provisions, from the act
    and the article numbers it is handed: nothing about the audited site can
    reach them. law_checker calls nothing else of law_fetcher that downloads."""
    parameters = set(inspect.signature(law_fetcher.fetch_provisions).parameters)
    assert parameters == {"act", "articles", "lang", "now", "client"}

    tree = ast.parse((PACKAGE / "law_checker.py").read_text(encoding="utf-8"))
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "law_fetcher"
    }
    assert used == {"fetch_provisions", "utc_stamp"}


def test_only_audit_consults_the_law_sources(doc):
    assert "_law_check" in called_names(function(PACKAGE / "cli.py", "audit"))
    assert "_law_check" not in called_names(function(PACKAGE / "cli.py", "batch"))
    assert "`batch` non contatta le fonti normative" in prose(doc)


def test_the_https_only_law_fetch_is_declared(doc):
    """publications.europa.eu answers the HTTPS request with a 303 to an http://
    address (recorded on 2026-10-11). Until that day fetch_html followed it and the
    act travelled without TLS; it now follows redirects by hand and takes such a
    hop over HTTPS (tests/test_law_fetch_https.py). The document says so."""
    source = (PACKAGE / "law_fetcher.py").read_text(encoding="utf-8")
    assert "follow_redirects=True" not in source
    assert "follow_redirects=False" in source
    assert "solo in HTTPS" in prose(doc)
    assert "arriva quindi in chiaro" not in prose(doc)


BROWSER_STATE = (
    "launch_persistent_context",
    "user_data_dir",
    "storage_state",
    "screenshot",
    "record_har",
    "record_video",
    "tracing",
)


def test_the_browser_keeps_nothing_on_disk(doc):
    """Each session gets a new browser context and none is saved: no persistent
    profile, no stored state, no screenshot, no recorded traffic."""
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for call in BROWSER_STATE:
            assert call not in source, f"{path.name} uses {call}"
    scan = function(PACKAGE / "scanner.py", "scan")
    loop = next(node for node in ast.walk(scan) if isinstance(node, ast.For))
    assert "new_context" in called_names(loop), "the contexts are not created one per session"
    sessions = next(
        node.value for node in ast.walk(scan)
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "sessions"
    )
    assert len(sessions.elts) == 3
    assert "profilo temporaneo" in prose(doc)


def test_the_report_carries_no_cookie_value(doc):
    """The report prints a cookie's name, domain and expiry. Its value is never
    read by the code that writes the report."""
    tree = ast.parse((PACKAGE / "cli.py").read_text(encoding="utf-8"))
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)}
    assert "value" not in constants
    assert "non i loro valori" in prose(doc)


def test_the_sandbox_the_document_describes(doc):
    """Playwright starts Chromium with --no-sandbox unless chromium_sandbox=True
    is passed; measured on 2026-10-11 on the command line of
    chrome-headless-shell. scanner.py passes nothing, so the document says the
    sandbox is off; enabling it has to change the document too."""
    scan = function(PACKAGE / "scanner.py", "scan")
    launch = next(
        node for node in ast.walk(scan)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "launch"
    )
    keywords = {k.arg for k in launch.keywords}
    assert "chromium_sandbox" not in keywords and "args" not in keywords
    assert "`--no-sandbox`" in doc


def test_the_trackerdb_is_read_from_disk_only(doc):
    """--trackers reads a copy of ghostery/trackerdb the operator already has."""
    assert not NETWORK_IMPORT.search((PACKAGE / "trackerdb.py").read_text(encoding="utf-8"))
    assert "--trackers" in doc


def test_the_lockfile_is_not_presented_as_what_the_image_installs(doc):
    """The Dockerfile installs with pip, which resolves `>=` ranges at build time
    and never reads uv.lock: the document says so, and points to the image SBOM
    for what an image really holds."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "pip install" in dockerfile
    assert not re.search(r"\buv\b", dockerfile)
    assert "non lo usano" in prose(doc)


def test_the_provenance_the_document_names_is_not_turned_off():
    """PEP 740 attestations come from gh-action-pypi-publish with trusted
    publishing, BuildKit's SLSA provenance from build-push-action's default:
    both checked on the 2026.44 artefacts on 2026-10-11. Turning either off in
    the workflows would make section 1 false for the next release."""
    publish = _workflow(WORKFLOWS / "publish.yml")
    job = publish["jobs"]["build-and-publish"]
    assert job["permissions"]["id-token"] == "write"
    step = next(s for s in job["steps"] if "gh-action-pypi-publish" in s.get("uses", ""))
    assert str((step.get("with") or {}).get("attestations", "true")).lower() != "false"
    docker = _workflow(DOCKER)["jobs"]["docker"]["steps"]
    push = next(s for s in docker if (s.get("with") or {}).get("push") is True)
    assert str(push["with"].get("provenance", "true")).lower() != "false"


# --- Question 2: who the container runs as -----------------------------------


def test_the_image_runs_as_the_user_the_document_names(doc):
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    user = re.findall(r"^USER\s+(\S+)", dockerfile, re.M)[-1]
    uid = re.search(rf"useradd\b[^\n]*-u\s+(\d+)[^\n]*\b{re.escape(user)}\b", dockerfile)
    assert user not in {"root", "0"}
    assert uid, f"the Dockerfile does not create {user} with an explicit UID"
    assert f"UID {uid.group(1)}" in doc
    assert f"`{user}`" in doc


# --- Questions 1 and 6: what every release carries ---------------------------


@pytest.fixture(scope="module")
def evidence() -> dict:
    return yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_evidence_follows_the_image_of_a_release(evidence):
    """The image SBOM and its scan describe the image of the tag, so the job runs
    when that image has been pushed — not when the tag is, when it does not exist
    yet. docker.yml has no trigger of its own here: "Publish to PyPI" calls it
    after the upload, and a called workflow runs inside its caller with no run of
    its own (it became a called workflow on 2026-09-18, and GitHub lists no
    docker.yml run for any release since), so the run to follow is the caller's."""
    callers = sorted(
        _workflow(path)["name"]
        for path in WORKFLOWS.glob("*.yml")
        if any(job.get("uses") == "./.github/workflows/docker.yml" for job in _workflow(path)["jobs"].values())
    )
    assert callers, "no workflow calls docker.yml"
    triggers = evidence.get(True, evidence.get("on"))
    assert triggers["workflow_run"]["workflows"] == callers
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert "tag" in triggers["workflow_dispatch"]["inputs"]
    job = next(iter(evidence["jobs"].values()))
    assert "conclusion == 'success'" in job["if"]
    assert "startsWith(github.event.workflow_run.head_branch, 'v')" in job["if"]


JOB_ENV_CONTEXTS = {"github", "inputs", "matrix", "needs", "secrets", "strategy", "vars"}


def test_the_job_env_uses_only_contexts_github_allows_there(evidence):
    """`runner` is not available in a job's `env`, and GitHub refuses the whole
    file when it finds it: on 2026-10-11 the first dispatch of mailradar's copy of
    this workflow answered HTTP 422, "Unrecognized named-value: 'runner'", after
    the tests and every check had passed. The contexts allowed there are listed in
    GitHub's context-availability table."""
    for job in evidence["jobs"].values():
        for name, value in (job.get("env") or {}).items():
            for expression in re.findall(r"\$\{\{(.*?)\}\}", str(value)):
                # The first name of each dotted path: github.event.x names github only.
                used = set(re.findall(r"(?<![\w.])([a-z_]+)\.", expression))
                assert used <= JOB_ENV_CONTEXTS, f"env {name} uses {sorted(used - JOB_ENV_CONTEXTS)}"


def test_the_image_tag_named_is_the_one_docker_yml_pushes(doc):
    """docker.yml pushes the git tag with its v (VERSION=v${RAW#v}): the image of
    a release is maksimtech/cookieradar:v<version>, which is also what Docker Hub
    lists (v2026.44 on 2026-10-11). mailradar's first dispatch of the same
    workflow asked for :2026.44 and got MANIFEST_UNKNOWN."""
    image = f"maksimtech/{PACKAGE.name}"
    docker = DOCKER.read_text(encoding="utf-8")
    assert re.search(r"VERSION=(?:\$\{RAW\}|v\$\{RAW#v\})", docker)
    pushed = (
        f"{image}:${{{{ steps.version.outputs.VERSION }}}}",
        "format('" + image + ":{0}', steps.version.outputs.VERSION)",
    )
    assert any(form in docker for form in pushed)
    for name, text in (("the document", doc), ("SECURITY.md", SECURITY.read_text(encoding="utf-8"))):
        assert f"{image}:v" in text, f"{name} does not name the image by its v tag"
        assert not re.search(rf"{re.escape(image)}:(?:\d|<)", text), f"{name} names a tag docker.yml never pushes"
    evidence = EVIDENCE.read_text(encoding="utf-8")
    assert '"registry:${IMAGE}:${TAG}"' in evidence
    assert "image-ref: ${{ env.IMAGE }}:${{ env.TAG }}" in evidence


def test_the_image_is_rebuilt_only_when_the_document_says(doc):
    """No schedule rebuilds the image here: it is built when a release is cut, or
    when the maintainer dispatches docker.yml by hand for a published version,
    which pushes that version's tag again. The document and SECURITY.md must not
    promise a weekly rebuild, and must say a tag can be pushed again."""
    triggers = _workflow(DOCKER)
    triggers = triggers.get(True, triggers.get("on"))
    assert set(triggers) == {"workflow_call", "workflow_dispatch"}
    security = SECURITY.read_text(encoding="utf-8")
    assert not re.search(r"ricostruit\w* ogni settimana|rebuilt weekly|weekly rebuild", doc + security, re.I)
    assert "non viene ricostruita tra una release e l'altra" in prose(doc)
    assert "is not rebuilt between releases" in prose(security)


def _evidence_step(evidence: dict, name: str) -> str:
    job = next(iter(evidence["jobs"].values()))
    return next(step["run"] for step in job["steps"] if step.get("name") == name)


def test_the_evidence_note_gives_the_digest_and_not_the_tag_twice(evidence):
    """Syft puts the tag in metadata.component.version, and mailradar's first
    EVIDENCE note, on v2026.44, read "digest v2026.44". The digest a customer pins
    comes from Docker Hub, which gives the index digest and one per platform."""
    note = _evidence_step(evidence, "Describe the evidence")
    assert '["metadata"]["component"]' not in note
    assert "https://hub.docker.com/v2/repositories/${IMAGE}/tags/${TAG}" in note


def test_the_source_sbom_names_the_package_it_describes():
    """Without --pyproject, cyclonedx-py lists the environment and names no main
    component: the SBOM did not say which product it was the SBOM of."""
    evidence = EVIDENCE.read_text(encoding="utf-8")
    assert "--pyproject pyproject.toml" in evidence
    assert "--mc-type application" in evidence


def test_the_source_sbom_gives_the_version_it_describes(evidence):
    """The version is dynamic in pyproject.toml (hatch reads it from
    cookieradar/__init__.py), so cyclonedx-py named the main component with no
    version: the source SBOM attached to v2026.44 on 2026-10-11 said "cookieradar"
    and nothing else. The step takes the version from the package it installed,
    refuses one that is not the tag's, and writes it into the SBOM."""
    step = _evidence_step(evidence, "SBOM of the Python environment")
    assert 'version("cookieradar")' in step
    assert '"VERSION"' in step and "exit(" in step
    assert '["version"] =' in step


REMOVABLE = ("pip", "setuptools", "wheel")


def test_the_source_sbom_leaves_out_what_the_image_removes(evidence):
    """The source SBOM describes a venv, which comes with its own pip; if the
    image removed pip (or setuptools, or wheel), the SBOM would list what the
    image does not ship, as releaseradar's first sbom-source did. This Dockerfile
    removes none of them, and the image SBOM of v2026.44 lists pip 25.0.1, as the
    source SBOM does: so nothing is uninstalled, and each must follow the other."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    step = _evidence_step(evidence, "SBOM of the Python environment")
    for package in REMOVABLE:
        removed = bool(re.search(rf"pip uninstall\b[^\n]*\b{package}\b", dockerfile))
        dropped = f"/tmp/product/bin/python -m pip uninstall --yes --quiet {package}" in step
        assert removed == dropped, f"{package}: removed from the image {removed}, from the SBOM venv {dropped}"


def test_an_empty_repository_scan_is_not_presented_as_a_clean_one(evidence, doc):
    """The trivy-fs report attached to v2026.44 on 2026-10-11 has no Results at
    all: that tag has no lockfile, so Trivy found nothing it could analyse. An
    empty report reads as "no vulnerabilities" to whoever opens it; the note and
    the document say what it is."""
    describe = _evidence_step(evidence, "Describe the evidence")
    assert '"Results"' in describe
    assert "found no file it could analyse" in describe
    assert "non indica l'assenza di vulnerabilità" in prose(doc)


def test_every_request_of_the_package_carries_the_user_agent_it_claims(doc):
    """The document says the requests to the law sources name CookieRadar and this
    repository. They all go through fetch_html, the only place that calls an
    httpx client, and it sets USER_AGENT before any header a caller adds. The
    browser's requests carry Chromium's own User-Agent, and the document says
    that instead."""
    tree = ast.parse((PACKAGE / "law_fetcher.py").read_text(encoding="utf-8"))
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "get"
            and isinstance(call.func.value, ast.Name) and call.func.value.id in {"client", "own_client"}
            for call in ast.walk(node)
        )
    }
    # Since 2026-10-11 the requests go out of _get_over_https, which follows
    # redirects by hand over HTTPS and sends the headers fetch_html gives it.
    assert callers == {"_get_over_https"}
    # Read from the file, not from the function: conftest replaces fetch_html in
    # every test so that none reaches the network.
    law = (PACKAGE / "law_fetcher.py").read_text(encoding="utf-8")
    source = ast.get_source_segment(law, function(PACKAGE / "law_fetcher.py", "fetch_html"))
    assert 'headers = {"User-Agent": USER_AGENT, **(headers or {})}' in source
    assert "_get_over_https(own_client, url, headers, source)" in source
    assert "_get_over_https(client, url, headers, source)" in source
    helper = ast.get_source_segment(law, function(PACKAGE / "law_fetcher.py", "_get_over_https"))
    assert "client.get(target, headers=headers, follow_redirects=False)" in helper
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name != "law_fetcher.py":
            assert not re.search(r"^\s*(?:import|from)\s+httpx\b", path.read_text(encoding="utf-8"), re.M), path.name
    assert "`HeadlessChrome`" in doc


def test_the_document_says_what_the_image_evidence_leaves_out(doc):
    """Chromium reaches the image through `playwright install chromium`, as an
    archive with no package metadata: the image SBOM of v2026.44 has no Chromium
    component, not even its files, and the Trivy image report has no result for
    it. The document says so, and names what does identify it."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^RUN playwright install chromium$", dockerfile, re.M)
    text = prose(doc)
    assert "non elenca Chromium" in text
    assert "non lo controlla" in text


def test_the_evidence_job_pins_its_actions():
    for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
        if "uses:" in line:
            ref = line.split("uses:", 1)[1].split("#")[0].strip()
            assert re.search(r"@[0-9a-f]{40}$", ref), f"not pinned to a commit: {line.strip()}"


def test_the_release_carries_the_files_the_document_promises(doc):
    promised = table_first_column(section(doc, "assets"))
    workflow = EVIDENCE.read_text(encoding="utf-8")
    assert promised, "the document promises no release file"
    for name in promised:
        stem = name.split("<")[0].rstrip("-")
        assert stem in workflow, f"{name} is promised but sbom.yml never writes {stem}"
    assert "gh release upload" in workflow


def test_the_scan_is_not_presented_as_a_penetration_test(doc):
    """Question 6 asks for a penetration test. There has been none, and a scan of
    known CVEs is not one: the release note that travels with the files says so."""
    assert "non è un penetration test" in prose(doc)
    assert "not a penetration test" in EVIDENCE.read_text(encoding="utf-8")


# --- Questions 4 and 5: policy and pipeline ----------------------------------

SCANNERS = {
    "CodeQL": "codeql",
    "Bandit": "bandit",
    "Trivy": "trivy",
    "Snyk": "snyk",
    "Docker Scout": "docker-scout",
    "SonarCloud": "sonarcloud",
    "Security Posture": "security-posture",
    "mutmut": "mutation",
    # Not a security scanner: it measures the benchmarks. Listed because
    # question 5 asks what checks the code, and leaving a workflow out of the
    # answer would make the list look complete when it is not.
    "CodSpeed": "codspeed",
}


def test_every_scanner_named_has_its_workflow_and_none_is_left_out(doc):
    named = table_first_column(section(doc, "scanners"))
    assert named <= set(SCANNERS), f"unknown scanner names: {sorted(named - set(SCANNERS))}"
    for name in named:
        assert (WORKFLOWS / f"{SCANNERS[name]}.yml").is_file(), f"{name} has no workflow"
    present = {n for n, w in SCANNERS.items() if (WORKFLOWS / f"{w}.yml").is_file()}
    assert present <= named, f"workflows the document does not name: {sorted(present - named)}"


def test_security_md_answers_the_fourth_question():
    text = SECURITY.read_text(encoding="utf-8")
    for heading in (
        "## Reporting a vulnerability",
        "## How vulnerabilities are found",
        "## Response times",
        "## Customer notification",
        "## Rollback",
    ):
        assert heading in text, f"SECURITY.md has no {heading!r}"
    assert "single maintainer" in text


def test_the_document_and_security_md_give_the_same_contact(doc):
    contact = re.search(r"[\w.+-]+@maksimtech\.com", SECURITY.read_text(encoding="utf-8"))
    assert contact
    assert contact.group(0) in doc


def test_the_document_does_not_claim_a_second_review(doc):
    """The repository has one maintainer and its ruleset requires no approval
    (required_approving_review_count 0, read on 2026-10-11). Question 5 asks for a
    second reviewer; the honest answer is that there is none."""
    text = prose(doc)
    assert "manutentore unico" in text
    assert "nessuna revisione obbligatoria da parte di una seconda persona" in text


FORBIDDEN = [
    re.compile(r"NIS2[- ](?:ready|compliant|certified)", re.I),
    re.compile(r"certificat\w* NIS2", re.I),
    re.compile(r"nessun dato (?:è )?inviato a terzi", re.I),
    re.compile(r"no data (?:is )?sent to third parties", re.I),
    re.compile(r"ogni PR richiede", re.I),
]


@pytest.mark.parametrize("path", [DOC, SECURITY, README], ids=lambda p: p.name)
def test_no_claim_this_repository_cannot_back(path):
    text = path.read_text(encoding="utf-8")
    for pattern in FORBIDDEN:
        assert not pattern.search(text), f"{path.name} says {pattern.search(text).group(0)!r}"


# --- Question 1: the licence gate the document cites --------------------------


def test_the_licence_gate_matches_the_names_packages_actually_declare():
    """Without --partial-match, pip-licenses fails only on a licence string equal
    to "GPL", and no package declares that: they declare classifiers such as
    "GNU Lesser General Public License v2 or later (LGPLv2+)". Measured on
    2026-10-11 in a fresh venv with cookieradar and chardet 5.2.0 installed:
    `--fail-on="GPL;AGPL;LGPL"` exited 0, the same with --partial-match exited 1.
    cookieradar's own runtime dependencies, alone, exit 0 with the flag."""
    licences = (WORKFLOWS / "licenses.yml").read_text(encoding="utf-8")
    gate = next(line for line in licences.splitlines() if "--fail-on" in line)
    assert "--partial-match" in gate


# --- The lockfile the document points to ------------------------------------


def test_quality_keeps_the_lockfile_in_step_with_pyproject():
    """cookieradar had no uv.lock until 2026-10-11. A lockfile shown to a customer
    as the list of dependencies has to be the current one, so the check that keeps
    it current came with it."""
    assert (ROOT / "uv.lock").is_file()
    quality = (WORKFLOWS / "quality.yml").read_text(encoding="utf-8")
    assert re.search(r"uv(?:==[\d.]+)?\s.*lock --check|uv lock --check", quality)


def test_the_mutation_run_copies_what_these_tests_read():
    """mutmut copies the package and tests/ into mutants/ and runs the suite from
    there, adding only `also_copy` and a few files of its own accord: a test that
    reads a file left behind dies in the stats phase, before a single mutant is
    tried. These tests read docs/, which was not copied (found on apkradar).
    The paths are read from this file, so a new one cannot be forgotten."""
    import tomllib

    mutmut = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mutmut"]
    copied = set(mutmut.get("also_copy", [])) | {"tests", "test", "setup.cfg", "pyproject.toml", "uv.lock"}
    copied |= {path.split("/")[0] for path in mutmut.get("source_paths", [])}
    read = set(re.findall(r'ROOT / "([\w.-]+)', Path(__file__).read_text(encoding="utf-8")))
    assert "docs" in read, "the rule found none of the paths these tests read"
    assert read <= copied, f"read by these tests but not copied by mutmut: {sorted(read - copied)}"


def test_the_branch_rules_are_described_without_an_exception(doc):
    """On 2026-10-12 the ruleset on main lost the owner's bypass and requires a pull
    request for every change, the version bump included (release.sh opens one). The
    document says so with the date it was read, and keeps the earlier state as past."""
    text = prose(doc)
    assert "lette dalle impostazioni del repository il 2026-10-12" in text
    assert "Non prevedono eccezioni, nemmeno per l'account del manutentore" in text
    for stale in ("è configurato per poter scavalcare", "può scavalcare queste regole",
                  "può scavalcare le regole", "vanno direttamente su `main`",
                  "Non c'è una regola che imponga la pull request"):
        assert stale not in text, stale
