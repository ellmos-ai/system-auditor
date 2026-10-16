"""Synthetic fixtures test the contract; production evidence uses the native engine."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
    Path(ocean["source_pins"]).write_text(
        json.dumps(
            {
                "recipe": {
                    "repository": "https://github.com/ellmos-ai/ellmos-development-system.git",
                    "commit": "4" * 40,
                }
            }
        )
    )
    design = {
        "schema": "ellmos.installer.design.v1",
        "components": ["module:alpha"],
        "target": {"mode": "portable", "root": str(tmp_path / "target")},
        "ocean": ocean,
        "content_hash": "sha256:synthetic-design",
    }
    path = tmp_path / "design.json"
    path.write_text(json.dumps(design))
    report = {
        "schema": "ellmos.open-ocean-up-report.v1",
        "apply": False,
        "verify": {
            "all_ok": True,
            "bundles_checked": 1,
            "results": [
                {
                    "ok": True,
                    "manifest_path": str(bundle),
                    "pinned_hash": "a" * 64,
                    "declared_hash": "a" * 64,
                    "computed_hash": "a" * 64,
                }
            ],
        },
        "source_pins": {"status": "verified"},
        "component_scope": {
            "expected": ["module:alpha"],
            "observed": ["module:alpha"],
            "match": True,
        },
    }
    monkeypatch.setattr(
        audit,
        "_producer",
        lambda root, repository, commit: {"repository": repository, "commit": commit},
    )
    monkeypatch.setattr(audit, "_run_native", lambda *args: observed(design, report))
    kwargs = {
        "installer_src": installer,
        "installer_commit": "1" * 40,
        "ocean_cli": ocean_cli,
        "ocean_commit": "2" * 40,
        "producer_commit": "3" * 40,
    }
    return path, design, report, kwargs


def observed(design, report):
    policy_path = (
        Path(report["verify"]["results"][0]["manifest_path"])
        if report["verify"]["results"]
        else Path(design["ocean"]["bundles_root"]) / "bundle.v1.json"
    )
    actual_sha = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    return {
        "design_hash": design["content_hash"],
        "report": report,
        "policy_evidence": {str(policy_path): actual_sha},
        "bundle_evidence": {str(policy_path): {"sha256": actual_sha, "content_hash": "a" * 64}},
    }


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
        audit._run_native([sys.executable, "-c", "import time; time.sleep(30)"], b"", 0.1)


def test_successful_native_parent_cannot_leave_a_detached_writer(tmp_path):
    marker = tmp_path / "late-descendant-write"
    child = f"import time,pathlib; time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    parent = (
        "import subprocess,sys,json; "
        f"p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',{child!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "print(json.dumps({'ok':True,'child':p.pid}),flush=True)"
    )
    report = audit._run_native([sys.executable, "-I", "-S", "-B", "-c", parent], b"", 10)
    assert report["ok"] is True
    time.sleep(1.3)
    assert not marker.exists(), "a descendant wrote after a successful audit returned"


def test_native_gate_preserves_argv_and_exact_input_bytes():
    payload = "äΩ & ' \n".encode() * 10000
    argv = ["space and & punctuation", "äΩ"]
    code = (
        "import sys,json,hashlib; b=sys.stdin.buffer.read(); "
        "print(json.dumps({'argv':sys.argv[1:],'sha':hashlib.sha256(b).hexdigest()}))"
    )
    report = audit._run_native([sys.executable, "-I", "-S", "-B", "-c", code, *argv],
                               payload, 10)
    assert report == {"argv": argv, "sha": hashlib.sha256(payload).hexdigest()}


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
@pytest.mark.parametrize("failure", ["__enter__", "assign"])
def test_windows_containment_failure_never_releases_command(tmp_path, monkeypatch, failure):
    from system_auditor._windows_job import WindowsAuditJob

    def unavailable(*_args):
        raise OSError("synthetic containment failure")

    monkeypatch.setattr(WindowsAuditJob, failure, unavailable)
    marker = tmp_path / "must-not-run"
    code = f"from pathlib import Path; Path({str(marker)!r}).touch(); print('{{}}')"
    with pytest.raises(audit.DesignAuditError, match="containment"):
        audit._run_native([sys.executable, "-I", "-S", "-B", "-c", code], b"", 10)
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows job kill-on-close")
def test_native_controller_death_terminates_its_writers(tmp_path):
    ready, marker = tmp_path / "writer-ready", tmp_path / "late-writer"
    child = (
        f"import pathlib,time; pathlib.Path({str(ready)!r}).touch(); "
        f"time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-I','-S','-B','-c',{child!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "time.sleep(2); print('{}')"
    )
    source = str(Path(audit.__file__).resolve().parents[1])
    controller = (
        f"import sys; sys.path.insert(0,{source!r}); "
        "from system_auditor.installer_design import _run_native; "
        f"_run_native([sys.executable,'-I','-S','-B','-c',{parent!r}],b'',10)"
    )
    with subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", controller],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as process:
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "contained writer did not reach the synchronization point"
        finally:
            if process.poll() is None:
                process.kill()  # Held Popen HANDLE of this test's controller.
            process.wait(timeout=10)
    time.sleep(2.2)
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows job kill-on-close")
def test_cleanup_error_cannot_return_pass_or_leave_a_writer(tmp_path, monkeypatch):
    from system_auditor._windows_job import WindowsAuditJob

    def fail_cleanup(_self):
        raise OSError("synthetic termination failure")

    monkeypatch.setattr(WindowsAuditJob, "terminate_and_wait", fail_cleanup)
    marker = tmp_path / "late-cleanup-writer"
    child = f"import time,pathlib; time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-I','-S','-B','-c',{child!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "print('{}',flush=True)"
    )
    with pytest.raises(audit.DesignAuditError, match="containment"):
        audit._run_native([sys.executable, "-I", "-S", "-B", "-c", parent], b"", 10)
    time.sleep(1.3)
    assert not marker.exists()


def test_native_output_byte_bound_never_produces_pass(tmp_path):
    marker = tmp_path / "late-audit-write"
    code = (
        "import sys,time,pathlib;sys.stdout.write('x'*20000000);sys.stdout.flush();"
        f"time.sleep(2);pathlib.Path({str(marker)!r}).touch()"
    )
    with pytest.raises(audit.DesignAuditError, match="output exceeded"):
        audit._run_native([sys.executable, "-I", "-S", "-B", "-c", code], b"", 20)
    import time

    time.sleep(2.1)
    assert not marker.exists()


def test_oversized_physical_input_never_reaches_audit(tmp_path):
    path = tmp_path / "oversized-design.json"
    with path.open("wb") as source:
        source.truncate(64 * 1024 * 1024 + 1)
    with pytest.raises(audit.DesignAuditError, match="oversized"):
        audit._input_bytes(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX physical FIFO capture")
def test_physical_audit_fifo_is_rejected_without_waiting(tmp_path):
    import time

    path = tmp_path / "design-fifo"
    os.mkfifo(path)
    started = time.monotonic()
    with pytest.raises(audit.DesignAuditError, match="unsupported"):
        audit._input_bytes(path)
    assert time.monotonic() - started < 1


def test_timeout_terminates_child_tree_before_delayed_mutation(tmp_path):
    marker = tmp_path / "delayed-child"
    child = f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).touch()"
    parent = (
        f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]);"
        " time.sleep(30)"
    )
    with pytest.raises(audit.DesignAuditError, match="timed out"):
        audit._run_native([sys.executable, "-c", parent], b"", 0.3)
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
    code = main(
        [
            "--json",
            "installer-design",
            "--design",
            str(tmp_path / "missing"),
            "--installer-src",
            str(tmp_path),
            "--installer-commit",
            "1" * 40,
            "--ocean-cli",
            str(tmp_path / "ocean.py"),
            "--ocean-commit",
            "2" * 40,
            "--producer-commit",
            "3" * 40,
        ]
    )
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert "ERROR" in output.err


@pytest.mark.parametrize(
    "kind",
    [
        "valid",
        "missing",
        "empty",
        "failed",
        "plan",
        "mutation",
        "late-drift",
        "late-design",
        "late-target",
        "late-policy",
        "late-recipe",
        "late-producer",
        *("late-input:" + key for key in audit.REQUIRED_INPUTS),
    ],
)
def test_package_audit_requires_additional_actual_evidence_and_final_recheck(
    tmp_path, monkeypatch, kind
):
    # Synthetic adapter evidence exercises the receipt gate, not native adoption.
    path, design, report, kwargs = fixture(tmp_path, monkeypatch)
    package = {
        "content_hash": "sha256:" + "5" * 64,
        "request": {"profile_id": "synthetic-test", "profile_sha256": "6" * 64},
    }
    design["ocean"]["python_packages"] = package
    path.write_text(json.dumps(design))
    checks = dict.fromkeys(
        ("profile-binding", "environment-binding", "wheel-closure", "beforestate", "no-apply"),
        "SUCCESS",
    )
    evidence = {
        "schema": "ellmos.ocean.python-packages.audit.v1",
        "plan_hash": package["content_hash"],
        "profile_id": "synthetic-test",
        "profile_sha256": "6" * 64,
        "checks": checks,
        "target_before_hash": "sha256:" + "7" * 64,
        "target_after_hash": "sha256:" + "7" * 64,
        "runtime_verified": False,
    }
    report["python_packages"] = {
        "plan_hash": package["content_hash"],
        "checks": checks,
        "target_before_hash": evidence["target_before_hash"],
        "target_after_hash": evidence["target_after_hash"],
    }
    if kind == "empty":
        evidence["checks"] = {}
    elif kind == "failed":
        checks["wheel-closure"] = "FAIL"
    elif kind == "plan":
        report["python_packages"]["plan_hash"] = "sha256:" + "0" * 64
    elif kind == "mutation":
        evidence["target_after_hash"] = "sha256:" + "8" * 64
    calls = []
    final_child_completed = False

    def producer(root, repository, commit):
        if final_child_completed and (
            kind == "late-producer"
            or (kind == "late-recipe" and root == Path(design["ocean"]["bundles_root"]))
        ):
            raise audit.DesignAuditError("changed producer after final child")
        return {"repository": repository, "commit": commit}

    monkeypatch.setattr(audit, "_producer", producer)

    def run(command, payload, timeout):
        nonlocal final_child_completed
        message = json.loads(payload)
        calls.append(message)
        if message.get("operation") == "package-check":
            final_child_completed = True
            if kind.startswith("late-input:"):
                Path(design["ocean"][kind.split(":", 1)[1]]).write_bytes(
                    b"legitimate concurrent change"
                )
            elif kind == "late-design":
                path.write_text("{}")
            elif kind == "late-target":
                Path(design["target"]["root"]).mkdir()
            elif kind == "late-policy":
                Path(report["verify"]["results"][0]["manifest_path"]).write_text("changed policy")
            return {**evidence, "profile_sha256": "9" * 64} if kind == "late-drift" else evidence
        value = observed(design, report)
        if kind != "missing":
            value["python_packages"] = evidence
        return value

    monkeypatch.setattr(audit, "_run_native", run)
    if kind == "valid":
        result = audit.audit_design(path, **kwargs)
        assert result["python_packages"] == evidence
        assert len(result["checks"]) == 8
        assert len(result["input_sha256"]) == 6
        assert result["runtime_verified"] is False
        assert len(calls) == 2
        assert calls[-1]["operation"] == "package-check"
        assert calls[-1]["design"]["ocean"]["python_packages"] == package
    else:
        with pytest.raises(audit.DesignAuditError):
            audit.audit_design(path, **kwargs)
    assert Path(design["target"]["root"]).exists() is (kind == "late-target")
