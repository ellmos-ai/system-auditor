"""Bounded local mechanical audit through the existing Installer/Ocean engine."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .discovery import discover

REQUIRED_INPUTS = (
    "modules_catalog",
    "skills_registry",
    "system_manifest",
    "component_bindings",
    "source_pins",
    "gui_archive",
)
CHILD = """
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
sys.path.insert(0,str(Path(sys.argv[2]).resolve().parents[1]))
sys.path.insert(0,sys.argv[3])
from ellmos_installer.adapters import OpenOceanAdapter,_verify_core_source,_bind_core_capture
from ellmos_installer.contracts import validate_design_hash
from ellmos_installer.jsonio import content_hash
from system_auditor.discovery import discover
from system_auditor.installer_design import _input_bytes
payload=json.loads(sys.stdin.buffer.read(67108865))
design=payload['design']
validate_design_hash(design)
core=None
if 'python_packages' in design['ocean']:
    root,captured=_verify_core_source(Path(sys.argv[2]),payload['ocean_producer'])
    core=_bind_core_capture(root,captured)
    canonical_hash,load_system_manifest,verify_bundle=core.canonical_hash,core.load_system_manifest,core.verify_bundle
else:
    from tools.resolve_bundles import canonical_hash,load_system_manifest,verify_bundle
def package_evidence():
    plan=design['ocean']['python_packages']
    core.validate_package_plan(plan,set(design['components']))
    before=core.package_hash(core.package_target_state(plan))
    return {'schema':'ellmos.ocean.python-packages.audit.v1','plan_hash':plan['content_hash'],
            'profile_id':plan['request']['profile_id'],'profile_sha256':plan['request']['profile_sha256'],
            'checks':plan['checks'],'target_before_hash':before,'target_after_hash':before,
            'runtime_verified':False}
if payload.get('operation')=='package-check':
    print(json.dumps(package_evidence(),sort_keys=True));sys.exit(0)
package_before=package_evidence() if 'python_packages' in design['ocean'] else None
execution=dict(design)
execution['ocean']=dict(design['ocean'])
execution['ocean'].update(payload['ocean'])
execution.pop('content_hash')
execution['content_hash']=content_hash(execution)
recipe=Path(execution['ocean']['bundles_root'])
policy_bytes={}
bundles={}
for reference in load_system_manifest(Path(execution['ocean']['system_manifest']))['bundle_refs']:
    checked,_=verify_bundle(reference,recipe)
    if not checked.ok: raise ValueError('native bundle preflight failed')
    path=Path(checked.manifest_path).resolve(strict=True)
    raw=_input_bytes(path)
    manifest=json.loads(raw)
    observed_hash=canonical_hash(manifest)
    if (observed_hash != checked.computed_hash
            or manifest.get('content_hash') != checked.declared_hash):
        raise ValueError('bundle changed after native preflight')
    bundles[str(path)]={'sha256':hashlib.sha256(raw).hexdigest(),'content_hash':observed_hash}
    found=discover(path.parent,max_depth=0)
    if not found.evidence_capable: raise ValueError('native policy discovery missing')
    for source in found.policy:
        policy_path=Path(source.target).resolve(strict=True)
        policy_bytes[str(policy_path)]=raw if policy_path==path else _input_bytes(policy_path)
report=OpenOceanAdapter(Path(sys.argv[2])).plan_design(execution,producer_pin=payload.get('ocean_producer'))
if package_before is not None:
    native=report.get('python_packages') or {}
    after=core.package_hash(core.package_target_state(design['ocean']['python_packages']))
    if (native.get('plan_hash')!=design['ocean']['python_packages']['content_hash']
            or native.get('checks')!=package_before['checks']
            or native.get('target_before_hash')!=package_before['target_before_hash']
            or native.get('target_after_hash')!=after
            or after!=package_before['target_before_hash'] or 'apply' in native):
        raise ValueError('native package no-apply evidence differs')
for row in report['verify']['results']:
    evidence=bundles[str(Path(row['manifest_path']).resolve(strict=True))]
    if any(row.get(key)!=evidence['content_hash']
           for key in ('pinned_hash','declared_hash','computed_hash')):
        raise ValueError('reported bundle differs from captured policy')
