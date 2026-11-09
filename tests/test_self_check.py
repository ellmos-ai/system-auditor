"""Phase (a-1) self audit and the report field ``self_check`` (T-20261101-574947335).

Real git repositories (a bare origin, the auditor's clone, a second publisher clone) in a
temp dir: the pull gate is exercised against actual git state. Every refusal is checked
with HEAD unchanged as the negative control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from system_auditor import selfcheck
from system_auditor.compare import AuditRun, check_comparability
from system_auditor.config import load as load_config
from system_auditor.report import (
    ReportHeader,
    inspect_report,
    parse_self_check,
)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit(repo: Path, name: str, text: str, message: str) -> str:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "--initial-branch=master", str(origin)], check=True
    )
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(origin), str(seed))
    for repo in (seed,):
        git(repo, "config", "user.email", "t@example.invalid")
        git(repo, "config", "user.name", "T")
        git(repo, "config", "core.autocrlf", "false")
    commit(seed, "src/system_auditor/__init__.py", "x = 1\n", "init")
    commit(seed, "prompts/AUDITOR.de.md", "prompt v1\n", "prompt")
    manifest = {"source_of_truth": {"repository": origin.as_posix()}}
    commit(seed, "ellmos-module.v2.json", json.dumps(manifest) + "\n", "manifest")
    git(seed, "push", "-q", "origin", "HEAD:master")
    clone = tmp_path / "clone"
    # autocrlf at clone time: set afterwards, a CRLF checkout would read as modified
    git(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(clone))
    for repo in (clone,):
        git(repo, "config", "user.email", "t@example.invalid")
        git(repo, "config", "user.name", "T")
        git(repo, "config", "core.autocrlf", "false")
    return origin, seed, clone


def advance_remote(seed: Path, text: str = "prompt v2\n") -> str:
    head = commit(seed, "prompts/AUDITOR.de.md", text, "advance")
    git(seed, "push", "-q", "origin", "HEAD:master")
    return head


def run(clone: Path, **kwargs) -> selfcheck.SelfCheck:
    kwargs.setdefault("expected_remote", str(clone.parent / "origin.git"))
    return selfcheck.run_self_check(clone / "src" / "system_auditor" / "__init__.py", **kwargs)


# --- the two good outcomes ------------------------------------------------------------------


def test_current_clone_is_current(repos):
    _, _, clone = repos
    result = run(clone)
    assert result.value == "current" and result.status == "current"


def test_behind_and_clean_is_pulled_only_with_apply(repos):
    _, seed, clone = repos
    old = git(clone, "rev-parse", "HEAD")
    new = advance_remote(seed)
    dry = run(clone)
    assert dry.status == "stale" and dry.would_pull
    assert git(clone, "rev-parse", "HEAD") == old  # dry run: no pull
    assert git(clone, "rev-parse", "origin/master") == old  # and no fetch either
    applied = run(clone, apply=True)
    assert applied.status == "pulled"
    assert applied.value == f"pulled {old[:12]}..{new[:12]}"
    assert git(clone, "rev-parse", "HEAD") == new  # readback
    assert not git(clone, "status", "--porcelain")


# --- every refusal leaves HEAD where it was ---------------------------------------------------


def assert_refused(clone: Path, result: selfcheck.SelfCheck, head: str, reason: str) -> None:
    assert result.status == "stale", result
    assert reason in result.value, result.value
    assert git(clone, "rev-parse", "HEAD") == head


def test_dirty_clone_is_not_pulled(repos):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    (clone / "prompts" / "AUDITOR.de.md").write_text("local edit\n", encoding="utf-8")
    assert_refused(clone, run(clone, apply=True), head, "uncommitted")


def test_untracked_file_counts_as_dirty(repos):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    (clone / "notes.txt").write_text("unsaved work\n", encoding="utf-8")
    assert_refused(clone, run(clone, apply=True), head, "uncommitted")


def test_ahead_clone_is_not_pulled(repos):
    _, _, clone = repos
    head = commit(clone, "local.txt", "x\n", "local only")
    assert_refused(clone, run(clone, apply=True), head, "ahead")


def test_diverged_clone_is_not_pulled(repos):
    _, seed, clone = repos
    advance_remote(seed)
    head = commit(clone, "local.txt", "x\n", "local only")
    assert_refused(clone, run(clone, apply=True), head, "diverged")


def test_detached_head_is_not_pulled(repos):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    git(clone, "checkout", "-q", "--detach")
    advance_remote(seed)
    assert_refused(clone, run(clone, apply=True), head, "detached")


def test_branch_without_upstream_is_not_pulled(repos):
    _, seed, clone = repos
    git(clone, "checkout", "-q", "-b", "local-only")
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    assert_refused(clone, run(clone, apply=True), head, "upstream")


def test_other_branch_than_the_default_is_not_pulled(repos):
    _, seed, clone = repos
    git(seed, "push", "-q", "origin", "HEAD:feature")
    git(clone, "fetch", "-q", "origin")
    git(clone, "checkout", "-q", "-b", "feature", "--track", "origin/feature")
    head = git(clone, "rev-parse", "HEAD")
    commit(seed, "f.txt", "f\n", "feature work")
    git(seed, "push", "-q", "origin", "HEAD:feature")
    assert_refused(clone, run(clone, apply=True), head, "default branch")


@pytest.mark.parametrize("name", ["LOCK.txt", "LOCK.self-check.txt", "lock.user.TXT"])
def test_lock_in_the_clone_blocks_the_pull(repos, name):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    (clone / name).write_text("owner: someone\n", encoding="utf-8")
    assert_refused(clone, run(clone, apply=True), head, "lock")


def test_lock_in_the_mirror_blocks_the_pull(repos, tmp_path):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    mirror = tmp_path / "mirror"
    (mirror / "prompts").mkdir(parents=True)
    (mirror / "prompts" / "AUDITOR.de.md").write_text("prompt v1\n", encoding="utf-8")
    (mirror / "LOCK.docs.txt").write_text("owner: someone\n", encoding="utf-8")
    assert_refused(clone, run(clone, apply=True, mirror=mirror), head, "lock")


@pytest.mark.parametrize(
    "command, reason",
    [
        (f'"{sys.executable}" -c "import sys; sys.exit(1)" {{path}}', "lock"),
        ("definitely-not-a-program-7f3a {path}", "lock"),
        (f'"{sys.executable}" -c "import time; time.sleep(3)" {{path}}', "lock"),
    ],
)
def test_lock_check_command_that_does_not_say_free_blocks_the_pull(repos, command, reason):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    result = run(clone, apply=True, lock_check_command=command, lock_timeout=1.0)
    assert_refused(clone, result, head, reason)


def test_lock_check_command_exit_zero_allows_the_pull(repos):
    _, seed, clone = repos
    new = advance_remote(seed)
    command = f'"{sys.executable}" -c "import sys; sys.exit(0)" {{path}}'
    assert run(clone, apply=True, lock_check_command=command).status == "pulled"
    assert git(clone, "rev-parse", "HEAD") == new


def test_import_path_outside_a_clone_is_stale(tmp_path, monkeypatch):
    # tmp_path lies below the repository's .pytest_temp; without a ceiling git would find
    # the repository itself above it.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    loose = tmp_path / "site-packages" / "system_auditor" / "__init__.py"
    loose.parent.mkdir(parents=True)
    loose.write_text("x = 1\n", encoding="utf-8")
    result = selfcheck.run_self_check(loose, apply=True)
    assert result.status == "stale" and "not inside a git clone" in result.value


def test_unreachable_remote_is_stale_and_not_pulled(repos):
    _, _, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    git(clone, "remote", "set-url", "origin", str(clone.parent / "gone.git"))
    assert_refused(clone, run(clone, apply=True), head, "remote")


# --- r1 review of b31add7: four gaps in the pull gate, and the hints ---------------------------


def test_lock_appearing_during_fetch_stops_the_merge(repos, monkeypatch):
    """TOCTOU: locks and the tree are checked again right before the fast-forward."""
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    real = selfcheck._git

    def fetch_then_lock(cwd, *args, **kwargs):
        result = real(cwd, *args, **kwargs)
        if "fetch" in args:
            (clone / "LOCK.txt").write_text("owner: late arrival\n", encoding="utf-8")
        return result

    monkeypatch.setattr(selfcheck, "_git", fetch_then_lock)
    assert_refused(clone, run(clone, apply=True), head, "lock")


def test_tree_changing_during_fetch_stops_the_merge(repos, monkeypatch):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    real = selfcheck._git

    def fetch_then_edit(cwd, *args, **kwargs):
        result = real(cwd, *args, **kwargs)
        if "fetch" in args:
            (clone / "src" / "system_auditor" / "__init__.py").write_text(
                "x = 2\n", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(selfcheck, "_git", fetch_then_edit)
    assert_refused(clone, run(clone, apply=True), head, "uncommitted")


def make_fork(tmp_path: Path, origin: Path) -> Path:
    fork = tmp_path / "fork.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(origin), str(fork)], check=True)
    work = tmp_path / "fork-work"
    git(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(fork), str(work))
    git(work, "config", "user.email", "t@example.invalid")
    git(work, "config", "user.name", "T")
    commit(work, "src/system_auditor/evil.py", "print('unreviewed')\n", "fork only")
    git(work, "push", "-q", "origin", "HEAD:master")
    return fork


def test_origin_pointing_at_a_fork_is_not_pulled(repos, tmp_path):
    origin, _, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    git(clone, "remote", "set-url", "origin", str(make_fork(tmp_path, origin)))
    assert_refused(clone, run(clone, apply=True), head, "not pinned")


def test_insteadof_redirect_to_a_fork_is_not_pulled(repos, tmp_path):
    origin, _, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    fork = make_fork(tmp_path, origin)
    git(clone, "config", f"url.{fork.as_posix()}.insteadOf", origin.as_posix())
    git(clone, "remote", "set-url", "origin", origin.as_posix())
    assert_refused(clone, run(clone, apply=True), head, "not pinned")


def test_without_an_expected_remote_nothing_is_pulled(repos):
    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    assert_refused(clone, run(clone, apply=True, expected_remote=None), head, "not pinned")


@pytest.mark.parametrize(
    "left, right",
    [
        (
            "https://github.com/ellmos-ai/system-auditor",
            "git@github.com:ellmos-ai/system-auditor.git",
        ),
        ("https://github.com/Ellmos-AI/System-Auditor.git", "ssh://git@github.com/ellmos-ai/system-auditor"),
        ("https://github.com/ellmos-ai/system-auditor/", "https://GitHub.com/ellmos-ai/system-auditor"),
    ],
)
def test_remote_comparison_ignores_scheme_suffix_and_case(left, right):
    assert selfcheck.same_remote(left, right)


@pytest.mark.parametrize(
    "left, right",
    [
        ("https://github.com/ellmos-ai/system-auditor", "https://github.com/someone/system-auditor"),
        ("https://github.com/ellmos-ai/system-auditor", "https://github.com/ellmos-ai/system-auditor-x"),
        ("https://github.com/ellmos-ai/system-auditor", "https://gitlab.com/ellmos-ai/system-auditor"),
        ("https://github.com/ellmos-ai/system-auditor", ""),
    ],
)
def test_remote_comparison_keeps_other_repositories_apart(left, right):
    assert not selfcheck.same_remote(left, right)


def test_linked_worktree_sees_the_main_clones_lock(repos, tmp_path):
    _, seed, clone = repos
    linked = tmp_path / "linked"
    git(clone, "worktree", "add", "-q", "--detach", str(linked))
    head = git(linked, "rev-parse", "HEAD")
    advance_remote(seed)
    (clone / "LOCK.txt").write_text("owner: main clone\n", encoding="utf-8")
    result = run(linked, apply=True)
    assert_refused(linked, result, head, "lock")
    assert "main/LOCK.txt" in result.value


def test_more_than_one_worktree_blocks_the_pull(repos, tmp_path):
    _, seed, clone = repos
    git(clone, "worktree", "add", "-q", "--detach", str(tmp_path / "second"))
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    assert_refused(clone, run(clone, apply=True), head, "worktree")


def test_ignored_local_file_is_not_overwritten_by_the_fast_forward(repos):
    _, seed, clone = repos
    commit(seed, ".gitignore", "local.cfg\n", "ignore local.cfg")
    git(seed, "push", "-q", "origin", "HEAD:master")
    git(clone, "pull", "-q", "--ff-only")  # test setup only: the clone knows the ignore rule
    (clone / "local.cfg").write_text("LOCAL SECRET\n", encoding="utf-8")
    (seed / "local.cfg").write_text("UPSTREAM\n", encoding="utf-8")
    git(seed, "add", "-f", "local.cfg")
    git(seed, "commit", "-q", "-m", "upstream starts tracking local.cfg")
    git(seed, "push", "-q", "origin", "HEAD:master")
    head = git(clone, "rev-parse", "HEAD")
    assert_refused(clone, run(clone, apply=True), head, "ignored")
    assert (clone / "local.cfg").read_text(encoding="utf-8") == "LOCAL SECRET\n"


def test_local_hooks_do_not_run_during_the_pull(repos):
    _, seed, clone = repos
    new = advance_remote(seed)
    marker = clone.parent / "hook-ran"
    hook = clone / ".git" / "hooks" / "post-merge"
    hook.write_text(
        f"#!/bin/sh\necho ran > '{marker.as_posix()}'\n", encoding="utf-8", newline="\n"
    )
    hook.chmod(0o755)
    assert run(clone, apply=True).status == "pulled"
    assert git(clone, "rev-parse", "HEAD") == new
    assert not marker.exists()


def test_git_commands_with_nohooks_also_disable_fsmonitor(repos, monkeypatch):
    _, seed, clone = repos
    advance_remote(seed)
    seen_commands = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        if cmd and cmd[0] == "git":
            seen_commands.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(selfcheck.subprocess, "run", spy)
    assert run(clone, apply=True).status == "pulled"

    hook_cmds = [
        cmd for cmd in seen_commands
        if any("core.hooksPath=" in str(arg) for arg in cmd)
    ]
    assert len(hook_cmds) >= 2  # fetch and merge
    for cmd in hook_cmds:
        # Check that -c core.fsmonitor=false is present in command arguments
        assert "-c" in cmd
        assert "core.fsmonitor=false" in cmd



def test_git_environment_from_the_caller_is_ignored(repos, tmp_path, monkeypatch):
    _, seed, clone = repos
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", str(other))
    new = advance_remote(seed)  # before the caller's GIT_* is set: it would steer git() too
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(tmp_path))
    result = run(clone, apply=True)
    assert result.status == "pulled", result.value
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    assert subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True,
        env=clean_env,
    ).stdout.strip() == new
    assert not (other / ".git" / "refs" / "heads" / "master").exists()


def test_branch_with_another_name_tracking_the_default_is_not_pulled(repos):
    _, seed, clone = repos
    git(clone, "checkout", "-q", "-b", "mine", "--track", "origin/master")
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    assert_refused(clone, run(clone, apply=True), head, "default branch")


def test_cli_apply_refuses_a_clone_other_than_its_own(repos, tmp_path, capsys):
    from system_auditor.cli import main

    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    code = main(["--config", str(tmp_path / "none.json"), "self-check", "--clone", str(clone),
                 "--apply"])
    assert code == 2 and "own clone" in capsys.readouterr().err
    assert git(clone, "rev-parse", "HEAD") == head


def test_cli_reads_the_pin_from_the_manifest_at_head(repos, tmp_path, capsys):
    from system_auditor.cli import main

    _, _, clone = repos
    assert main(["--json", "--config", str(tmp_path / "none.json"), "self-check",
                 "--clone", str(clone)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "current"


# --- mirror and rule sources ------------------------------------------------------------------


def make_mirror(tmp_path: Path, text: str) -> Path:
    mirror = tmp_path / "mirror"
    (mirror / "prompts").mkdir(parents=True, exist_ok=True)
    (mirror / "prompts" / "AUDITOR.de.md").write_bytes(text.encode("utf-8"))
    return mirror


def test_mirror_differing_only_in_line_endings_is_in_step(repos, tmp_path):
    _, _, clone = repos
    result = run(clone, mirror=make_mirror(tmp_path, "prompt v1\r\n"))
    assert result.value == "current" and result.mirror_diffs == []


def test_mirror_behind_without_pull_is_stale(repos, tmp_path):
    _, _, clone = repos
    result = run(clone, mirror=make_mirror(tmp_path, "prompt v0\n"))
    assert result.status == "stale" and "mirror" in result.value
    assert result.mirror_diffs == ["prompts/AUDITOR.de.md"]


def test_mirror_lag_right_after_a_pull_is_listed_not_stale(repos, tmp_path):
    _, seed, clone = repos
    advance_remote(seed)
    result = run(clone, apply=True, mirror=make_mirror(tmp_path, "prompt v1\n"))
    assert result.status == "pulled" and result.mirror_diffs == ["prompts/AUDITOR.de.md"]


def test_missing_rule_source_is_stale(repos, tmp_path):
    _, _, clone = repos
    present = tmp_path / "policies"
    present.mkdir()
    result = run(clone, rule_sources=[str(present), str(tmp_path / "gone")])
    assert result.status == "stale" and "rule source" in result.value
    assert result.missing_rule_sources == [str(tmp_path / "gone")]


def test_git_runs_without_any_prompt(monkeypatch, repos):
    _, _, clone = repos
    seen = []
    real = subprocess.run

    def spy(cmd, *args, **kwargs):
        if cmd and cmd[0] == "git":
            seen.append((kwargs.get("env") or {}, kwargs.get("stdin"), kwargs.get("timeout")))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(selfcheck.subprocess, "run", spy)
    run(clone)
    assert seen and all(
        env.get("GIT_TERMINAL_PROMPT") == "0" and env.get("GCM_INTERACTIVE") == "never"
        and stdin == subprocess.DEVNULL and timeout
        for env, stdin, timeout in seen
    )


def test_cli_self_check_is_a_dry_run_and_prints_the_header_line(repos, tmp_path, capsys):
    import json

    from system_auditor.cli import main

    _, seed, clone = repos
    head = git(clone, "rev-parse", "HEAD")
    advance_remote(seed)
    code = main(["--json", "--config", str(tmp_path / "none.json"), "self-check",
                 "--clone", str(clone)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["status"] == "stale" and payload["would_pull"]
    assert payload["header_line"].startswith("self_check: stale ")
    assert git(clone, "rev-parse", "HEAD") == head


# --- report field -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, status",
    [
        ("current", "current"),
        ("pulled 1a2b3c4d5e6f..0f9e8d7c6b5a", "pulled"),
        ("stale clone 3 commits behind: no pull [lock]", "stale"),
        ("pulled", "unknown"),
        ("pulled 1a2b..zz", "unknown"),
        ("stale", "unknown"),
        ("stale   ", "unknown"),
        ("Current", "unknown"),
        ("", "unknown"),
        ("yes", "unknown"),
    ],
)
def test_parse_self_check(value, status):
    assert parse_self_check(value) == status


def write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "AUDIT-2026-W45--control.ASUS-GEI.claude-opus-5-5.md"
    path.write_text(
        "---\naudit_mode: self\ntime_token: 2026-W45\ndomain: control\nsystem: ASUS-GEI\n"
        f"auditor: claude-opus-5-5\n{extra}findings: 0\n---\n\nbody\n",
        encoding="utf-8",
    )
    return path


def test_report_without_the_field_reads_unknown(tmp_path):
    assert inspect_report(write(tmp_path, "")).self_check == "unknown"


def test_report_field_round_trips_with_awkward_reasons(tmp_path):
    value = "stale clone diverged: HEAD abc # see [M-1], 2 ahead"
    header = inspect_report(write(tmp_path, f"self_check: {value}\n"))
    assert header.self_check == value
    assert f"self_check: {value}" in header.to_front_matter()


def test_front_matter_omits_an_unset_or_unknown_field():
    assert "self_check" not in ReportHeader(domain="d", system="s").to_front_matter()
    header = ReportHeader(domain="d", system="s", self_check="unknown")
    assert "self_check" not in header.to_front_matter()


# --- meta audits name a stale tool --------------------------------------------------------------


def runs_with(tmp_path: Path, values: list[str]) -> list[AuditRun]:
    out = []
    for index, value in enumerate(values):
        name = f"AUDIT-2026-W45--control.HOST{index}.claude-opus-5-5.md"
        path = tmp_path / name
        extra = f"self_check: {value}\n" if value else ""
        path.write_text(
            "---\naudit_mode: self\ntime_token: 2026-W45\ndomain: control\n"
            f"system: HOST{index}\nauditor: claude-opus-5-5\n{extra}coverage: [x]\n"
            "findings: 0\n---\n",
            encoding="utf-8",
        )
        out.append(AuditRun(header=inspect_report(path), findings=[]))
    return out


def test_meta_caveat_names_a_participant_with_a_stale_tool(tmp_path):
    from system_auditor.compare import CROSS_SYSTEM

    runs = runs_with(tmp_path, ["current", "stale clone 11 commits behind"])
    caveats = check_comparability(runs, CROSS_SYSTEM).caveats
    assert any("HOST1" in note and "stale" in note for note in caveats)


def test_meta_report_text_names_the_stale_tool(tmp_path):
    """meta.py needs no change: the caveat reaches the META text through render_markdown."""
    from system_auditor.compare import CROSS_SYSTEM, build_meta, render_markdown

    runs = runs_with(tmp_path, ["current", "stale clone 11 commits behind"])
    text = render_markdown(build_meta(runs, CROSS_SYSTEM))
    assert "stale auditor tool" in text and "11 commits behind" in text


def test_meta_has_no_new_caveat_for_current_or_old_reports(tmp_path):
    from system_auditor.compare import CROSS_SYSTEM

    runs = runs_with(tmp_path, ["current", ""])
    assert not any("self_check" in note for note in check_comparability(runs, CROSS_SYSTEM).caveats)


# --- config -----------------------------------------------------------------------------------


def test_config_reads_mirror_dir_and_lock_check_command(tmp_path):
    cfg = tmp_path / "system-auditor.config.json"
    cfg.write_text(
        '{"system": "H", "mirror_dir": "<HOME>/mirror", '
        '"lock_check_command": "lockscan --check-dir {path}"}',
        encoding="utf-8",
    )
    config = load_config(cfg, home="C:/Users/T")
    assert config.mirror_dir == "C:/Users/T/mirror"
    assert config.lock_check_command == "lockscan --check-dir {path}"
    assert load_config(tmp_path / "missing.json").mirror_dir == ""
