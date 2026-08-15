"""Meta-audit lifecycle -- one current answer per period window.

Bundling rule, in the user's words: audits sharing a period token and a domain
token but differing in the system token trigger a meta audit for that domain.
Meta audits sharing a period token but differing in domain can in turn be
aggregated further.  The aggregation ladder is in :mod:`system_auditor.tokens`.

Two lifecycle properties follow from putting the period token in the file name:

* **Overwrite, don't archive.**  When a fourth machine joins, the meta audit for
  that window is rewritten in place.  "What do we know about this domain in this
  window" has one current answer; keeping meta-2 next to meta-3 would leave two
  answers to one question.
* **History is free.**  Last window is a different token, hence a different
  file, and stays untouched.  Nothing needs to be moved for the record to exist.

The only thing that overwrites a *single* audit is a restatement with the same
four tokens -- same period, domain, machine and auditor.  That is a correction,
and it forces the meta audit of that window to be rebuilt.
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
    time_token: str
    scope: list[str] = field(default_factory=list)
    level: int = 0
    participants: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    target: str = ""
    replaces: Path | None = None
    previous_level: int = 0
    reason: str = ""
    restated: list[str] = field(default_factory=list)

    @property
    def should_write(self) -> bool:
        return self.action in (ACTION_CREATE, ACTION_UPDATE)


def audit_ref(header: ReportHeader) -> str:
    """Stable reference of a single audit inside a meta bundle."""
    return header.run_id or (header.path.name if header.path else "")


def scope_of(aggregation: Aggregation, key: tuple[str, ...]) -> list[str]:
    """The fixed dimensions other than time -- what the meta audit is *about*."""
    return [
        value
        for dimension, value in zip(aggregation.fixed, key, strict=True)
        if dimension != DIM_TIME
    ]


def time_of(aggregation: Aggregation, key: tuple[str, ...]) -> str:
    for dimension, value in zip(aggregation.fixed, key, strict=True):
        if dimension == DIM_TIME:
            return value
    return ""


def current_single_audits(
    reports_dir: Path, time_token: str | None = None
) -> tuple[list[ReportHeader], list[str]]:
    """Single audits, deduplicated by identity (newest wins).

    Returns ``(current, restated)`` -- the second lists identities whose earlier
    statement was replaced by a newer one with the same four tokens.
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
    reports_dir: Path, aggregation: str, time_token: str, scope: list[str]
) -> ReportHeader | None:
    """The meta audit currently in force for exactly this window and scope."""
    wanted = meta_filename(aggregation, time_token, scope)
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
    """Which meta audits are due -- and for the rest, why not.

    One plan per bundle.  Bundles below ``min_participants`` are not returned as
    skips (they are simply not bundles yet); a skip means "this bundle exists
    and its meta audit is already current".
    """
    resolved = AGGREGATIONS[aggregation] if isinstance(aggregation, str) else aggregation
    current, restated = current_single_audits(reports_dir, time_token)
    by_identity = {header.identity: header for header in current}

    bundles: list[Bundle] = find_bundles(
        list(by_identity.keys()), resolved, min_participants=min_participants
    )

    plans: list[MetaPlan] = []
    for bundle in bundles:
        window = time_of(resolved, bundle.key)
        scope = scope_of(resolved, bundle.key)
        members = [by_identity[identity] for identity in bundle.identities]
        inputs = sorted(audit_ref(header) for header in members)
        previous = existing_meta(reports_dir, resolved.name, window, scope)

        if previous is not None and sorted(previous.inputs) == inputs:
            action, reason = ACTION_SKIP, (
                f"meta-{previous.meta_level} for this window already rests on "
                f"exactly these {len(inputs)} audits"
            )
        elif previous is not None:
            action, reason = ACTION_UPDATE, (
                f"participants changed: meta-{previous.meta_level} -> "
                f"meta-{bundle.level}; the window's meta audit is rewritten in place"
            )
        else:
            action, reason = ACTION_CREATE, (
                f"{bundle.level} participants in this window, no meta audit yet"
            )

        plans.append(
            MetaPlan(
                action=action,
                aggregation=resolved.name,
                time_token=window,
                scope=scope,
                level=bundle.level,
                participants=bundle.varying_values,
                inputs=inputs,
                target=meta_filename(resolved.name, window, scope),
                replaces=previous.path if previous else None,
                previous_level=previous.meta_level if previous else 0,
                reason=reason,
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
    """Convenience: the plan for one domain in one window, or ``None``."""
    for plan in plan_metas(reports_dir, aggregation, time_token, min_participants):
        if domain in plan.scope or not plan.scope:
            return plan
    return None


def stale_windows(
    reports_dir: Path, current_token: str, system: str | None = None
) -> list[ReportHeader]:
    """Audits belonging to an earlier window -- candidates for a refresh.

    They are not wrong and are not touched: a past window's audit stays as the
    record of that window.  It simply cannot contribute to the current one, and
    only the machine that produced it may restate it.
    """
    return [
        header
        for header in list_reports(reports_dir, audit_mode=MODE_SELF)
        if header.time_token != current_token
        and (system is None or header.system == system)
    ]


def archive(path: Path, archive_dir: Path | None = None) -> Path | None:
    """Move an artefact aside. Not part of the normal flow.

    With the period token in the file name, history keeps itself; this exists
    for deliberate housekeeping of long-past windows, never for supersession.
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
