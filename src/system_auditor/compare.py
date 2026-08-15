"""Cross-system classification -- the core of a meta audit.

N systems auditing the same domain do **not** produce the same result, and that
is the point rather than a defect.  Worked example, measured 2026-08-15:

    Finding T-20260815-08 -- "Gardener governance hardcodes the laptop home path"
    (``AGENTS.md`` points at ``C:\\Users\\User\\...``).

On WORKSTATION-LG this is a real finding: the path does not exist there.  On the
laptop the very same line is *correct* and produces no finding at all.  A single
system can only ever see one half of that.

Comparing the valid single audits of a domain yields a classification no single
run can produce:

================  ====================================================
class             meaning
================  ====================================================
``systemwide``    every participant found it -> genuine system defect
``host_specific`` some found it, others checked and did not
``inverse``       found on one, explicitly confirmed as fine on another
                  -> host dependency, typically a hardcoded path
``divergent``     same locator, *different* rules broken -> differing
                  sync state or differing interpretation
``unverifiable``  at least one participant never looked there, and none
                  contradicts -> no statement possible, and we say so
================  ====================================================

``unverifiable`` is the honest rung.  Without it every gap in a participant's
coverage would silently masquerade as a real difference between systems.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .report import ReportHeader

SYSTEMWIDE = "systemwide"
HOST_SPECIFIC = "host_specific"
INVERSE = "inverse"
DIVERGENT = "divergent"
UNVERIFIABLE = "unverifiable"

CLASS_ORDER = (SYSTEMWIDE, HOST_SPECIFIC, INVERSE, DIVERGENT, UNVERIFIABLE)

#: Home directories differ per host (``C:\\Users\\lukas`` vs ``C:\\Users\\User``).
#: Without folding them to a placeholder, no locator would ever match its
#: counterpart and every finding would look host-specific.
_HOME_PATTERNS = (
    re.compile(r"^[a-z]:[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+home[\\/]+[^\\/]+", re.IGNORECASE),
)


def normalize_locator(raw: str) -> str:
    """Host-neutral, comparable form of a path-ish locator."""
    text = (raw or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    for pattern in _HOME_PATTERNS:
        if pattern.match(text):
            text = pattern.sub("<HOME>", text, count=1)
            break
    return text.rstrip("/").lower()


@dataclass
class Finding:
    """One audited defect. ``rule`` carries evidence B, ``locator`` evidence A."""

    locator: str
    rule: str
    title: str = ""
    host: str = ""
    detail: str = ""
    key: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            self.key = f"{self.rule.strip().lower()}@{normalize_locator(self.locator)}"

    @property
    def norm_locator(self) -> str:
        return normalize_locator(self.locator)


@dataclass
class AuditRun:
    """One system's single audit of one domain."""

    header: ReportHeader
    findings: list[Finding] = field(default_factory=list)

    @property
    def host(self) -> str:
        return self.header.host

    def covers(self, locator: str) -> bool:
        target = normalize_locator(locator)
        return any(
            target.startswith(normalize_locator(prefix))
            for prefix in self.header.coverage
        )

    def declares_clean(self, locator: str) -> bool:
        target = normalize_locator(locator)
        return any(target == normalize_locator(entry) for entry in self.header.clean)


@dataclass
class Comparability:
    ok: bool
    blockers: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.ok:
            return "not comparable: " + "; ".join(self.blockers)
        if self.caveats:
            return "comparable with caveats: " + "; ".join(self.caveats)
        return "comparable"


@dataclass
class MetaFinding:
    finding: Finding
    classification: str
    present_on: list[str] = field(default_factory=list)
    absent_on: list[str] = field(default_factory=list)
    clean_on: list[str] = field(default_factory=list)
    unknown_on: list[str] = field(default_factory=list)
    divergent_rules: dict[str, str] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class MetaResult:
    comparability: Comparability
    participants: list[str] = field(default_factory=list)
    items: list[MetaFinding] = field(default_factory=list)

    @property
    def level(self) -> int:
        """Meta level = number of participating systems (meta-2, meta-3, ...)."""
        return len(self.participants)

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for item in self.items:
            tally[item.classification] = tally.get(item.classification, 0) + 1
        return tally

    def of_class(self, classification: str) -> list[MetaFinding]:
        return [item for item in self.items if item.classification == classification]


def check_comparability(runs: list[AuditRun]) -> Comparability:
    """Gate before comparing. Comparing incomparable runs invents findings."""
    blockers: list[str] = []
    caveats: list[str] = []

    if len(runs) < 2:
        blockers.append("a meta audit needs at least two participating systems")
        return Comparability(False, blockers, caveats)

    areas = {run.header.area for run in runs}
    if len(areas) > 1:
        blockers.append("participants audited different domains: " + ", ".join(sorted(areas)))

    hosts = [run.host for run in runs]
    duplicates = {host for host in hosts if hosts.count(host) > 1}
    if duplicates:
        blockers.append(
            "more than one run per system: " + ", ".join(sorted(duplicates))
        )

    for run in runs:
        if not run.header.coverage:
            caveats.append(f"{run.host} declared no coverage -- gaps stay unverifiable")
        if run.header.legacy:
            caveats.append(f"{run.host} contributed a legacy report without header")

    levels = {run.header.evidence_level for run in runs}
    if len(levels) > 1:
        caveats.append(
            "evidence levels differ: "
            + ", ".join(f"{run.host}={run.header.evidence_level}" for run in runs)
        )

    stamps = [run.header.finished_utc for run in runs if run.header.finished_utc]
    if len(stamps) > 1:
        span_days = (max(stamps) - min(stamps)).days
        if span_days > 0:
            caveats.append(f"runs span {span_days} days")

    return Comparability(ok=not blockers, blockers=blockers, caveats=caveats)


