"""Automated metadata, documentation parity, and security contract test suite.

Ensures that READMEs, SECURITY.md, pyproject.toml, llms.txt, CI workflows, and source
invariants remain strictly synchronized and adhere to ecosystem standards.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

# tomllib ist erst ab 3.11 in der stdlib, pyproject sagt requires-python >=3.10
# und die CI-Matrix testet 3.10 -- dort brach die Sammlung des ganzen Moduls ab.
# Ueberspringen statt tomli als Testabhaengigkeit aufzunehmen: die geprueften
# Invarianten sind repoweit, nicht versionsabhaengig, und werden auf 3.11-3.13
# weiterhin gepruft. Ein Skip meldet sich, ein ImportError toetet den Lauf.
tomllib = pytest.importorskip("tomllib", reason="stdlib erst ab Python 3.11")

ROOT = Path(__file__).resolve().parent.parent


def test_required_root_documents_exist():
    """Verify that all standard governance and documentation files are present."""
    required = [
        "README.md",
        "README_de.md",
        "SECURITY.md",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_LICENSES.md",
        "CHANGELOG.md",
        "MARKETING-LOG.txt",
        "llms.txt",
        "pyproject.toml",
        "ellmos-module.v2.json",
        ".github/workflows/ci.yml",
        ".github/workflows/welcome.yml",
    ]
    for rel_path in required:
        target = ROOT / rel_path
        assert target.is_file(), f"Missing required file: {rel_path}"


def test_version_parity():
    """Verify version 0.9.2 parity across code, manifests, and documentation."""
    expected_version = "0.9.2"

    # 1. Python package __version__
    import system_auditor

    assert system_auditor.__version__ == expected_version

    # 2. pyproject.toml
    pyproject_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject_data["project"]["version"] == expected_version

    # 3. llms.txt
    llms_content = (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert f"Version: {expected_version}" in llms_content

    # 4. CHANGELOG.md
    changelog_content = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{expected_version}]" in changelog_content


def test_readme_badges_parity():
    """Verify Shields.io badges in both English and German READMEs."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    expected_badges = [
        "https://img.shields.io/badge/pytest-196",
        "https://github.com/ellmos-ai/system-auditor/actions/workflows/ci.yml/badge.svg",
        "https://img.shields.io/badge/python-3.10",
        "https://img.shields.io/badge/ecosystem-ellmos--ai-purple",
        "https://img.shields.io/badge/umbrella-open--bricks-blueviolet",
        "https://img.shields.io/badge/version-0.9.2",
        "https://img.shields.io/badge/llms.txt-Discovery%20Context-informational",
        "https://img.shields.io/badge/security%20SLA-48h%20response%20%7C%205d%20triage-blue",
        "https://img.shields.io/badge/code%20style-ruff-000000.svg",
        "https://img.shields.io/badge/attribution-NOTICE-blue.svg",
        "https://img.shields.io/badge/last%20checked-2026--09--26-informational",
    ]

    for badge in expected_badges:
        assert badge in readme_en, f"Missing badge in README.md: {badge}"
        assert badge in readme_de, f"Missing badge in README_de.md: {badge}"

    # License badge (EN: license-MIT, DE: lizenz-MIT or license-MIT)
    assert "license-MIT" in readme_en
    assert "license-MIT" in readme_de or "lizenz-MIT" in readme_de


def test_mermaid_diagrams_syntax():
    """Verify Mermaid diagrams in both READMEs are present and well-formed."""
    for filename in ["README.md", "README_de.md"]:
        content = (ROOT / filename).read_text(encoding="utf-8")
        diagrams = re.findall(r"```mermaid\n(.*?)```", content, re.DOTALL)
        assert len(diagrams) >= 3, f"Expected at least 3 Mermaid diagrams in {filename}"

        flowchart_found = any("flowchart" in d or "graph" in d for d in diagrams)
        sequence_found = any("sequenceDiagram" in d for d in diagrams)

        assert flowchart_found, f"Flowchart/Graph diagram missing in {filename}"
        assert sequence_found, f"Sequence diagram missing in {filename}"
        assert sum(1 for d in diagrams if "sequenceDiagram" in d) >= 2, (
            f"Expected at least 2 sequence diagrams in {filename}"
        )

        for d in diagrams:
            # Check basic syntax balance
            assert d.count("(") == d.count(")"), f"Unbalanced parentheses in {filename} diagram"
            assert d.count("[") == d.count("]"), f"Unbalanced square brackets in {filename} diagram"


