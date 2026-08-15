"""Identity of an audit -- four tokens, and what may be aggregated over which.

Every audit answers four questions, and each answer is a token:

============  =========================================================
token         question
============  =========================================================
``time``      *when* -- which period window does this statement belong to
``domain``    *what* -- which domain was audited
``system``    *where* -- which machine was looked at
``auditor``   *who* -- which model/agent did the looking
============  =========================================================

**Why discrete time windows instead of a sliding validity span.**  A sliding
window ("valid for 14 days from the run") makes overlap a matter of degree: two
audits three days apart overlap, ten days apart maybe, and every machine has to
compare pairs to find out.  A window *grid* derived from config turns that into
a lookup: ask the clock, get a token.  Two machines that never talk to each
other derive the same token for the same moment -- so "same period" becomes a
string comparison instead of an agreement problem.

The price is the boundary: two runs four minutes apart can land in different
windows if the boundary falls between them.  That is deliberate.  Determinism
across machines is worth more here than smoothness at the edge, and longer
windows make the edge rarer.

**Aggregation** is then simply: hold some tokens fixed, let exactly one vary.

===================  ==================  ===========  ==============================
aggregation          fixed               varies       what it tells you
===================  ==================  ===========  ==============================
``interrater``       time+domain+system  auditor      do two models agree?
``cross-system``     time+domain         system       is it the system or the machine?
``cross-domain``     time                domain       is the same rule broken everywhere?
===================  ==================  ===========  ==============================

Note the third one groups by **rule alone**.  Across systems you compare the
same *place* on different machines; across domains there is no shared place --
what carries meaning is whether the same rule is broken in unrelated corners of
the system, which makes it a problem of the rule rather than of one location.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_PERIOD_RE = re.compile(r"^\s*(\d+)\s*([dhw])\s*$", re.IGNORECASE)

DIM_TIME = "time"
DIM_DOMAIN = "domain"
DIM_SYSTEM = "system"
DIM_AUDITOR = "auditor"
DIMENSIONS = (DIM_TIME, DIM_DOMAIN, DIM_SYSTEM, DIM_AUDITOR)

#: How findings are matched when comparing.  ``locator`` = the same place on
#: different machines; ``rule`` = the same rule in unrelated places.
GROUP_BY_LOCATOR = "locator+rule"
GROUP_BY_RULE = "rule"


def parse_period(raw: str) -> timedelta:
    match = _PERIOD_RE.match(raw or "")
    if not match:
        raise ValueError(f"unparsable period: {raw!r}")
    amount, unit = int(match.group(1)), match.group(2).lower()
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    return timedelta(hours=amount)


@dataclass
class TimeGrid:
    """A period table derived from a rule -- the 'heartbeat'.

    ``anchor`` fixes the phase of the grid; every window is
    ``[anchor + n*period, anchor + (n+1)*period)``.  Both are config, so every
    machine computes the same window boundaries without coordination.
    """

    period: str = "7d"
    anchor: datetime = field(
        default_factory=lambda: datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday
    )

    def __post_init__(self) -> None:
        self.length = parse_period(self.period)
        if self.length <= timedelta(0):
            raise ValueError("period must be positive")
        if self.anchor.tzinfo is None:
            self.anchor = self.anchor.replace(tzinfo=timezone.utc)

    def index(self, moment: datetime) -> int:
        delta = moment.astimezone(timezone.utc) - self.anchor
        return int(delta.total_seconds() // self.length.total_seconds())

    def window(self, moment: datetime) -> tuple[datetime, datetime]:
        start = self.anchor + self.length * self.index(moment)
        return start, start + self.length

    def token(self, moment: datetime) -> str:
        """Sortable, filename-safe label of the window a moment falls into."""
        start, _ = self.window(moment)
        if self.length >= timedelta(days=1):
            return start.strftime("%Y%m%d")
        return start.strftime("%Y%m%dT%H")


@dataclass
class TimeTable:
    """Explicit period table -- for calendars a rule cannot express.

    Entries are ``{"token": str, "from": iso, "to": iso}``; ``to`` is exclusive.
    Overlapping entries are a configuration error, and the first match wins so
    the outcome stays deterministic rather than merely undefined.
    """

    entries: list[dict] = field(default_factory=list)

    def token(self, moment: datetime) -> str | None:
        target = moment.astimezone(timezone.utc)
        for entry in self.entries:
            start = _parse_iso(str(entry.get("from", "")))
            end = _parse_iso(str(entry.get("to", "")))
            if start and end and start <= target < end:
                return str(entry.get("token", ""))
        return None


def _parse_iso(raw: str) -> datetime | None:
    text = (raw or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def resolve_time_token(
    moment: datetime, grid: TimeGrid | None = None, table: TimeTable | None = None
) -> str:
    """Ask the clock, get the period token.

    An explicit table wins where it has an entry; otherwise the grid answers.
    A moment outside an explicit table falls back to the grid rather than being
    rejected -- an audit must never fail because the calendar has a hole.
    """
    if table is not None:
        found = table.token(moment)
        if found:
            return found
    return (grid or TimeGrid()).token(moment)


@dataclass(frozen=True)
class AuditIdentity:
    """The four tokens of one audit. Two audits sharing all four are the same
    statement restated -- the newer one replaces the older."""

    time: str
    domain: str
    system: str
    auditor: str = "unspecified"

    def as_dict(self) -> dict[str, str]:
        return {
            DIM_TIME: self.time,
            DIM_DOMAIN: self.domain,
            DIM_SYSTEM: self.system,
            DIM_AUDITOR: self.auditor,
        }

    def value(self, dimension: str) -> str:
        return self.as_dict()[dimension]

    def key_for(self, dimensions: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self.value(dimension) for dimension in dimensions)


@dataclass(frozen=True)
class Aggregation:
    """A meta audit is: hold these tokens fixed, let that one vary."""

    name: str
    fixed: tuple[str, ...]
    varying: str
    group_by: str = GROUP_BY_LOCATOR
    description: str = ""

    def label(self, key: tuple[str, ...]) -> str:
        pairs = zip(self.fixed, key, strict=True)
        return " · ".join(f"{dim}={value}" for dim, value in pairs)


INTERRATER = Aggregation(
    name="interrater",
    fixed=(DIM_TIME, DIM_DOMAIN, DIM_SYSTEM),
    varying=DIM_AUDITOR,
    group_by=GROUP_BY_LOCATOR,
    description="Same machine, same domain, same period, different models -- do they agree?",
)

CROSS_SYSTEM = Aggregation(
    name="cross-system",
    fixed=(DIM_TIME, DIM_DOMAIN),
    varying=DIM_SYSTEM,
    group_by=GROUP_BY_LOCATOR,
    description="Same domain and period on different machines -- system defect or host drift?",
)

CROSS_DOMAIN = Aggregation(
    name="cross-domain",
    fixed=(DIM_TIME,),
    varying=DIM_DOMAIN,
    group_by=GROUP_BY_RULE,
    description="Same period, different domains -- is the same rule broken everywhere?",
)

AGGREGATIONS = {
    item.name: item for item in (INTERRATER, CROSS_SYSTEM, CROSS_DOMAIN)
}


@dataclass
class Bundle:
    """Candidates for one meta audit: same fixed key, differing varying token."""

    aggregation: Aggregation
    key: tuple[str, ...]
    identities: list[AuditIdentity] = field(default_factory=list)

    @property
    def varying_values(self) -> list[str]:
        return sorted({item.value(self.aggregation.varying) for item in self.identities})

    @property
    def level(self) -> int:
        """How many distinct participants -- meta-2, meta-3, ..."""
        return len(self.varying_values)

    def label(self) -> str:
        return self.aggregation.label(self.key)


def find_bundles(
    identities: list[AuditIdentity],
    aggregation: Aggregation,
    min_participants: int = 2,
) -> list[Bundle]:
    """Group identities into meta-audit candidates.

    A bundle needs at least ``min_participants`` *distinct* values in the
    varying dimension.  Two audits differing in no dimension at all are one
    restated statement, not two participants -- deduplicated by the caller
    before this point.
    """
    grouped: dict[tuple[str, ...], list[AuditIdentity]] = {}
    for identity in identities:
        grouped.setdefault(identity.key_for(aggregation.fixed), []).append(identity)

    bundles = [
        Bundle(aggregation=aggregation, key=key, identities=members)
        for key, members in grouped.items()
    ]
    return sorted(
        [bundle for bundle in bundles if bundle.level >= min_participants],
        key=lambda item: item.key,
    )


def newest_per_identity(
    entries: list[tuple[AuditIdentity, object]], sort_key
) -> list[tuple[AuditIdentity, object]]:
    """Collapse repeated statements: same four tokens -> keep the newest.

    This is what makes a re-run harmless.  Auditing the same domain again, on
    the same machine, with the same model, in the same period is a *correction*
    -- so it replaces its predecessor and forces the meta audit to be rebuilt,
    rather than appearing beside it as a second opinion.
    """
    newest: dict[AuditIdentity, tuple[AuditIdentity, object]] = {}
    for identity, payload in entries:
        current = newest.get(identity)
        if current is None or sort_key(payload) > sort_key(current[1]):
            newest[identity] = (identity, payload)
    return [newest[key] for key in sorted(newest, key=lambda item: item.key_for(DIMENSIONS))]
