"""Synthetic fixtures test the contract; production evidence uses the native engine."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

from system_auditor import installer_design as audit
from system_auditor.cli import main


def fixture(tmp_path, monkeypatch):
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    bundle = recipe / "bundle.v1.json"
    bundle.write_text('{"schema":"synthetic-test-only"}')
    installer = tmp_path / "installer" / "src"
    installer.mkdir(parents=True)
    ocean_cli = tmp_path / "ocean" / "tools" / "ocean_dev.py"
    ocean_cli.parent.mkdir(parents=True)
    ocean_cli.write_text("# synthetic test only\n")
    ocean = {"bundles_root": str(recipe), "ring": "addon"}
    for key in audit.REQUIRED_INPUTS:
        path = tmp_path / key
        path.write_bytes(b"captured test input")
        ocean[key] = str(path)
    Path(ocean["source_pins"]).write_text(json.dumps({"recipe": {
        "repository": "https://github.com/ellmos-ai/ellmos-development-system.git",
        "commit": "4" * 40,
    }}))
    design = {"schema": "ellmos.installer.design.v1", "components": ["module:alpha"],
              "target": {"mode": "portable", "root": str(tmp_path / "target")},
              "ocean": ocean, "content_hash": "sha256:synthetic-design"}
    path = tmp_path / "design.json"
    path.write_text(json.dumps(design))
    report = {"schema": "ellmos.open-ocean-up-report.v1", "apply": False,
              "verify": {"all_ok": True, "bundles_checked": 1,
                         "results": [{"ok": True, "manifest_path": str(bundle),
                                      "pinned_hash": "a" * 64, "declared_hash": "a" * 64,
                                      "computed_hash": "a" * 64}]},
              "source_pins": {"status": "verified"},
              "component_scope": {"expected": ["module:alpha"],
                                  "observed": ["module:alpha"], "match": True}}
    monkeypatch.setattr(audit, "_producer", lambda root, repository, commit:
                        {"repository": repository, "commit": commit})
    monkeypatch.setattr(audit, "_run_native", lambda *args:
                        observed(design, report))
    kwargs = {"installer_src": installer, "installer_commit": "1" * 40,
              "ocean_cli": ocean_cli, "ocean_commit": "2" * 40, "producer_commit": "3" * 40}
    return path, design, report, kwargs


def observed(design, report):
    policy_path = Path(report["verify"]["results"][0]["manifest_path"]) \
        if report["verify"]["results"] else Path(design["ocean"]["bundles_root"]) / "bundle.v1.json"
    actual_sha = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    return {"design_hash": design["content_hash"], "report": report,
            "policy_evidence": {str(policy_path): actual_sha},
            "bundle_evidence": {str(policy_path): {"sha256": actual_sha,
                                                    "content_hash": "a" * 64}}}


def test_complete_mechanical_receipt_from_executed_checks(tmp_path, monkeypatch):
    path, design, report, kwargs = fixture(tmp_path, monkeypatch)
    result = audit.audit_design(path, **kwargs)
    assert result["native_report"] == report
    assert result["design_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["target"] == design["target"]
    assert len(result["checks"]) == 8
    assert set(result["checks"].values()) == {"SUCCESS"}
    assert result["authorization"] is False
    assert result["runtime_verified"] is False
    assert not Path(design["target"]["root"]).exists()


@pytest.mark.parametrize("change", ["empty", "failed", "apply", "scope", "pins"])
def test_missing_or_failed_native_evidence_never_passes(tmp_path, monkeypatch, change):
    path, _, report, kwargs = fixture(tmp_path, monkeypatch)
    if change == "empty":
        report["verify"]["results"] = []
    elif change == "failed":
        report["verify"]["results"][0]["ok"] = False
    elif change == "apply":
        report["apply"] = True
    elif change == "scope":
        report["component_scope"]["observed"] += ["module:foreign"]
    else:
        report["source_pins"]["status"] = "missing"
    with pytest.raises(audit.DesignAuditError):
        audit.audit_design(path, **kwargs)


def test_inputs_consumed_are_immutable_snapshot_bytes(tmp_path, monkeypatch):
    path, design, report, kwargs = fixture(tmp_path, monkeypatch)
    def run(command, payload, timeout):
        captured = json.loads(payload)
        assert "--apply" not in command
        assert command[1:3] == ["-I", "-B"]
        for key in audit.REQUIRED_INPUTS:
            assert Path(captured["ocean"][key]).read_bytes() == (
                Path(design["ocean"][key]).read_bytes()
            )
            assert captured["ocean"][key] != design["ocean"][key]
        return observed(design, report)
    monkeypatch.setattr(audit, "_run_native", run)
    audit.audit_design(path, **kwargs)


@pytest.mark.parametrize("kind", ["input", "design", "target", "producer"])
def test_concurrent_changes_fail_closed(tmp_path, monkeypatch, kind):
    path, design, report, kwargs = fixture(tmp_path, monkeypatch)
    calls = 0
    def producer(*args):
        nonlocal calls
        calls += 1
        if kind == "producer" and calls > 4:
            raise audit.DesignAuditError("changed producer")
        return {"repository": args[1], "commit": args[2]}
    monkeypatch.setattr(audit, "_producer", producer)
    def run(*args):
        if kind == "input":
            Path(design["ocean"]["gui_archive"]).write_bytes(b"changed")
        elif kind == "design":
            path.write_text("{}")
        elif kind == "target":
            Path(design["target"]["root"]).mkdir()
        return observed(design, report)
    monkeypatch.setattr(audit, "_run_native", run)
    with pytest.raises(audit.DesignAuditError):
        audit.audit_design(path, **kwargs)


def test_timeout_terminates_before_returning_failure():
    with pytest.raises(audit.DesignAuditError, match="timed out"):
        audit._run_native([sys.executable, "-c", "import time; time.sleep(30)"], b"", .1)


def test_timeout_terminates_child_tree_before_delayed_mutation(tmp_path):
    marker = tmp_path / "delayed-child"
    child = f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).touch()"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]);" \
             " time.sleep(30)"
    with pytest.raises(audit.DesignAuditError, match="timed out"):
        audit._run_native([sys.executable, "-c", parent], b"", .3)
    time.sleep(2.2)
    assert not marker.exists()


def test_invalid_producer_pin_is_rejected_before_any_git_call(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError("invalid pin must not query/import a producer")
    monkeypatch.setattr(audit, "_git", forbidden)
    with pytest.raises(audit.DesignAuditError, match="immutable"):
        audit._producer(tmp_path, "https://github.com/ellmos-ai/system-auditor", "short")


def test_bundle_policy_changed_after_native_verification_is_rejected(tmp_path, monkeypatch):
    path, design, report, kwargs = fixture(tmp_path, monkeypatch)
    def run(*args):
        result = observed(design, report)
        Path(report["verify"]["results"][0]["manifest_path"]).write_text("changed policy")
        return result
    monkeypatch.setattr(audit, "_run_native", run)
    with pytest.raises(audit.DesignAuditError, match="policy bytes"):
        audit.audit_design(path, **kwargs)


def test_cli_failure_prints_no_receipt(tmp_path, capsys):
    code = main(["--json", "installer-design", "--design", str(tmp_path / "missing"),
                 "--installer-src", str(tmp_path), "--installer-commit", "1" * 40,
                 "--ocean-cli", str(tmp_path / "ocean.py"), "--ocean-commit", "2" * 40,
                 "--producer-commit", "3" * 40])
    output = capsys.readouterr()
    assert code == 2 and output.out == "" and "ERROR" in output.err