def test_three_stages_convergence_diagram_parity():
    """Verify the 3-stage convergence sequence diagram in both READMEs."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    assert 'participant Explorer as "system-explorer (Map)"' in readme_en
    assert 'participant Auditor as "system-auditor (Verdict)"' in readme_en
    assert 'participant Sink as "Handover Sink (Measure)"' in readme_en
    assert 'participant Gov as "Governance & Maintainer (Decision)"' in readme_en

    assert 'participant Explorer as "system-explorer (Karte)"' in readme_de
    assert 'participant Auditor as "system-auditor (Urteil)"' in readme_de
    assert 'participant Sink as "Handover-Senke (Maßnahme)"' in readme_de
    assert 'participant Gov as "Governance & Maintainer (Entscheidung)"' in readme_de


def test_quick_navigation_anchors():
    """Verify quick navigation links resolve to headers or HTML anchors in READMEs."""
    for filename in ["README.md", "README_de.md"]:
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert "Quick Navigation" in content or "Schnellnavigation" in content

        # Extract markdown anchor links [Text](#anchor)
        anchor_links = re.findall(r"\[([^\]]+)\]\(#([^\)]+)\)", content)
        assert len(anchor_links) >= 8, f"Expected at least 8 quick nav links in {filename}"

        # Extract headers ## Header Title
        headers = re.findall(r"^#{2,4}\s+(.+)$", content, re.MULTILINE)
        normalized_headers = [
            re.sub(r"[^\w\s-]", "", h).strip().lower().replace(" ", "-") for h in headers
        ]
        html_anchors = set(re.findall(r'<a\s+id="([^"]+)">', content))

        for _text, anchor in anchor_links:
            assert (
                anchor in normalized_headers
                or anchor in html_anchors
                or any(anchor in nh for nh in normalized_headers)
            ), f"Anchor #{anchor} in {filename} does not match any header or HTML anchor"


def test_security_policy_and_invariants():
    """Verify SECURITY.md bilingual structure, supported versions, and maintainer contacts."""
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "## English" in security
    assert "## Deutsch" in security
    assert "`0.9.x`" in security
    assert "security@ellmos.ai" in security
    assert "security@open-bricks.org" in security
    assert "lukas@open-bricks.org" in security
    assert "support@lukasgeiger.com" in security
    assert "github.com/ellmos-ai/system-auditor/security/advisories" in security
    assert "Zero-Egress" in security
    assert "Local-First" in security


def test_sibling_ecosystem_and_urls():
    """Verify sister tools and open-bricks umbrella linking in documentation."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    sibling_repos = [
        "system-explorer",
        "ellmos-controlcenter-mcp",
        "ellmos-delegation-authority",
        "sqlite-transit-sync",
        "ellmos-voice-io",
        "memoryhooker-provenance",
        "workflowhooker-provenance",
        "automation-master",
        "automizer-for-claude-desktop",
        "WikiStub-Seed",
        "ProSync",
        "CleanMarkdown",
        "PrivacyMailDesk",
        "prompt-archaeology-casestudy2",
        "open-bricks",
    ]

    for repo in sibling_repos:
        assert repo in readme_en, f"Sibling repo '{repo}' missing in README.md"
        assert repo in readme_de, f"Sibling repo '{repo}' missing in README_de.md"


