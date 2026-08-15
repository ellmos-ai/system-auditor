"""system-auditor -- evidence-based system audits across machines, models and domains.

Three stages, three owners:

    map      what is there            -> system-explorer (optional)
    verdict  what is wrong about it   -> THIS module
    measure  what we do about it      -> ticket system (optional)

Every audit carries four tokens -- period, domain, system, auditor. Holding some
fixed and letting exactly one vary yields the aggregation ladder: interrater
(models disagree?), cross-system (machine or system?), cross-domain (is the rule
itself the problem?).

Nothing here requires its neighbours. Detected, they are used; absent, the
auditor degrades to reading directly and writing files.
"""

from .audit_lock import (
    MODE_CLAIM,
    MODE_PRESENCE,
    AuditLock,
    ClaimResult,
    foreign_presence,
    list_locks,
    read_lock,
    release,
    resolve_claim,
    write_lock,
)
from .compare import (
    DIVERGENT,
    HOST_SPECIFIC,
    INVERSE,
    SYSTEMWIDE,
    UNVERIFIABLE,
    AuditRun,
    Finding,
    MetaResult,
    build_meta,
    normalize_locator,
    render_markdown,
)
from .discovery import DiscoveryResult, discover
from .meta import (
    ACTION_CREATE,
    ACTION_SKIP,
    ACTION_UPDATE,
    MetaPlan,
    current_single_audits,
    existing_meta,
    plan_meta,
    plan_metas,
    stale_windows,
)
from .report import (
    MODE_META,
    MODE_SELF,
    ReportHeader,
    latest_report,
    list_reports,
    meta_filename,
    next_domain,
    read_report,
    write_report,
)
from .sinks import Sink, emit
from .tokens import (
    AGGREGATIONS,
    CROSS_DOMAIN,
    CROSS_SYSTEM,
    INTERRATER,
    Aggregation,
    AuditIdentity,
    Bundle,
    TimeGrid,
    TimeTable,
    find_bundles,
    resolve_time_token,
)

__version__ = "0.2.0"

__all__ = [
    "__version__",
    # tokens and aggregation
    "AuditIdentity",
    "Aggregation",
    "Bundle",
    "TimeGrid",
    "TimeTable",
    "resolve_time_token",
    "find_bundles",
    "AGGREGATIONS",
    "INTERRATER",
    "CROSS_SYSTEM",
    "CROSS_DOMAIN",
    # locks
    "AuditLock",
    "ClaimResult",
    "MODE_PRESENCE",
    "MODE_CLAIM",
    "write_lock",
    "read_lock",
    "list_locks",
    "release",
    "resolve_claim",
    "foreign_presence",
    # reports
    "ReportHeader",
    "MODE_SELF",
    "MODE_META",
    "read_report",
    "list_reports",
    "latest_report",
    "next_domain",
    "write_report",
    "meta_filename",
    # comparison
    "Finding",
    "AuditRun",
    "MetaResult",
    "build_meta",
    "render_markdown",
    "normalize_locator",
    "SYSTEMWIDE",
    "HOST_SPECIFIC",
    "INVERSE",
    "DIVERGENT",
    "UNVERIFIABLE",
    # meta lifecycle
    "MetaPlan",
    "plan_meta",
    "plan_metas",
    "current_single_audits",
    "existing_meta",
    "stale_windows",
    "ACTION_CREATE",
    "ACTION_UPDATE",
    "ACTION_SKIP",
    # discovery + sinks
    "discover",
    "DiscoveryResult",
    "Sink",
    "emit",
]
