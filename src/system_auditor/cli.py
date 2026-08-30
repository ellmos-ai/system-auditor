"""Command line surface -- one shell call per protocol step.

Deliberately thin: every subcommand maps to one library function, so an agent
following the role prompt never reimplements protocol logic by hand.  That is
the lesson from the ticket-ID collision of 2026-08-08, where picking a number
"by eye" instead of calling the helper produced a same-minute clash.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import load as load_config
from .discovery import discover
from .meta import due_aggregations, plan_all, stale_windows
from .pages_drift import PagesDriftError, audit_pages_drift
from .report import list_reports, next_domain
from .tokens import AGGREGATIONS, TimeGrid, utcnow


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


#: One load per process. Without this, a command that consults the config twice
#: (meta-plan: grid, then policy) printed every note twice -- and a warning that
#: repeats reads as two problems.
_CONFIG_CACHE: dict = {}


def _config(args: argparse.Namespace):
    """Load the config once per process and report what it did -- once."""
    key = str(getattr(args, "config", None))
    if key in _CONFIG_CACHE:
        return _CONFIG_CACHE[key]
    config = load_config(getattr(args, "config", None))
    # The auditor is a property of the *model running right now*, not of the
    # host: a shared host config cannot know it. CLI flag and environment
    # override the file and silence the unset warning.
    override = getattr(args, "auditor", None) or os.environ.get("SYSTEM_AUDITOR_AUDITOR")
    if override:
        config.auditor = override
        config.notes = [note for note in config.notes if "auditor is unset" not in note]
    for note in config.notes:
        print(f"config: {note}", file=sys.stderr)
    _CONFIG_CACHE[key] = config
    return config


def _grid(args: argparse.Namespace) -> TimeGrid:
    """Build the window grid, defaulting to the *library* anchor.

    This used to default to midnight of the day the command ran. That silently
    destroyed the whole point of the grid: with a 7d period, Monday and
    Wednesday of the same week produced different tokens, so a weekly window
    degenerated into daily ones and ``meta-plan`` never bundled across days.
    The anchor fixes the *phase* of the grid and must therefore be a constant,
    not "now".
    """
    if getattr(args, "anchor", None):
        anchor = datetime.fromisoformat(args.anchor.replace("Z", "+00:00"))
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        return TimeGrid(period=args.period, anchor=anchor)
    if getattr(args, "period", "7d") == "7d":
        # No explicit period given: the config's grid wins over the built-in
        # default, otherwise the file that documents the heartbeat would not
        # actually set it.
        return _config(args).grid
    return TimeGrid(period=args.period)


def cmd_time_token(args: argparse.Namespace) -> int:
    grid = _grid(args)
    moment = utcnow()
    start, end = grid.window(moment)
    _print(
        {
            "time_token": grid.token(moment),
            "period": args.period,
            "window_start": start,
            "window_end": end,
        },
        args.json,
    )
    return 0


def cmd_next_domain(args: argparse.Namespace) -> int:
    if args.domains:
        domains = [item.strip() for item in args.domains.split(",") if item.strip()]
    else:
        domains = _config(args).domain_names()
        if not domains:
            print(
                "ERROR: no --domains given and no domains[] in the config",
                file=sys.stderr,
            )
            return 1
    chosen = next_domain(domains, Path(args.reports), system=args.system)
    _print({"domain": chosen, "system": args.system or "(any)"}, args.json)
    return 0


def cmd_meta_plan(args: argparse.Namespace) -> int:
    token = args.time_token or _grid(args).token(utcnow())
    config = _config(args)
    due = due_aggregations(config.policy, requested=args.aggregation)
    if args.aggregation and not due:
        print(
            f"ERROR: aggregation '{args.aggregation}' is switched off in the policy. "
            "Turning it on is a config decision, not a per-call one.",
            file=sys.stderr,
        )
        return 1
    plans = plan_all(
        Path(args.reports),
        policy=config.policy,
        time_token=None if args.all_windows else token,
        requested=args.aggregation,
    )
    _print(
        {
            "aggregation": args.aggregation or "(policy: "
            + ", ".join(item.name for item, _ in due) + ")",
            "time_token": "(all)" if args.all_windows else token,
            "bundles": len(plans),
            "plans": [
                f"{plan.action} · {plan.target} · {plan.level} Teilnehmer "
                f"[{', '.join(plan.participants)}] · {plan.reason}"
                + (f" · unkontrolliert: {plan.uncontrolled}" if plan.uncontrolled else "")
                for plan in plans
            ],
            "restated_inputs": plans[0].restated if plans else [],
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
                f"{item.time_token} · {item.domain} · {item.system} · {item.auditor}"
                f" · {item.audit_mode}"
                + (f"-{item.meta_level}" if item.meta_level else "")
                + (" · legacy" if item.legacy else "")
                for item in reports
            ],
        },
        args.json,
    )
    return 0


def cmd_stale(args: argparse.Namespace) -> int:
    token = args.time_token or _grid(args).token(utcnow())
    old = stale_windows(Path(args.reports), token, system=args.system)
    _print(
        {
            "current_window": token,
            "count": len(old),
            "note": "earlier windows stay as history; only their own machine may restate them",
            "audits": [
                f"{item.time_token} · {item.domain} · {item.system} · {item.auditor}"
                for item in old
            ],
        },
        args.json,
    )
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    config = _config(args)
    if args.domain:
        config = config.for_domain(args.domain)
    path = args.domain_path or config.domain_path(args.domain or "")
    if not path:
        print("ERROR: give --domain-path, or --domain with a configured path", file=sys.stderr)
        return 1
    result = discover(
        path,
        policy_stores=config.policy_stores,
        decision_stores=config.decision_stores,
        known_modules=config.known_modules,
        max_depth=config.convention_max_depth,
    )
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


def _add_grid_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", default="7d", help="length of one audit window")
    parser.add_argument("--anchor", default=None, help="ISO start of the window grid")


def cmd_config(args: argparse.Namespace) -> int:
    """Show what the tool actually read -- the fastest way to catch a config
    that is present but not being used."""
    config = _config(args)
    start, end = config.grid.window(utcnow())
    _print(
        {
            "source": config.source,
            "system": config.system or "(unset)",
            "auditor": config.auditor,
            "reports_dir": config.reports_dir or "(unset)",
            "period": config.grid.period,
            "current_window": f"{config.grid.token(utcnow())} ({start:%Y-%m-%d} .. {end:%Y-%m-%d})",
            "domains": config.domain_names(),
            "standing_aggregations": [
                name for name, entry in sorted(config.policy.items())
                if entry.get("mode") == "always"
            ],
            "measure_sink": config.measure_sink.get("kind", "file"),
            "notes": config.notes,
        },
        args.json,
    )
    return 0


def cmd_pages_drift(args: argparse.Namespace) -> int:
    try:
        result = audit_pages_drift(
            Path(args.modules_catalog),
            Path(args.skills_registry),
            Path(args.bundles_catalog),
            Path(args.site_dir),
        )
    except PagesDriftError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _print(result.as_dict(), args.json)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-auditor",
        description="Audits across machines, models and domains, with meta bundling.",
    )
    parser.add_argument("--version", action="version", version=f"system-auditor {__version__}")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--config",
        default=None,
        help="path to system-auditor.config.json (default: env SYSTEM_AUDITOR_CONFIG, "
        "then ./ and ./config/ and ~/.system-auditor/)",
    )
    parser.add_argument(
        "--auditor",
        default=None,
        help="auditor token of the model running now (overrides the config; "
        "env SYSTEM_AUDITOR_AUDITOR works too)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_token = sub.add_parser("time-token", help="which audit window is it right now?")
    _add_grid_args(p_token)
    p_token.set_defaults(func=cmd_time_token)

    p_next = sub.add_parser("next-domain", help="resolve the next domain in the rotation")
    p_next.add_argument(
        "--domains", default="", help="comma-separated rotation list (default: from config)"
    )
    p_next.add_argument("--reports", required=True)
    p_next.add_argument("--system", default=None)
    p_next.set_defaults(func=cmd_next_domain)

    p_meta = sub.add_parser("meta-plan", help="which meta audits are due?")
    p_meta.add_argument("--reports", required=True)
    p_meta.add_argument(
        "--aggregation",
        choices=sorted(AGGREGATIONS),
        default=None,
        help="omit: build what the policy marks 'always'; name one to ask on demand",
    )
    p_meta.add_argument("--time-token", default=None, help="default: current window")
    p_meta.add_argument("--all-windows", action="store_true")
    _add_grid_args(p_meta)
    p_meta.set_defaults(func=cmd_meta_plan)

    p_reports = sub.add_parser("reports", help="list known audit artefacts")
    p_reports.add_argument("--reports", required=True)
    p_reports.set_defaults(func=cmd_reports)

    p_stale = sub.add_parser("stale", help="audits belonging to an earlier window")
    p_stale.add_argument("--reports", required=True)
    p_stale.add_argument("--system", default=None)
    p_stale.add_argument("--time-token", default=None)
    _add_grid_args(p_stale)
    p_stale.set_defaults(func=cmd_stale)

    p_disc = sub.add_parser("discover", help="find policy/decision sources for a domain")
    p_disc.add_argument("--domain-path", default="", help="path to audit (or use --domain)")
    p_disc.add_argument("--domain", default="", help="domain name from the config")
    p_disc.set_defaults(func=cmd_discover)

    p_config = sub.add_parser("config", help="show the resolved configuration")
    p_config.set_defaults(func=cmd_config)

    p_pages = sub.add_parser(
        "pages-drift", help="compare module/skill/bundle catalogs with the generated Pages site"
    )
    p_pages.add_argument("--modules-catalog", required=True)
    p_pages.add_argument("--skills-registry", required=True)
    p_pages.add_argument("--bundles-catalog", required=True)
    p_pages.add_argument("--site-dir", required=True)
    p_pages.set_defaults(func=cmd_pages_drift)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