def test_pyproject_pep621_classifiers_and_urls():
    """Verify PEP 621 classifiers, zero dependencies, and complete project.urls."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})

    assert project.get("dependencies") == []

    urls = project.get("urls", {})
    required_urls = [
        "Homepage",
        "Documentation",
        "Repository",
        "Issues",
        "Changelog",
        "Security",
        "Umbrella",
    ]
    for key in required_urls:
        assert key in urls, f"Missing project URL key: {key}"
        assert urls[key].startswith("https://"), f"Invalid URL for {key}: {urls[key]}"

    classifiers = project.get("classifiers", [])
    assert any("OS Independent" in c for c in classifiers)
    assert any("Microsoft :: Windows" in c for c in classifiers)
    assert any("POSIX :: Linux" in c for c in classifiers)
    assert any("MacOS" in c for c in classifiers)
    assert any("Quality Assurance" in c for c in classifiers)
    assert any("Security" in c for c in classifiers)


def test_offline_and_zero_egress_invariants():
    """Scan all source code files to verify 0 network/telemetry module imports."""
    forbidden_modules = [
        "urllib.request",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "telemetry",
        "ftplib",
        "smtplib",
    ]

    src_dir = ROOT / "src" / "system_auditor"
    assert src_dir.is_dir()

    py_files = list(src_dir.glob("**/*.py"))
    assert len(py_files) >= 8

    for py_file in py_files:
        code = py_file.read_text(encoding="utf-8")
        for mod in forbidden_modules:
            pattern = rf"^\s*(import\s+{re.escape(mod)}|from\s+{re.escape(mod)}\s+import)"
            assert not re.search(pattern, code, re.MULTILINE), (
                f"Forbidden network module '{mod}' found in {py_file.name}"
            )


def test_ci_workflow_integrity():
    """Verify GitHub Actions CI matrix coverage and concurrency guardrails."""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_file.is_file()

    ci_content = ci_file.read_text(encoding="utf-8")
    assert "cancel-in-progress: true" in ci_content
    assert "ubuntu-latest" in ci_content
    assert "windows-latest" in ci_content
    assert "macos-latest" in ci_content
    assert "3.10" in ci_content
    assert "3.11" in ci_content
    assert "3.12" in ci_content
    assert "3.13" in ci_content
    assert "ruff check" in ci_content
    assert "compileall" in ci_content
    assert "pytest" in ci_content


def test_cli_subcommands_registration():
    """Verify that all standard subcommands are registered in CLI argument parser."""
    from system_auditor.cli import build_parser

    parser = build_parser()
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    subparsers = subparsers_actions[0]
    expected_commands = {
        "config",
        "time-token",
        "next-domain",
        "meta-plan",
        "reports",
        "stale",
        "discover",
        "pages-drift",
    }
    for cmd in expected_commands:
        assert cmd in subparsers.choices, f"Subcommand '{cmd}' not found in CLI parser"


def test_pages_drift_exports_and_contract():
    """Verify deterministic pages-drift domain exports and invariants."""
    import system_auditor

    assert hasattr(system_auditor, "audit_pages_drift")
    assert hasattr(system_auditor, "PagesDriftResult")
    assert hasattr(system_auditor, "PagesDriftError")
    assert "audit_pages_drift" in system_auditor.__all__
    assert "PagesDriftResult" in system_auditor.__all__
    assert "PagesDriftError" in system_auditor.__all__


def test_governance_invariants_10_points_matrix():
    """Verify that both English and German READMEs contain all 10 invariants."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    en_keys = [
        "1. 100% Local-First & Zero-Egress",
        "2. Unprivileged Non-Elevation",
        "3. Deterministic Classification",
        "4. Identifiability Guard",
        "5. Write-Guard Race Protection",
        "6. Discrete Window Tokens",
        "7. One Current Answer Per Window",
        "8. Coverage Transparency Floor",
        "9. Multi-Host & Lock Hardening",
        "10. 48h Security & 5-Day Triage SLA",
    ]
    for key in en_keys:
        assert key in readme_en, f"Invariant '{key}' missing in README.md"

    de_keys = [
        "1. 100% Local-First & Zero-Egress",
        "2. Unprivilegierte Non-Elevation",
        "3. Deterministische Klassifikation",
        "4. Identifizierbarkeits-Schutz",
        "5. Schreibsicherung (Write-Guard)",
        "6. Diskrete Zeitfenster-Token",
        "7. Eine gültige Antwort je Fenster",
        "8. Ehrliche Nicht-Belegbarkeit",
        "9. Multi-Host- & Lock-Härtung",
        "10. 48h Sicherheits- & 5-Tage-Triage-SLA",
    ]
    for key in de_keys:
        assert key in readme_de, f"Invariant '{key}' missing in README_de.md"


def test_security_policy_triage_and_open_bricks_contact():
    """Verify triage SLA commitments and open-bricks security contacts in SECURITY.md."""
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "security@open-bricks.org" in security
    assert "5 business days" in security
    assert "5 Werktagen" in security
    assert "48 hours" in security
    assert "48 Stunden" in security


def test_ci_bytecode_compilation_gate():
    """Verify that CI workflow enforces bytecode compilation gate before testing."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m compileall -q src tests" in ci


def test_gitignore_hygiene_patterns():
    """Verify that .gitignore guards against multi-host conflict files, lock tokens, and caches."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*-conflict-*" in gitignore
    assert "*.sync-temp-*" in gitignore
    assert "LOCK.*" in gitignore
    assert ".pytest_cache" in gitignore
    assert ".ruff_cache" in gitignore


def test_local_marketing_log_present():
    """Verify presence and structure of local MARKETING-LOG.txt."""
    log_file = ROOT / "MARKETING-LOG.txt"
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "Pfad A: Repository-Hygiene" in content
    assert "2026-09-13" in content
    assert "2026-09-16" in content
    assert "2026-09-26" in content
    assert "Pfad B: Discoverability" in content
    assert (
        "Pfad B: Discoverability, Branding, Dual Mermaid & Governance Invariants Hardening"
        in content
    )
    assert "100% Local-First & Zero-Egress" in content


