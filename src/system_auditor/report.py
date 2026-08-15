"""Audit artefacts -- carriers of the four tokens.

Two kinds share one format:

``self``
    One auditor's audit of one domain on one machine in one period window.
    File name: ``AUDIT-<time>-<domain>.<system>[.<auditor>].md``

``meta``
    A cross-cutting audit over the audits of one period window.
    File name: ``META-<kind>-<time>[-<scope>...].md`` -- **no host token.**

**Why the meta file carries no host.**  There is exactly one meta audit per
(period, scope, aggregation).  When a fourth machine joins, the meta audit for
that window is *overwritten*, not placed beside its predecessor: the statement
"what do we know about this domain in this window" has one current answer.  The
author is recorded in the header, not in the name -- otherwise every machine
would keep its own copy and the single answer would fragment into N.

**Why archiving is barely needed.**  The period token is part of the name, so
last window's meta audit is already a different file and stays as history by
itself.  Only a *restatement* -- same four tokens -- overwrites, and that is
what a correction should do.

The front matter exists so nothing has to be guessed.  Two ways of guessing were
measured on 2026-08-15 and both fail: within one day, alphabetical file order is
not chronological, and mtime is unreliable across a synchronised folder (all
three reports of that day carried a "created" stamp *after* their "modified"
stamp).  So each run states its own ``finished_utc``.

Legacy ``SIG-TU-*.md`` reports without front matter are still read and flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .audit_lock import format_ts, parse_ts
from .tokens import AuditIdentity

SELF_FILENAME_RE = re.compile(
    r"^AUDIT-(?P<time>[A-Za-z0-9]+)-(?P<domain>[A-Za-z0-9_-]+)"
    r"\.(?P<system>[A-Za-z0-9_-]+)(?:\.(?P<auditor>[A-Za-z0-9_.-]+?))?\.md$"
)
META_FILENAME_RE = re.compile(
    r"^META-(?P<kind>[a-z-]+)-(?P<time>[A-Za-z0-9]+)(?:-(?P<scope>.+?))?\.md$"
)
LEGACY_FILENAME_RE = re.compile(
    r"^(?:SIG-TU|AUDIT)-(?P<date>\d{8})-(?P<domain>[A-Za-z0-9_-]+)"
    r"(?:\.(?P<system>[A-Za-z0-9_-]+))?\.md$"
)

MODE_SELF = "self"
MODE_META = "meta"

UNSPECIFIED_AUDITOR = "unspecified"

#: 1 = read the domain directly · 2 = a system map narrowed the search
#: 3 = additionally backed by receipts.  Declared per run so a later, deeper
#: pass reads as an improvement rather than a contradiction.
EVIDENCE_LEVELS = (1, 2, 3)


def _parse_scalar(raw: str) -> object:
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]
    if text.isdigit():
        return int(text)
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    return text.strip("'\"")


def parse_front_matter(text: str) -> dict:
    """Minimal flat YAML front matter reader (no PyYAML dependency).

    Supports ``key: value``, inline lists ``key: [a, b]`` and ``- item`` blocks.
    That is all the format uses; anything richer would invite drift between what
    the spec promises and what this parser accepts.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict = {}
    current_key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("- ") or line.startswith("  - "):
            if current_key is not None:
                data.setdefault(current_key, [])
                if isinstance(data[current_key], list):
                    data[current_key].append(line.split("- ", 1)[1].strip().strip("'\""))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not value.strip():
            data[key] = []
            current_key = key
            continue
        data[key] = _parse_scalar(value)
        current_key = key
    return data


def _slug(text: str) -> str:
    keep = [char if (char.isalnum() or char in "-_") else "-" for char in str(text)]
    return "".join(keep).strip("-") or "x"


