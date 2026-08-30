"""Automated metadata, documentation parity, and security contract test suite.

Ensures that READMEs, SECURITY.md, pyproject.toml, llms.txt, CI workflows, and source
invariants remain strictly synchronized and adhere to ecosystem standards.
"""

from __future__ import annotations

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
        "CHANGELOG.md",
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
        "https://img.shields.io/badge/pytest-",
        "https://github.com/ellmos-ai/system-auditor/actions/workflows/ci.yml/badge.svg",
        "https://img.shields.io/badge/python-3.10",
        "https://img.shields.io/badge/ecosystem-ellmos--ai-purple",
        "https://img.shields.io/badge/umbrella-open--bricks-blueviolet",
        "https://img.shields.io/badge/version-0.9.1",
        "https://img.shields.io/badge/llms.txt-Discovery%20Context-informational",
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
        "automation-master",
        "automizer-for-claude-desktop",
        "ProSync",
        "CleanMarkdown",
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
    assert "pytest" in ci_content
