"""Discovery degrades honestly; sinks degrade to files."""

import json
import os
import shlex
import sys

from system_auditor.discovery import (
    TIER_CONFIGURED,
    TIER_CONVENTION,
    TIER_MODULE,
    TIER_NONE,
    discover,
)
from system_auditor.sinks import Sink, emit, emit_command, split_command


def test_configured_stores_win(tmp_path):
    policy = tmp_path / "POLICY.md"
    policy.write_text("rules", encoding="utf-8")
    result = discover(
        tmp_path,
        policy_stores=[{"name": "p", "kind": "file", "target": str(policy)}],
        probe_runner=lambda cmd: False,
    )
    assert result.tier_reached == TIER_CONFIGURED
    assert result.evidence_capable


def test_configured_but_missing_file_is_dropped(tmp_path):
    result = discover(
        tmp_path,
        policy_stores=[{"name": "p", "kind": "file", "target": str(tmp_path / "nope.md")}],
        probe_runner=lambda cmd: False,
    )
    assert result.tier_reached == TIER_NONE


def test_known_module_is_used_when_its_probe_succeeds(tmp_path):
    result = discover(
        tmp_path,
        known_modules=[
            {"name": "policy-registry", "enabled_probe": "true",
             "provides": "policy", "target": "policy-registry list"}
        ],
        probe_runner=lambda cmd: True,
    )
    assert result.tier_reached == TIER_MODULE
    assert result.policy[0].name == "policy-registry"


def test_absent_module_is_normal_not_an_error(tmp_path):
    result = discover(
        tmp_path,
        known_modules=[{"name": "policy-registry", "enabled_probe": "x", "provides": "policy"}],
        probe_runner=lambda cmd: False,
    )
    assert result.probed[0].available is False
    assert result.tier_reached == TIER_NONE


def test_convention_lookup_finds_foreign_systems_rules(tmp_path):
    """A stranger's system has no known modules -- but conventions travel."""
    (tmp_path / "CLAUDE.md").write_text("house rules", encoding="utf-8")
    (tmp_path / "DECISIONS.md").write_text("adr", encoding="utf-8")
    result = discover(tmp_path, probe_runner=lambda cmd: False)
    assert result.tier_reached == TIER_CONVENTION
    assert result.evidence_capable
    assert {item.name for item in result.decision} == {"DECISIONS.md"}


def test_convention_lookup_respects_depth_bound(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "CLAUDE.md").write_text("too deep", encoding="utf-8")
    result = discover(tmp_path, max_depth=2, probe_runner=lambda cmd: False)
    assert result.policy == []


def test_no_policy_source_means_observations_not_tickets(tmp_path):
    """The role's own fail-safe: no evidence B, no ticket."""
    result = discover(tmp_path, probe_runner=lambda cmd: False)
    assert result.evidence_capable is False
    assert any("no policy source" in note for note in result.notes)


def test_noise_directories_are_skipped(tmp_path):
    junk = tmp_path / "node_modules" / "pkg"
    junk.mkdir(parents=True)
    (junk / "CLAUDE.md").write_text("noise", encoding="utf-8")
    result = discover(tmp_path, probe_runner=lambda cmd: False)
    assert result.policy == []


def test_file_sink_writes_a_finding(tmp_path):
    result = emit("Pointer drift", "body", Sink(), tmp_path, run_id="run-1")
    assert result.ok and result.kind == "file"
    assert "run-1" in result.ref


def test_file_sink_numbers_findings_of_one_run(tmp_path):
    emit("first", "b", Sink(), tmp_path, run_id="run-1")
    second = emit("second", "b", Sink(), tmp_path, run_id="run-1")
    assert "FINDING-02" in second.ref


def test_command_split_survives_native_windows_paths():
    """POSIX-Splitting frisst Backslashes -- und damit jeden Windows-Pfad.

    `shlex.split` behandelt `\\` als Escape. Ein nativ konfiguriertes Ziel wie
    `python C:\\_Local_DEV\\repos\\ticket-master\\bin\\ticket_master.py --intake`
    zerfaellt dabei zu `C:_Local_DEVreposticket-masterbinticket_master.py` -- eine
    Datei, die es nicht gibt. Die Senke scheitert, faellt still auf Dateien zurueck,
    und die oeffentliche Uebergabe wirkt "kaputt", obwohl die Konfiguration stimmt.
    Genau das ist ein Grund, warum nur die interne Verdrahtung des Ticketsystems je
    funktionierte (M-20260820-auditor-ticket-sink).
    """
    target = r"python C:\_Local_DEV\repos\ticket-master\bin\ticket_master.py --intake"
    parts = split_command(target)
    if os.name == "nt":
        assert parts == [
            "python",
            r"C:\_Local_DEV\repos\ticket-master\bin\ticket_master.py",
            "--intake",
        ]
        # Pfad mit Leerzeichen bleibt EIN Argument und verliert seine Quotes.
        quoted = r'"C:\Program Files\Python\python.exe" script.py --intake'
        assert split_command(quoted) == [
            r"C:\Program Files\Python\python.exe",
            "script.py",
            "--intake",
        ]
    else:
        assert parts[0] == "python" and parts[-1] == "--intake"


def test_command_sink_hands_over_title_and_body_verbatim(tmp_path):
    """Der oeffentliche Produzenten-Vertrag, festgenagelt am echten argv.

    Der Auditor kennt genau eine ausgehende Schnittstelle: er haengt an das
    konfigurierte Kommando `--title <titel> --body <text>` an und weiss sonst
    nichts ueber das Ticketsystem. Bis 2026-09-12 nahm `ticket_master.py --intake`
    kein `--body` entgegen, sodass nur die interne Verdrahtung ueber
    `lib/ticket_writer.py` funktionierte (M-20260820-auditor-ticket-sink).
    Dieser Test prueft die Produzentenseite ohne Mock: das Stub-Kommando gibt
    sein eigenes argv zurueck.
    """
    stub = (
        f"{shlex.quote(sys.executable)} -c "
        + shlex.quote("import json,sys; print(json.dumps(sys.argv[1:]))")
    )
    title = "Registry-Quellattestierung aktualisieren"
    body = "Zeile eins\nZeile zwei mit Umlauten: aeoeue\nZeile drei"

    result = emit_command(title, body, stub)

    assert result.ok, result.detail
    assert json.loads(result.ref) == ["--title", title, "--body", body]


def test_command_sink_falls_back_to_files_when_absent(tmp_path):
    """No ticket system installed is not a failure -- only no routing."""
    sink = Sink(kind="command", target="ticket-master --intake", enabled_probe="probe")
    result = emit("Finding", "body", sink, tmp_path, run_id="run-1", probe_runner=lambda c: False)
    assert result.ok
    assert result.fell_back
    assert result.kind == "file"
    assert "not available" in result.detail


def test_dot_github_is_not_skipped_as_a_git_prefix(tmp_path):
    """Fable-Review: startswith('.git') uebersprang auch .github -- genau das
    Verzeichnis, in dem ein Repository seine Regeln fuehrt."""
    workflows = tmp_path / ".github"
    workflows.mkdir()
    (workflows / "CONTRIBUTING.md").write_text("rules", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "CLAUDE.md").write_text("noise", encoding="utf-8")

    result = discover(tmp_path, probe_runner=lambda cmd: False)
    targets = [item.target for item in result.policy]
    assert any(".github" in target for target in targets)
    assert not any(f"{chr(92)}.git{chr(92)}" in target or "/.git/" in target for target in targets)
