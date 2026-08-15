"""Audit artefacts -- the trail, the rotation anchor and the meta input.

Two kinds of artefact share one format:

``self``
    One system's audit of one domain.  Carries a validity window: an audit is a
    statement about a moment, and a statement about last month must not be
    bundled with one from today as if both were current.

``meta``
    A cross-system audit over the *valid* single audits of one domain.  Named
    by its level -- ``meta-2`` for two participating systems, ``meta-3`` for
    three -- because the level says how much cross-checking the statement rests
    on.

A small flat front matter block carries the machine-readable part.  It exists
for one concrete reason: rotation and meta bundling must not guess.  Two ways of
guessing were measured on 2026-08-15 and both fail:

* **by file name** -- within one day, alphabetical order is not chronological
  (``ai-modules-memory`` < ``control-center`` < ``sync-register`` while the real
  order was the reverse);
* **by mtime** -- unreliable across a synchronised folder; all three reports of
  that day carried a "created" stamp *after* their "modified" stamp, because the
  sync materialised them locally in a different order.

So each run states its own ``finished_utc`` and ``valid_until``.

Legacy ``SIG-TU-<date>-<area>.md`` reports (no host token, no front matter) are
still read, flagged ``legacy``, and dated from the file name so the changeover
does not break the rotation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .audit_lock import format_ts, parse_ts, utcnow

REPORT_PREFIX = "AUDIT"
META_PREFIX = "META"

REPORT_FILENAME_RE = re.compile(
    r"^AUDIT-(?P<date>\d{8})-(?P<area>[A-Za-z0-9_-]+)\.(?P<host>[A-Za-z0-9_-]+)\.md$"
)
META_FILENAME_RE = re.compile(
    r"^META-(?P<level>\d+)-(?P<date>\d{8})-(?P<area>[A-Za-z0-9_-]+)\.(?P<host>[A-Za-z0-9_-]+)\.md$"
)
LEGACY_FILENAME_RE = re.compile(
    r"^SIG-TU-(?P<date>\d{8})-(?P<area>[A-Za-z0-9_-]+)(?:\.(?P<host>[A-Za-z0-9_-]+))?\.md$"
)

MODE_SELF = "self"
MODE_META = "meta"

#: 1 = read the area directly · 2 = a system map narrowed the search
#: 3 = additionally backed by receipts.  Declared per run so a later, deeper
#: pass reads as an improvement rather than a contradiction.
EVIDENCE_LEVELS = (1, 2, 3)

DEFAULT_VALIDITY = "14d"
_DURATION_RE = re.compile(r"^\s*(\d+)\s*([dhm])\s*$", re.IGNORECASE)


def parse_validity(raw: str) -> timedelta:
    match = _DURATION_RE.match(raw or "")
    if not match:
        raise ValueError(f"unparsable validity: {raw!r}")
    amount, unit = int(match.group(1)), match.group(2).lower()
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(minutes=amount)


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


@dataclass
class ReportHeader:
    area: str
    host: str
    run_id: str = ""
    audit_mode: str = MODE_SELF
    started_utc: datetime | None = None
    finished_utc: datetime | None = None
    valid_until: datetime | None = None
    next_area: str = ""
    findings: int = 0
    measures: list[str] = field(default_factory=list)
    evidence_level: int = 1
    #: Path prefixes actually looked at.  Without this a meta audit cannot tell
    #: "that system checked here and found nothing" from "it never looked" --
    #: and would invent differences between systems.
    coverage: list[str] = field(default_factory=list)
    #: Locators explicitly confirmed as fine.  Evidence for the INVERSE class.
    clean: list[str] = field(default_factory=list)
    #: meta only: run_ids of the single audits this meta audit rests on.
    inputs: list[str] = field(default_factory=list)
    meta_level: int = 0
    superseded_by: str = ""
    legacy: bool = False
    path: Path | None = field(default=None, compare=False)

    @property
    def sort_key(self) -> datetime:
        return self.finished_utc or self.started_utc or datetime.min.replace(
            tzinfo=timezone.utc
        )

    def expiry(self, validity: str = DEFAULT_VALIDITY) -> datetime:
        if self.valid_until:
            return self.valid_until
        base = self.finished_utc or self.started_utc or utcnow()
        return base + parse_validity(validity)

    def is_valid(self, now: datetime | None = None, validity: str = DEFAULT_VALIDITY) -> bool:
        """A stale audit is not wrong -- it is merely no longer a statement
        about the current system, and must not enter a meta bundle."""
        return (now or utcnow()) <= self.expiry(validity)

    def to_front_matter(self) -> str:
        lines = ["---", f"run_id: {self.run_id}", f"area: {self.area}", f"host: {self.host}"]
        lines.append(f"audit_mode: {self.audit_mode}")
        if self.started_utc:
            lines.append(f"started_utc: {format_ts(self.started_utc)}")
        if self.finished_utc:
            lines.append(f"finished_utc: {format_ts(self.finished_utc)}")
        if self.valid_until:
            lines.append(f"valid_until: {format_ts(self.valid_until)}")
        if self.audit_mode == MODE_META:
            lines.append(f"meta_level: {self.meta_level}")
            lines.append(f"inputs: [{', '.join(self.inputs)}]")
        else:
            lines.append(f"next_area: {self.next_area}")
        lines.append(f"findings: {self.findings}")
        lines.append(f"measures: [{', '.join(self.measures)}]")
        lines.append(f"evidence_level: {self.evidence_level}")
        lines.append(f"coverage: [{', '.join(self.coverage)}]")
        lines.append(f"clean: [{', '.join(self.clean)}]")
        if self.superseded_by:
            lines.append(f"superseded_by: {self.superseded_by}")
        lines.append("---")
        return "\n".join(lines) + "\n"

    def filename(self) -> str:
        stamp = (self.finished_utc or self.started_utc or utcnow()).strftime("%Y%m%d")
        if self.audit_mode == MODE_META:
            return f"{META_PREFIX}-{self.meta_level}-{stamp}-{self.area}.{self.host}.md"
        return f"{REPORT_PREFIX}-{stamp}-{self.area}.{self.host}.md"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def read_report(path: Path) -> ReportHeader | None:
    """Read one artefact. Returns ``None`` for files that are not audits."""
    path = Path(path)
    match = REPORT_FILENAME_RE.match(path.name)
    meta_match = None if match else META_FILENAME_RE.match(path.name)
    legacy_match = None if (match or meta_match) else LEGACY_FILENAME_RE.match(path.name)
    name_match = match or meta_match or legacy_match
    if name_match is None:
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    data = parse_front_matter(text)

    area = str(data.get("area") or name_match.group("area"))
    host = str(data.get("host") or (name_match.groupdict().get("host") or "unknown"))

    def _ts(key: str) -> datetime | None:
        raw = data.get(key)
        if not raw:
            return None
        try:
            return parse_ts(str(raw))
        except Exception:
            return None

    finished = _ts("finished_utc")
    legacy = bool(legacy_match) or not data
    if finished is None:
        # Legacy fallback: the file name carries the date but no time. Use the
        # end of that day so a legacy report never outranks a dated one from the
        # same day, and mark the run as legacy.
        stamp = name_match.group("date")
        finished = datetime.strptime(stamp, "%Y%m%d").replace(
            hour=23, minute=59, second=0, tzinfo=timezone.utc
        )
        legacy = True

    mode = str(data.get("audit_mode", MODE_META if meta_match else MODE_SELF))
    meta_level = int(data.get("meta_level", 0) or 0)
    if meta_match and not meta_level:
        meta_level = int(meta_match.group("level"))

    return ReportHeader(
        area=area,
        host=host,
        run_id=str(data.get("run_id", "")),
        audit_mode=mode,
        started_utc=_ts("started_utc"),
        finished_utc=finished,
        valid_until=_ts("valid_until"),
        next_area=str(data.get("next_area", "")),
        findings=int(data.get("findings", 0) or 0),
        measures=_as_list(data.get("measures")),
        evidence_level=int(data.get("evidence_level", 1) or 1),
        coverage=_as_list(data.get("coverage")),
        clean=_as_list(data.get("clean")),
        inputs=_as_list(data.get("inputs")),
        meta_level=meta_level,
        superseded_by=str(data.get("superseded_by", "")),
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
    area: str | None = None,
    host: str | None = None,
    audit_mode: str | None = MODE_SELF,
) -> ReportHeader | None:
    candidates = list_reports(reports_dir, audit_mode=audit_mode)
    if area is not None:
        candidates = [item for item in candidates if item.area == area]
    if host is not None:
        candidates = [item for item in candidates if item.host == host]
    return candidates[-1] if candidates else None


def next_area(areas: list[str], reports_dir: Path, host: str | None = None) -> str:
    """Next domain in the rotation.

    ``host`` narrows the anchor to one system's own history.  That matters now
    that several systems legitimately audit the same domain: each walks its own
    cycle instead of being pushed forward by a foreign run.
    """
    if not areas:
        raise ValueError("rotation needs at least one area")
    last = latest_report(reports_dir, host=host)
    if last is None:
        return areas[0]
    if last.next_area and last.next_area in areas:
        return last.next_area
    if last.area not in areas:
        return areas[0]
    return areas[(areas.index(last.area) + 1) % len(areas)]


def write_report(reports_dir: Path, header: ReportHeader, body: str) -> Path:
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / header.filename()
    target.write_text(header.to_front_matter() + "\n" + body.rstrip() + "\n", encoding="utf-8")
    header.path = target
    return target
