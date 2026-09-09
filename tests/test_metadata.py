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
        "THIRD_PARTY_LICENSES.md",
        "CHANGELOG.md",
        "MARKETING-LOG.txt",
        "llms.txt",
        "pyproject.toml",
        "ellmos-module.v2.json",
        ".github/workflows/ci.yml",
    ]
    for rel_path in required:
        target = ROOT / rel_path
        assert target.is_file(), f"Missing required file: {rel_path}"


def test_version_parity():
    """Verify version 0.9.1 parity across code, manifests, and documentation."""
    expected_version = "0.9.1"

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
        "https://img.shields.io/badge/pytest-184",
        "https://github.com/ellmos-ai/system-auditor/actions/workflows/ci.yml/badge.svg",
        "https://img.shields.io/badge/python-3.10",
        "https://img.shields.io/badge/ecosystem-ellmos--ai-purple",
        "https://img.shields.io/badge/umbrella-open--bricks-blueviolet",
        "https://img.shields.io/badge/version-0.9.1",
        "https://img.shields.io/badge/llms.txt-Discovery%20Context-informational",
        "https://img.shields.io/badge/security%20SLA-48h%20response%20%7C%205d%20triage-blue",
        "https://img.shields.io/badge/code%20style-ruff-000000.svg",
        "https://img.shields.io/badge/last%20checked-2026--09--09-informational",
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
        assert len(diagrams) >= 2, f"Expected at least 2 Mermaid diagrams in {filename}"

        flowchart_found = any("flowchart" in d or "graph" in d for d in diagrams)
        sequence_found = any("sequenceDiagram" in d for d in diagrams)

        assert flowchart_found, f"Flowchart/Graph diagram missing in {filename}"
        assert sequence_found, f"Sequence diagram missing in {filename}"

        for d in diagrams:
            # Check basic syntax balance
            assert d.count("(") == d.count(")"), f"Unbalanced parentheses in {filename} diagram"
            assert d.count("[") == d.count("]"), f"Unbalanced square brackets in {filename} diagram"


def test_quick_navigation_anchors():
    """Verify quick navigation links resolve to headers in READMEs."""
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

        for _text, anchor in anchor_links:
            assert anchor in normalized_headers or any(
                anchor in nh for nh in normalized_headers
            ), f"Anchor #{anchor} in {filename} does not match any header"


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
    assert (
        "Pfad B: Discoverability, Branding, Dual Mermaid & Governance Invariants Hardening"
        in content
    )
    assert "100% Local-First & Zero-Egress" in content
    assert "2026-09-09" in content


def test_pyproject_pytest_addopts_and_ecosystem_urls():
    """Verify pytest addopts and PEP 621 ecosystem URLs in pyproject.toml."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = pyproject.get("project", {}).get("urls", {})
    assert "Parent Organization" in urls
    assert urls["Parent Organization"] == "https://github.com/ellmos-ai"
    assert "Umbrella Ecosystem" in urls
    assert urls["Umbrella Ecosystem"] == "https://github.com/open-bricks"

    pytest_opts = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert pytest_opts.get("addopts") == "-v"


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
