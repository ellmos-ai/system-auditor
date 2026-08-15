"""Development over time -- a different question, therefore different classes.

A snapshot comparison asks *who saw what* at one moment.  A time series asks
*what happened* to a finding across windows.  The snapshot classes cannot answer
that: "every window found it" is not "systemwide", it is **persistent**, and the
difference matters -- one is a statement about machines, the other about trend.

==================  =====================================================
class               meaning
==================  =====================================================
``new``             appears for the first time in the newest window
``persistent``      present in every window since it first appeared
``resolved``        was there, is gone -- and the latest run *did look*
``recurring``       came back after at least one window without it
``unverifiable``    the latest run did not cover the place; no statement
==================  =====================================================

``resolved`` is the class that most easily lies.  A finding that merely stopped
being *checked* looks exactly like a fixed one.  So it is only awarded when the
newest run declares coverage of that locator -- otherwise the honest answer is
``unverifiable``.  This is the same discipline as in the snapshot case, applied
to time instead of participants.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .compare import AuditRun, Finding
from .tokens import Aggregation

NEW = "new"
PERSISTENT = "persistent"
RESOLVED = "resolved"
RECURRING = "recurring"
UNVERIFIABLE = "unverifiable"

TREND_CLASSES = (NEW, PERSISTENT, RECURRING, RESOLVED, UNVERIFIABLE)


@dataclass
class TrendFinding:
    finding: Finding
    classification: str
    windows_present: list[str] = field(default_factory=list)
    windows_absent: list[str] = field(default_factory=list)
    windows_unknown: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    rationale: str = ""

    @property
    def age_in_windows(self) -> int:
        return len(self.windows_present)


@dataclass
class TimeseriesResult:
    aggregation: Aggregation
    windows: list[str] = field(default_factory=list)
    items: list[TrendFinding] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for item in self.items:
            tally[item.classification] = tally.get(item.classification, 0) + 1
        return tally

    def of_class(self, classification: str) -> list[TrendFinding]:
        return [item for item in self.items if item.classification == classification]

    @property
    def latest_window(self) -> str:
        return self.windows[-1] if self.windows else ""

    @property
    def net_change(self) -> int:
        """New minus resolved in the newest window -- is it getting better?"""
        tally = self.counts
        return tally.get(NEW, 0) + tally.get(RECURRING, 0) - tally.get(RESOLVED, 0)


def build_timeseries(
    runs: list[AuditRun], aggregation: Aggregation
) -> TimeseriesResult:
    """Trace each finding across the windows of one series.

    ``runs`` may contain several audits per window (e.g. two models when the
    auditor dimension is uncontrolled); a finding counts as present in a window
    when *any* run of that window reported it.
    """
    ordered = sorted(runs, key=lambda run: run.header.time_token)
    windows: list[str] = []
    for run in ordered:
        if run.header.time_token not in windows:
            windows.append(run.header.time_token)

    result = TimeseriesResult(aggregation=aggregation, windows=windows)
    if len(windows) < 2:
        result.caveats.append("a time series needs at least two windows")
        return result

    uncontrolled = {
        dimension
        for dimension in aggregation.uncontrolled
        if len({run.header.identity.value(dimension) for run in ordered}) > 1
    }
    for dimension in sorted(uncontrolled):
        result.caveats.append(
            f"{dimension} is not held constant across the series -- "
            "changes may come from there rather than from the system"
        )

    by_window: dict[str, list[AuditRun]] = {}
    for run in ordered:
        by_window.setdefault(run.header.time_token, []).append(run)

    group_by = aggregation.group_by
    seen: dict[str, Finding] = {}
    for run in ordered:
        for finding in run.findings:
            seen.setdefault(finding.key(group_by), finding)

    for key, representative in seen.items():
        present: list[str] = []
        absent: list[str] = []
        unknown: list[str] = []

        for window in windows:
            window_runs = by_window[window]
            found = any(
                key in {item.key(group_by) for item in run.findings}
                for run in window_runs
            )
            if found:
                present.append(window)
            elif any(run.covers(representative.locator) for run in window_runs):
                absent.append(window)
            else:
                unknown.append(window)

        result.items.append(
            _classify_trend(representative, windows, present, absent, unknown)
        )

    result.items.sort(
        key=lambda item: (TREND_CLASSES.index(item.classification), item.finding.locator)
    )
    return result


def _classify_trend(
    finding: Finding,
    windows: list[str],
    present: list[str],
    absent: list[str],
    unknown: list[str],
) -> TrendFinding:
    latest = windows[-1]
    first_seen = present[0] if present else ""
    last_seen = present[-1] if present else ""

    def _make(classification: str, rationale: str) -> TrendFinding:
        return TrendFinding(
            finding=finding,
            classification=classification,
            windows_present=present,
            windows_absent=absent,
            windows_unknown=unknown,
            first_seen=first_seen,
            last_seen=last_seen,
            rationale=rationale,
        )

    if latest in unknown:
        return _make(
            UNVERIFIABLE,
            f"the newest window {latest} did not cover this locator -- "
            "gone and merely unchecked look identical",
        )

    if latest not in present:
        return _make(
            RESOLVED,
            f"last seen in {last_seen}; {latest} covered the locator and found nothing",
        )

    if len(present) == 1:
        return _make(NEW, f"first appearance, in {latest}")

    # Present in the newest window and seen before: continuous or interrupted?
    since_first = windows[windows.index(first_seen):]
    interrupted = [window for window in since_first if window in absent]
    if interrupted:
        return _make(
            RECURRING,
            f"first seen {first_seen}, absent in {', '.join(interrupted)}, back in {latest}",
        )
    return _make(
        PERSISTENT,
        f"present in every window since {first_seen} ({len(present)} windows)",
    )


_HEADINGS = {
    NEW: "Neu (erstmals in diesem Fenster)",
    PERSISTENT: "Anhaltend (seit dem ersten Auftreten durchgehend)",
    RECURRING: "Wiederkehrend (war weg, ist zurueck)",
    RESOLVED: "Erledigt (Ort geprueft, kein Befund mehr)",
    UNVERIFIABLE: "Nicht verifizierbar (juengstes Fenster deckte den Ort nicht ab)",
}


def render_markdown(result: TimeseriesResult, scope_label: str = "") -> str:
    """Human-readable time-series body."""
    title = f"Zeitreihe ({result.aggregation.name})"
    if scope_label:
        title += f" -- {scope_label}"
    lines = [
        f"# {title}",
        "",
        f"**Fenster:** {' -> '.join(result.windows) or '—'}",
    ]
    if result.caveats:
        lines.append(f"**Vorbehalte:** {'; '.join(result.caveats)}")
    if len(result.windows) < 2:
        lines.append("")
        lines.append("Keine Zeitreihe erstellt.")
        return "\n".join(lines) + "\n"

    counts = result.counts
    lines.append(
        "**Bilanz:** " + " · ".join(f"{name}: {counts.get(name, 0)}" for name in TREND_CLASSES)
    )
    direction = (
        "mehr Neues als Erledigtes"
        if result.net_change > 0
        else ("mehr Erledigtes als Neues" if result.net_change < 0 else "ausgeglichen")
    )
    lines.append(f"**Richtung:** {direction} (netto {result.net_change:+d})")
    lines.append("")

    for classification in TREND_CLASSES:
        group = result.of_class(classification)
        if not group:
            continue
        lines.append(f"## {_HEADINGS[classification]}")
        lines.append("")
        for item in group:
            lines.append(f"- `{item.finding.locator}` — {item.finding.title or item.finding.rule}")
            lines.append(f"  - Regel: {item.finding.rule}")
            lines.append(
                f"  - Fenster mit Befund: {', '.join(item.windows_present) or '—'}"
            )
            if item.windows_absent:
                lines.append(f"  - Geprueft ohne Befund: {', '.join(item.windows_absent)}")
            if item.windows_unknown:
                lines.append(f"  - Nicht abgedeckt: {', '.join(item.windows_unknown)}")
            lines.append(f"  - Einordnung: {item.rationale}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
