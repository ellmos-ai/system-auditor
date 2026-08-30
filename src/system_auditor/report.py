"""Audit artefacts -- carriers of the four tokens.

Two kinds share one format:

``self``
    One auditor's audit of one domain on one machine in one period window.
    File name: ``AUDIT-<time>--<domain>.<system>[.<auditor>].md``
    (double hyphen between key components -- see ``meta_filename``)

``meta``
    A cross-cutting audit over the audits of one period window.
    File name: ``META-<kind>--<time>[--<scope>...].md`` -- **no host token.**

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

import hashlib
import re
import unicodedata
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .tokens import AuditIdentity, format_ts, parse_ts

SELF_FILENAME_RE = re.compile(
    r"^AUDIT-(?P<time>[A-Za-z0-9_-]+?)--(?P<domain>[A-Za-z0-9_-]+?)"
    r"\.(?P<system>[A-Za-z0-9_-]+?)(?:\.(?P<auditor>[A-Za-z0-9_.-]+?))?\.md$"
)
#: The aggregation name itself may contain hyphens ("timeseries-rater"), so the
#: file name is only recognised as *a* meta artefact here; which aggregation it
#: is comes from the header.
META_FILENAME_RE = re.compile(r"^META-(?P<body>.+)\.md$")
LEGACY_FILENAME_RE = re.compile(
    r"^(?:SIG-TU|AUDIT)-(?P<date>\d{8})-(?P<domain>[A-Za-z0-9_-]+)"
    r"(?:\.(?P<system>[A-Za-z0-9_-]+))?\.md$"
)

MODE_SELF = "self"
MODE_META = "meta"

UNSPECIFIED_AUDITOR = "unspecified"

#: The auditor could not be determined for this run. Deliberately distinct from
#: UNSPECIFIED: ".AI/GLOSSARY.md" separates "nothing found" (empty) from "could
#: not look" (unavailable), and this is the second. A model cannot introspect
#: its own deployment name -- it only knows what the harness told it -- so an
#: honest "unknown" beats a plausible guess. What it must never do is look like
#: a rater: see is_identified_auditor().
UNKNOWN_AUDITOR = "unknown"


def is_identified_auditor(token: str) -> bool:
    """Does this token name a model that can stand as its own rater?

    False for the empty string, for ``unspecified`` and for every ``unknown``
    form including the disambiguated ``unknown-<hash>``. The distinction is not
    cosmetic: an unidentified run may still be written and read, but it must not
    be counted as an independent voice in an interrater comparison -- two audits
    that agree because they came from the same model would otherwise read as
    agreement between two models.
    """
    value = (token or "").strip().casefold()
    if not value or value == UNSPECIFIED_AUDITOR:
        return False
    return not (value == UNKNOWN_AUDITOR or value.startswith(UNKNOWN_AUDITOR + "-"))

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
    # Without a closing delimiter the block is not front matter: reading on
    # would let body text overwrite header fields that already parsed fine.
    if "---" not in [line.strip() for line in lines[1:]]:
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


#: File-name components are joined with a DOUBLE hyphen while single hyphens
#: inside a component survive. Without that separation ``["a-b", "c"]`` and
#: ``["a", "b-c"]`` produce the same name and silently overwrite each other --
#: the invariant "same fixed key, same file" needs its converse to hold too.
_KEY_SEPARATOR = "--"


def _slug(text: str) -> str:
    """ASCII, filename-safe, and never containing the component separator.

    Folded to ASCII on purpose: ``_slug`` used to keep every character for which
    ``isalnum()`` is true, so a domain "muenchen" written with an umlaut
    produced a file the ASCII-only recognition regex could no longer read. The
    writer and the reader must speak the same language.
    """
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    keep = [char if (char.isalnum() or char in "-_") else "-" for char in ascii_only]
    slug = "".join(keep).strip("-")
    while "--" in slug:  # collapse, so "--" only ever appears as separator
        slug = slug.replace("--", "-")
    return slug or "x"


@dataclass
class ReportHeader:
    # --- the four tokens -------------------------------------------------
    domain: str
    system: str
    time_token: str = ""
    auditor: str = UNSPECIFIED_AUDITOR
    #: Start of the audit window in UTC. The token is an identity, not a
    #: timestamp: an explicit TimeTable may use "sprint-10", which sorts before
    #: "sprint-9". Chronology therefore follows this field, never the token.
    window_start_utc: datetime | None = None
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
        if self.window_start_utc:
            lines.append(f"window_start_utc: {format_ts(self.window_start_utc)}")
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
            return meta_filename(self.aggregation, self.scope)
        name = (
            "AUDIT-"
            + _KEY_SEPARATOR.join((_slug(self.time_token), _slug(self.domain)))
            + f".{_slug(self.system)}"
        )
        # An unidentified auditor used to be omitted from the name. That made
        # two unknown raters of the same window/domain/machine collide on one
        # filename, and write_report overwrites a repeated identity by design --
        # so the second audit silently deleted the first. Naming them apart
        # costs one path segment and keeps both.
        name += f".{_slug(self.auditor if is_identified_auditor(self.auditor) else self.unidentified_token())}"
        return name + ".md"

    def unidentified_token(self) -> str:
        """A distinct, *stable* stand-in for a run whose auditor is unknown.

        Stable matters twice over: a corrected rerun of the same audit must
        overwrite its own artefact (that is what write_report is for), while a
        different run must not. The run id is the natural seed; the start time
        is the fallback. With neither, the bare token is all that is honest --
        two such runs still collide, but nothing better is knowable.
        """
        given = (self.auditor or "").strip()
        if given.casefold().startswith(UNKNOWN_AUDITOR):
            return given
        seed = self.run_id or (self.started_utc.isoformat() if self.started_utc else "")
        if not seed:
            return UNKNOWN_AUDITOR
        return f"{UNKNOWN_AUDITOR}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


def meta_filename(aggregation: str, key: list[str]) -> str:
    """Stable name: one meta artefact per (aggregation, fixed key).

    ``key`` is the value of every dimension the aggregation holds fixed, in
    order -- which puts the period token in the name exactly when the period is
    fixed, and leaves it out for a time series that spans windows by design.

    Deliberately **without participant counts**: the level changes whenever a
    participant joins, and a changing name would defeat the overwrite rule that
    guarantees one current answer.  The counts live in the header and the title.
    Deliberately **without a host token**: otherwise every machine would keep
    its own copy of the one answer.
    """
    parts = [_slug(aggregation)]
    parts.extend(_slug(item) for item in key if item)
    return "META-" + _KEY_SEPARATOR.join(parts) + ".md"


def _as_int(value: object, default: int = 0) -> int:
    """Never let a malformed neighbour report abort the run.

    ``findings: nope`` used to raise straight through ``list_reports()``. The
    lock parser already skips broken foreign files; reports must follow the
    same fail-open rule.
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_text(value: object) -> str:
    """Empty scalars round-trip as ``[]`` through the minimal parser."""
    if isinstance(value, list):
        return ""
    return str(value)


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
        time_token = str(data.get("time_token", ""))
        aggregation = str(data.get("aggregation", ""))
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
        run_id=_as_text(data.get("run_id", "")),
        audit_mode=str(data.get("audit_mode", MODE_META if meta_match else MODE_SELF)),
        started_utc=_ts("started_utc"),
        finished_utc=finished,
        window_start_utc=_ts("window_start_utc"),
        next_domain=_as_text(data.get("next_domain", "")),
        findings=_as_int(data.get("findings")),
        measures=_as_list(data.get("measures")),
        evidence_level=_as_int(data.get("evidence_level"), 1),
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
    found = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        try:
            found.append(read_report(entry))
        except Exception:  # noqa: BLE001 - a hostile neighbour must not stop us
            continue
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
    if header.audit_mode != MODE_META and not is_identified_auditor(header.auditor):
        # This is the one moment the missing token has consequences, and it was
        # the one moment nothing said so: the CLI warned on every read-only
        # query instead. warnings, not stderr -- a library must not decide where
        # a caller's diagnostics go.
        warnings.warn(
            f"writing an audit without an identified auditor (filed as "
            f"{header.filename()}); it will not count as a rater in interrater "
            f"comparisons -- pass --auditor or set SYSTEM_AUDITOR_AUDITOR",
            stacklevel=2,
        )
    target.write_text(header.to_front_matter() + "\n" + body.rstrip() + "\n", encoding="utf-8")
    header.path = target
    return target
