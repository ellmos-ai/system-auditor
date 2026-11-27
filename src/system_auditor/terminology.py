"""Aggregated multi-repo terminology congruence audit hook (`system-auditor`).

Follows the core system-auditor principle: if ``doc_keeper.terminology`` is
installed in the active environment, it is used directly (``engine="doc-keeper"``);
otherwise a zero-dependency builtin implementation executes the exact same spec
contract (``engine="builtin"``).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_SCAN_EXTENSIONS: tuple[str, ...] = (
    ".astro",
    ".html",
    ".jsx",
    ".md",
    ".mdx",
    ".mjs",
    ".ts",
    ".tsx",
)

_DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".task-worktrees",
        ".venv",
        "__pycache__",
        "_archive",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

_DEFAULT_EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "CHANGELOG.md",
        "MARKETING-LOG.txt",
        "TERMINOLOGIE-RESSOURCEN-UND-AGENTEN.md",
        "terminology-congruence.v1.json",
    }
)

_LEGACY_DOM_TOKEN_RE = re.compile(
    r"""(?:id|for|name|data-[a-z0-9_-]+)\s*=\s*["'][^"']*["']|#[a-z][a-z0-9_-]*""",
    re.IGNORECASE,
)


class TerminologyAuditError(ValueError):
    """Raised when the terminology spec or target repositories cannot be read."""


@dataclass
class TerminologyAuditResult:
    """Aggregated multi-repo terminology congruence audit outcome."""

    spec_path: str
    spec_schema: str
    engine: str
    repos_scanned: int
    files_scanned: int
    total_violations: int
    total_legacy_wire_compat_hits: int
    violations_by_repo: dict[str, int] = field(default_factory=dict)
    violations_by_term: dict[str, int] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    cross_repo_findings: list[dict] = field(default_factory=list)
    repos: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.total_violations == 0

    def as_dict(self) -> dict:
        return {
            "domain": "terminology-congruence",
            "ok": self.ok,
            "engine": self.engine,
            "spec_path": self.spec_path,
            "spec_schema": self.spec_schema,
            "summary": {
                "repos_scanned": self.repos_scanned,
                "files_scanned": self.files_scanned,
                "total_violations": self.total_violations,
                "total_legacy_wire_compat_hits": self.total_legacy_wire_compat_hits,
                "violations_by_repo": self.violations_by_repo,
                "violations_by_term": self.violations_by_term,
            },
            "cross_repo_findings": self.cross_repo_findings,
            "findings": self.findings,
            "repos": [
                {
                    "repo_name": r["repo_name"],
                    "repo_path": r["repo_path"],
                    "ok": r["ok"],
                    "files_scanned": r["files_scanned"],
                    "violation_count": r["violation_count"],
                    "legacy_wire_compat_count": r["legacy_wire_compat_count"],
                    "canonical_terms_present": r["canonical_terms_present"],
                }
                for r in self.repos
            ],
        }


def _load_spec(spec_path: Path) -> dict:
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TerminologyAuditError(
            f"Terminology spec unreadable: {spec_path} ({exc.__class__.__name__})"
        ) from exc
    if not isinstance(raw, dict):
        raise TerminologyAuditError(f"Terminology spec root is not an object: {spec_path}")
    policy = raw.get("policy")
    concepts = raw.get("concepts")
    if not isinstance(policy, dict) or not isinstance(concepts, list) or not concepts:
        raise TerminologyAuditError(
            f"Terminology spec missing required policy/concepts fields: {spec_path}"
        )
    forbidden = policy.get("forbidden_in_new_ui_and_docs")
    if not isinstance(forbidden, list) or not all(
        isinstance(x, str) and x.strip() for x in forbidden
    ):
        raise TerminologyAuditError(
            f"Terminology spec policy.forbidden_in_new_ui_and_docs invalid: {spec_path}"
        )
    return raw


def _normalise_repos(repos: Sequence[Path | tuple[str, Path]]) -> list[tuple[str, Path]]:
    normalised: list[tuple[str, Path]] = []
    for item in repos:
        if isinstance(item, tuple):
            name, path = str(item[0]), Path(item[1]).resolve()
        else:
            path = Path(item).resolve()
            name = path.name
        if not path.is_dir():
            raise TerminologyAuditError(f"Repository directory does not exist: {path}")
        normalised.append((name, path))
    if not normalised:
        raise TerminologyAuditError("At least one repository is required for terminology audit")
    return normalised


