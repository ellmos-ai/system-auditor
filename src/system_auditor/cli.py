"""Command line surface -- one shell call per protocol step.

Deliberately thin: every subcommand maps to one library function, so an agent
following the role prompt never has to reimplement protocol logic by hand.
That is the lesson from the ticket-ID collision of 2026-08-08, where picking a
number "by eye" instead of calling the helper produced a same-minute clash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .audit_lock import (
    MODE_CLAIM,
    MODE_PRESENCE,
    LockError,
    foreign_presence,
    list_locks,
    release,
    resolve_claim,
    write_lock,
)
from .discovery import discover
from .meta import plan_meta
from .report import DEFAULT_VALIDITY, list_reports, next_area


def _print(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"  - {item}")
        else:
            print(f"{key}: {value}")


def cmd_next_area(args: argparse.Namespace) -> int:
    areas = [item.strip() for item in args.areas.split(",") if item.strip()]
    chosen = next_area(areas, Path(args.reports), host=args.host)
    _print({"area": chosen, "host": args.host or "(any)"}, args.json)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    try:
        lock = write_lock(
            Path(args.locks),
            area=args.area,
            host=args.host,
            mode=args.mode,
            run_id=args.run_id or f"{args.host}-{args.area}",
            area_path=args.area_path,
            purpose=args.purpose,
            compares=args.compares,
        )
    except LockError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    others = foreign_presence(Path(args.locks), args.area, args.host)
    payload = {
        "lock": str(lock.path),
        "mode": lock.mode,
        "advisory": lock.is_advisory(),
        "other_systems_present": [item.host for item in others],
    }
    if lock.mode == MODE_CLAIM:
        outcome = resolve_claim(Path(args.locks), lock)
        payload["claim_won"] = outcome.won
        payload["claim_reason"] = outcome.reason
        if not outcome.won:
            release(lock)
            payload["lock"] = "(released -- lost the claim)"
    _print(payload, args.json)
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    path = Path(args.locks) / f"LOCK.audit.{args.area}.{args.host}.txt"
    _print({"released": release(path), "lock": str(path)}, args.json)
    return 0


def cmd_locks(args: argparse.Namespace) -> int:
    locks = list_locks(Path(args.locks), area=args.area)
    _print(
        {
            "count": len(locks),
            "locks": [
                f"{item.area} · {item.host} · {item.mode} · until {item.expires_at:%Y-%m-%d %H:%M}Z"
                for item in locks
            ],
        },
        args.json,
    )
    return 0


def cmd_meta_plan(args: argparse.Namespace) -> int:
    plan = plan_meta(
        Path(args.reports),
        area=args.area,
        validity=args.validity,
        host=args.host,
    )
    _print(
        {
            "action": plan.action,
            "reason": plan.reason,
            "level": plan.level,
            "participants": plan.participants,
            "inputs": plan.inputs,
            "supersedes": str(plan.supersedes) if plan.supersedes else "",
            "stale_excluded": plan.stale_excluded,
            "renew_needed": plan.renew_needed,
        },
        args.json,
    )
    return 0


def cmd_reports(args: argparse.Namespace) -> int:
    reports = list_reports(Path(args.reports))
    _print(
        {
            "count": len(reports),
            "reports": [
                f"{item.area} · {item.host} · {item.audit_mode}"
                + (f"-{item.meta_level}" if item.meta_level else "")
                + f" · {item.sort_key:%Y-%m-%d %H:%M}Z"
                + (" · legacy" if item.legacy else "")
                for item in reports
            ],
        },
        args.json,
    )
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    result = discover(args.area_path)
    _print(
        {
            "tier": result.tier_reached,
            "evidence_capable": result.evidence_capable,
            "policy": [item.target for item in result.policy],
            "decision": [item.target for item in result.decision],
            "notes": result.notes,
        },
        args.json,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-auditor", description="Cross-system audits with meta bundling."
    )
    parser.add_argument("--version", action="version", version=f"system-auditor {__version__}")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_next = sub.add_parser("next-area", help="resolve the next domain in the rotation")
    p_next.add_argument("--areas", required=True, help="comma-separated rotation list")
    p_next.add_argument("--reports", required=True)
    p_next.add_argument("--host", default=None)
    p_next.set_defaults(func=cmd_next_area)

    p_claim = sub.add_parser("claim", help="announce presence or claim a meta audit")
    p_claim.add_argument("--locks", required=True)
    p_claim.add_argument("--area", required=True)
    p_claim.add_argument("--host", required=True)
    p_claim.add_argument("--mode", choices=(MODE_PRESENCE, MODE_CLAIM), default=MODE_PRESENCE)
    p_claim.add_argument("--run-id", default="")
    p_claim.add_argument("--area-path", default="")
    p_claim.add_argument("--purpose", default="")
    p_claim.add_argument("--compares", default="", help="meta claims: the input set")
    p_claim.set_defaults(func=cmd_claim)

    p_release = sub.add_parser("release", help="remove our own lock")
    p_release.add_argument("--locks", required=True)
    p_release.add_argument("--area", required=True)
    p_release.add_argument("--host", required=True)
    p_release.set_defaults(func=cmd_release)

    p_locks = sub.add_parser("locks", help="list active audit locks")
    p_locks.add_argument("--locks", required=True)
    p_locks.add_argument("--area", default=None)
    p_locks.set_defaults(func=cmd_locks)

    p_meta = sub.add_parser("meta-plan", help="is a meta audit due for this domain?")
    p_meta.add_argument("--reports", required=True)
    p_meta.add_argument("--area", required=True)
    p_meta.add_argument("--host", default=None)
    p_meta.add_argument("--validity", default=DEFAULT_VALIDITY)
    p_meta.set_defaults(func=cmd_meta_plan)

    p_reports = sub.add_parser("reports", help="list known audit artefacts")
    p_reports.add_argument("--reports", required=True)
    p_reports.set_defaults(func=cmd_reports)

    p_disc = sub.add_parser("discover", help="find policy/decision sources for a domain")
    p_disc.add_argument("--area-path", required=True)
    p_disc.set_defaults(func=cmd_discover)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