def _collect_keys(runs: list[AuditRun]) -> list[tuple[str, Finding]]:
    ordered: list[tuple[str, Finding]] = []
    seen: set[str] = set()
    for run in runs:
        for finding in run.findings:
            if finding.key not in seen:
                seen.add(finding.key)
                ordered.append((finding.key, finding))
    return ordered


def _classify(
    key: str, representative: Finding, runs: list[AuditRun]
) -> MetaFinding:
    present: list[str] = []
    absent: list[str] = []
    clean: list[str] = []
    unknown: list[str] = []
    divergent: dict[str, str] = {}

    locator = representative.norm_locator
    for run in runs:
        keys = {finding.key for finding in run.findings}
        if key in keys:
            present.append(run.host)
            continue
        same_place = [
            finding for finding in run.findings if finding.norm_locator == locator
        ]
        if same_place:
            divergent[run.host] = ", ".join(sorted({item.rule for item in same_place}))
            continue
        if run.declares_clean(representative.locator):
            clean.append(run.host)
            continue
        if not run.covers(representative.locator):
            unknown.append(run.host)
            continue
        absent.append(run.host)

    all_hosts = [run.host for run in runs]

    if divergent:
        classification = DIVERGENT
        rationale = "same locator, different rules on: " + ", ".join(
            f"{host} ({rules})" for host, rules in sorted(divergent.items())
        )
    elif clean:
        classification = INVERSE
        rationale = (
            "found on " + ", ".join(present)
            + " while explicitly confirmed as fine on " + ", ".join(clean)
        )
    elif len(present) == len(all_hosts):
        classification = SYSTEMWIDE
        rationale = "every participating system found it"
    elif absent:
        classification = HOST_SPECIFIC
        rationale = (
            "found on " + ", ".join(present)
            + "; covered but not found on " + ", ".join(absent)
        )
        if unknown:
            rationale += "; not covered on " + ", ".join(unknown)
    else:
        classification = UNVERIFIABLE
        rationale = (
            "found on " + ", ".join(present)
            + "; not covered on " + ", ".join(unknown)
            + " -- no system contradicts, so no conclusion"
        )

    return MetaFinding(
        finding=representative,
        classification=classification,
        present_on=present,
        absent_on=absent,
        clean_on=clean,
        unknown_on=unknown,
        divergent_rules=divergent,
        rationale=rationale,
    )


def build_meta(runs: list[AuditRun]) -> MetaResult:
    """Classify the findings of all participating systems against each other."""
    comparability = check_comparability(runs)
    participants = sorted(run.host for run in runs)
    if not comparability.ok:
        return MetaResult(comparability, participants, [])

    items = [_classify(key, finding, runs) for key, finding in _collect_keys(runs)]
    items.sort(key=lambda item: (CLASS_ORDER.index(item.classification), item.finding.key))
    return MetaResult(comparability, participants, items)


HEADINGS = {
    SYSTEMWIDE: "Systemweit (echte Systeminkonsistenz)",
    HOST_SPECIFIC: "Host-spezifisch (Drift einzelner Systeme)",
    INVERSE: "Invers (Host-Abhaengigkeit, oft hartkodierter Pfad)",
    DIVERGENT: "Divergent (unterschiedlicher Stand oder Auslegung)",
    UNVERIFIABLE: "Nicht verifizierbar (Luecke in der Abdeckung)",
}


def render_markdown(result: MetaResult, area: str) -> str:
    """Human-readable meta-audit body."""
    lines = [
        f"# Meta-{result.level}-Audit -- Domaene `{area}`",
        "",
        f"**Teilnehmende Systeme:** {', '.join(result.participants)}",
        f"**Vergleichbarkeit:** {result.comparability.summary}",
        "",
    ]
    if not result.comparability.ok:
        lines.append("Kein Meta-Audit erstellt.")
        return "\n".join(lines) + "\n"

    counts = result.counts
    lines.append(
        "**Bilanz:** "
        + " · ".join(f"{name}: {counts.get(name, 0)}" for name in CLASS_ORDER)
    )
    lines.append("")

    for classification in CLASS_ORDER:
        group = result.of_class(classification)
        if not group:
            continue
        lines.append(f"## {HEADINGS[classification]}")
        lines.append("")
        for item in group:
            lines.append(f"- `{item.finding.locator}` — {item.finding.title or item.finding.rule}")
            lines.append(f"  - Regel: {item.finding.rule}")
            lines.append(f"  - Befund auf: {', '.join(item.present_on) or '—'}")
            if item.absent_on:
                lines.append(f"  - Geprueft ohne Befund: {', '.join(item.absent_on)}")
            if item.clean_on:
                lines.append(f"  - Ausdruecklich in Ordnung: {', '.join(item.clean_on)}")
            if item.unknown_on:
                lines.append(f"  - Nicht abgedeckt: {', '.join(item.unknown_on)}")
            lines.append(f"  - Einordnung: {item.rationale}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
