"""Configuration -- read the file the example has been promising all along.

Until 0.5.0 the shipped `system-auditor.config.example.json` was documentation
and nothing else: no module loaded it, the CLI had no `--config`, and every
setting in it -- the window grid, the aggregation policy, the policy stores, the
measure sink -- was inert. A configuration file that nothing reads is worse than
none, because it tells the reader a lie about what the tool will do.

Design decisions worth stating:

* **Comment keys are data, not noise.** The example file carries its reasoning
  in ``_comment_*`` keys. They are ignored on load rather than rejected, so the
  file can keep explaining itself to the next human.
* **``<HOME>`` is expanded, ``<domain>`` is not.** The first is host-neutral
  boilerplate that only a machine can resolve; the second depends on the domain
  assigned for *this run* and is therefore resolved by the caller, per run.
* **Absent beats wrong.** Missing file, unreadable file, broken JSON: the caller
  gets defaults and a stated reason, never a half-applied configuration.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .meta import resolve_policy
from .tokens import TimeGrid, TimeTable

DEFAULT_FILENAME = "system-auditor.config.json"
HOME_PLACEHOLDER = "<HOME>"
DOMAIN_PLACEHOLDER = "<domain>"


@dataclass
class Config:
    """Resolved settings for one run."""

    system: str = ""
    auditor: str = "unspecified"
    audit_home: str = ""
    reports_dir: str = ""
    findings_dir: str = ""
    grid: TimeGrid = field(default_factory=TimeGrid)
    table: TimeTable | None = None
    policy: dict[str, dict] = field(default_factory=resolve_policy)
    domains: list[dict] = field(default_factory=list)
    domain_selector_command: str | None = None
    policy_stores: list[dict] = field(default_factory=list)
    decision_stores: list[dict] = field(default_factory=list)
    known_modules: list[dict] = field(default_factory=list)
    convention_max_depth: int = 2
    measure_sink: dict = field(default_factory=lambda: {"kind": "file"})
    evidence_level_default: int = 1
    source: str = "defaults"
    notes: list[str] = field(default_factory=list)
    # T-20260830-419610437: (konfigurierter Host, tatsaechlicher Host), sonst None.
    # Schreibende Laeufe muessen hierauf fail-closed reagieren; Leseabfragen duerfen
    # weiterlaufen, muessen die Abweichung aber melden.
    host_mismatch: tuple[str, str] | None = None

    def domain_names(self) -> list[str]:
        return [str(entry.get("name", "")) for entry in self.domains if entry.get("name")]

    def domain_path(self, name: str) -> str:
        for entry in self.domains:
            if entry.get("name") == name:
                return str(entry.get("path", ""))
        return ""

    def for_domain(self, name: str) -> Config:
        """Copy with ``<domain>`` resolved to this run's domain path.

        Store entries are declared once and reused for every domain, so the
        placeholder can only be filled when the domain is known -- that is per
        run, not at load time.
        """
        path = self.domain_path(name)
        if not path:
            return self

        def _fill(entries: list[dict]) -> list[dict]:
            return [
                {**entry, "target": str(entry.get("target", "")).replace(DOMAIN_PLACEHOLDER, path)}
                for entry in entries
            ]

        clone = Config(**{**self.__dict__})
        clone.policy_stores = _fill(self.policy_stores)
        clone.decision_stores = _fill(self.decision_stores)
        return clone


def _expand(value: str, home: str) -> str:
    return value.replace(HOME_PLACEHOLDER, home) if isinstance(value, str) else value


def _expand_stores(entries: list, home: str) -> list[dict]:
    return [
        {**entry, "target": _expand(str(entry.get("target", "")), home)}
        for entry in entries or []
        if isinstance(entry, dict)
    ]


#: Substrings that suggest a cloud-synchronised (= shareable) location. A pure
#: heuristic for a *note*, never a gate: an unrecognised sync tool is fine, the
#: note just tells the operator what to check. Meta audits can only ever happen
#: where the machines' reports physically meet.
_SHARED_HINTS = (
    "onedrive", "dropbox", "nextcloud", "owncloud", "google drive", "googledrive",
    "syncthing", "icloud", "cloudstation", "/.sync", "\\.sync",
)


def live_host() -> str:
    """The name this machine actually answers to, or "" if it cannot be determined.

    Deliberately the OS, not the environment and not the session: ``COMPUTERNAME`` and
    ``HOSTNAME`` are inherited by child processes and can therefore carry a foreign
    value into a run that has nothing to do with them. ``platform.node()`` asks the
    machine.  Returns "" rather than raising -- an unanswerable question must not abort
    a read-only sweep; the caller decides what an unknown host means.
    """
    try:
        return platform.node() or ""
    except Exception:
        return ""


def _looks_shared(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in _SHARED_HINTS)


def _parse_anchor(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def find_config(explicit: str | Path | None = None) -> Path | None:
    """Locate the config: explicit path, env var, then conventional places."""
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    env = os.environ.get("SYSTEM_AUDITOR_CONFIG")
    if env and Path(env).is_file():
        return Path(env)
    for candidate in (
        Path.cwd() / DEFAULT_FILENAME,
        Path.cwd() / "config" / DEFAULT_FILENAME,
        Path.home() / ".system-auditor" / DEFAULT_FILENAME,
    ):
        if candidate.is_file():
            return candidate
    return None


def load(path: str | Path | None = None, home: str | None = None) -> Config:
    """Load a config, or return defaults with a stated reason.

    Never raises on a bad file: an audit that cannot read its configuration
    should say so and run with defaults, not abort in the middle of a sweep.
    """
    resolved_home = home or str(Path.home()).replace("\\", "/")
    found = find_config(path)
    if found is None:
        return Config(notes=["no config file found -- running on defaults"])

    try:
        raw = json.loads(found.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Config(
            source=str(found),
            notes=[f"config unreadable ({exc.__class__.__name__}) -- running on defaults"],
        )

    # Comment keys carry the file's own reasoning; ignore them, never reject.
    data = {key: value for key, value in raw.items() if not key.startswith("_comment")}
    notes: list[str] = []

    grid_data = data.get("time_grid") or {}
    anchor = _parse_anchor(grid_data.get("anchor"))
    try:
        period = str(grid_data.get("period", "7d"))
        grid = TimeGrid(period=period, anchor=anchor) if anchor else TimeGrid(period=period)
    except ValueError as exc:
        grid = TimeGrid()
        notes.append(f"time_grid rejected ({exc}) -- using the default 7d grid")

    table_entries = data.get("time_table") or []
    table = TimeTable(entries=list(table_entries)) if table_entries else None

    config = Config(
        system=str(data.get("system", "")),
        auditor=str(data.get("auditor", "unspecified")),
        audit_home=_expand(str(data.get("audit_home", "")), resolved_home),
        reports_dir=_expand(str(data.get("reports_dir", "")), resolved_home),
        findings_dir=_expand(str(data.get("findings_dir", "")), resolved_home),
        grid=grid,
        table=table,
        policy=resolve_policy(data.get("aggregations") or {}),
        domains=[
            {**entry, "path": _expand(str(entry.get("path", "")), resolved_home)}
            for entry in data.get("domains") or []
            if isinstance(entry, dict)
        ],
        domain_selector_command=data.get("domain_selector_command") or None,
        policy_stores=_expand_stores(data.get("policy_stores"), resolved_home),
        decision_stores=_expand_stores(data.get("decision_stores"), resolved_home),
        known_modules=list(data.get("known_modules") or []),
        convention_max_depth=int(data.get("convention_max_depth", 2) or 2),
        measure_sink=dict(data.get("measure_sink") or {"kind": "file"}),
        evidence_level_default=int(data.get("evidence_level_default", 1) or 1),
        source=str(found),
        notes=notes,
    )

    if config.reports_dir and not _looks_shared(config.reports_dir):
        config.notes.append(
            "reports_dir looks host-local -- meta audits need a cloud-shared "
            "folder that every participating machine syncs, or no second "
            "machine's reports will ever meet yours"
        )
    if config.system in ("", "<HOSTNAME>"):
        config.notes.append(
            "system is unset or still the placeholder -- reports would be filed "
            "under a name no other machine recognises"
        )
    else:
        # T-20260830-419610437: the old check caught only the forgetful case (empty or
        # placeholder). It did not catch the more dangerous one -- a value that is set,
        # plausible and simply wrong. That happens by copying a config: the shared
        # findings ask for a host-local file "from a template", and a forgotten
        # `system` survives that unnoticed. The host is one of the four tokens an audit
        # is identified by, so a wrong one makes two reports of the SAME machine look
        # like two systems -- and cross-system aggregation would then claim an
        # agreement that never happened. Unlike the model token, the true value is
        # cheap and reliable to obtain: the OS knows it. So we ask.
        live = live_host()
        if live and config.system.strip().casefold() != live.strip().casefold():
            config.host_mismatch = (config.system, live)
            config.notes.append(
                f"system is {config.system!r} but this machine reports {live!r} -- "
                "a copied config; reports and locks would be filed under a foreign "
                "host name"
            )
    if config.auditor in ("", "unspecified", "<MODELL-ODER-AGENT>"):
        config.notes.append(
            "auditor is unset -- a second model would overwrite this one's audit "
            "and interrater comparison is impossible"
        )
    return config
