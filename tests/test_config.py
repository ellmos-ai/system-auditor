"""Configuration -- a file that nothing reads is worse than none."""
import json

from system_auditor.config import live_host, load
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
    assert config.domain_names() == [
        "pages-drift",
        "beispiel-domaene",
        "beispiel-integrationspfad",
    ]
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


def test_integration_domain_members_survive_loading(tmp_path):
    """A domain may be an integration path: members[] names the links of a
    collaboration chain. The loader must carry unknown per-domain fields
    through untouched -- the role prompt reads them, not the library."""
    path = _write(tmp_path, {
        "domains": [{
            "name": "kette",
            "path": "<HOME>/familie",
            "members": ["<HOME>/familie/a", "<HOME>/familie/b"],
        }]
    })
    config = load(path, home="C:/U")
    entry = config.domains[0]
    assert entry["members"] == ["<HOME>/familie/a", "<HOME>/familie/b"]
    assert entry["path"] == "C:/U/familie"


def test_the_example_declares_an_integration_domain(tmp_path):
    """The shipped example must show the members[] concept -- config keys that
    only the prompt documents get lost."""
    import json
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "config/system-auditor.config.example.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    assert any("members" in d for d in raw["domains"])


def test_a_host_local_reports_dir_earns_a_warning(tmp_path):
    """Meta audits happen where reports physically meet. A host-local
    reports_dir means no second machine ever writes there -- warn, don't gate:
    an unrecognised sync tool is legitimate."""
    local = load(_write(tmp_path, {"reports_dir": "<HOME>/.system-auditor/reports"}))
    assert any("host-local" in note for note in local.notes)

    tmp2 = tmp_path / "b"
    tmp2.mkdir()
    shared = load(_write(tmp2, {"reports_dir": "<HOME>/OneDrive/x/reports"}))
    assert not any("host-local" in note for note in shared.notes)


def test_the_aggregation_policy_comes_from_the_file(tmp_path):
    path = _write(tmp_path, {"aggregations": {"timeseries": {"mode": "always"}}})
    policy = load(path).policy
    assert policy["timeseries"]["mode"] == "always"
    assert policy["cross-system-rater"]["mode"] == "always"  # default kept


# --- T-20260830-419610437: deterministische Hostbestimmung -------------------

def _write_host_cfg(tmp_path, **over):
    import json
    cfg = {"system": "SOME-HOST", "reports_dir": "X:/onedrive/reports"}
    cfg.update(over)
    target = tmp_path / "system-auditor.config.json"
    target.write_text(json.dumps(cfg), encoding="utf-8")
    return target


def test_host_mismatch_is_detected_and_named(tmp_path, monkeypatch):
    """Ein gesetzter, plausibler, aber FALSCHER Host muss auffallen.

    Der alte Check fing nur leer/Platzhalter ab -- also den vergesslichen Fall.
    Dieser hier ist der gefaehrliche: eine kopierte Config traegt den Hostnamen
    der Quellmaschine und besteht jede Plausibilitaetspruefung.
    """
    from system_auditor import config as cfgmod

    monkeypatch.setattr(cfgmod, "live_host", lambda: "REAL-HOST")
    cfg = cfgmod.load(_write_host_cfg(tmp_path, system="FOREIGN-HOST"))

    assert cfg.host_mismatch == ("FOREIGN-HOST", "REAL-HOST")
    assert any("FOREIGN-HOST" in n and "REAL-HOST" in n for n in cfg.notes)


def test_matching_host_is_silent(tmp_path, monkeypatch):
    """Stimmt der Host, darf nichts gemeldet werden -- sonst wird die Meldung Rauschen."""
    from system_auditor import config as cfgmod

    monkeypatch.setattr(cfgmod, "live_host", lambda: "REAL-HOST")
    cfg = cfgmod.load(_write_host_cfg(tmp_path, system="real-host"))  # Gross/Klein egal

    assert cfg.host_mismatch is None
    assert not any("reports" in n and "foreign host" in n for n in cfg.notes)


def test_unknown_live_host_does_not_claim_a_mismatch(tmp_path, monkeypatch):
    """Laesst sich der Host nicht ermitteln, ist das KEIN Fehlbefund.

    'nicht feststellbar' und 'stimmt nicht' sind verschiedene Aussagen; sie zu
    vermischen wuerde einen stillen Fehler in einen lauten Fehlalarm verwandeln.
    """
    from system_auditor import config as cfgmod

    monkeypatch.setattr(cfgmod, "live_host", lambda: "")
    cfg = cfgmod.load(_write_host_cfg(tmp_path, system="FOREIGN-HOST"))

    assert cfg.host_mismatch is None


def test_auditor_policy_per_run_reads_as_a_decision_not_an_oversight(tmp_path):
    """T-20260830-966677444: Absicht und Versaeumnis waren nicht unterscheidbar.

    Die alte Zeile ("a second model would overwrite this one's audit") stand bei
    JEDEM Aufruf -- auch bei reinen Leseabfragen, wo ein fehlender Token folgenlos
    ist. Ein Leser ohne Modulkenntnis hat sie daraufhin als Fehlkonfiguration
    gemeldet. Das ist tatsaechlich passiert und der Anlass dieses Tickets.
    """
    path = tmp_path / "system-auditor.config.json"
    path.write_text(
        json.dumps({"system": live_host() or "H1", "auditor_policy": "per-run"}),
        encoding="utf-8",
    )
    notes = " ".join(load(path).notes)
    assert "by design" in notes
    assert "would overwrite" not in notes


def test_without_the_policy_the_note_still_asks_for_a_token(tmp_path):
    """Ein wirklich vergessener Token muss weiterhin auffallen."""
    path = tmp_path / "system-auditor.config.json"
    path.write_text(json.dumps({"system": live_host() or "H1"}), encoding="utf-8")
    notes = " ".join(load(path).notes)
    assert "auditor is unset" in notes
    assert "per-run" in notes  # nennt den Ausweg, statt nur zu klagen