def test_pyproject_pytest_addopts_and_ecosystem_urls():
    """Verify pytest addopts and PEP 621 ecosystem URLs in pyproject.toml."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = pyproject.get("project", {}).get("urls", {})
    assert "Parent Organization" in urls
    assert urls["Parent Organization"] == "https://github.com/ellmos-ai"
    assert "Umbrella Ecosystem" in urls
    assert urls["Umbrella Ecosystem"] == "https://github.com/open-bricks"

    pytest_opts = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert "-v" in pytest_opts.get("addopts", "")
    assert "--basetemp=.pytest_temp" in pytest_opts.get("addopts", "")


def test_third_party_licenses_inventory_and_zero_dependencies():
    """Verify THIRD_PARTY_LICENSES.md presence, zero runtime dependencies, and license texts."""
    target = ROOT / "THIRD_PARTY_LICENSES.md"
    assert target.is_file(), "THIRD_PARTY_LICENSES.md is missing"

    content = target.read_text(encoding="utf-8")
    assert "Zero-Runtime-Dependency Guarantee" in content
    assert "dependencies = []" in content
    assert "pytest" in content
    assert "ruff" in content
    assert "setuptools" in content
    assert "build" in content
    assert "MIT License" in content
    assert "Apache License 2.0" in content
    assert "Python Software Foundation License" in content


def test_pep639_license_files_metadata():
    """Verify PEP 639 license-files declaration and optional dev dependencies in pyproject.toml."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    license_files = pyproject.get("project", {}).get("license-files", [])
    assert "LICENSE" in license_files
    assert "THIRD_PARTY_LICENSES.md" in license_files

    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    assert "dev" in optional_deps
    assert any("pytest" in d for d in optional_deps["dev"])


def test_gitignore_secret_and_credential_patterns():
    """Verify that .gitignore excludes secrets, private keys, tokens, certs, and merge residue."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.pem" in gitignore
    assert "*.key" in gitignore
    assert "*.token" in gitignore
    assert "*.p12" in gitignore
    assert ".npmrc" in gitignore
    assert ".pypirc" in gitignore
    assert "*.orig" in gitignore


def test_ci_workflow_timeouts():
    """Verify explicit timeout-minutes across all CI and automation workflows."""
    ci_yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: 15" in ci_yml, "ci.yml test job must have timeout-minutes: 15"

    stale_yml = (ROOT / ".github" / "workflows" / "stale.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: 10" in stale_yml, "stale.yml must have timeout-minutes: 10"


def test_stale_workflow_present_and_valid():
    """Verify presence, schedule, and permissions of stale.yml workflow."""
    stale_file = ROOT / ".github" / "workflows" / "stale.yml"
    assert stale_file.is_file(), "stale.yml must exist"
    content = stale_file.read_text(encoding="utf-8")
    assert "actions/stale@v9" in content
    assert "cron: '30 1 * * *'" in content
    assert "issues: write" in content
    assert "pull-requests: write" in content
    assert "operations-per-run: 30" in content


def test_gitignore_onedrive_conflict_and_cache_patterns():
    """Verify that .gitignore excludes OneDrive conflict copies and caches."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "* (kopie)*" in gitignore
    assert "* (copy)*" in gitignore
    assert "*-ASUS.*" in gitignore
    assert "*-LAPTOP.*" in gitignore
    assert "*-Mac Studio.*" in gitignore
    assert ".mypy_cache/" in gitignore
    assert ".tox/" in gitignore
    assert ".turbo/" in gitignore
    assert "!package-lock.json" in gitignore


