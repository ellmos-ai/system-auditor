"""Finding the rules -- a tiered resolver, deliberately not a scanner.

An audit needs two things it cannot invent: the rule a finding violates
(evidence B) and the decision a recommendation rests on (evidence C).  On the
author's own system those live in known modules.  On somebody else's system they
live wherever that person put them -- or nowhere.

The temptation is to crawl the filesystem.  That is wrong twice over: it is slow
to the point of timing out on cloud-synchronised trees, and it turns a bounded
audit into an unbounded search.  So this resolver walks four rungs and stops at
the first that answers:

1. **configured** -- ``policy_stores[]`` / ``decision_stores[]`` from the config
2. **module probe** -- known modules, detected the same way the existing config
   detects USMC (``enabled_probe``), never assumed
3. **convention** -- a *bounded* set of file names at *bounded* depth, inside
   the assigned area only
4. **nothing** -- and then we say so: findings without B/C evidence are
   observations for the report, never tickets.  That is the role's own
   fail-safe, not a workaround.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TIER_CONFIGURED = "configured"
TIER_MODULE = "module-probe"
TIER_CONVENTION = "convention"
TIER_NONE = "none"

KIND_POLICY = "policy"
KIND_DECISION = "decision"

#: Bounded name set. Extending it is a deliberate act -- every entry costs
#: search time in every area, on every run.
CONVENTION_NAMES: dict[str, tuple[str, ...]] = {
    KIND_POLICY: (
        "CLAUDE.md",
        "AGENTS.md",
        "GEMINI.md",
        "POLICY.md",
        "POLICIES.md",
        "POLICY-REG.md",
        "MANIFEST.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "LOCK.permissions.json",
    ),
    KIND_DECISION: (
        "DECISIONS.md",
        "DECISION-LOG.md",
        "ADR.md",
        "TO-DECIDE-USER.txt",
        "DECIDED-AND-DONE.md",
        "CHANGELOG.md",
    ),
}

DEFAULT_MAX_DEPTH = 2

#: Never descend into these -- noise, and expensive on synchronised trees.
#: Matched as whole names, not as prefixes: ``startswith(".git")`` also skipped
#: ``.github``, which is exactly where a repository keeps its rules.
_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "_archive"})


@dataclass
class Source:
    name: str
    kind: str
    target: str
    tier: str
    available: bool = True
    detail: str = ""


@dataclass
class DiscoveryResult:
    policy: list[Source] = field(default_factory=list)
    decision: list[Source] = field(default_factory=list)
    probed: list[Source] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def tier_reached(self) -> str:
        tiers = [source.tier for source in self.policy + self.decision]
        for tier in (TIER_CONFIGURED, TIER_MODULE, TIER_CONVENTION):
            if tier in tiers:
                return tier
        return TIER_NONE

    @property
    def evidence_capable(self) -> bool:
        """Can this run produce ticket-worthy findings at all?

        Without a policy source there is no evidence B, and without evidence B
        a finding is an observation -- by the role's own definition.
        """
        return bool(self.policy)

    def summary(self) -> str:
        return (
            f"tier={self.tier_reached} policy={len(self.policy)} "
            f"decision={len(self.decision)} evidence_capable={self.evidence_capable}"
        )


def _run_probe(command: str, timeout: int = 20) -> bool:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _existing(target: str) -> bool:
    try:
        return Path(target).exists()
    except OSError:
        return False


def _from_configured(entries: list[dict], kind: str) -> list[Source]:
    sources: list[Source] = []
    for entry in entries or []:
        target = str(entry.get("target", ""))
        store_kind = str(entry.get("kind", "file"))
        available = _existing(target) if store_kind == "file" else True
        sources.append(
            Source(
                name=str(entry.get("name", target)),
                kind=kind,
                target=target,
                tier=TIER_CONFIGURED,
                available=available,
                detail="" if available else "configured but not present",
            )
        )
    return [source for source in sources if source.available]


def _from_modules(modules: list[dict], probe_runner) -> tuple[list[Source], list[Source]]:
    """Detect known modules. Absence is normal, never an error."""
    found: list[Source] = []
    probed: list[Source] = []
    for module in modules or []:
        probe = str(module.get("enabled_probe", ""))
        kind = str(module.get("provides", KIND_POLICY))
        name = str(module.get("name", "module"))
        available = probe_runner(probe) if probe else False
        record = Source(
            name=name,
            kind=kind,
            target=str(module.get("target", probe)),
            tier=TIER_MODULE,
            available=available,
            detail="probe ok" if available else "not installed",
        )
        probed.append(record)
        if available:
            found.append(record)
    return found, probed


def _from_convention(area_path: Path, kind: str, max_depth: int) -> list[Source]:
    """Bounded lookup: fixed names, limited depth, inside the area only."""
    root = Path(area_path)
    if not root.is_dir():
        return []
    names = CONVENTION_NAMES[kind]
    sources: list[Source] = []
    seen: set[Path] = set()

    def scan(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.is_file() and entry.name in names and entry not in seen:
                seen.add(entry)
                sources.append(
                    Source(
                        name=entry.name,
                        kind=kind,
                        target=str(entry),
                        tier=TIER_CONVENTION,
                        detail=f"found by convention at depth {depth}",
                    )
                )
            elif entry.is_dir() and entry.name not in _SKIP_DIRS:
                scan(entry, depth + 1)

    scan(root, 0)
    return sources


def discover(
    area_path: str | Path,
    policy_stores: list[dict] | None = None,
    decision_stores: list[dict] | None = None,
    known_modules: list[dict] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    probe_runner=None,
) -> DiscoveryResult:
    """Resolve policy and decision sources for one area."""
    runner = probe_runner or _run_probe
    result = DiscoveryResult()

    result.policy.extend(_from_configured(policy_stores or [], KIND_POLICY))
    result.decision.extend(_from_configured(decision_stores or [], KIND_DECISION))

    module_sources, probed = _from_modules(known_modules or [], runner)
    result.probed.extend(probed)
    for source in module_sources:
        bucket = result.policy if source.kind == KIND_POLICY else result.decision
        bucket.append(source)

    if not result.policy:
        result.policy.extend(_from_convention(Path(area_path), KIND_POLICY, max_depth))
    if not result.decision:
        result.decision.extend(_from_convention(Path(area_path), KIND_DECISION, max_depth))

    if not result.policy:
        result.notes.append(
            "no policy source found -- findings stay observations "
            "(no evidence B, therefore no ticket)"
        )
    if not result.decision:
        result.notes.append(
            "no decision source found -- recommendations carry no evidence C"
        )
    return result
