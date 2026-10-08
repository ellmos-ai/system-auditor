"""Bounded local mechanical audit through the existing Installer/Ocean engine."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from .discovery import discover

REQUIRED_INPUTS = (
    "modules_catalog", "skills_registry", "system_manifest", "component_bindings",
    "source_pins", "gui_archive",
)
CHILD = """
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
sys.path.insert(0,str(Path(sys.argv[2]).resolve().parents[1]))
sys.path.insert(0,sys.argv[3])
from ellmos_installer.adapters import OpenOceanAdapter
from ellmos_installer.contracts import validate_design_hash
from ellmos_installer.jsonio import content_hash
from tools.resolve_bundles import canonical_hash,load_system_manifest,verify_bundle
from system_auditor.discovery import discover
payload=json.loads(sys.stdin.buffer.read())
design=payload['design']
validate_design_hash(design)
execution=dict(design)
execution['ocean']=payload['ocean']
execution.pop('content_hash')
execution['content_hash']=content_hash(execution)
recipe=Path(execution['ocean']['bundles_root'])
policy_bytes={}
bundles={}
for reference in load_system_manifest(Path(execution['ocean']['system_manifest']))['bundle_refs']:
    checked,_=verify_bundle(reference,recipe)
    if not checked.ok: raise ValueError('native bundle preflight failed')
    path=Path(checked.manifest_path).resolve(strict=True)
    raw=path.read_bytes()
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
        policy_bytes[str(policy_path)]=raw if policy_path==path else policy_path.read_bytes()
report=OpenOceanAdapter(Path(sys.argv[2])).plan_design(execution)
for row in report['verify']['results']:
    evidence=bundles[str(Path(row['manifest_path']).resolve(strict=True))]
    if any(row.get(key)!=evidence['content_hash']
           for key in ('pinned_hash','declared_hash','computed_hash')):
        raise ValueError('reported bundle differs from captured policy')
for path,raw in policy_bytes.items():
    if Path(path).read_bytes()!=raw: raise ValueError('native policy changed during plan')
print(json.dumps({'design_hash':design['content_hash'],'report':report,'bundle_evidence':bundles,
                 'policy_evidence':{path:hashlib.sha256(raw).hexdigest()
                                    for path,raw in policy_bytes.items()}},sort_keys=True))
