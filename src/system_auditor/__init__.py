"""system-auditor -- evidence-based system audits across several machines.

Three stages, three owners:

    map      what is there            -> system-explorer (optional)
    verdict  what is wrong about it   -> THIS module
    measure  what we do about it      -> ticket system (optional)

Nothing here requires its neighbours.  Detected, they are used; absent, the
auditor degrades to reading directly and writing files.
"""

from .audit_lock import (
    MODE_CLAIM,
    MODE_PRESENCE,
    AuditLock,
    ClaimResult,
    foreign_presence,
    list_locks,
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
from .meta import MetaPlan, current_meta, plan_meta, renew_own_audits, valid_single_audits
from .report import (
    MODE_META,
    MODE_SELF,
    ReportHeader,
    latest_report,
    list_reports,
    next_area,
    read_report,
    write_report,
)
from .sinks import Sink, emit

__version__ = "0.1.0"

__all__ = [
    "__version__",
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
    "next_area",
    "write_report",
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
    "current_meta",
    "valid_single_audits",
    "renew_own_audits",
    # discovery + sinks
    "discover",
    "DiscoveryResult",
    "Sink",
    "emit",
]

from .audit_lock import read_lock  # noqa: E402  (kept last for a flat __all__)