@dataclass
class ReportHeader:
    # --- the four tokens -------------------------------------------------
    domain: str
    system: str
    time_token: str = ""
    auditor: str = UNSPECIFIED_AUDITOR
    # --- run data --------------------------------------------------------
    run_id: str = ""
    audit_mode: str = MODE_SELF
    started_utc: datetime | None = None
    finished_utc: datetime | None = None
    next_domain: str = ""
    findings: int = 0
    measures: list[str] = field(default_factory=list)
    evidence_level: int = 1
    #: Path prefixes actually looked at.  Without this a meta audit cannot tell
    #: "checked here and found nothing" from "never looked" -- and would invent
    #: differences between participants.
    coverage: list[str] = field(default_factory=list)
    #: Locators explicitly confirmed as fine.  Evidence for the INVERSE class.
    clean: list[str] = field(default_factory=list)
    # --- meta only -------------------------------------------------------
    aggregation: str = ""
    meta_level: int = 0
    participants: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    # --- housekeeping ----------------------------------------------------
    legacy: bool = False
    path: Path | None = field(default=None, compare=False)

    @property
    def identity(self) -> AuditIdentity:
        return AuditIdentity(
            time=self.time_token,
            domain=self.domain,
            system=self.system,
            auditor=self.auditor or UNSPECIFIED_AUDITOR,
        )

    @property
    def sort_key(self) -> datetime:
        return self.finished_utc or self.started_utc or datetime.min.replace(
            tzinfo=timezone.utc
        )

    def to_front_matter(self) -> str:
        lines = [
            "---",
            f"run_id: {self.run_id}",
            f"audit_mode: {self.audit_mode}",
            f"time_token: {self.time_token}",
            f"domain: {self.domain}",
            f"system: {self.system}",
            f"auditor: {self.auditor}",
        ]
        if self.started_utc:
            lines.append(f"started_utc: {format_ts(self.started_utc)}")
        if self.finished_utc:
            lines.append(f"finished_utc: {format_ts(self.finished_utc)}")
        if self.audit_mode == MODE_META:
            lines.append(f"aggregation: {self.aggregation}")
            lines.append(f"meta_level: {self.meta_level}")
            lines.append(f"participants: [{', '.join(self.participants)}]")
            lines.append(f"inputs: [{', '.join(self.inputs)}]")
            lines.append(f"scope: [{', '.join(self.scope)}]")
        else:
            lines.append(f"next_domain: {self.next_domain}")
        lines.append(f"findings: {self.findings}")
        lines.append(f"measures: [{', '.join(self.measures)}]")
        lines.append(f"evidence_level: {self.evidence_level}")
        lines.append(f"coverage: [{', '.join(self.coverage)}]")
        lines.append(f"clean: [{', '.join(self.clean)}]")
        lines.append("---")
        return "\n".join(lines) + "\n"

    def filename(self) -> str:
        if self.audit_mode == MODE_META:
            return meta_filename(self.aggregation, self.time_token, self.scope)
        name = f"AUDIT-{_slug(self.time_token)}-{_slug(self.domain)}.{_slug(self.system)}"
        if self.auditor and self.auditor != UNSPECIFIED_AUDITOR:
            name += f".{_slug(self.auditor)}"
        return name + ".md"