"""


class DesignAuditError(ValueError):
    """No mechanical PASS can be issued for these inputs."""


def _hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", check=False, timeout=20,
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


def _run_native(command: list[str], payload: bytes, timeout: float) -> dict:
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} \
        if os.name == "nt" else {"start_new_session": True}
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, **options) as process:
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                        capture_output=True, check=False, timeout=20)
                if killed.returncode and process.poll() is None:
                    raise DesignAuditError("cannot confirm terminated audit process tree") from exc
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=20)
            raise DesignAuditError("native audit timed out; no unchanged/PASS claim") from exc
        if process.returncode:
            raise DesignAuditError(
                "native no-apply plan failed: " + stderr.decode("utf-8", "replace")
            )
    try:
        value = json.loads(stdout)
    except (ValueError, UnicodeError) as exc:
        raise DesignAuditError("native adapter returned no valid report") from exc
    if not isinstance(value, dict):
        raise DesignAuditError("native adapter report must be an object")
    return value


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
    design_path: Path, *, installer_src: Path, installer_commit: str,
    ocean_cli: Path, ocean_commit: str, producer_commit: str, timeout: float = 60,
) -> dict:
    """Return evidence for actual mechanical checks; errors never produce PASS."""
    if timeout <= 0 or timeout > 300:
        raise DesignAuditError("audit timeout must be between 0 and 300 seconds")
    original = design_path.read_bytes()
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
        "system-auditor": (auditor_root, "https://github.com/ellmos-ai/system-auditor",
                           producer_commit),
        "ellmos-installer": (installer_src.parent, "https://github.com/ellmos-ai/ellmos-installer",
                             installer_commit),
        "open-ocean": (ocean_cli.parent.parent, "https://github.com/ellmos-ai/open-ocean",
                       ocean_commit),
    }
    if installer_src.name != "src" or ocean_cli.name != "ocean_dev.py" \
            or ocean_cli.parent.name != "tools":
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
    input_bytes = {key: Path(ocean[key]).read_bytes() for key in REQUIRED_INPUTS}
    input_hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in input_bytes.items()}
    recipe = Path(ocean["bundles_root"]).resolve(strict=True)
    recipe_pin = json.loads(input_bytes["source_pins"])["recipe"]
    if recipe_pin["repository"].removesuffix(".git") != \
            "https://github.com/ellmos-ai/ellmos-development-system":
        raise DesignAuditError("canonical native recipe repository required")
    recipe_identity = _producer(recipe, recipe_pin["repository"], recipe_pin["commit"])
    if Path(tempfile.gettempdir()).resolve().is_relative_to(target.resolve(strict=False)):
        raise DesignAuditError("audit snapshot directory must be outside the technical target")
    with tempfile.TemporaryDirectory(prefix="system-auditor-design-") as temporary:
        snapshot = deepcopy(ocean)
        for key, raw in input_bytes.items():
            path = Path(temporary) / key
            path.write_bytes(raw)
            snapshot[key] = str(path)
        payload = json.dumps({"design": design, "ocean": snapshot}, ensure_ascii=False).encode()
        observed = _run_native(
            [sys.executable, "-I", "-B", "-c", CHILD, str(installer_src), str(ocean_cli),
             str(auditor_root / "src")],
            payload, timeout,
        )
        report = observed.get("report")
        if not isinstance(report, dict):
            raise DesignAuditError("native Ocean report missing")
        verification = report.get("verify") or {}
        results = verification.get("results")
        if not isinstance(results, list) or not results or verification.get("all_ok") is not True \
                or verification.get("bundles_checked") != len(results) \
                or any(not isinstance(row, dict) or row.get("ok") is not True for row in results):
            raise DesignAuditError("native composition checks missing or failed")
        policy_sha = {}
        captured_policy = observed.get("policy_evidence")
        captured_bundles = observed.get("bundle_evidence")
        if not isinstance(captured_policy, dict) or not captured_policy \
                or not isinstance(captured_bundles, dict) or not captured_bundles:
            raise DesignAuditError("native captured policy evidence missing")
        for row in results:
            manifest = Path(row["manifest_path"]).resolve(strict=True)
            if not manifest.is_relative_to(recipe):
                raise DesignAuditError("native policy input is outside pinned recipe")
            bundle = captured_bundles.get(str(manifest)) or {}
            if not bundle or any(row.get(key) != bundle.get("content_hash")
                                 for key in ("pinned_hash", "declared_hash", "computed_hash")) \
                    or hashlib.sha256(manifest.read_bytes()).hexdigest() != bundle.get("sha256"):
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
                actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                if captured_policy.get(str(path)) != actual_sha:
                    raise DesignAuditError("policy bytes differ from captured native input")
                policy_sha[str(path.relative_to(recipe))] = actual_sha
        if {str(recipe / relative) for relative in policy_sha} != set(captured_policy):
            raise DesignAuditError("native policy discovery scope changed")
        scope = report.get("component_scope") or {}
        expected = sorted(components)
        if scope.get("expected") != expected or scope.get("observed") != expected \
                or scope.get("match") is not True:
            raise DesignAuditError("native component scope differs from design")
        if report.get("schema") != "ellmos.open-ocean-up-report.v1" \
                or report.get("apply") is not False \
                or (report.get("source_pins") or {}).get("status") != "verified":
            raise DesignAuditError("verified native no-apply report required")
        if observed.get("design_hash") != design.get("content_hash"):
            raise DesignAuditError("native adapter design binding differs")
    if _target_state(target, components) != before:
        raise DesignAuditError("selected technical target metadata changed")
    if design_path.read_bytes() != original or any(
        Path(ocean[key]).read_bytes() != raw for key, raw in input_bytes.items()
    ):
        raise DesignAuditError("design or source inputs changed during audit")
    for identity in identities.values():
        _producer(*identity)
    _producer(recipe, recipe_pin["repository"], recipe_pin["commit"])
    for relative, expected_sha in policy_sha.items():
        if hashlib.sha256((recipe / relative).read_bytes()).hexdigest() != expected_sha:
            raise DesignAuditError("recipe policy changed before receipt")
    result = {
        "schema": "ellmos.installer.audit-receipt.v1", "source": "system-auditor",
        "scope": "installation-design-mechanical", "status": "pass", "policy_violations": [],
        "design_hash": design["content_hash"],
        "design_sha256": hashlib.sha256(original).hexdigest(),
        "target": design["target"], "input_sha256": input_hashes,
        "policy_sha256": policy_sha, "producers": producers, "recipe_identity": recipe_identity,
        "native_report": report, "native_report_hash": _hash(report),
        "checks": {key: "SUCCESS" for key in (
            "design-binding", "producer-pins", "input-pins", "native-composition",
            "component-scope", "policy-discovery", "no-apply", "target-unchanged",
        )},
        "target_verification": "local selected module placement metadata only; no file contents",
        "input_verification": "native validators consumed immutable captured input snapshots",
        "runtime_verified": False, "governance_verified": False, "authorization": False,
    }
    result["content_hash"] = _hash(result)
    return result
