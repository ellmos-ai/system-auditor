"""Phase (a-1) self audit and the report field ``self_check`` (T-20261101-574947335).

Real git repositories (a bare origin, the auditor's clone, a second publisher clone) in a
temp dir: the pull gate is exercised against actual git state. Every refusal is checked
with HEAD unchanged as the negative control.
"""

from __future__ import annotations

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
