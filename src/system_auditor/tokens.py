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

Aggregation
-----------

Hold some tokens fixed, let others vary.  Every dimension is *fixed*, *varying*
or -- deliberately -- **uncontrolled**: not held constant and not the subject of
the comparison.  An uncontrolled dimension that actually differs produces a
caveat rather than a blocker, because refusing those comparisons outright would
make cross-machine audits impossible in a fleet where each machine runs a
different model.

Two **kinds** of aggregation, and they are not interchangeable:

``snapshot``
    Several participants look at the *same* moment.  The question is who saw
    what: agreement, drift, contradiction.

``timeseries``
    One participant across *several* windows.  The question is development:
    is a finding new, still there, gone, or back again.  The snapshot classes
    would be nonsense here -- "every window found it" is *persistent*, not
    "systemwide".

===================  =====================  ==============  ===================================
aggregation          fixed                  varies          question
===================  =====================  ==============  ===================================
``interrater``       time+domain+system     auditor         do two models agree?
``cross-domain``     time+system+auditor    domain          same rule broken across domains?
``cross-system``     time+domain            system          system defect or machine drift?
``full-system``      time+system            domain+auditor  full picture of one machine
``timeseries``       system+domain          time            how did this domain develop?
``timeseries-rater`` system+domain+auditor  time            how did one model's view develop?
===================  =====================  ==============  ===================================

**Matching follows the axis.**  Where ``domain`` varies there is no shared
location, so findings are matched by *rule*: the same rule broken in unrelated
corners is a problem of the rule, not of one place.  Everywhere else the same
*place* is compared.
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

#: How findings are matched when comparing.  ``locator`` = the same place;
#: ``rule`` = the same rule in unrelated places.
GROUP_BY_LOCATOR = "locator+rule"
GROUP_BY_RULE = "rule"

KIND_SNAPSHOT = "snapshot"
KIND_TIMESERIES = "timeseries"


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
    """Hold these tokens fixed, let those vary; the rest is uncontrolled."""

    name: str
    fixed: tuple[str, ...]
    varying: tuple[str, ...]
    kind: str = KIND_SNAPSHOT
    description: str = ""

    @property
    def uncontrolled(self) -> tuple[str, ...]:
        """Neither held constant nor compared -- honest about what it ignores."""
        return tuple(
            dimension
            for dimension in DIMENSIONS
            if dimension not in self.fixed and dimension not in self.varying
        )

    @property
    def group_by(self) -> str:
        """Across domains there is no shared place, so match by rule."""
        return GROUP_BY_RULE if DIM_DOMAIN in self.varying else GROUP_BY_LOCATOR

    @property
    def is_timeseries(self) -> bool:
        return self.kind == KIND_TIMESERIES

    def participant(self, identity: AuditIdentity) -> str:
        """Label of one participant along the varying axis (``d×a`` if both)."""
        return " / ".join(identity.value(dimension) for dimension in self.varying)

    def label(self, key: tuple[str, ...]) -> str:
        pairs = zip(self.fixed, key, strict=True)
        return " · ".join(f"{dim}={value}" for dim, value in pairs)


INTERRATER = Aggregation(
    name="interrater",
    fixed=(DIM_TIME, DIM_DOMAIN, DIM_SYSTEM),
    varying=(DIM_AUDITOR,),
    description="Same machine, domain and window, different models -- do they agree?",
)

CROSS_DOMAIN = Aggregation(
    name="cross-domain",
    fixed=(DIM_TIME, DIM_SYSTEM, DIM_AUDITOR),
    varying=(DIM_DOMAIN,),
    description="One machine and model across its domains -- is the rule the problem?",
)

CROSS_SYSTEM = Aggregation(
    name="cross-system",
    fixed=(DIM_TIME, DIM_DOMAIN),
    varying=(DIM_SYSTEM,),
    description="Same domain and window on different machines -- defect or drift?",
)

FULL_SYSTEM = Aggregation(
    name="full-system",
    fixed=(DIM_TIME, DIM_SYSTEM),
    varying=(DIM_DOMAIN, DIM_AUDITOR),
    description="Everything known about one machine in one window.",
)

TIMESERIES = Aggregation(
    name="timeseries",
    fixed=(DIM_SYSTEM, DIM_DOMAIN),
    varying=(DIM_TIME,),
    kind=KIND_TIMESERIES,
    description="One domain on one machine over several windows -- development.",
)

TIMESERIES_RATER = Aggregation(
    name="timeseries-rater",
    fixed=(DIM_SYSTEM, DIM_DOMAIN, DIM_AUDITOR),
    varying=(DIM_TIME,),
    kind=KIND_TIMESERIES,
    description="One model's view of one domain over several windows.",
)

AGGREGATIONS = {
    item.name: item
    for item in (
        INTERRATER,
        CROSS_DOMAIN,
        CROSS_SYSTEM,
        FULL_SYSTEM,
        TIMESERIES,
        TIMESERIES_RATER,
    )
}


@dataclass
class Bundle:
    """Candidates for one meta audit: same fixed key, differing varying tokens."""

    aggregation: Aggregation
    key: tuple[str, ...]
    identities: list[AuditIdentity] = field(default_factory=list)

    @property
    def varying_values(self) -> list[str]:
        return sorted({self.aggregation.participant(item) for item in self.identities})

    @property
    def level(self) -> int:
        """How many distinct participants -- meta-2, meta-3, ..."""
        return len(self.varying_values)

    def counts(self) -> dict[str, int]:
        """Distinct values per varying dimension.

        For ``full-system`` this is what the user's naming asks for: how many
        domains and how many auditors the picture rests on.
        """
        return {
            dimension: len({item.value(dimension) for item in self.identities})
            for dimension in self.aggregation.varying
        }

    def uncontrolled_spread(self) -> dict[str, list[str]]:
        """Values seen in dimensions this aggregation neither fixes nor compares."""
        spread: dict[str, list[str]] = {}
        for dimension in self.aggregation.uncontrolled:
            values = sorted({item.value(dimension) for item in self.identities})
            if len(values) > 1:
                spread[dimension] = values
        return spread

    def label(self) -> str:
        return self.aggregation.label(self.key)


def find_bundles(
    identities: list[AuditIdentity],
    aggregation: Aggregation,
    min_participants: int = 2,
) -> list[Bundle]:
    """Group identities into meta-audit candidates.

    A bundle needs at least ``min_participants`` *distinct* participants along
    the varying axis.  Where two dimensions vary (``full-system``), a
    participant is their combination -- so one domain audited by two models
    already counts as two.
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
    the same machine, with the same model, in the same window is a *correction*
    -- so it replaces its predecessor and forces the meta audit to be rebuilt,
    rather than appearing beside it as a second opinion.
    """
    newest: dict[AuditIdentity, tuple[AuditIdentity, object]] = {}
    for identity, payload in entries:
        current = newest.get(identity)
        if current is None or sort_key(payload) > sort_key(current[1]):
            newest[identity] = (identity, payload)
    return [newest[key] for key in sorted(newest, key=lambda item: item.key_for(DIMENSIONS))]
