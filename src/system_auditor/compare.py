"""Classification across participants -- the core of a meta audit.

Participants of a meta audit are whatever varies along the aggregation axis:
machines (``cross-system``), models (``interrater``) or domains
(``cross-domain``).  The classification is the same in all three cases; only its
reading changes with the axis.

Worked example, measured 2026-08-15, axis = system:

    Finding "Gardener governance hardcodes the laptop home path"
    (``AGENTS.md`` points at ``C:\\Users\\bob\\...``).

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

from .report import ReportHeader, is_identified_auditor
from .tokens import (
    CROSS_SYSTEM,
    DIM_DOMAIN,
    GROUP_BY_LOCATOR,
    GROUP_BY_RULE,
    Aggregation,
)

SYSTEMWIDE = "systemwide"
HOST_SPECIFIC = "host_specific"
INVERSE = "inverse"
DIVERGENT = "divergent"
UNVERIFIABLE = "unverifiable"

CLASS_ORDER = (SYSTEMWIDE, HOST_SPECIFIC, INVERSE, DIVERGENT, UNVERIFIABLE)

#: Home directories differ per machine (``C:\\Users\\alice`` vs ``C:\\Users\\bob``).
#: Without folding them to a placeholder, no locator would ever match its
#: counterpart and every finding would look participant-specific.
_HOME_PATTERNS = (
    re.compile(r"^[a-z]:[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+users[\\/]+[^\\/]+", re.IGNORECASE),
    re.compile(r"^[\\/]+home[\\/]+[^\\/]+", re.IGNORECASE),
)


#: UNC paths (``\\server\share``) are a different namespace from POSIX
#: ``/server/share``. Collapsing both to one string made them compare equal.
_UNC_PREFIX = "//"


def normalize_locator(raw: str) -> str:
    """Machine-neutral, comparable form of a path-ish locator.

    Case folding is applied only to paths that came from a case-insensitive
    namespace (drive letters, UNC, an already-folded ``<HOME>``). On a
    case-sensitive filesystem ``/srv/Repo/X`` and ``/srv/repo/x`` are two
    different files and must not compare equal.

    **Known limits, deliberately not guessed at:** symlinks, ``..`` segments,
    ``~`` and WSL aliases (``/mnt/c/...``) are not resolved -- that needs the
    filesystem of the machine that produced the locator, which a comparing host
    does not have. Producers should emit resolved paths.
    """
    text = (raw or "").strip().replace("\\", "/")
    is_unc = text.startswith(_UNC_PREFIX)
    while "//" in text:
        text = text.replace("//", "/")
    if is_unc:
        text = "unc:" + text.lstrip("/")

    folded_home = False
    for pattern in _HOME_PATTERNS:
        if pattern.match(text):
            text = pattern.sub("<HOME>", text, count=1)
            folded_home = True
            break

    text = text.rstrip("/")
    has_drive = len(text) > 1 and text[1] == ":" and text[0].isalpha()
    if folded_home or is_unc or has_drive:
        return text.lower()
    return text


def _is_under(target: str, prefix: str) -> bool:
    """Path containment, not string prefix.

    ``startswith`` alone made the coverage ``/repo/foo`` swallow the locator
    ``/repo/foobar/AGENTS.md`` -- and coverage is exactly what decides between
    "checked and found nothing" and "never looked". A plain character prefix is
    not an ancestor relation.
    """
    if not prefix:
        return False
    return target == prefix or target.startswith(prefix.rstrip("/") + "/")


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
        return aggregation.participant(self.header.identity)

    def covers(self, locator: str) -> bool:
        target = normalize_locator(locator)
        return any(
            _is_under(target, normalize_locator(prefix))
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
    #: Evidence states that ALSO apply. The classes are a priority projection,
    #: not a partition: with four participants the same key can be divergent on
    #: one, explicitly clean on another and merely absent on a third. Naming
    #: only the winning class would hide the stronger negative confirmation.
    also: list[str] = field(default_factory=list)


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
        """Single varying dimension, or "+"-joined when several vary."""
        return "+".join(self.aggregation.varying)

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for item in self.items:
            tally[item.classification] = tally.get(item.classification, 0) + 1
        return tally

    def of_class(self, classification: str) -> list[MetaFinding]:
        return [item for item in self.items if item.classification == classification]

    @property
    def unanimity(self) -> float | None:
        """Share of decidable findings that *every* participant reported.

        Deliberately **not** called "agreement": the denominator contains only
        keys at least one participant raised, so shared negative judgements
        about clean rules never enter it -- there is no predefined item universe
        to be silent about. With more than two participants only unanimity
        counts as a hit.

        That makes it a Jaccard-like positive-unanimity rate. A proper
        chance-corrected measure (Cohen's kappa) is not computable here for the
        same reason: it needs a common set of items both raters judged.

        ``None`` when nothing was decidable.
        """
        decidable = [
            item for item in self.items if item.classification != UNVERIFIABLE
        ]
        if not decidable:
            return None
        agreed = len([item for item in decidable if item.classification == SYSTEMWIDE])
        return round(agreed / len(decidable), 3)

    @property
    def pairwise_jaccard(self) -> float | None:
        """Mean pairwise Jaccard over the participants' finding sets.

        For two participants this is the honest name for what ``unanimity``
        computes; for more it is the milder, more informative sibling, because a
        single dissenter no longer zeroes out an otherwise broad overlap.
        """
        sets = {
            name: {
                item.finding.key(GROUP_BY_RULE)
                for item in self.items
                if name in item.present_on
            }
            for name in self.participants
        }
        pairs = [
            (a, b)
            for index, a in enumerate(self.participants)
            for b in self.participants[index + 1:]
        ]
        scores = []
        for left, right in pairs:
            union = sets[left] | sets[right]
            if union:
                scores.append(len(sets[left] & sets[right]) / len(union))
        return round(sum(scores) / len(scores), 3) if scores else None


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

    # An unidentified auditor cannot stand as a voice of its own. Blocking is
    # deliberate rather than quietly dropping the run: a comparison that silently
    # omits a participant still reads as a complete rater panel. Naming the run
    # lets the operator supply --auditor and rerun.
    if "auditor" in aggregation.varying:
        unidentified = sorted(
            run.header.identity.value("system") + "/" + (run.header.auditor or "")
            for run in runs
            if not is_identified_auditor(run.header.auditor)
        )
        if unidentified:
            blockers.append(
                "auditor not identified for: " + ", ".join(unidentified)
                + " -- an unknown model cannot be compared against another model"
            )

    participants = [run.participant(aggregation) for run in runs]
    duplicates = {name for name in participants if participants.count(name) > 1}
    if duplicates:
        axis = "+".join(aggregation.varying)
        blockers.append(
            f"more than one run per {axis}: " + ", ".join(sorted(duplicates))
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

    # An uncontrolled dimension that actually differs is not a blocker -- in a
    # fleet where each machine runs its own model, refusing those comparisons
    # would mean never comparing machines at all. But it must be said, because
    # the difference may come from there rather than from the compared axis.
    for dimension in aggregation.uncontrolled:
        values = sorted({run.header.identity.value(dimension) for run in runs})
        if len(values) > 1:
            caveats.append(
                f"{dimension} is not held constant ({', '.join(values)}) -- "
                "differences may come from there rather than from the compared axis"
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


def effective_group_by(runs: list[AuditRun], aggregation: Aggregation) -> str:
    """Match by rule only when the domain *actually* differs among these runs.

    ``full-system`` lets domain and auditor vary, so its declared ``group_by``
    is ``rule``. But if the concrete participants are two models on one domain,
    rule-matching alone would call "same rule at different places" an
    agreement -- for rater agreement the *place* has to match too. The declared
    axis states what may vary; only the data says what does.
    """
    if DIM_DOMAIN not in aggregation.varying:
        return aggregation.group_by
    domains = {run.header.identity.value(DIM_DOMAIN) for run in runs}
    return GROUP_BY_RULE if len(domains) > 1 else GROUP_BY_LOCATOR


def _classify(
    key: str,
    representative: Finding,
    runs: list[AuditRun],
    aggregation: Aggregation,
    group_by: str | None = None,
) -> MetaFinding:
    present: list[str] = []
    absent: list[str] = []
    clean: list[str] = []
    unknown: list[str] = []
    divergent: dict[str, str] = {}

    group_by = group_by or aggregation.group_by
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

    also: list[str] = []
    if divergent and (clean or absent):
        also.append("clean_on: " + ", ".join(clean) if clean else "")
        also.append("absent_on: " + ", ".join(absent) if absent else "")
    elif clean and absent:
        also.append("absent_on: " + ", ".join(absent))
    also = [note for note in also if note]

    if group_by == GROUP_BY_RULE and (absent or unknown):
        # Matching by rule means the participants have no shared location. A
        # participant that did not report the rule cannot be called "checked and
        # found nothing" -- its coverage could never have covered a foreign
        # domain's locator. Absence is not observable on this axis, so the class
        # stays unverifiable and says why instead of implying a negative result.
        unknown = sorted(unknown + absent)
        absent = []
        also.append("absence is not observable when matching by rule")

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
        also=also,
    )


def build_meta(
    runs: list[AuditRun], aggregation: Aggregation = CROSS_SYSTEM
) -> MetaResult:
    """Classify a *snapshot* -- several participants at one moment.

    Refuses the other two kinds rather than producing a plausible-looking
    nonsense: a time series asked through these classes reports "systemwide"
    for a finding present in every window, which is *persistent* and a statement
    about trend, not about machines.
    """
    if aggregation.is_timeseries:
        raise ValueError(
            f"{aggregation.name} varies time: the snapshot classes describe who "
            "saw what at one moment, not how something developed. Use "
            "build_timeseries() instead."
        )
    if not aggregation.is_inferential:
        raise ValueError(
            f"{aggregation.name} is descriptive: with {len(aggregation.varying)} "
            "dimensions varying, a difference cannot be attributed to a cause. "
            "Use build_inventory() instead."
        )
    return _build_meta(runs, aggregation)


def _build_meta(
    runs: list[AuditRun], aggregation: Aggregation
) -> MetaResult:
    """Classify all participants' findings against each other.

    The runs are ordered canonically first. Without that, the same *set* of
    audits passed in a different order produced a different representative
    title and a different ``present_on`` order -- the classification held, but
    the artefact was not byte-identical, which is what an idempotence claim
    actually requires.
    """
    runs = sorted(runs, key=lambda run: run.participant(aggregation))
    comparability = check_comparability(runs, aggregation)
    participants = sorted({run.participant(aggregation) for run in runs})
    if not comparability.ok:
        return MetaResult(comparability, aggregation, participants, [])

    group_by = effective_group_by(runs, aggregation)
    items = [
        _classify(key, finding, runs, aggregation, group_by)
        for key, finding in _collect_keys(runs, group_by)
    ]
    items.sort(
        key=lambda item: (CLASS_ORDER.index(item.classification), item.finding.key(group_by))
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


#: Where several dimensions vary at once (full-system: domain+auditor), the
#: domain reading is the honest one -- findings are matched by rule there.
_HEADINGS["domain+auditor"] = _HEADINGS["domain"]


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
    if result.aggregation.name == "interrater" and result.unanimity is not None:
        lines.append(
            f"**Positive Einstimmigkeit:** {result.unanimity:.0%}"
            + (f" · **paarweiser Jaccard:** {result.pairwise_jaccard:.0%}"
               if result.pairwise_jaccard is not None else "")
        )
        lines.append(
            "> Kein allgemeines Interrater-Mass: Gezaehlt werden nur Schluessel, die "
            "mindestens ein Auditor gemeldet hat. Gemeinsames Schweigen ueber saubere "
            "Stellen geht mangels definierter Item-Menge nicht ein."
        )
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


# ---------------------------------------------------------------------------
# Descriptive inventory -- for aggregations that must not draw a conclusion
# ---------------------------------------------------------------------------


@dataclass
class InventoryEntry:
    participant: str
    findings: list[Finding] = field(default_factory=list)
    coverage: list[str] = field(default_factory=list)


@dataclass
class InventoryResult:
    """What was found, where and by whom -- without attributing a cause.

    ``full-system`` lets domain and auditor vary at once. That is a useful
    picture of one machine in one window, but it cannot answer *why* two cells
    differ: domain, model, or their interaction are not separable. So this
    artefact states the holdings and stops there.
    """

    aggregation: Aggregation
    entries: list[InventoryEntry] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def participants(self) -> list[str]:
        return [entry.participant for entry in self.entries]

    @property
    def total_findings(self) -> int:
        return sum(len(entry.findings) for entry in self.entries)

    def rule_frequency(self) -> dict[str, int]:
        """How often each rule appears across the whole matrix.

        A frequent rule is a hint worth following -- but only a hint: which cell
        it came from is not a cause, and this artefact does not pretend it is.
        """
        tally: dict[str, int] = {}
        for entry in self.entries:
            for finding in entry.findings:
                tally[finding.rule] = tally.get(finding.rule, 0) + 1
        return dict(sorted(tally.items(), key=lambda pair: (-pair[1], pair[0])))

    def cells(self) -> dict[tuple[str, ...], int]:
            return {
            tuple(entry.participant.split(" / ")): len(entry.findings)
            for entry in self.entries
        }


def build_inventory(
    runs: list[AuditRun], aggregation: Aggregation
) -> InventoryResult:
    """Holdings of a descriptive aggregation. No classes, no attribution."""
    if aggregation.is_inferential:
        raise ValueError(
            f"{aggregation.name} is inferential -- use build_meta() to classify."
        )
    ordered = sorted(runs, key=lambda run: run.participant(aggregation))
    result = InventoryResult(aggregation=aggregation)
    for run in ordered:
        result.entries.append(
            InventoryEntry(
                participant=run.participant(aggregation),
                findings=list(run.findings),
                coverage=list(run.header.coverage),
            )
        )

    varying = "+".join(aggregation.varying)
    result.caveats.append(
        f"deskriptiv: {varying} variieren gleichzeitig -- ein Unterschied zwischen "
        "zwei Zellen ist keiner Ursache zuzuordnen"
    )
    grid = {dimension: {run.header.identity.value(dimension) for run in ordered}
            for dimension in aggregation.varying}
    expected = 1
    for values in grid.values():
        expected *= len(values)
    if len(ordered) < expected:
        result.caveats.append(
            f"Raster unvollstaendig: {len(ordered)} von {expected} moeglichen Zellen besetzt"
        )
    return result


def render_inventory(result: InventoryResult, scope_label: str = "") -> str:
    title = f"Bestandsaufnahme ({result.aggregation.name})"
    if scope_label:
        title += f" -- {scope_label}"
    lines = [
        f"# {title}",
        "",
        f"**Zellen:** {len(result.entries)} · **Befunde gesamt:** {result.total_findings}",
    ]
    for note in result.caveats:
        lines.append(f"> {note}")
    lines.append("")
    lines.append("## Belegung")
    lines.append("")
    for entry in result.entries:
        lines.append(f"- **{entry.participant}** — {len(entry.findings)} Befund(e)")
        for finding in entry.findings:
            lines.append(f"  - `{finding.locator}` · {finding.rule}")
    frequency = result.rule_frequency()
    if frequency:
        lines.append("")
        lines.append("## Regelhaeufigkeit")
        lines.append("")
        for rule, count in frequency.items():
            lines.append(f"- {rule}: {count}x")
        lines.append("")
        lines.append(
            "> Haeufigkeit ist ein Hinweis, keine Ursache. Wer wissen will, ob eine "
            "Regel *domaenenuebergreifend* bricht, nimmt `cross-domain` (Modell und "
            "Maschine festgehalten); wer Modelle vergleichen will, `interrater`."
        )
    return "\n".join(lines).rstrip() + "\n"
