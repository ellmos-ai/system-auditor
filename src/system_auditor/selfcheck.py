"""Phase (a-1): the auditor audits its own tool before it audits the system.

T-20261101-574947335 (user decision 2026-11-01): fixes that were merged did not reach
the running auditor, because its clone was eleven commits behind and nobody pulled it.
An outdated tool produces wrong verdicts. So before (a0) the auditor checks:

* its own clone against the remote (read with ``git ls-remote``, nothing written),
* that the code it runs is a tracked file of that clone (the import path),
* prompt and templates against the cloud mirror, if one is configured,
* that the configured rule sources exist.

The one write it may make is the narrow exception in the role prompt's principle 4: with
``apply=True``, and only when the clone is clean, on its default branch, free of locks
and strictly behind the remote (merge-base == HEAD), it runs ``git fetch`` and
``git merge --ff-only`` on its own clone and reads the result back. Anything else -- dirty,
ahead, diverged, detached, a lock, an unreachable remote, an error or a timeout -- means
no pull and ``stale <reason>``. The audit then runs on, marked as such.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Folders whose files the role prompt and the report templates come from.
MIRRORED = ("prompts", "templates")
SHORT_SHA = 12
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class SelfCheck:
    status: str  # current | pulled | stale
    value: str  # the header value: current / pulled <old>..<new> / stale <reason>
    import_path: str
    clone: str = ""
    branch: str = ""
    upstream: str = ""
    head_before: str = ""
    head_after: str = ""
    remote_head: str = ""
    would_pull: bool = False
    reasons: list[str] = field(default_factory=list)
    mirror_diffs: list[str] = field(default_factory=list)
    missing_rule_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _git(cwd: Path, *args: str, timeout: float) -> tuple[bool, str]:
    """Run git non-interactively: a credential prompt fails the call instead of hanging."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, result.stdout.strip()


def _one_line(text: str, limit: int = 160) -> str:
    return " ".join(str(text).split())[:limit]


def _lock_files(directory: Path) -> list[str]:
    """``LOCK.txt`` / ``LOCK.*.txt`` in a directory, any case; unreadable counts as locked."""
    try:
        return sorted(
            entry.name
            for entry in directory.iterdir()
            if entry.is_file()
            and entry.name.casefold().startswith("lock.")
            and entry.name.casefold().endswith(".txt")
        )
    except OSError as exc:
        return [f"<unreadable: {exc.__class__.__name__}>"]


def _quote(path: Path) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([str(path)])
    import shlex

    return shlex.quote(str(path))


def _lock_command_says_free(command: str, path: Path, timeout: float) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command.replace("{path}", _quote(path)),
            shell=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"lock check failed ({exc.__class__.__name__})"
    if result.returncode != 0:
        return False, f"lock check reported exit {result.returncode}"
    return True, ""


def _normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _mirror_diffs(clone: Path, mirror: Path, timeout: float) -> list[str]:
    ok, listing = _git(clone, "ls-files", "-z", "--", *MIRRORED, timeout=timeout)
    if not ok:
        return ["<git ls-files failed>"]
    diffs = []
    for rel in sorted(name for name in listing.split("\0") if name):
        try:
            mine = _normalized((clone / rel).read_bytes())
        except OSError:
            continue
        try:
            theirs = _normalized((mirror / rel).read_bytes())
        except OSError:
            diffs.append(rel)
            continue
        if mine != theirs:
            diffs.append(rel)
    return diffs


def _default_branch(clone: Path, remote: str, timeout: float) -> tuple[bool, str]:
    ok, out = _git(clone, "ls-remote", "--symref", remote, "HEAD", timeout=timeout)
    if not ok:
        return False, out
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/") and line.rstrip().endswith("HEAD"):
            return True, line[len("ref: refs/heads/"):].split()[0]
    return False, "remote does not name a default branch"


