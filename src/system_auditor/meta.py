"""Meta-audit lifecycle -- validity, bundling, supersession.

The rule this implements, in the user's words: valid single audits of one domain
whose validity windows *overlap* are processed into a meta audit; stale ones are
not used.  A later system that adds its own audit builds the next, higher meta
level and replaces the previous one.

    system A audits `ai-bundles`                        -> single audit
    system B audits `ai-bundles`, sees A's              -> meta-2
    system C audits `ai-bundles`, sees meta-2 + 3 singles -> meta-3,
                                                            meta-2 archived

Two properties make this safe rather than merely clever:

* **Validity is explicit.** An audit is a statement about a moment. Bundling a
  statement from last month with one from today would fabricate a "difference
  between systems" that is really a difference in time. Stale audits are
  excluded and the exclusion is named in the plan, never silent.
* **Renewal belongs to the bearer.** A stale audit is refreshed by the system
  that produced it -- no other system can honestly restate what that machine
  saw. The old one is archived, not deleted.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .audit_lock import utcnow
from .report import (
    DEFAULT_VALIDITY,
    MODE_META,
    MODE_SELF,
    ReportHeader,
    list_reports,
)

ARCHIVE_DIRNAME = "_archive"
MIN_PARTICIPANTS = 2


@dataclass
class MetaPlan:
    """What a meta run should do -- decided before anything is written."""

    action: str  # "create" | "skip"
    area: str
    reason: str
    level: int = 0
    participants: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    supersedes: Path | None = None
    stale_excluded: list[str] = field(default_factory=list)
    renew_needed: list[str] = field(default_factory=list)

    @property
    def should_create(self) -> bool:
        return self.action == "create"


def _run_ref(header: ReportHeader) -> str:
    """Stable reference for a single audit inside a meta bundle."""
    return header.run_id or (header.path.name if header.path else f"{header.host}:{header.area}")


def valid_single_audits(
    reports_dir: Path,
    area: str,
    now: datetime | None = None,
    validity: str = DEFAULT_VALIDITY,
) -> tuple[list[ReportHeader], list[ReportHeader]]:
    """Current single audits of one domain, one per system.

    Returns ``(valid, stale)``.  Per system only the newest audit counts -- an
    older one from the same machine is superseded by its own successor, not a
    second opinion.
    """
    moment = now or utcnow()
    newest_per_host: dict[str, ReportHeader] = {}
    for header in list_reports(reports_dir, audit_mode=MODE_SELF):
        if header.area != area or header.superseded_by:
            continue
        current = newest_per_host.get(header.host)
        if current is None or header.sort_key > current.sort_key:
            newest_per_host[header.host] = header

    valid: list[ReportHeader] = []
    stale: list[ReportHeader] = []
    for header in sorted(newest_per_host.values(), key=lambda item: item.host):
        (valid if header.is_valid(moment, validity) else stale).append(header)
    return valid, stale


def current_meta(reports_dir: Path, area: str) -> ReportHeader | None:
    """The meta audit currently in force for a domain (highest level, newest)."""
    candidates = [
        header
        for header in list_reports(reports_dir, audit_mode=MODE_META)
        if header.area == area and not header.superseded_by
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.meta_level, item.sort_key))
    return candidates[-1]


def plan_meta(
    reports_dir: Path,
    area: str,
    now: datetime | None = None,
    validity: str = DEFAULT_VALIDITY,
    host: str | None = None,
    min_participants: int = MIN_PARTICIPANTS,
) -> MetaPlan:
    """Decide whether a new meta audit is due -- and say why, either way."""
    moment = now or utcnow()
    valid, stale = valid_single_audits(reports_dir, area, moment, validity)
    stale_refs = [f"{item.host} ({_run_ref(item)})" for item in stale]
    renew = [item.host for item in stale if host and item.host == host]

    inputs = sorted(_run_ref(item) for item in valid)
    participants = sorted(item.host for item in valid)
    existing = current_meta(reports_dir, area)

    if len(valid) < min_participants:
        return MetaPlan(
            action="skip",
            area=area,
            reason=(
                f"only {len(valid)} valid single audit(s); "
                f"a meta audit needs {min_participants}"
            ),
            participants=participants,
            inputs=inputs,
            stale_excluded=stale_refs,
            renew_needed=renew,
        )

    if existing is not None and sorted(existing.inputs) == inputs:
        return MetaPlan(
            action="skip",
            area=area,
            reason=(
                f"meta-{existing.meta_level} already rests on exactly these "
                f"{len(inputs)} audits"
            ),
            level=existing.meta_level,
            participants=participants,
            inputs=inputs,
            stale_excluded=stale_refs,
            renew_needed=renew,
        )

    reason = f"{len(valid)} valid single audits available"
    if existing is not None:
        reason += (
            f"; supersedes meta-{existing.meta_level} "
            f"(rested on {len(existing.inputs)})"
        )
    return MetaPlan(
        action="create",
        area=area,
        reason=reason,
        level=len(valid),
        participants=participants,
        inputs=inputs,
        supersedes=existing.path if existing else None,
        stale_excluded=stale_refs,
        renew_needed=renew,
    )


def archive(path: Path, archive_dir: Path | None = None) -> Path | None:
    """Move an artefact out of the active set. Never deletes.

    History is the point: a superseded meta audit documents what was known at
    the time, and a renewed single audit documents what that system saw before.
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


def mark_superseded(header: ReportHeader, successor: str) -> bool:
    """Note the successor inside the artefact before archiving it."""
    if header.path is None or not header.path.exists():
        return False
    text = header.path.read_text(encoding="utf-8")
    if "superseded_by:" in text:
        return False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            lines.insert(index, f"superseded_by: {successor}")
            break
    header.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def supersede(
    previous: ReportHeader, successor_name: str, archive_dir: Path | None = None
) -> Path | None:
    """Retire the previous meta audit in favour of a new, higher one."""
    mark_superseded(previous, successor_name)
    return archive(previous.path, archive_dir) if previous.path else None


def renew_own_audits(
    reports_dir: Path,
    area: str,
    host: str,
    now: datetime | None = None,
    validity: str = DEFAULT_VALIDITY,
    archive_dir: Path | None = None,
) -> list[Path]:
    """Archive this system's own stale audits of a domain.

    Only its own: no system may retire another's statement about a machine it
    cannot see.
    """
    moment = now or utcnow()
    archived: list[Path] = []
    for header in list_reports(reports_dir, audit_mode=MODE_SELF):
        if header.area != area or header.host != host:
            continue
        if header.is_valid(moment, validity):
            continue
        moved = archive(header.path, archive_dir) if header.path else None
        if moved:
            archived.append(moved)
    return archived
