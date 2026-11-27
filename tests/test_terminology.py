"""Tests for the aggregated multi-repo terminology congruence hook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from system_auditor import TerminologyAuditError, audit_terminology
from system_auditor.cli import main as cli_main


def _write_spec(path: Path) -> Path:
    spec = {
        "schema": "ellmos.ocean-terminology-congruence.v1",
        "schema_version": 1,
        "decided_at": "2026-11-27",
        "policy": {
            "one_term_per_concept": True,
            "preserve_legacy_wire_compatibility": True,
            "forbidden_in_new_ui_and_docs": [
                "Hardware-Fackel",
                "Aktueller Fackelhalter",
                "Steckplatz einrichten",
                "Agenten-Fabrik",
            ],
        },
        "concepts": [
            {
                "id": "stage1_ram_allocation",
                "canonical_de": "RAM-Zuteilung",
                "legacy_wire_compat": ["/api/fackel", "fackel"],
                "deprecated_ui_terms": ["Hardware-Fackel", "Aktueller Fackelhalter"],
            },
            {
                "id": "stage2_model_time_allocation",
                "canonical_de": "Modellzeit-Zuteilung",
                "legacy_wire_compat": ["compute_turn"],
                "deprecated_ui_terms": ["Model Torch"],
            },
            {
                "id": "configured_agent",
                "canonical_de": "Agent",
                "legacy_wire_compat": ["/api/slots", "slots_config.json"],
                "deprecated_ui_terms": ["Steckplatz einrichten"],
            },
            {
                "id": "library_role_template",
                "canonical_de": "Rollenvorlage",
                "legacy_wire_compat": ["ellmos.role-socket-catalog.v1"],
                "deprecated_ui_terms": ["Agenten-Fabrik"],
            },
        ],
    }
    target = path / "terminology-congruence.v1.json"
    target.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def test_builtin_multi_repo_audit_separates_legacy_wire_and_flags_asymmetry(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path)
    gui = tmp_path / "ellmos-system-gui"
    (gui / "src" / "pages").mkdir(parents=True)
    (gui / "src" / "pages" / "running.astro").write_text(
        '<div id="fackel-box">RAM-Zuteilung &amp; Modellzeit-Zuteilung</div>\n'
        '<script>fetch("/api/fackel"); fetch("/api/slots");</script>\n',
        encoding="utf-8",
    )

    ocean = tmp_path / "open-ocean"
    ocean.mkdir()
    (ocean / "README.md").write_text(
        "# OCEAN\nNutzt RAM-Zuteilung und Modellzeit-Zuteilung.\n", encoding="utf-8"
    )

    clean = audit_terminology(spec, [gui, ocean], prefer_doc_keeper=False)
    assert clean.ok is True
    assert clean.engine == "builtin"
    assert clean.total_violations == 0
    assert clean.total_legacy_wire_compat_hits >= 1

    # Add a drifting repo to verify cross-repo asymmetry detection
    bach = tmp_path / "bach"
    bach.mkdir()
    (bach / "README.md").write_text("Steuert die Hardware-Fackel im Host.\n", encoding="utf-8")

    dirty = audit_terminology(spec, [gui, ocean, bach], prefer_doc_keeper=False)
    assert dirty.ok is False
    assert dirty.total_violations == 1
    assert dirty.violations_by_repo == {"ellmos-system-gui": 0, "open-ocean": 0, "bach": 1}
    assert len(dirty.cross_repo_findings) == 1
    assert dirty.cross_repo_findings[0]["repo"] == "bach"
    assert dirty.cross_repo_findings[0]["canonical_de"] == "RAM-Zuteilung"
    assert set(dirty.cross_repo_findings[0]["aligned_peer_repos"]) == {
        "ellmos-system-gui",
        "open-ocean",
    }


def test_cli_terminology_supports_repos_root_and_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _write_spec(tmp_path)
    root = tmp_path / "repos"
    (root / "repo-ok").mkdir(parents=True)
    (root / "repo-ok" / "README.md").write_text("RAM-Zuteilung aktiv.\n", encoding="utf-8")
    (root / "repo-bad").mkdir(parents=True)
    (root / "repo-bad" / "README.md").write_text(
        "Willkommen in der Agenten-Fabrik.\n", encoding="utf-8"
    )

    rc_ok = cli_main(
        [
            "--json",
            "terminology",
            "--spec",
            str(spec),
            "--repos-root",
            str(root),
            "--repos",
            "repo-ok",
            "--builtin-only",
        ]
    )
    assert rc_ok == 0
    payload_ok = json.loads(capsys.readouterr().out)
    assert payload_ok["ok"] is True
    assert payload_ok["domain"] == "terminology-congruence"

    rc_bad = cli_main(
        [
            "--json",
            "terminology",
            "--spec",
            str(spec),
            "--repos-root",
            str(root),
            "--repos",
            "repo-ok,repo-bad",
            "--builtin-only",
        ]
    )
    assert rc_bad == 1
    payload_bad = json.loads(capsys.readouterr().out)
    assert payload_bad["ok"] is False
    assert payload_bad["summary"]["total_violations"] == 1


def test_invalid_inputs_raise_and_return_exit_2(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(TerminologyAuditError):
        audit_terminology(missing, [tmp_path], prefer_doc_keeper=False)
    assert cli_main(["terminology", "--spec", str(missing), "--repo", str(tmp_path)]) == 2