def _builtin_audit(
    spec_path: Path,
    repos: list[tuple[str, Path]],
    *,
    include_tests: bool = False,
) -> dict:
    raw = _load_spec(spec_path)
    concepts = raw["concepts"]
    legacy_tokens: set[str] = set()
    canonical_terms: list[str] = []
    dep_map: dict[str, dict[str, str]] = {}

    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        cid = str(concept.get("id") or "")
        c_de = str(concept.get("canonical_de") or "")
        if c_de and c_de not in canonical_terms:
            canonical_terms.append(c_de)
        for token in concept.get("legacy_wire_compat") or []:
            if isinstance(token, str) and token.strip():
                legacy_tokens.add(token.strip())
        for dep in concept.get("deprecated_ui_terms") or []:
            if isinstance(dep, str) and dep.strip():
                dep_map.setdefault(dep.strip().lower(), {"concept_id": cid, "canonical_de": c_de})

    compiled = []
    for term in raw["policy"]["forbidden_in_new_ui_and_docs"]:
        clean = term.strip()
        meta = dep_map.get(clean.lower())
        if meta is None:
            for concept in concepts:
                if not isinstance(concept, dict):
                    continue
                deps = [str(d).lower() for d in (concept.get("deprecated_ui_terms") or [])]
                if any(d and d in clean.lower() for d in deps):
                    meta = {
                        "concept_id": str(concept.get("id") or ""),
                        "canonical_de": str(concept.get("canonical_de") or ""),
                    }
                    break
        compiled.append(
            (
                clean,
                meta or {"concept_id": "unmapped", "canonical_de": ""},
                re.compile(rf"(?<!\w){re.escape(clean)}(?!\w)", re.IGNORECASE),
            )
        )

    sorted_legacy = sorted(legacy_tokens, key=len, reverse=True)
    ex_dirs = set(_DEFAULT_EXCLUDED_DIRS)
    if not include_tests:
        ex_dirs.update({"tests", "test", "__tests__"})

    repo_reports: list[dict] = []
    violations_by_repo: dict[str, int] = {}
    violations_by_term: dict[str, int] = {}
    total_files = 0
    total_violations = 0
    total_legacy = 0

    for repo_name, root in repos:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = sorted(d for d in dirnames if d not in ex_dirs)
            base = Path(dirpath)
            for fname in sorted(filenames):
                if fname in _DEFAULT_EXCLUDED_FILES:
                    continue
                path = base / fname
                if path.suffix.lower() not in _DEFAULT_SCAN_EXTENSIONS:
                    continue
                if not include_tests and (
                    fname.startswith("test_")
                    or fname.endswith((".test.mjs", ".test.js", ".test.ts", ".spec.ts", ".spec.js"))
                ):
                    continue
                files.append(path)

        violations: list[dict] = []
        legacy_count = 0
        canonical_present: set[str] = set()

        for fpath in files:
            rel_str = fpath.relative_to(root).as_posix()
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for c_term in canonical_terms:
                if c_term in text:
                    canonical_present.add(c_term)

            for line_no, raw_line in enumerate(text.splitlines(), start=1):
                cleaned = raw_line
                had_legacy = False
                for token in sorted_legacy:
                    if token in cleaned:
                        had_legacy = True
                        cleaned = cleaned.replace(token, " ")
                if had_legacy:
                    legacy_count += 1
                cleaned = _LEGACY_DOM_TOKEN_RE.sub(" ", cleaned)
                for term, meta, pat in compiled:
                    if pat.search(cleaned):
                        violations.append(
                            {
                                "rule": "TERMINOLOGY-FORBIDDEN-UI-OR-DOC",
                                "severity": "error",
                                "repo": repo_name,
                                "term": term,
                                "concept_id": meta["concept_id"],
                                "canonical_de": meta["canonical_de"],
                                "file": rel_str,
                                "line": line_no,
                                "excerpt": raw_line.strip()[:160],
                            }
                        )
                        violations_by_term[term] = violations_by_term.get(term, 0) + 1

        total_files += len(files)
        total_violations += len(violations)
        total_legacy += legacy_count
        violations_by_repo[repo_name] = len(violations)
        repo_reports.append(
            {
                "repo_name": repo_name,
                "repo_path": str(root),
                "ok": len(violations) == 0,
                "files_scanned": len(files),
                "violation_count": len(violations),
                "legacy_wire_compat_count": legacy_count,
                "canonical_terms_present": sorted(canonical_present),
                "violations": violations,
            }
        )

    cross_repo: list[dict] = []
    if len(repo_reports) > 1:
        adopters: dict[str, list[str]] = {}
        for rep in repo_reports:
            for c_term in rep["canonical_terms_present"]:
                adopters.setdefault(c_term, []).append(rep["repo_name"])
        for rep in repo_reports:
            if not rep["violations"]:
                continue
            by_canonical: dict[str, list[str]] = {}
            for v in rep["violations"]:
                if v["canonical_de"]:
                    by_canonical.setdefault(v["canonical_de"], []).append(v["term"])
            for c_de, used in sorted(by_canonical.items()):
                peers = [r for r in adopters.get(c_de, []) if r != rep["repo_name"]]
                if peers:
                    cross_repo.append(
                        {
                            "rule": "TERMINOLOGY-CROSS-REPO-ASYMMETRY",
                            "repo": rep["repo_name"],
                            "canonical_de": c_de,
                            "deprecated_terms_found": sorted(set(used)),
                            "aligned_peer_repos": sorted(peers),
                        }
                    )

    return {
        "spec_schema": str(raw.get("schema") or "unknown"),
        "spec_path": str(spec_path.resolve()),
        "summary": {
            "repos_scanned": len(repo_reports),
            "files_scanned": total_files,
            "total_violations": total_violations,
            "total_legacy_wire_compat_hits": total_legacy,
            "violations_by_repo": violations_by_repo,
            "violations_by_term": dict(sorted(violations_by_term.items())),
        },
        "repos": repo_reports,
        "cross_repo_findings": cross_repo,
    }


