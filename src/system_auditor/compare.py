"""Classification across participants -- the core of a meta audit.

Participants of a meta audit are whatever varies along the aggregation axis:
machines (``cross-system``), models (``interrater``) or domains
(``cross-domain``).  The classification is the same in all three cases; only its
reading changes with the axis.

Worked example, measured 2026-08-15, axis = system:

    Finding "Gardener governance hardcodes the laptop home path"
    (``AGENTS.md`` points at ``C:\\Users\\User\\...``).

On WORKSTATION-LG this is real: the path does not exist there.  On the laptop
the very same line is correct and produces no finding at all.  One machine can
only ever see one half of that.

================  ====================================================
class             meaning
================  ====================================================
``systemwide``    every participant found it
``host_specific`` some found it, others checked and did not
``inverse``       found by one where another explicitly confirmed the
                  same locator as fine
``divergent``     same locator, *different* rules broken
``unverifiable``  a participant never looked there, and none contradicts
================  ====================================================

``unverifiable`` is the honest rung.  Without it every gap in a participant's
coverage would masquerade as a real difference.

**Matching depends on the axis.**  Across machines the same *place* is compared
(``locator+rule``).  Across domains there is no shared place, so what carries
meaning is the *rule*: the same rule broken in unrelated corners is a problem of
the rule, not of one location.  The aggregation decides which applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .report import ReportHeader
from .tokens import CROSS_SYSTEM, GROUP_BY_RULE, Aggregation

SYSTEMWIDE = "systemwide"
HOST_SPECIFIC = "host_specific"
INVERSE = "inverse"
DIVERGENT = "divergent"
UNVERIFIABLE = "unverifiable"

CLASS_ORDER = (SYSTEMWIDE, HOST_SPECIFIC, INVERSE, DIVERGENT, UNVERIFIABLE)

#: Home directories differ per machine (``C:\\Users\\lukas`` vs ``C:\\Users\\User``).
#: Without folding them to a placeholder, no locator would ever match its
#: counterpart and every finding would look participant-specific.
_HOME_PATTERNS = (
    re.compile(r"^[a-z]:[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+home[\\/]+[^\\/]+", re.IGNORECASE),
)


def normalize_locator(raw: str) -> str:
    """Machine-neutral, comparable form of a path-ish locator."""
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
    detail: str = ""

    @property
    def norm_locator(self) -> str:
        return normalize_locator(self.locator)

    @property
    def norm_rule(self) -> str:
        return self.rule.strip().lower()

    def key(self, group_by: str) -> str:
        if group_by == GROUP_BY_RULE:
            return self.norm_rule
        return f"{self.norm_rule}@{self.norm_locator}"


@dataclass
class AuditRun:
    """One participant's audit."""

    header: ReportHeader
    findings: list[Finding] = field(default_factory=list)

    def participant(self, aggregation: Aggregation) -> str:
        return self.header.identity.value(aggregation.varying)

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
    aggregation: Aggregation
    participants: list[str] = field(default_factory=list)
    items: list[MetaFinding] = field(default_factory=list)

    @property
    def level(self) -> int:
        return len(self.participants)

    @property
    def axis(self) -> str:
        return self.aggregation.varying

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for item in self.items:
            tally[item.classification] = tally.get(item.classification, 0) + 1
        return tally

    def of_class(self, classification: str) -> list[MetaFinding]:
        return [item for item in self.items if item.classification == classification]

    @property
    def agreement(self) -> float | None:
        """Share of findings all participants agree on.

        Most meaningful on the ``interrater`` axis, where participants look at
        the *same* machine: there a low value is not a system defect but a
        reliability problem of the auditors themselves.  ``None`` when nothing
        was decidable.
        """
        decidable = [
            item for item in self.items if item.classification != UNVERIFIABLE
        ]
        if not decidable:
            return None
        agreed = len([item for item in decidable if item.classification == SYSTEMWIDE])
        return round(agreed / len(decidable), 3)


def check_comparability(runs: list[AuditRun], aggregation: Aggregation) -> Comparability:
    """Gate before comparing. Comparing incomparable runs invents findings."""
    blockers: list[str] = []
    caveats: list[str] = []

    if len(runs) < 2:
        return Comparability(False, ["a meta audit needs at least two participants"], [])

    for dimension in aggregation.fixed:
        values = {run.header.identity.value(dimension) for run in runs}
        if len(values) > 1:
            blockers.append(
                f"participants differ in fixed dimension {dimension}: "
                + ", ".join(sorted(values))
            )

    participants = [run.participant(aggregation) for run in runs]
    duplicates = {name for name in participants if participants.count(name) > 1}
    if duplicates:
        blockers.append(
            f"more than one run per {aggregation.varying}: " + ", ".join(sorted(duplicates))
        )

    for run in runs:
        if not run.header.coverage:
            caveats.append(
                f"{run.participant(aggregation)} declared no coverage -- "
                "gaps stay unverifiable"
            )
        if run.header.legacy:
            caveats.append(
                f"{run.participant(aggregation)} contributed a legacy report without header"
            )

    levels = {run.header.evidence_level for run in runs}
    if len(levels) > 1:
        caveats.append(
            "evidence levels differ: "
            + ", ".join(
                f"{run.participant(aggregation)}={run.header.evidence_level}" for run in runs
            )
        )

    return Comparability(ok=not blockers, blockers=blockers, caveats=caveats)