def run_self_check(
    import_path: str | Path,
    *,
    apply: bool = False,
    mirror: str | Path | None = None,
    rule_sources: list[str] | None = None,
    lock_check_command: str | None = None,
    timeout: float = 30.0,
    lock_timeout: float | None = None,
) -> SelfCheck:
    """Audit the auditor's own tool. Writes to git only with ``apply`` and only a fast-forward."""
    import_path = Path(import_path).resolve()
    result = SelfCheck(status="stale", value="", import_path=str(import_path))
    reasons = result.reasons

    def finish() -> SelfCheck:
        pulled = bool(result.head_after) and result.head_after != result.head_before
        if reasons:
            result.status = "stale"
            result.value = "stale " + "; ".join(_one_line(r) for r in reasons)
            if pulled:
                result.value += f" (pulled {result.head_before[:SHORT_SHA]}"
                result.value += f"..{result.head_after[:SHORT_SHA]})"
        elif pulled:
            result.status = "pulled"
            short = (result.head_before[:SHORT_SHA], result.head_after[:SHORT_SHA])
            result.value = "pulled {}..{}".format(*short)
        else:
            result.status, result.value = "current", "current"
        return result

    # --- configuration, independent of git ---------------------------------------
    missing = [src for src in rule_sources or [] if src and not Path(src).exists()]
    result.missing_rule_sources = missing
    if missing:
        reasons.append(f"{len(missing)} configured rule source(s) missing")
    mirror_dir = Path(mirror) if mirror else None
    if mirror_dir is not None and not mirror_dir.is_dir():
        reasons.append(f"mirror not found ({mirror_dir})")
        mirror_dir = None

    # --- which clone, and is the running code part of it -----------------------------
    ok, top = _git(import_path.parent, "rev-parse", "--show-toplevel", timeout=timeout)
    if not ok:
        reasons.append(f"import path is not inside a git clone ({import_path})")
        return finish()
    clone = Path(top).resolve()
    result.clone = str(clone)
    try:
        relative = import_path.relative_to(clone).as_posix()
    except ValueError:
        relative = ""
    tracked, _ = (
        _git(clone, "ls-files", "--error-unmatch", "--", relative, timeout=timeout)
        if relative
        else (False, "")
    )
    if not tracked:
        reasons.append("import path is not a tracked file of the clone (installed copy?)")

    # --- state of the clone (read only) ----------------------------------------------
    ok, head = _git(clone, "rev-parse", "HEAD", timeout=timeout)
    if not ok:
        reasons.append(f"cannot read HEAD ({_one_line(head, 80)})")
        return finish()
    result.head_before = head
    ok, porcelain = _git(clone, "status", "--porcelain", timeout=timeout)
    if not ok or porcelain:
        reasons.append("uncommitted changes in the clone")
    ok, branch = _git(clone, "symbolic-ref", "--short", "-q", "HEAD", timeout=timeout)
    blocked = bool(reasons)
    if not ok:
        reasons.append("detached HEAD")
        return finish()
    result.branch = branch
    ok, upstream = _git(
        clone, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", timeout=timeout
    )
    if not ok or "/" not in upstream:
        reasons.append(f"no upstream for branch {branch}")
        return finish()
    result.upstream = upstream
    remote, remote_branch = upstream.split("/", 1)
    ok, default = _default_branch(clone, remote, timeout)
    if not ok:
        reasons.append(f"remote {remote} not reachable ({_one_line(default, 80)})")
        return finish()
    if remote_branch != default:
        reasons.append(f"branch {branch} tracks {upstream}, not the default branch {default}")
        blocked = True
    ok, remote_line = _git(
        clone, "ls-remote", "--exit-code", remote, f"refs/heads/{remote_branch}", timeout=timeout
    )
    if not ok or not remote_line.split():
        reasons.append(f"remote {remote} not reachable for {remote_branch}")
        return finish()
    remote_head = remote_line.split()[0]
    result.remote_head = remote_head

    # --- locks: clone and mirror (two trees), and the configured check ---------------
    locks = [f"clone/{name}" for name in _lock_files(clone)]
    if mirror_dir is not None:
        locks += [f"mirror/{name}" for name in _lock_files(mirror_dir)]
    if lock_check_command:
        for place in [clone] + ([mirror_dir] if mirror_dir is not None else []):
            free, why = _lock_command_says_free(
                lock_check_command, place, timeout if lock_timeout is None else lock_timeout
            )
            if not free:
                locks.append(f"{why} for {place.name}")
    if locks:
        reasons.append("lock present, no pull: " + ", ".join(locks))
        blocked = True

    # --- relation to the remote --------------------------------------------------------
    if remote_head != head:
        known, _ = _git(clone, "cat-file", "-e", f"{remote_head}^{{commit}}", timeout=timeout)
        ahead = known and _git(
            clone, "merge-base", "--is-ancestor", remote_head, head, timeout=timeout
        )[0]
        if ahead:
            reasons.append(f"clone is ahead of {upstream} (unpushed commits)")
        elif not apply:
            result.would_pull = not blocked
            reasons.append(
                f"clone differs from {upstream} (HEAD {head[:SHORT_SHA]}, remote "
                f"{remote_head[:SHORT_SHA]}); "
                + ("run self-check --apply" if not blocked else "no pull")
            )
        elif blocked:
            reasons.append(f"clone differs from {upstream}; no pull")
        else:
            _pull(clone, upstream, remote, remote_branch, result, timeout)

    if mirror_dir is not None:
        result.mirror_diffs = _mirror_diffs(clone, mirror_dir, timeout)
        pulled_now = bool(result.head_after) and result.head_after != result.head_before
        if result.mirror_diffs and not pulled_now:
            reasons.append(f"mirror differs from the clone: {len(result.mirror_diffs)} file(s)")
    return finish()


def _pull(
    clone: Path, upstream: str, remote: str, branch: str, result: SelfCheck, timeout: float
) -> None:
    """Fetch and fast-forward, only if HEAD is an ancestor of the fetched upstream."""
    reasons, head = result.reasons, result.head_before
    ok, out = _git(clone, "fetch", "--quiet", remote, branch, timeout=timeout)
    if not ok:
        reasons.append(f"fetch failed ({_one_line(out, 80)})")
        return
    ok, fetched = _git(clone, "rev-parse", "@{u}", timeout=timeout)
    if not ok:
        reasons.append("upstream unreadable after fetch")
        return
    if fetched == head:
        return
    ok, base = _git(clone, "merge-base", head, fetched, timeout=timeout)
    if not ok or base != head:
        kind = "ahead of" if ok and base == fetched else "diverged from"
        reasons.append(f"clone {kind} {upstream}; no pull")
        return
    ok, out = _git(clone, "merge", "--ff-only", "--quiet", "@{u}", timeout=timeout)
    ok_head, after = _git(clone, "rev-parse", "HEAD", timeout=timeout)
    ok_status, porcelain = _git(clone, "status", "--porcelain", timeout=timeout)
    if not (ok and ok_head and after == fetched and ok_status and not porcelain):
        reasons.append(f"fast-forward did not read back cleanly ({_one_line(out, 80)})")
        if ok_head:
            result.head_after = after
        return
    result.head_after = after