def audit_terminology(
    spec_path: Path,
    repos: Sequence[Path | tuple[str, Path]],
    *,
    include_tests: bool = False,
    prefer_doc_keeper: bool = True,
) -> TerminologyAuditResult:
    """Run an aggregated multi-repo terminology congruence audit."""
    resolved_spec = Path(spec_path).resolve()
    normalised = _normalise_repos(repos)

    engine = "builtin"
    raw_report: dict | None = None
    if prefer_doc_keeper:
        try:
            from doc_keeper.terminology import (  # type: ignore[import-not-found]
                TerminologySpecError,
                audit_terminology_cross_repo,
            )
        except ImportError:
            raw_report = None
        else:
            try:
                raw_report = audit_terminology_cross_repo(
                    dict(normalised),
                    resolved_spec,
                    include_tests=include_tests,
                )
                engine = "doc-keeper"
            except TerminologySpecError as exc:
                raise TerminologyAuditError(str(exc)) from exc

    if raw_report is None:
        raw_report = _builtin_audit(resolved_spec, normalised, include_tests=include_tests)

    flat_findings: list[dict] = []
    for rep in raw_report["repos"]:
        rname = rep["repo_name"]
        for v in rep.get("violations") or []:
            item = dict(v)
            item.setdefault("repo", rname)
            flat_findings.append(item)

    summary = raw_report["summary"]
    return TerminologyAuditResult(
        spec_path=raw_report.get("spec_path", str(resolved_spec)),
        spec_schema=raw_report.get("spec_schema", "unknown"),
        engine=engine,
        repos_scanned=int(summary["repos_scanned"]),
        files_scanned=int(summary["files_scanned"]),
        total_violations=int(summary["total_violations"]),
        total_legacy_wire_compat_hits=int(summary["total_legacy_wire_compat_hits"]),
        violations_by_repo=dict(summary["violations_by_repo"]),
        violations_by_term=dict(summary["violations_by_term"]),
        findings=flat_findings,
        cross_repo_findings=list(raw_report.get("cross_repo_findings") or []),
        repos=list(raw_report["repos"]),
    )


def resolve_repo_targets(
    explicit_repos: Iterable[str],
    *,
    repos_root: str | None = None,
    repo_names_csv: str | None = None,
) -> list[Path]:
    """Resolve CLI ``--repo`` and ``--repos-root``/``--repos`` arguments into unique paths."""
    targets: list[Path] = []
    seen: set[Path] = set()
    for raw in explicit_repos:
        p = Path(raw).resolve()
        if p not in seen:
            seen.add(p)
            targets.append(p)
    if repos_root and repo_names_csv:
        root = Path(repos_root).resolve()
        for name in (part.strip() for part in repo_names_csv.split(",") if part.strip()):
            p = (root / name).resolve()
            if p not in seen:
                seen.add(p)
                targets.append(p)
    return targets