def _collect_keys(runs: list[AuditRun], group_by: str) -> list[tuple[str, Finding]]:
    ordered: list[tuple[str, Finding]] = []
    seen: set[str] = set()
    for run in runs:
        for finding in run.findings:
            key = finding.key(group_by)
            if key not in seen:
                seen.add(key)
                ordered.append((key, finding))
    return ordered


def _classify(
    key: str, representative: Finding, runs: list[AuditRun], aggregation: Aggregation
) -> MetaFinding:
    present: list[str] = []
    absent: list[str] = []
    clean: list[str] = []
    unknown: list[str] = []
    divergent: dict[str, str] = {}

    group_by = aggregation.group_by
    locator = representative.norm_locator

    for run in runs:
        name = run.participant(aggregation)
        if key in {finding.key(group_by) for finding in run.findings}:
            present.append(name)
            continue
        same_place = [
            finding for finding in run.findings if finding.norm_locator == locator
        ]
        if same_place and group_by != GROUP_BY_RULE:
            divergent[name] = ", ".join(sorted({item.rule for item in same_place}))
            continue
        if run.declares_clean(representative.locator):
            clean.append(name)
            continue
        if not run.covers(representative.locator):
            unknown.append(name)
            continue
        absent.append(name)

    everyone = [run.participant(aggregation) for run in runs]

    if divergent:
        classification = DIVERGENT
        rationale = "same locator, different rules on: " + ", ".join(
            f"{name} ({rules})" for name, rules in sorted(divergent.items())
        )
    elif clean:
        classification = INVERSE
        rationale = (
            "found on " + ", ".join(present)
            + " while explicitly confirmed as fine on " + ", ".join(clean)
        )
    elif len(present) == len(everyone):
        classification = SYSTEMWIDE
        rationale = "every participant found it"
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
            + " -- nobody contradicts, so no conclusion"
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


def build_meta(
    runs: list[AuditRun], aggregation: Aggregation = CROSS_SYSTEM
) -> MetaResult:
    """Classify all participants' findings against each other."""
    comparability = check_comparability(runs, aggregation)
    participants = sorted({run.participant(aggregation) for run in runs})
    if not comparability.ok:
        return MetaResult(comparability, aggregation, participants, [])

    items = [
        _classify(key, finding, runs, aggregation)
        for key, finding in _collect_keys(runs, aggregation.group_by)
    ]
    items.sort(
        key=lambda item: (
            CLASS_ORDER.index(item.classification),
            item.finding.key(aggregation.group_by),
        )
    )
    return MetaResult(comparability, aggregation, participants, items)


#: Headings adapt to the axis -- "on all machines" and "in all domains" are the
#: same class but not the same sentence.
_HEADINGS = {
    "system": {
        SYSTEMWIDE: "Systemweit (echte Systeminkonsistenz)",
        HOST_SPECIFIC: "Host-spezifisch (Drift einzelner Maschinen)",
        INVERSE: "Invers (Host-Abhaengigkeit, oft hartkodierter Pfad)",
        DIVERGENT: "Divergent (unterschiedlicher Stand oder Auslegung)",
        UNVERIFIABLE: "Nicht verifizierbar (Luecke in der Abdeckung)",
    },
    "auditor": {
        SYSTEMWIDE: "Uebereinstimmung (alle Auditoren einig)",
        HOST_SPECIFIC: "Nur von einzelnen Auditoren gesehen (Rater-Divergenz)",
        INVERSE: "Widerspruch (ein Auditor bestaetigt, was ein anderer bemaengelt)",
        DIVERGENT: "Gleiche Stelle, andere Regel gelesen",
        UNVERIFIABLE: "Nicht verifizierbar (Luecke in der Abdeckung)",
    },
    "domain": {
        SYSTEMWIDE: "Durchgaengig (Regel in allen Domaenen verletzt)",
        HOST_SPECIFIC: "Lokal (nur in einzelnen Domaenen)",
        INVERSE: "Invers (anderswo ausdruecklich in Ordnung)",
        DIVERGENT: "Gleiche Stelle, andere Regel",
        UNVERIFIABLE: "Nicht verifizierbar (Luecke in der Abdeckung)",
    },
}


def headings_for(axis: str) -> dict[str, str]:
    return _HEADINGS.get(axis, _HEADINGS["system"])


def render_markdown(result: MetaResult, scope_label: str = "") -> str:
    """Human-readable meta-audit body."""
    title = f"Meta-{result.level}-Audit ({result.aggregation.name})"
    if scope_label:
        title += f" -- {scope_label}"
    lines = [
        f"# {title}",
        "",
        f"**Achse:** {result.axis} · **Teilnehmer:** {', '.join(result.participants)}",
        f"**Vergleichbarkeit:** {result.comparability.summary}",
    ]
    if result.aggregation.name == "interrater" and result.agreement is not None:
        lines.append(f"**Uebereinstimmung der Auditoren:** {result.agreement:.0%}")
    lines.append("")

    if not result.comparability.ok:
        lines.append("Kein Meta-Audit erstellt.")
        return "\n".join(lines) + "\n"

    counts = result.counts
    headings = headings_for(result.axis)
    lines.append(
        "**Bilanz:** " + " · ".join(f"{name}: {counts.get(name, 0)}" for name in CLASS_ORDER)
    )
    lines.append("")

    for classification in CLASS_ORDER:
        group = result.of_class(classification)
        if not group:
            continue
        lines.append(f"## {headings[classification]}")
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
