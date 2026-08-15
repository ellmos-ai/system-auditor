"""Configuration -- a file that nothing reads is worse than none."""
import json

from system_auditor.config import load
from system_auditor.tokens import utcnow


def _write(tmp_path, data: dict):
    target = tmp_path / "system-auditor.config.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_the_shipped_example_actually_loads(tmp_path):
    """Until 0.5.0 nothing read the config: no json.load in src/, no --config.
    Every setting it documented -- grid, policy, stores, sink -- was inert."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "config/system-auditor.config.example.json"
    target = tmp_path / "system-auditor.config.json"
    target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    config = load(target, home="C:/Users/testuser")
    assert config.grid.period == "7d"
    assert config.domain_names() == ["beispiel-domaene"]
    assert config.policy["cross-system-rater"]["mode"] == "always"
    assert config.policy_stores  # not empty


def test_comment_keys_are_ignored_not_rejected(tmp_path):
    """The example carries its reasoning in _comment_* keys. It must keep
    explaining itself to the next human without breaking the loader."""
    path = _write(tmp_path, {"_comment": "warum", "_comment_x": "auch", "system": "H1"})
    assert load(path).system == "H1"


def test_home_placeholder_is_expanded(tmp_path):
    path = _write(tmp_path, {"reports_dir": "<HOME>/.system-auditor/reports"})
    assert load(path, home="C:/Users/x").reports_dir == "C:/Users/x/.system-auditor/reports"


def test_domain_placeholder_is_resolved_per_run(tmp_path):
    """Store entries are declared once and reused for every domain, so <domain>
    can only be filled when the run's domain is known."""
    path = _write(tmp_path, {
        "domains": [{"name": "bundles", "path": "<HOME>/x/bundles"}],
        "policy_stores": [{"name": "rules", "kind": "file", "target": "<domain>/CLAUDE.md"}],
    })
    config = load(path, home="C:/Users/x")
    assert "<domain>" in config.policy_stores[0]["target"]  # unresolved before the run

    for_run = config.for_domain("bundles")
    assert for_run.policy_stores[0]["target"] == "C:/Users/x/x/bundles/CLAUDE.md"


def test_placeholders_left_in_place_are_reported(tmp_path):
    """A config copied but never filled in would file reports under a name no
    other machine recognises -- and a missing auditor makes interrater
    comparison impossible."""
    path = _write(tmp_path, {"system": "<HOSTNAME>", "auditor": "<MODELL-ODER-AGENT>"})
    notes = load(path).notes
    assert any("system is unset" in note for note in notes)
    assert any("auditor is unset" in note for note in notes)


def test_a_broken_file_yields_defaults_with_a_reason(tmp_path):
    """An audit that cannot read its config should say so and run, not abort
    mid-sweep."""
    target = tmp_path / "system-auditor.config.json"
    target.write_text("{ this is not json", encoding="utf-8")
    config = load(target)
    assert config.grid.period == "7d"
    assert any("unreadable" in note for note in config.notes)


def test_a_missing_file_is_normal(tmp_path):
    config = load(tmp_path / "nope.json")
    assert config.source == "defaults"
    assert any("no config file found" in note for note in config.notes)


def test_an_absurd_period_falls_back_instead_of_exploding(tmp_path):
    path = _write(tmp_path, {"time_grid": {"period": "999999999d"}})
    config = load(path)
    assert config.grid.period == "7d"
    assert any("time_grid rejected" in note for note in config.notes)


def test_an_explicit_time_table_is_carried_through(tmp_path):
    path = _write(tmp_path, {
        "time_table": [{"token": "sprint-42", "from": "2026-08-10", "to": "2026-08-24"}]
    })
    config = load(path)
    assert config.table is not None
    assert config.table.token(utcnow().replace(year=2026, month=8, day=15)) == "sprint-42"


def test_the_aggregation_policy_comes_from_the_file(tmp_path):
    path = _write(tmp_path, {"aggregations": {"timeseries": {"mode": "always"}}})
    policy = load(path).policy
    assert policy["timeseries"]["mode"] == "always"
    assert policy["cross-system-rater"]["mode"] == "always"  # default kept
