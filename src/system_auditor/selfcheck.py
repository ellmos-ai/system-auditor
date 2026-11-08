"""Phase (a-1): the auditor audits its own tool before it audits the system.

T-20261101-574947335 (user decision 2026-11-01): fixes that were merged did not reach
the running auditor, because its clone was eleven commits behind and nobody pulled it.
An outdated tool produces wrong verdicts. So before (a0) the auditor checks:

* its own clone against the remote (read with ``git ls-remote``, nothing written),
* that the remote is the expected repository (pinned; ``insteadOf`` resolved),
* that the code it runs is a tracked file of that clone (the import path),
* prompt and templates against the cloud mirror, if one is configured,
* that the configured rule sources exist.

The one write it may make is the narrow exception in the role prompt's principle 4: with
``apply=True``, and only when the clone is clean, the only worktree, on its default branch,
pinned to the expected remote, free of locks (clone, main clone, mirror) and strictly behind
the remote (merge-base == HEAD), it runs ``git fetch`` and ``git merge --ff-only`` on its own
clone, with local hooks disabled. Right before the merge it checks locks and tree again and
refuses if the fast-forward would overwrite an untracked or ignored local file. Anything
else -- dirty, ahead, diverged, detached, a lock, a foreign remote, an error or a timeout --
means no pull and ``stale <reason>``. The audit then runs on, marked as such.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Folders whose files the role prompt and the report templates come from.
MIRRORED = ("prompts", "templates")
SHORT_SHA = 12
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
#: Caller environment that would point git at another repository or inject configuration.
_SCRUBBED_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX",
}
_SCP_URL = re.compile(r"^[\w.-]+@([^:/]+):(.+)$")


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


def _git_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _SCRUBBED_ENV and not key.startswith("GIT_CONFIG")
    }
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    return env


def _git(
    cwd: Path, *args: str, timeout: float, config: tuple[str, ...] = ()
) -> tuple[bool, str]:
    """Run git non-interactively, in a scrubbed environment, with optional ``-c`` settings."""
    command = ["git"]
    for setting in config:
        command += ["-c", setting]
    command += ["-C", str(cwd), *args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, result.stdout.strip()


def _one_line(text: str, limit: int = 160) -> str:
    return " ".join(str(text).split())[:limit]


def _remote_key(url: str) -> str:
    """Comparable form of a repository URL: host/owner/name, or a resolved local path."""
    text = str(url or "").strip()
    if not text:
        return ""
    scp = _SCP_URL.match(text)
    if scp:
        host, path = scp.groups()
    else:
        parts = urllib.parse.urlsplit(text)
        if parts.scheme in ("http", "https", "ssh", "git") and parts.hostname:
            host, path = parts.hostname, parts.path
        else:
            local = urllib.parse.unquote(parts.path) if parts.scheme == "file" else text
            try:
                return "file:" + Path(local).resolve().as_posix().casefold()
            except OSError:
                return "file:" + local.replace("\\", "/").casefold()
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return f"{host.casefold()}/{path.casefold()}"


def same_remote(left: str, right: str) -> bool:
    """Do two URLs name the same repository? https/ssh/scp forms, ``.git`` and case aside."""
    key = _remote_key(left)
    return bool(key) and key == _remote_key(right)


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


def clone_root(import_path: str | Path, timeout: float = 30.0) -> Path | None:
    """The git toplevel that contains ``import_path``, or None."""
    ok, top = _git(Path(import_path).resolve().parent, "rev-parse", "--show-toplevel",
                   timeout=timeout)
    return Path(top).resolve() if ok else None


def pinned_remote(import_path: str | Path, timeout: float = 30.0) -> str | None:
    """Expected repository from ``ellmos-module.v2.json`` as committed at HEAD of the clone.

    Read from HEAD, not from the working tree: an uncommitted edit cannot re-pin the tool.
    """
    root = clone_root(import_path, timeout)
    if root is None:
        return None
    ok, text = _git(root, "show", "HEAD:ellmos-module.v2.json", timeout=timeout)
    if not ok:
        return None
    try:
        repository = (json.loads(text).get("source_of_truth") or {}).get("repository")
    except (ValueError, AttributeError):
        return None
    return str(repository) if repository else None


def run_self_check(
    import_path: str | Path,
    *,
    apply: bool = False,
    mirror: str | Path | None = None,
    rule_sources: list[str] | None = None,
    lock_check_command: str | None = None,
    expected_remote: str | None = None,
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

    # --- locks: this worktree, the main clone of a linked worktree, the mirror ---------
    places = [("clone", clone)]
    ok, common = _git(clone, "rev-parse", "--path-format=absolute", "--git-common-dir",
                      timeout=timeout)
    if not ok:
        reasons.append("cannot locate the main clone (git-common-dir)")
    elif Path(common).name.casefold() == ".git":
        main_root = Path(common).resolve().parent
        if main_root != clone:
            places.append(("main", main_root))
    if mirror_dir is not None:
        places.append(("mirror", mirror_dir))
    check_timeout = timeout if lock_timeout is None else lock_timeout

    def collect_locks() -> list[str]:
        found = []
        for label, place in places:
            found += [f"{label}/{name}" for name in _lock_files(place)]
            if lock_check_command:
                free, why = _lock_command_says_free(lock_check_command, place, check_timeout)
                if not free:
                    found.append(f"{why} for {label}")
        return found

    blocked = False
    locks = collect_locks()
    if locks:
        reasons.append("lock present, no pull: " + ", ".join(locks))
        blocked = True
    ok, listing = _git(clone, "worktree", "list", "--porcelain", timeout=timeout)
    worktrees = sum(1 for line in listing.splitlines() if line.startswith("worktree ")) if ok else 0
    if not ok or worktrees > 1:
        reasons.append(f"more than one worktree ({worktrees or 'unknown'}), no pull")
        blocked = True

    # --- state of the clone (read only) ----------------------------------------------
    ok, head = _git(clone, "rev-parse", "HEAD", timeout=timeout)
    if not ok:
        reasons.append(f"cannot read HEAD ({_one_line(head, 80)})")
        return finish()
    result.head_before = head
    ok, porcelain = _git(clone, "status", "--porcelain", timeout=timeout)
    if not ok or porcelain:
        reasons.append("uncommitted changes in the clone")
        blocked = True
    ok, branch = _git(clone, "symbolic-ref", "--short", "-q", "HEAD", timeout=timeout)
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

    # --- the remote must be the expected repository (insteadOf resolved) -------------
    ok, url = _git(clone, "ls-remote", "--get-url", remote, timeout=timeout)
    if not expected_remote:
        reasons.append("remote not pinned (no expected repository configured), no pull")
        blocked = True
    elif not ok or not same_remote(url, expected_remote):
        reasons.append(
            f"remote not pinned: {remote} resolves to {_one_line(url, 80)}, expected "
            f"{_one_line(expected_remote, 80)}; no pull"
        )
        blocked = True

    ok, default = _default_branch(clone, remote, timeout)
    if not ok:
        reasons.append(f"remote {remote} not reachable ({_one_line(default, 80)})")
        return finish()
    if branch != default or remote_branch != default:
        reasons.append(
            f"branch {branch} tracks {upstream}, not the default branch {default} by name"
        )
        blocked = True
    ok, remote_line = _git(
        clone, "ls-remote", "--exit-code", remote, f"refs/heads/{remote_branch}", timeout=timeout
    )
    if not ok or not remote_line.split():
        reasons.append(f"remote {remote} not reachable for {remote_branch}")
        return finish()
    remote_head = remote_line.split()[0]
    result.remote_head = remote_head

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

            def recheck() -> list[str]:
                """Right before the merge: nothing may have changed since the gate."""
                found = []
                late = collect_locks()
                if late:
                    found.append("lock appeared before the fast-forward, no pull: "
                                 + ", ".join(late))
                ok_s, now_porcelain = _git(clone, "status", "--porcelain", timeout=timeout)
                if not ok_s or now_porcelain:
                    found.append("uncommitted changes appeared before the fast-forward")
                ok_h, now_head = _git(clone, "rev-parse", "HEAD", timeout=timeout)
                if not ok_h or now_head != head:
                    found.append("HEAD moved before the fast-forward")
                return found

            _pull(clone, upstream, remote, remote_branch, result, timeout, recheck)

    if mirror_dir is not None:
        result.mirror_diffs = _mirror_diffs(clone, mirror_dir, timeout)
        pulled_now = bool(result.head_after) and result.head_after != result.head_before
        if result.mirror_diffs and not pulled_now:
            reasons.append(f"mirror differs from the clone: {len(result.mirror_diffs)} file(s)")
    return finish()


def _pull(
    clone: Path,
    upstream: str,
    remote: str,
    branch: str,
    result: SelfCheck,
    timeout: float,
    recheck: Callable[[], list[str]],
) -> None:
    """Fetch and fast-forward, only if HEAD is an ancestor of the fetched upstream.

    Local hooks are disabled for both steps (an empty ``core.hooksPath``).
    """
    reasons, head = result.reasons, result.head_before
    with tempfile.TemporaryDirectory(prefix="system-auditor-nohooks-") as no_hooks:
        quiet = (f"core.hooksPath={Path(no_hooks).as_posix()}", "core.fsmonitor=false")
        ok, out = _git(clone, "fetch", "--quiet", remote, branch, timeout=timeout, config=quiet)
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
        # git treats ignored files as expendable: a path upstream starts to track would
        # silently replace the local file. Untracked files already make the tree dirty.
        ok_d, changed = _git(clone, "diff", "--name-only", "-z", head, fetched, timeout=timeout)
        ok_i, ignored = _git(clone, "ls-files", "-z", "--others", "--ignored",
                             "--exclude-standard", timeout=timeout)
        if not (ok_d and ok_i):
            reasons.append("cannot compare incoming paths with local files; no pull")
            return
        clash = {p.casefold() for p in changed.split("\0") if p} & {
            p.casefold() for p in ignored.split("\0") if p
        }
        if clash:
            reasons.append(
                f"fast-forward would overwrite {len(clash)} ignored local file(s); no pull"
            )
            return
        late = recheck()
        if late:
            reasons.extend(late)
            return
        ok, out = _git(clone, "merge", "--ff-only", "--quiet", fetched, timeout=timeout,
                       config=quiet)
    ok_head, after = _git(clone, "rev-parse", "HEAD", timeout=timeout)
    ok_status, porcelain = _git(clone, "status", "--porcelain", timeout=timeout)
    if not (ok and ok_head and after == fetched and ok_status and not porcelain):
        reasons.append(f"fast-forward did not read back cleanly ({_one_line(out, 80)})")
        if ok_head:
            result.head_after = after
        return
    result.head_after = after
