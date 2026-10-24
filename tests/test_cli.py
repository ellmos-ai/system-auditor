"""CLI -- the surface the role prompt actually calls.

The Fable review found the CLI untested and, in fact, broken over its documented
invocation. These tests exercise it the way an auditor does: via main(argv).
"""
import json
from pathlib import Path

import pytest

from system_auditor import cli


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    cli._CONFIG_CACHE.clear()
    yield
    cli._CONFIG_CACHE.clear()


def _write_config(tmp_path, **extra):
    data = {"system": "HOST-A", **extra}
    path = tmp_path / "system-auditor.config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_discover_resolves_configured_domain_and_names_missing_store(tmp_path, capsys):
    domain = tmp_path / "domäne-ü"
    domain.mkdir()
    policy = domain / "README.md"
    policy.write_text("rules", encoding="utf-8")
    missing_decision = domain / "DECISIONS.md"
    config_path = _write_config(
        tmp_path,
        domains=[{"name": "example", "path": str(domain)}],
        policy_stores=[{"name": "domain-policy", "kind": "file", "target": "<domain>/README.md"}],
        decision_stores=[{"name": "domain-decisions", "kind": "file",
                          "target": "<domain>/DECISIONS.md"}],
    )
    rc = cli.main(["--config", str(config_path), "--json", "discover", "--domain", "example"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["tier"] == "configured"
    assert [Path(target) for target in payload["policy"]] == [policy]
    assert payload["decision"] == []
    assert payload["evidence_capable"] is True
    assert any(note.startswith("configured but not present: decision domain-decisions -> ")
               and Path(note.split(" -> ", 1)[1]) == missing_decision
               for note in payload["notes"])
    rc = cli.main(["--config", str(config_path), "discover", "--domain", "example"])
    plain = capsys.readouterr().out
    assert rc == 0
    assert "notes:" in plain
    assert "configured but not present: decision domain-decisions -> " in plain


def test_discover_domain_path_still_accepts_unconfigured_areas(tmp_path, capsys):
    domain = tmp_path / "ad-hoc"
    domain.mkdir()
    policy = domain / "CLAUDE.md"
    policy.write_text("rules", encoding="utf-8")
    config_path = _write_config(tmp_path)
    rc = cli.main(["--config", str(config_path), "--json", "discover",
                   "--domain-path", str(domain)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tier"] == "convention"
    assert payload["policy"] == [str(policy)]


def test_role_prompts_use_domain_name_for_configured_sources():
    prompts = Path(__file__).resolve().parents[1] / "prompts"
    for name in ("AUDITOR.de.md", "AUDITOR.en.md"):
        text = (prompts / name).read_text(encoding="utf-8")
        section = text.split("### (c)", 1)[1].split("### (d)", 1)[0]
        assert "discover --domain <name>" in section
        assert "discover --domain-path" in section


def test_auditor_flag_overrides_the_config_and_silences_the_warning(tmp_path, capsys, monkeypatch):
    """The auditor is a property of the model running now, not of the host --
    a shared host config cannot know it. First live run printed the unset
    warning on every call; the flag is the intended way to state identity."""
    monkeypatch.delenv("SYSTEM_AUDITOR_AUDITOR", raising=False)
    config_path = _write_config(tmp_path)
    rc = cli.main(["--config", str(config_path), "--auditor", "opus-5", "--json", "config"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["auditor"] == "opus-5"
    assert "auditor is unset" not in captured.err


def test_auditor_env_works_like_the_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SYSTEM_AUDITOR_AUDITOR", "codex")
    config_path = _write_config(tmp_path)
    rc = cli.main(["--config", str(config_path), "--json", "config"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["auditor"] == "codex"
    assert "auditor is unset" not in captured.err


def test_config_notes_print_once_even_when_a_command_loads_twice(tmp_path, capsys, monkeypatch):
    """meta-plan consults the config for the grid AND the policy. Before the
    cache, every note printed twice -- a warning that repeats reads as two
    problems."""
    monkeypatch.delenv("SYSTEM_AUDITOR_AUDITOR", raising=False)
    config_path = _write_config(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    rc = cli.main([
        "--config", str(config_path), "--json",
        "meta-plan", "--reports", str(reports), "--aggregation", "cross-system-rater",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err.count("auditor is unset") == 1


def test_meta_plan_uses_the_grid_anchor_not_todays_midnight(tmp_path, capsys, monkeypatch):
    """Regression guard for the 0.6.0 fix: two runs on different weekdays of
    one week must land in the same window token."""
    monkeypatch.delenv("SYSTEM_AUDITOR_AUDITOR", raising=False)
    config_path = _write_config(tmp_path)
    rc = cli.main(["--config", str(config_path), "--json", "time-token"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # The default grid is anchored on a Monday; the window must start on one.
    from datetime import datetime

    start = datetime.fromisoformat(str(payload["window_start"]))
    assert start.weekday() == 0