for path,raw in policy_bytes.items():
    if _input_bytes(Path(path))!=raw: raise ValueError('native policy changed during plan')
print(json.dumps({'design_hash':design['content_hash'],'report':report,'bundle_evidence':bundles,
                 'python_packages':package_before,
                 'policy_evidence':{path:hashlib.sha256(raw).hexdigest()
                                    for path,raw in policy_bytes.items()}},sort_keys=True))
"""


class DesignAuditError(ValueError):
    """No mechanical PASS can be issued for these inputs."""


def _package_evidence(design: dict, observed: dict, report: dict) -> dict | None:
    if "python_packages" not in design["ocean"]:
        return None
    plan = design["ocean"]["python_packages"]
    evidence = observed.get("python_packages")
    native = report.get("python_packages")
    checks = {"profile-binding", "environment-binding", "wheel-closure", "beforestate", "no-apply"}
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema") != "ellmos.ocean.python-packages.audit.v1"
        or evidence.get("plan_hash") != plan["content_hash"]
        or evidence.get("profile_id") != plan["request"]["profile_id"]
        or evidence.get("profile_sha256") != plan["request"]["profile_sha256"]
        or evidence.get("runtime_verified") is not False
        or not isinstance(evidence.get("checks"), dict)
        or set(evidence["checks"]) != checks
        or any(value != "SUCCESS" for value in evidence["checks"].values())
        or not isinstance(native, dict)
        or native.get("plan_hash") != plan["content_hash"]
        or native.get("checks") != evidence["checks"]
        or "apply" in native
    ):
        raise DesignAuditError("actual native package plan/check evidence missing or unbound")
    before = evidence.get("target_before_hash")
    if (
        not isinstance(before, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", before)
        or evidence.get("target_after_hash") != before
        or native.get("target_before_hash") != before
        or native.get("target_after_hash") != before
    ):
        raise DesignAuditError("native package target changed during no-apply audit")
    return evidence


def _hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=20,
    )
    if result.returncode:
        raise DesignAuditError("cannot verify native producer Git identity")
    return result.stdout.strip()


def _producer(root: Path, repository: str, commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DesignAuditError("full immutable producer commit required")
    root = root.resolve(strict=True)
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise DesignAuditError("producer must be the actual checkout root")
    if _git(root, "rev-parse", "HEAD") != commit:
        raise DesignAuditError("producer HEAD differs from declared pin")
    actual = _git(root, "remote", "get-url", "origin").removesuffix(".git").rstrip("/")
    if actual != repository.removesuffix(".git").rstrip("/"):
        raise DesignAuditError("producer origin differs from canonical repository")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise DesignAuditError("native producer checkout is not clean")
    return {"repository": repository, "commit": commit}


@contextlib.contextmanager
def _native_job():
    if os.name != "nt":
        yield None
        return
    from ._windows_job import WindowsAuditJob

    try:
        with WindowsAuditJob() as job:
            yield job
    except OSError as exc:
        raise DesignAuditError(
            "native audit process containment failed; no mechanical PASS"
        ) from exc


def _run_native(command: list[str], payload: bytes, timeout: float) -> dict:
    if len(payload) > 64 * 1024 * 1024:
        raise DesignAuditError("native audit input exceeds byte bound")
    if os.name == "nt":
        from ._windows_job import frame_command

        try:
            command, payload = frame_command(command, payload)
        except ValueError as exc:
            raise DesignAuditError("native audit command exceeds gate contract") from exc
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options
    ) as process, _native_job() as job:
        if job is not None:
            try:
                job.assign(process)
            except OSError:
                # No command frame has been sent. Kill only the held Popen
                # handle for the trusted gate, never a rediscovered PID.
                process.kill()
                process.wait(timeout=20)
                raise
        output = [bytearray(), bytearray()]
        exceeded = threading.Event()
        guard = threading.Lock()

        def capture(stream, index):
            while chunk := stream.read(65536):
                with guard:
                    if sum(map(len, output)) + len(chunk) > 16 * 1024 * 1024:
                        exceeded.set()
                    elif not exceeded.is_set():
                        output[index].extend(chunk)

        def send():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threads = [
            threading.Thread(target=capture, args=(stream, index), daemon=True)
            for index, stream in enumerate((process.stdout, process.stderr))
        ]
        threads.append(threading.Thread(target=send, daemon=True))
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None or any(thread.is_alive() for thread in threads):
                if exceeded.is_set() or time.monotonic() >= deadline:
                    raise DesignAuditError(
                        "native audit timed out/output exceeded; no unchanged/PASS claim"
                    )
                time.sleep(0.01)
            if process.returncode:
                raise DesignAuditError("native no-apply plan failed; no mechanical PASS")
            stdout = bytes(output[0])
        finally:
            if job is not None:
                job.terminate_and_wait()
            else:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=20)
            for thread in threads:
                thread.join(timeout=20)
            if any(thread.is_alive() for thread in threads):
                raise DesignAuditError("audit process/output termination is unconfirmed")
    try:
        value = json.loads(stdout)
    except (ValueError, UnicodeError) as exc:
        raise DesignAuditError("native adapter returned no valid report") from exc
    if not isinstance(value, dict):
        raise DesignAuditError("native adapter report must be an object")
    return value


def _input_bytes(path: Path) -> bytes:
    descriptor = None
    limit = 64 * 1024 * 1024
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise DesignAuditError("native design/input is unsupported or oversized")
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        )

        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns)

        if identity(os.fstat(descriptor)) != identity(before):
            raise DesignAuditError("native design/input identity changed before capture")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            raw = source.read(limit + 1)
        if (
            len(raw) > limit
            or identity(os.fstat(descriptor)) != identity(before)
            or identity(path.lstat()) != identity(before)
        ):
            raise DesignAuditError("native design/input changed during bounded capture")
        return raw
    except OSError as exc:
        raise DesignAuditError("native design/input could not be captured safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _payload(original: bytes, extra: dict) -> bytes:
    # Preserve the exact captured design bytes. Serialize only small technical
    # locators/pins, never materialize the full package plan a second time.
    tail = json.dumps(extra, ensure_ascii=False).encode()
    if len(original) + len(tail) + 16 > 64 * 1024 * 1024:
        raise DesignAuditError("native audit DTO exceeds byte bound")
    return b'{"design":' + original + b"," + tail[1:]


def _target_state(root: Path, components: list[str]) -> dict:
    """Only stat explicitly selected technical module placements; never read contents."""
    if not root.is_absolute():
        raise DesignAuditError("target must be an absolute local path on this host")
    if root.is_symlink() or (root / "modules").is_symlink():
        raise DesignAuditError("target or module parent is a symlink")
    result = {}
    count = 0
    paths = [root, root / "modules"]
    for ref in components:
        kind, _, name = ref.partition(":")
        if kind != "module" or not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise DesignAuditError("bounded audit supports explicit module placements only")
        selected = root / "modules" / name
        if selected.is_symlink():
            raise DesignAuditError("selected technical module placement is a symlink")
        paths.append(selected)
        if selected.is_dir():
            for current, directories, files in os.walk(selected, followlinks=False):
                for name_in_tree in directories + files:
                    paths.append(Path(current) / name_in_tree)
                    count += 1
                    if count > 50000:
                        raise DesignAuditError("technical placement metadata exceeds audit bound")
    for path in paths:
        try:
            stat = path.lstat()
        except FileNotFoundError:
            result[str(path)] = None
        else:
            result[str(path)] = [stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ino]
    return result


def audit_design(
    design_path: Path,
    *,
    installer_src: Path,
    installer_commit: str,
    ocean_cli: Path,
    ocean_commit: str,
    producer_commit: str,
    timeout: float = 60,
) -> dict:
    """Return evidence for actual mechanical checks; errors never produce PASS."""
    if timeout <= 0 or timeout > 300:
        raise DesignAuditError("audit timeout must be between 0 and 300 seconds")
    original = _input_bytes(design_path)
    try:
        design = json.loads(original)
    except (ValueError, UnicodeError) as exc:
        raise DesignAuditError("invalid design JSON") from exc
    if not isinstance(design, dict) or design.get("schema") != "ellmos.installer.design.v1":
        raise DesignAuditError("native installer design required")
    installer_src = installer_src.resolve(strict=True)
    ocean_cli = ocean_cli.resolve(strict=True)
    auditor_root = Path(__file__).resolve().parents[2]
    identities = {
        "system-auditor": (
            auditor_root,
            "https://github.com/ellmos-ai/system-auditor",
            producer_commit,
        ),
        "ellmos-installer": (
            installer_src.parent,
            "https://github.com/ellmos-ai/ellmos-installer",
            installer_commit,
        ),
        "open-ocean": (
            ocean_cli.parent.parent,
            "https://github.com/ellmos-ai/open-ocean",
            ocean_commit,
        ),
    }
    if (
        installer_src.name != "src"
        or ocean_cli.name != "ocean_dev.py"
        or ocean_cli.parent.name != "tools"
    ):
        raise DesignAuditError("canonical native source entry points required")
    producers = {name: _producer(*identity) for name, identity in identities.items()}
    ocean = design.get("ocean")
    components = design.get("components")
    if not isinstance(ocean, dict) or not isinstance(components, list) or not components:
        raise DesignAuditError("explicit nonempty design scope required")
    if ocean.get("skeleton"):
        raise DesignAuditError("mechanical add-on audit does not cover skeleton installation")
    target = Path(design["target"]["root"])
    before = _target_state(target, components)
    input_bytes = {key: _input_bytes(Path(ocean[key])) for key in REQUIRED_INPUTS}
    input_hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in input_bytes.items()}
    recipe = Path(ocean["bundles_root"]).resolve(strict=True)
    recipe_pin = json.loads(input_bytes["source_pins"])["recipe"]
    if (
        recipe_pin["repository"].removesuffix(".git")
        != "https://github.com/ellmos-ai/ellmos-development-system"
    ):
        raise DesignAuditError("canonical native recipe repository required")
    recipe_identity = _producer(recipe, recipe_pin["repository"], recipe_pin["commit"])
    if Path(tempfile.gettempdir()).resolve().is_relative_to(target.resolve(strict=False)):
        raise DesignAuditError("audit snapshot directory must be outside the technical target")
    with tempfile.TemporaryDirectory(prefix="system-auditor-design-") as temporary:
        snapshot = {}
        for key, raw in input_bytes.items():
            path = Path(temporary) / key
            path.write_bytes(raw)
            snapshot[key] = str(path)
        payload = _payload(original, {"ocean": snapshot, "ocean_producer": producers["open-ocean"]})
        observed = _run_native(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                CHILD,
                str(installer_src),
                str(ocean_cli),
                str(auditor_root / "src"),
            ],
            payload,
            timeout,
        )
        report = observed.get("report")
        if not isinstance(report, dict):
            raise DesignAuditError("native Ocean report missing")
        verification = report.get("verify") or {}
        results = verification.get("results")
        if (
            not isinstance(results, list)
            or not results
            or verification.get("all_ok") is not True
            or verification.get("bundles_checked") != len(results)
            or any(not isinstance(row, dict) or row.get("ok") is not True for row in results)
        ):
            raise DesignAuditError("native composition checks missing or failed")
        policy_sha = {}
        captured_policy = observed.get("policy_evidence")
        captured_bundles = observed.get("bundle_evidence")
        if (
            not isinstance(captured_policy, dict)
            or not captured_policy
            or not isinstance(captured_bundles, dict)
            or not captured_bundles
        ):
            raise DesignAuditError("native captured policy evidence missing")
        for row in results:
            manifest = Path(row["manifest_path"]).resolve(strict=True)
            if not manifest.is_relative_to(recipe):
                raise DesignAuditError("native policy input is outside pinned recipe")
            bundle = captured_bundles.get(str(manifest)) or {}
            if (
                not bundle
                or any(
                    row.get(key) != bundle.get("content_hash")
                    for key in ("pinned_hash", "declared_hash", "computed_hash")
                )
                or hashlib.sha256(_input_bytes(manifest)).hexdigest() != bundle.get("sha256")
            ):
                raise DesignAuditError(
                    "bundle policy bytes differ from executed native verification"
                )
            policy = discover(manifest.parent, max_depth=0)
            if not policy.evidence_capable:
                raise DesignAuditError("native policy discovery found no evidence")
            for source in policy.policy:
                path = Path(source.target).resolve(strict=True)
                if not path.is_relative_to(recipe):
                    raise DesignAuditError("policy source outside pinned recipe")
                actual_sha = hashlib.sha256(_input_bytes(path)).hexdigest()
                if captured_policy.get(str(path)) != actual_sha:
                    raise DesignAuditError("policy bytes differ from captured native input")
                policy_sha[str(path.relative_to(recipe))] = actual_sha
        if {str(recipe / relative) for relative in policy_sha} != set(captured_policy):
            raise DesignAuditError("native policy discovery scope changed")
        scope = report.get("component_scope") or {}
        expected = sorted(components)
        if (
            scope.get("expected") != expected
            or scope.get("observed") != expected
            or scope.get("match") is not True
        ):
            raise DesignAuditError("native component scope differs from design")
        if (
            report.get("schema") != "ellmos.open-ocean-up-report.v1"
            or report.get("apply") is not False
            or (report.get("source_pins") or {}).get("status") != "verified"
        ):
            raise DesignAuditError("verified native no-apply report required")
        if observed.get("design_hash") != design.get("content_hash"):
            raise DesignAuditError("native adapter design binding differs")
        packages = _package_evidence(design, observed, report)

    def assert_original_inputs_unchanged():
        # Repeat after the final package child: every receipt still binds the
        # original six inputs, recipe/discovery scope and technical target.
        if _target_state(target, components) != before:
            raise DesignAuditError("selected technical target metadata changed")
        if _input_bytes(design_path) != original or any(
            _input_bytes(Path(ocean[key])) != raw for key, raw in input_bytes.items()
        ):
            raise DesignAuditError("design or source inputs changed during audit")
        for identity in identities.values():
            _producer(*identity)
        _producer(recipe, recipe_pin["repository"], recipe_pin["commit"])
        current_policy = {}
        for manifest_text, bundle in captured_bundles.items():
            manifest = Path(manifest_text)
            if hashlib.sha256(_input_bytes(manifest)).hexdigest() != bundle["sha256"]:
                raise DesignAuditError("recipe bundle changed before receipt")
            found = discover(manifest.parent, max_depth=0)
            if not found.evidence_capable:
                raise DesignAuditError("native policy discovery scope changed")
            for source in found.policy:
                source_path = Path(source.target).resolve(strict=True)
                if not source_path.is_relative_to(recipe):
                    raise DesignAuditError("policy source outside pinned recipe")
                current_policy[str(source_path.relative_to(recipe))] = hashlib.sha256(
                    _input_bytes(source_path)
                ).hexdigest()
        if current_policy != policy_sha:
            raise DesignAuditError("recipe policy/discovery changed before receipt")

    assert_original_inputs_unchanged()
    if packages is not None:
        # Same isolated pinned helper and same inherited operator profile source;
        # the design contains an identity/hash, never a second target locator.
        fresh = _run_native(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                CHILD,
                str(installer_src),
                str(ocean_cli),
                str(auditor_root / "src"),
            ],
            _payload(
                original, {"operation": "package-check", "ocean_producer": producers["open-ocean"]}
            ),
            timeout,
        )
        if fresh != packages:
            raise DesignAuditError("package profile/artifacts/environment changed before receipt")
        assert_original_inputs_unchanged()
    result = {
        "schema": "ellmos.installer.audit-receipt.v1",
        "source": "system-auditor",
        "scope": "installation-design-mechanical",
        "status": "pass",
        "policy_violations": [],
        "design_hash": design["content_hash"],
        "design_sha256": hashlib.sha256(original).hexdigest(),
        "target": design["target"],
        "input_sha256": input_hashes,
        "policy_sha256": policy_sha,
        "producers": producers,
        "recipe_identity": recipe_identity,
        "native_report": report,
        "native_report_hash": _hash(report),
        "checks": {
            key: "SUCCESS"
            for key in (
                "design-binding",
                "producer-pins",
                "input-pins",
                "native-composition",
                "component-scope",
                "policy-discovery",
                "no-apply",
                "target-unchanged",
            )
        },
        "target_verification": "local selected module placement metadata only; no file contents",
        "input_verification": "native validators consumed immutable captured input snapshots",
        "runtime_verified": False,
        "governance_verified": False,
        "authorization": False,
    }
    if packages is not None:
        result["python_packages"] = packages
    result["content_hash"] = _hash(result)
    return result
