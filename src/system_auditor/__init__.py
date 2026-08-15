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

**No lock, but a guarded write.** Parallel audits of one domain are the
*premise* of a meta audit, not a collision, so there is nothing to exclude --
and the classification is deterministic. That is not the same as being safe to
write blindly: a run that planned earlier can overwrite a newer artefact that
another machine published in the meantime. ``write_meta`` therefore re-reads
the target before writing and refuses when the file on disk already rests on a
superset of the planned inputs. The coordination *protocol* moved to
``lock-master`` (``pure-locking/contested.py``), where exclusion is the purpose
rather than a nuisance.
"""

from .compare import (
    DIVERGENT,
    HOST_SPECIFIC,
    INVERSE,
    SYSTEMWIDE,
    UNVERIFIABLE,
    AuditRun,
    Finding,
    InventoryResult,
    MetaResult,
    build_inventory,
    build_meta,
    normalize_locator,
    render_markdown,
)
from .discovery import DiscoveryResult, discover
from .meta import (
    ACTION_CREATE,
    ACTION_SKIP,
    ACTION_UPDATE,
    DEFAULT_POLICY,
    MODE_ALWAYS,
    MODE_OFF,
    MODE_ON_DEMAND,
    MetaPlan,
    current_single_audits,
    due_aggregations,
    existing_meta,
    plan_all,
    plan_meta,
    plan_metas,
    resolve_policy,
    stale_windows,
    write_meta,
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
from .timeseries import (
    NEW,
    PERSISTENT,
    RECURRING,
    RESOLVED,
    TimeseriesResult,
    build_timeseries,
)
from .tokens import (
    AGGREGATIONS,
    CROSS_DOMAIN,
    CROSS_SYSTEM,
    CROSS_SYSTEM_RATER,
    FULL_SYSTEM,
    INTERRATER,
    TIMESERIES,
    TIMESERIES_RATER,
    Aggregation,
    AuditIdentity,
    Bundle,
    TimeGrid,
    TimeTable,
    find_bundles,
    format_ts,
    parse_ts,
    resolve_time_token,
    utcnow,
)

__version__ = "0.9.0"

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
    "utcnow",
    "format_ts",
    "parse_ts",
    "AGGREGATIONS",
    "INTERRATER",
    "CROSS_SYSTEM",
    "CROSS_SYSTEM_RATER",
    "CROSS_DOMAIN",
    "FULL_SYSTEM",
    "TIMESERIES",
    "TIMESERIES_RATER",
    # time series
    "build_timeseries",
    "TimeseriesResult",
    "NEW",
    "PERSISTENT",
    "RECURRING",
    "RESOLVED",
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
    "build_inventory",
    "InventoryResult",
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
    "plan_all",
    "resolve_policy",
    "due_aggregations",
    "DEFAULT_POLICY",
    "MODE_ALWAYS",
    "MODE_ON_DEMAND",
    "MODE_OFF",
    "current_single_audits",
    "existing_meta",
    "stale_windows",
    "write_meta",
    "ACTION_CREATE",
    "ACTION_UPDATE",
    "ACTION_SKIP",
    # discovery + sinks
    "discover",
    "DiscoveryResult",
    "Sink",
    "emit",
]
