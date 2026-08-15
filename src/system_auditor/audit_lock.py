"""Audit-Host-Lock — presence signalling and (only where needed) reservation.

Two distinct semantics share one file format:

``presence``
    "A self-audit of this area is running on host X."  Informational only.
    A presence lock is **never** a reason to skip an area: two hosts auditing
    the same area produce two legitimate, differing results, because each host
    sees its own reality.  The lock exists so an auditor can *notice* the other
    and schedule a comparative audit afterwards.

``claim``
    "I am comparing host A against host B for this area."  Here redundancy is
    genuinely worthless -- two comparisons of the same pairing say the same
    thing -- so claims are mutually exclusive and resolved by the deterministic
    loser-rule in :func:`resolve_claim`.

The file name follows the ecosystem-wide lock grammar
(``^LOCK(\\.[A-Za-z0-9_-]+)*\\.txt$``) so existing scanners see these files
without any code change.  ``mode`` and ``advisory_for`` inside tell every other
agent that this lock does not block their work.

Zero dependencies: plain text, standard library only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCK_FILENAME_RE = re.compile(
    r"^LOCK\.audit\.(?P<area>[A-Za-z0-9_-]+)\.(?P<host>[A-Za-z0-9_-]+)\.txt$"
)

MODE_PRESENCE = "presence"
MODE_CLAIM = "claim"
VALID_MODES = (MODE_PRESENCE, MODE_CLAIM)

ADVISORY_FOR = "system-auditor"
DEFAULT_EXPIRES = "2h"

# Deviation from the base LOCK format, deliberate and documented in
# protocols/audit-host-lock/SPEC.md: `created` is second-granular.  The base
# format is minute-granular, which would push most same-minute races into the
# host tiebreak -- and there the same host would lose structurally, every time.
# The prefix stays identical, so minute-granular parsers still read it.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([hm])\s*$", re.IGNORECASE)


class LockError(RuntimeError):
    """Raised when a lock cannot be written or parsed."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT) + "Z"


def parse_ts(raw: str) -> datetime:
    text = raw.strip().rstrip("Z")
    for fmt in (TIMESTAMP_FORMAT, "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise LockError(f"unparsable timestamp: {raw!r}")


def parse_duration(raw: str) -> timedelta:
    match = _DURATION_RE.match(raw or "")
    if not match:
        raise LockError(f"unparsable duration: {raw!r}")
    amount, unit = int(match.group(1)), match.group(2).lower()
    return timedelta(hours=amount) if unit == "h" else timedelta(minutes=amount)


@dataclass
class AuditLock:
    area: str
    host: str
    mode: str
    run_id: str
    created: datetime
    expires_after: str = DEFAULT_EXPIRES
    phase: str = ""
    area_path: str = ""
    purpose: str = ""
    compares: str = ""
    path: Path | None = field(default=None, compare=False)

    @property
    def filename(self) -> str:
        return f"LOCK.audit.{self.area}.{self.host}.txt"

    @property
    def expires_at(self) -> datetime:
        return self.created + parse_duration(self.expires_after)

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or utcnow()) > self.expires_at

    def is_advisory(self) -> bool:
        """True when this lock must not stop anybody from working."""
        return self.mode == MODE_PRESENCE

    def to_text(self) -> str:
        lines = [
            "# Audit-Host-Lock -- protocols/audit-host-lock/SPEC.md",
            "# ADVISORY: this lock does not block work in the audited area.",
            "",
            f"owner: {ADVISORY_FOR}",
            f"host: {self.host}",
            f"created: {format_ts(self.created)}",
            f"expires_after: {self.expires_after}",
            "mode: soft",
            f"advisory_for: {ADVISORY_FOR}",
            "",
            f"audit_mode: {self.mode}",
            f"area: {self.area}",
            f"area_path: {self.area_path}",
            f"run_id: {self.run_id}",
            f"phase: {self.phase}",
        ]
        if self.compares:
            lines.append(f"compares: {self.compares}")
        if self.purpose:
            lines.append(f"purpose: {self.purpose}")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_text(cls, text: str, path: Path | None = None) -> AuditLock:
        fields: dict[str, str] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            fields[key.strip()] = value.strip()

        area = fields.get("area", "")
        host = fields.get("host", "")
        if path is not None:
            match = LOCK_FILENAME_RE.match(path.name)
            if match:
                # The filename is authoritative for scope, exactly as in the
                # ecosystem lock spec; the body fields are informational.
                area = match.group("area")
                host = match.group("host")
        if not area or not host:
            raise LockError("lock is missing area/host")

        mode = fields.get("audit_mode", MODE_PRESENCE)
        if mode not in VALID_MODES:
            raise LockError(f"unknown audit_mode: {mode!r}")

        return cls(
            area=area,
            host=host,
            mode=mode,
            run_id=fields.get("run_id", ""),
            created=parse_ts(fields.get("created", "")),
            expires_after=fields.get("expires_after", DEFAULT_EXPIRES),
            phase=fields.get("phase", ""),
            area_path=fields.get("area_path", ""),
            purpose=fields.get("purpose", ""),
            compares=fields.get("compares", ""),
            path=path,
        )