def meta_filename(aggregation: str, time_token: str, scope: list[str]) -> str:
    """Stable name: one meta audit per (period, scope, aggregation).

    Deliberately without a host token -- a newer, higher-level meta audit
    *overwrites* its predecessor for the same window instead of joining it.
    """
    parts = [f"META-{_slug(aggregation)}-{_slug(time_token)}"]
    parts.extend(_slug(item) for item in scope if item)
    return "-".join(parts) + ".md"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def read_report(path: Path) -> ReportHeader | None:
    """Read one artefact. Returns ``None`` for files that are not audits."""
    path = Path(path)
    self_match = SELF_FILENAME_RE.match(path.name)
    meta_match = None if self_match else META_FILENAME_RE.match(path.name)
    legacy_match = None if (self_match or meta_match) else LEGACY_FILENAME_RE.match(path.name)
    if not (self_match or meta_match or legacy_match):
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    data = parse_front_matter(text)

    def _ts(key: str) -> datetime | None:
        raw = data.get(key)
        if not raw:
            return None
        try:
            return parse_ts(str(raw))
        except Exception:
            return None

    legacy = bool(legacy_match) or not data
    finished = _ts("finished_utc")
    if finished is None and legacy_match:
        # The file name carries the date but no time. Use the end of that day so
        # a legacy report never outranks a dated one from the same day.
        finished = datetime.strptime(legacy_match.group("date"), "%Y%m%d").replace(
            hour=23, minute=59, second=0, tzinfo=timezone.utc
        )
        legacy = True

    if meta_match:
        domain = str(data.get("domain", ""))
        system = str(data.get("system", ""))
        time_token = str(data.get("time_token") or meta_match.group("time"))
        aggregation = str(data.get("aggregation") or meta_match.group("kind"))
    else:
        name_match = self_match or legacy_match
        domain = str(data.get("domain") or name_match.group("domain"))
        system = str(data.get("system") or (name_match.groupdict().get("system") or "unknown"))
        time_token = str(
            data.get("time_token")
            or (self_match.group("time") if self_match else legacy_match.group("date"))
        )
        aggregation = ""

    auditor = str(
        data.get("auditor")
        or (self_match.groupdict().get("auditor") if self_match else "")
        or UNSPECIFIED_AUDITOR
    )

    return ReportHeader(
        domain=domain,
        system=system,
        time_token=time_token,
        auditor=auditor,
        run_id=str(data.get("run_id", "")),
        audit_mode=str(data.get("audit_mode", MODE_META if meta_match else MODE_SELF)),
        started_utc=_ts("started_utc"),
        finished_utc=finished,
        next_domain=str(data.get("next_domain", "")),
        findings=int(data.get("findings", 0) or 0),
        measures=_as_list(data.get("measures")),
        evidence_level=int(data.get("evidence_level", 1) or 1),
        coverage=_as_list(data.get("coverage")),
        clean=_as_list(data.get("clean")),
        aggregation=aggregation,
        meta_level=int(data.get("meta_level", 0) or 0),
        participants=_as_list(data.get("participants")),
        inputs=_as_list(data.get("inputs")),
        scope=_as_list(data.get("scope")),
        legacy=legacy,
        path=path,
    )


def list_reports(reports_dir: Path, audit_mode: str | None = None) -> list[ReportHeader]:
    directory = Path(reports_dir)
    if not directory.is_dir():
        return []
    found = [read_report(entry) for entry in sorted(directory.iterdir()) if entry.is_file()]
    reports = [item for item in found if item is not None]
    if audit_mode is not None:
        reports = [item for item in reports if item.audit_mode == audit_mode]
    return sorted(reports, key=lambda item: item.sort_key)


def latest_report(
    reports_dir: Path,
    domain: str | None = None,
    system: str | None = None,
    audit_mode: str | None = MODE_SELF,
) -> ReportHeader | None:
    candidates = list_reports(reports_dir, audit_mode=audit_mode)
    if domain is not None:
        candidates = [item for item in candidates if item.domain == domain]
    if system is not None:
        candidates = [item for item in candidates if item.system == system]
    return candidates[-1] if candidates else None


def next_domain(domains: list[str], reports_dir: Path, system: str | None = None) -> str:
    """Next domain in the rotation.

    ``system`` narrows the anchor to one machine's own history: several machines
    legitimately audit the same domain, so a foreign run must not push this one
    forward in its own cycle.
    """
    if not domains:
        raise ValueError("rotation needs at least one domain")
    last = latest_report(reports_dir, system=system)
    if last is None:
        return domains[0]
    if last.next_domain and last.next_domain in domains:
        return last.next_domain
    if last.domain not in domains:
        return domains[0]
    return domains[(domains.index(last.domain) + 1) % len(domains)]


def write_report(reports_dir: Path, header: ReportHeader, body: str) -> Path:
    """Write an artefact, overwriting a restatement of the same identity.

    Overwriting is intended: a repeated audit with identical tokens is a
    correction of the same statement, and a meta audit for a window has one
    current answer.
    """
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / header.filename()
    target.write_text(header.to_front_matter() + "\n" + body.rstrip() + "\n", encoding="utf-8")
    header.path = target
    return target
