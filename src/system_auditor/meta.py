"""Meta-audit lifecycle -- one current answer per fixed key.

Bundling rule, in the user's words: things only ever land in the same pot when
their fixed tokens match.  Which tokens those are is what distinguishes the
aggregations (see :mod:`system_auditor.tokens`).  Everything else follows:

* **Overwrite, don't archive.**  When a participant joins, the artefact for that
  key is rewritten in place.  "What do we know about X" has one current answer;
  keeping meta-2 next to meta-3 would leave two answers to one question.
* **History is free** for snapshots: another window is another period token,
  hence another file, untouched.  Time series deliberately have no period in
  their name -- they *are* the history and are always "as of now".
* **Restating overwrites itself.**  Identical four tokens produce an identical
  file name, so a correction lands on top of its predecessor without any
  bookkeeping.  Only the meta artefact has to notice and rebuild.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .report import MODE_META, MODE_SELF, ReportHeader, list_reports, meta_filename
from .tokens import (
    AGGREGATIONS,
    CROSS_SYSTEM,
    DIM_TIME,
    Aggregation,
    Bundle,
    find_bundles,
    newest_per_identity,
)

ARCHIVE_DIRNAME = "_archive"
MIN_PARTICIPANTS = 2

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_SKIP = "skip"


@dataclass
class MetaPlan:
    """What to do for one bundle -- decided before anything is written."""

    action: str
    aggregation: str
    key: list[str] = field(default_factory=list)
    time_token: str = ""
    level: int = 0
    participants: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    target: str = ""
    replaces: Path | None = None
    previous_level: int = 0
    reason: str = ""
    uncontrolled: dict[str, list[str]] = field(default_factory=dict)
    restated: list[str] = field(default_factory=list)

    @property
    def should_write(self) -> bool:
        return self.action in (ACTION_CREATE, ACTION_UPDATE)

    def title(self) -> str:
        """Human title carrying the counts the file name deliberately omits.

        For ``full-system`` this reads e.g. "5 Domaenen x 2 Auditoren" -- the
        naming the user asked for, kept out of the file name so the overwrite
        rule survives a changing participant count.
        """
        parts = " x ".join(f"{count} {dim}" for dim, count in sorted(self.counts.items()))
        scope = "-".join(self.key)
        return f"{self.aggregation} [{parts}] {scope}".strip()


# ---------------------------------------------------------------------------
# Which artefacts get built -- policy, not appetite
# ---------------------------------------------------------------------------
#
# The aggregation ladder is combinatorial: 14 domains x 3 machines x 2 models
# yields ~191 possible artefacts per window. Building all of them is not
# thoroughness, it is noise -- and noise that costs a run every window and
# buries the two artefacts somebody actually reads.
#
# So each aggregation carries a mode:
#
#   always      built whenever a bundle exists (the standing question)
#   on_demand   built only when explicitly asked for (the occasional question)
#   off         not built at all
#
# plus its own participant threshold, because "enough to be worth stating"
# differs per aggregation: two machines already say something, while a series
# of two windows says almost nothing.

MODE_ALWAYS = "always"
MODE_ON_DEMAND = "on_demand"
MODE_OFF = "off"

#: Deliberately narrow: exactly one standing artefact. Everything else is a
#: question somebody asks, not a report that accumulates unread.
DEFAULT_POLICY: dict[str, dict] = {
    "cross-system": {"mode": MODE_ALWAYS, "min_participants": 2},
    "interrater": {"mode": MODE_ON_DEMAND, "min_participants": 2},
    "cross-domain": {"mode": MODE_ON_DEMAND, "min_participants": 3},
    "full-system": {"mode": MODE_ON_DEMAND, "min_participants": 2},
    "timeseries": {"mode": MODE_ON_DEMAND, "min_participants": 3},
    "timeseries-rater": {"mode": MODE_OFF, "min_participants": 3},
}


def resolve_policy(config: dict | None = None) -> dict[str, dict]:
    """Merge a config fragment over the defaults, ignoring unknown names."""
    policy = {name: dict(entry) for name, entry in DEFAULT_POLICY.items()}
    for name, entry in (config or {}).items():
        if name not in policy:
            continue
        policy[name].update(
            {key: value for key, value in (entry or {}).items()
             if key in ("mode", "min_participants")}
        )
    return policy


def due_aggregations(
    policy: dict[str, dict] | None = None, requested: str | None = None
) -> list[tuple[Aggregation, int]]:
    """Which aggregations to plan now, with their thresholds.

    Without ``requested``: every ``always`` aggregation -- the standing report.
    With ``requested``: that one, even if it is ``on_demand``; an ``off``
    aggregation stays off, because switching it on is a config decision and not
    something a single call should do silently.
    """
    resolved = policy or resolve_policy()
    if requested is not None:
        entry = resolved.get(requested, {})
        if entry.get("mode", MODE_OFF) == MODE_OFF:
            return []
        return [(AGGREGATIONS[requested], int(entry.get("min_participants", MIN_PARTICIPANTS)))]
    return [
        (AGGREGATIONS[name], int(entry.get("min_participants", MIN_PARTICIPANTS)))
        for name, entry in sorted(resolved.items())
        if entry.get("mode") == MODE_ALWAYS and name in AGGREGATIONS
    ]


def plan_all(
    reports_dir: Path,
    policy: dict[str, dict] | None = None,
    time_token: str | None = None,
    requested: str | None = None,
) -> list[MetaPlan]:
    """Plans for every aggregation that is due -- the normal entry point."""
    plans: list[MetaPlan] = []
    for aggregation, threshold in due_aggregations(policy, requested):
        plans.extend(
            plan_metas(reports_dir, aggregation, time_token, min_participants=threshold)
        )
    return plans


def audit_ref(header: ReportHeader) -> str:
    """Stable reference of a single audit inside a meta bundle."""
    return header.run_id or (header.path.name if header.path else "")


def time_of(aggregation: Aggregation, key: tuple[str, ...]) -> str:
    """The period value -- empty when the aggregation spans windows."""
    for dimension, value in zip(aggregation.fixed, key, strict=True):
        if dimension == DIM_TIME:
            return value
    return ""


def current_single_audits(
    reports_dir: Path, time_token: str | None = None
) -> tuple[list[ReportHeader], list[str]]:
    """Single audits, deduplicated by identity (newest wins).

    Returns ``(current, restated)`` -- the second lists identities whose earlier
    statement was replaced by a newer one carrying the same four tokens.
    """
    headers = [
        header
        for header in list_reports(reports_dir, audit_mode=MODE_SELF)
        if time_token is None or header.time_token == time_token
    ]
    pairs = [(header.identity, header) for header in headers]
    kept = newest_per_identity(pairs, sort_key=lambda header: header.sort_key)
    kept_paths = {header.path for _identity, header in kept}

    restated = [
        f"{header.identity.system}/{header.identity.auditor}"
        for header in headers
        if header.path not in kept_paths
    ]
    return [header for _identity, header in kept], sorted(set(restated))


def existing_meta(
    reports_dir: Path, aggregation: str, key: list[str]
) -> ReportHeader | None:
    """The meta artefact currently in force for exactly this key."""
    wanted = meta_filename(aggregation, key)
    for header in list_reports(reports_dir, audit_mode=MODE_META):
        if header.path is not None and header.path.name == wanted:
            return header
    return None


def plan_metas(
    reports_dir: Path,
    aggregation: Aggregation | str = CROSS_SYSTEM,
    time_token: str | None = None,
    min_participants: int = MIN_PARTICIPANTS,
) -> list[MetaPlan]:
    """Which meta artefacts are due -- and for the rest, why not.

    ``time_token`` narrows to one window and is **ignored for time series**,
    which span windows by definition: filtering there would leave exactly one
    window and no series at all.
    """
    resolved = AGGREGATIONS[aggregation] if isinstance(aggregation, str) else aggregation
    window_filter = None if resolved.is_timeseries else time_token
    current, restated = current_single_audits(reports_dir, window_filter)
    by_identity = {header.identity: header for header in current}

    bundles: list[Bundle] = find_bundles(
        list(by_identity.keys()), resolved, min_participants=min_participants
    )

    plans: list[MetaPlan] = []
    for bundle in bundles:
        key = list(bundle.key)
        members = [by_identity[identity] for identity in bundle.identities]
        inputs = sorted(audit_ref(header) for header in members)
        previous = existing_meta(reports_dir, resolved.name, key)

        if previous is not None and sorted(previous.inputs) == inputs:
            action, reason = ACTION_SKIP, (
                f"the artefact for this key already rests on exactly these "
                f"{len(inputs)} audits"
            )
        elif previous is not None:
            action, reason = ACTION_UPDATE, (
                f"participants changed: {previous.meta_level} -> {bundle.level}; "
                "rewritten in place"
            )
        else:
            action, reason = ACTION_CREATE, (
                f"{bundle.level} participants, no artefact for this key yet"
            )

        plans.append(
            MetaPlan(
                action=action,
                aggregation=resolved.name,
                key=key,
                time_token=time_of(resolved, bundle.key),
                level=bundle.level,
                participants=bundle.varying_values,
                counts=bundle.counts(),
                inputs=inputs,
                target=meta_filename(resolved.name, key),
                replaces=previous.path if previous else None,
                previous_level=previous.meta_level if previous else 0,
                reason=reason,
                uncontrolled=bundle.uncontrolled_spread(),
                restated=restated,
            )
        )
    return plans


def plan_meta(
    reports_dir: Path,
    domain: str,
    time_token: str,
    aggregation: Aggregation | str = CROSS_SYSTEM,
    min_participants: int = MIN_PARTICIPANTS,
) -> MetaPlan | None:
    """Convenience: the plan whose key mentions this domain, or ``None``."""
    for plan in plan_metas(reports_dir, aggregation, time_token, min_participants):
        if domain in plan.key or not plan.key:
            return plan
    return None


def stale_windows(
    reports_dir: Path, current_token: str, system: str | None = None
) -> list[ReportHeader]:
    """Audits belonging to an earlier window -- candidates for a refresh.

    They are not wrong and are not touched: a past window's audit stays as the
    record of that window, and only the machine that produced it may restate it.
    For a time series they are not stale at all -- they are the material.
    """
    return [
        header
        for header in list_reports(reports_dir, audit_mode=MODE_SELF)
        if header.time_token != current_token
        and (system is None or header.system == system)
    ]


@dataclass
class WriteOutcome:
    """Result of a guarded meta write."""

    written: bool
    reason: str
    path: Path | None = None


def write_meta(
    reports_dir: Path,
    header: ReportHeader,
    body: str,
    planned_inputs: list[str] | None = None,
) -> WriteOutcome:
    """Write a meta artefact, but never over a *newer* one.

    The gap this closes was reproduced on 2026-08-15: run A plans meta-3 from
    ``r1,r2,r3``; run B meanwhile sees ``r4``, plans and writes meta-4; then A
    writes its stale meta-3 over the same path. The published state loses ``r4``
    until somebody plans again.

    ``ACTION_SKIP`` cannot prevent this -- it only stops a run that *starts*
    after the newer artefact is already visible, not one that planned earlier
    and writes later. So the check has to happen at write time, against the file
    as it is *now*: if the artefact on disk rests on a superset of what we
    planned, our result is outdated and we do not write it.

    This is the honest correction to the idempotence argument: the
    classification is deterministic, but "deterministic" was never the same as
    "safe to write blindly".
    """
    directory = Path(reports_dir)
    target = directory / header.filename()
    planned = set(planned_inputs if planned_inputs is not None else header.inputs)

    if target.exists():
        from .report import read_report

        current = read_report(target)
        if current is not None:
            on_disk = set(current.inputs)
            if on_disk > planned:
                return WriteOutcome(
                    False,
                    f"artefact on disk already rests on {len(on_disk)} audits "
                    f"(we planned {len(planned)}) -- ours is stale, not written",
                    target,
                )
            if on_disk == planned and current.meta_level >= header.meta_level:
                return WriteOutcome(False, "artefact is already current", target)

    from .report import write_report

    return WriteOutcome(True, "written", write_report(directory, header, body))


def archive(path: Path, archive_dir: Path | None = None) -> Path | None:
    """Move an artefact aside. Not part of the normal flow.

    With the fixed key in the file name, history keeps itself; this exists for
    deliberate housekeeping of long-past windows, never for supersession.
    """
    source = Path(path)
    if not source.exists():
        return None
    target_dir = Path(archive_dir) if archive_dir else source.parent / ARCHIVE_DIRNAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    counter = 2
    while target.exists():
        target = target_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    shutil.move(str(source), str(target))
    return target