def test_changelog_release_entry_and_date():
    """Verify that CHANGELOG.md contains the current release entry and standard headings."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [0.9.2] - 2026-09-13" in changelog
    assert "### Hinzugefuegt" in changelog
    assert "### Geaendert" in changelog
    assert "Pfad A Repository-Hygiene" in changelog


def test_notice_file_and_attribution():
    """Verify canonical NOTICE file presence and formal attribution contents."""
    notice_file = ROOT / "NOTICE"
    assert notice_file.is_file(), "NOTICE file must exist in repo root"

    content = notice_file.read_text(encoding="utf-8")
    assert "system-auditor" in content
    assert "Lukas Geiger" in content
    assert "ellmos-ai" in content
    assert "open-bricks" in content
    assert "MIT License" in content
    assert "THIRD_PARTY_LICENSES.md" in content


def test_welcome_workflow_concurrency_and_timeout():
    """Verify welcome.yml workflow configuration, concurrency guard and timeout."""
    welcome_file = ROOT / ".github" / "workflows" / "welcome.yml"
    assert welcome_file.is_file(), "welcome.yml must exist"

    content = welcome_file.read_text(encoding="utf-8")
    assert "actions/first-interaction@v3" in content
    assert "timeout-minutes: 5" in content
    assert "cancel-in-progress: true" in content
    assert "issues: write" in content
    assert "pull-requests: write" in content


def test_ci_least_privilege_permissions():
    """Verify top-level least-privilege permissions in CI workflow."""
    ci_file = ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    assert "permissions:" in content
    assert "contents: read" in content


def test_lock_defense_patterns_in_gitignore():
    """Verify that .gitignore guards against canonical locks, host tokens, and cloud sync conflicts.
    """
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "LOCK.user.*" in gitignore
    assert "LOCK.until.*" in gitignore
    assert "LOCK.condition.*" in gitignore
    assert ".automation-lock" in gitignore
    assert "*conflicted copy*" in gitignore
    assert "*-WORKSTATION-LG*" in gitignore
    assert "*-ASUS-GEI*" in gitignore
    assert ".hypothesis/" in gitignore
    assert ".nyc_output/" in gitignore
    assert "uv.lock" in gitignore


def test_pep621_notice_url_and_license_files():
    """Verify Notice URL, PEP 639 license-files, keywords, and pytest options in pyproject.toml."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})

    license_files = project.get("license-files", [])
    assert "NOTICE" in license_files
    assert "LICENSE" in license_files
    assert "THIRD_PARTY_LICENSES.md" in license_files

    urls = project.get("urls", {})
    assert "Notice" in urls
    assert urls["Notice"].startswith("https://")
    assert "NOTICE" in urls["Notice"]

    keywords = project.get("keywords", [])
    assert len(keywords) >= 20, f"Expected at least 20 keywords, got {len(keywords)}"

    pytest_opts = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert pytest_opts.get("minversion") == "7.0"
    assert "norecursedirs" in pytest_opts


def test_18_points_bilateral_navigation_anchors_parity():
    """Verify that both README.md and README_de.md contain all 18 dual reciprocal anchors."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    for i in range(1, 19):
        anchor_id = f"sec-{i:02d}"
        assert f'<a id="{anchor_id}"></a>' in readme_en, (
            f"Anchor {anchor_id} missing in README.md"
        )
        assert f'<a id="{anchor_id}"></a>' in readme_de, (
            f"Anchor {anchor_id} missing in README_de.md"
        )

        header_prefix = f"### {i}."
        assert header_prefix in readme_en, (
            f"Section header '{header_prefix}' missing in README.md"
        )
        assert header_prefix in readme_de, (
            f"Section header '{header_prefix}' missing in README_de.md"
        )


def test_target_personas_and_comparative_matrix_parity():
    """Verify presence of target personas and alternatives comparison matrix in both READMEs."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    assert "Target Personas & Discoverability" in readme_en
    assert "Multi-Agent Fleet Operators" in readme_en
    assert "Comparative Matrix vs. Alternatives" in readme_en
    assert "osquery" in readme_en
    assert "Lynis" in readme_en
    assert "Chef InSpec" in readme_en
    assert "OpenSCAP" in readme_en

    assert "Zielgruppen & Discoverability" in readme_de
    assert "Multi-Agenten-Flottenbetreiber" in readme_de
    assert "Vergleichsmatrix mit Alternativen" in readme_de
    assert "osquery" in readme_de
    assert "Lynis" in readme_de
    assert "Chef InSpec" in readme_de
    assert "OpenSCAP" in readme_de


def test_level_1_sbom_cross_reference_matrix_in_licenses():
    """Verify Level 1 SBOM invariant cross-reference table and re-audit recency."""
    licenses = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert "Level 1 SBOM & Governance Invariant Cross-Reference Matrix" in licenses
    assert "2026-09-26 (Pfad B Re-Audit)" in licenses
    assert "RunAsInvoker" in licenses
    assert "[NOTICE](NOTICE)" in licenses

    invariants = [
        "INV-LOCAL-01",
        "INV-UNPRIV-02",
        "INV-DETERM-03",
        "INV-IDENT-04",
        "INV-RACE-05",
        "INV-WINDOW-06",
        "INV-SINGLE-07",
        "INV-COVER-08",
        "INV-LOCK-09",
        "INV-SLA-10",
    ]
    for inv in invariants:
        assert inv in licenses, f"Invariant {inv} missing in THIRD_PARTY_LICENSES.md"