@dataclass
class ClaimResult:
    won: bool
    reason: str
    winner: AuditLock | None = None
    competitors: list[AuditLock] = field(default_factory=list)


def read_lock(path: Path) -> AuditLock:
    return AuditLock.from_text(Path(path).read_text(encoding="utf-8"), Path(path))


def list_locks(
    locks_dir: Path,
    area: str | None = None,
    mode: str | None = None,
    include_expired: bool = False,
    now: datetime | None = None,
) -> list[AuditLock]:
    """All readable audit locks, newest-irrelevant, sorted by ``created``.

    Unparsable files are skipped rather than raising: a broken foreign lock must
    never stop this host from working.
    """
    directory = Path(locks_dir)
    if not directory.is_dir():
        return []
    moment = now or utcnow()
    found: list[AuditLock] = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not LOCK_FILENAME_RE.match(entry.name):
            continue
        try:
            lock = read_lock(entry)
        except (LockError, OSError, UnicodeDecodeError):
            continue
        if area is not None and lock.area != area:
            continue
        if mode is not None and lock.mode != mode:
            continue
        if not include_expired and lock.is_expired(moment):
            continue
        found.append(lock)
    return sorted(found, key=lambda item: (item.created, item.host))


def write_lock(
    locks_dir: Path,
    area: str,
    host: str,
    mode: str,
    run_id: str,
    area_path: str = "",
    phase: str = "",
    purpose: str = "",
    compares: str = "",
    expires_after: str = DEFAULT_EXPIRES,
    created: datetime | None = None,
) -> AuditLock:
    """Write our own lock, exclusively.

    An existing lock of the *same* host is replaced only when it has expired --
    otherwise a second local session would silently steal the first one's run.
    A foreign lock is never touched.
    """
    if mode not in VALID_MODES:
        raise LockError(f"unknown mode: {mode!r}")
    directory = Path(locks_dir)
    directory.mkdir(parents=True, exist_ok=True)

    lock = AuditLock(
        area=area,
        host=host,
        mode=mode,
        run_id=run_id,
        created=created or utcnow(),
        expires_after=expires_after,
        phase=phase or mode,
        area_path=area_path,
        purpose=purpose,
        compares=compares,
    )
    target = directory / lock.filename
    payload = lock.to_text()
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError:
        try:
            existing = read_lock(target)
        except LockError:
            existing = None
        if existing is not None and not existing.is_expired(lock.created):
            raise LockError(
                f"active lock already present for {area} on {host}: {target}"
            ) from None
        target.write_text(payload, encoding="utf-8")
    lock.path = target
    return lock


def release(lock: AuditLock | Path) -> bool:
    """Remove our lock. Missing file is success, not an error."""
    path = lock.path if isinstance(lock, AuditLock) else Path(lock)
    if path is None:
        return False
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def foreign_presence(
    locks_dir: Path, area: str, host: str, now: datetime | None = None
) -> list[AuditLock]:
    """Other hosts currently auditing this area.

    The reason this function exists at all: knowing that another host is looking
    at the same area is *useful* (it tells you a comparative audit will be
    possible), while being no reason whatsoever to stay away.
    """
    return [
        lock
        for lock in list_locks(locks_dir, area=area, now=now)
        if lock.host != host
    ]


def resolve_claim(
    locks_dir: Path, mine: AuditLock, now: datetime | None = None
) -> ClaimResult:
    """Decide a comparative-audit claim deterministically.

    Winner is the earliest ``created``; on an exact tie the lexicographically
    smaller ``host`` wins.  Both hosts reach the same verdict from the same
    data, without a server, a database or any real-time channel.

    Only ``claim`` locks take part.  Presence locks are ignored on purpose --
    they signal a self-audit, which never competes with anything.
    """
    if mine.mode != MODE_CLAIM:
        return ClaimResult(True, "presence mode does not compete", winner=mine)

    competitors = [
        lock
        for lock in list_locks(locks_dir, area=mine.area, mode=MODE_CLAIM, now=now)
        if lock.host != mine.host and lock.compares == mine.compares
    ]
    if not competitors:
        return ClaimResult(True, "no competing claim", winner=mine)

    ranked = sorted([mine, *competitors], key=lambda item: (item.created, item.host))
    winner = ranked[0]
    if winner.host == mine.host:
        return ClaimResult(
            True, "earliest claim", winner=winner, competitors=competitors
        )
    reason = (
        f"earlier claim by {winner.host}"
        if winner.created < mine.created
        else f"tie resolved by host order in favour of {winner.host}"
    )
    return ClaimResult(False, reason, winner=winner, competitors=competitors)
