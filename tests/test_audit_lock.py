"""Lock protocol: presence never excludes, claims resolve deterministically."""

from datetime import timedelta

import pytest

from system_auditor.audit_lock import (
    MODE_CLAIM,
    MODE_PRESENCE,
    AuditLock,
    LockError,
    foreign_presence,
    list_locks,
    read_lock,
    release,
    resolve_claim,
    utcnow,
    write_lock,
)


def test_presence_lock_is_advisory_and_roundtrips(tmp_path):
    lock = write_lock(tmp_path, "ai-bundles", "ASUS-GEI", MODE_PRESENCE, "run-1")
    assert lock.path.name == "LOCK.audit.ai-bundles.ASUS-GEI.txt"
    assert lock.is_advisory()

    text = lock.path.read_text(encoding="utf-8")
    assert "ADVISORY" in text
    assert "mode: soft" in text  # base-format field: does not block anyone

    parsed = read_lock(lock.path)
    assert (parsed.area, parsed.host, parsed.mode) == ("ai-bundles", "ASUS-GEI", MODE_PRESENCE)


def test_filename_is_authoritative_for_scope(tmp_path):
    """Body fields are informational; the name decides -- as in the base spec."""
    target = tmp_path / "LOCK.audit.real-area.REAL-HOST.txt"
    target.write_text(
        "host: WRONG\narea: wrong-area\ncreated: 2026-08-15T10:00:00Z\naudit_mode: presence\n",
        encoding="utf-8",
    )
    lock = read_lock(target)
    assert (lock.area, lock.host) == ("real-area", "REAL-HOST")


def test_presence_of_other_systems_is_visible_but_not_blocking(tmp_path):
    write_lock(tmp_path, "ai-bundles", "WORKSTATION-LG", MODE_PRESENCE, "run-w")
    mine = write_lock(tmp_path, "ai-bundles", "ASUS-GEI", MODE_PRESENCE, "run-a")

    others = foreign_presence(tmp_path, "ai-bundles", "ASUS-GEI")
    assert [item.host for item in others] == ["WORKSTATION-LG"]

    # A presence lock never competes -- two self-audits of one domain are the
    # premise of a meta audit, not a collision.
    assert resolve_claim(tmp_path, mine).won is True


def test_claim_earliest_created_wins(tmp_path):
    now = utcnow()
    write_lock(
        tmp_path, "ai-bundles", "WORKSTATION-LG", MODE_CLAIM, "run-w",
        compares="a+b", created=now - timedelta(seconds=30),
    )
    mine = write_lock(
        tmp_path, "ai-bundles", "ASUS-GEI", MODE_CLAIM, "run-a",
        compares="a+b", created=now,
    )
    outcome = resolve_claim(tmp_path, mine)
    assert outcome.won is False
    assert outcome.winner.host == "WORKSTATION-LG"
    assert "earlier claim" in outcome.reason


def test_claim_tie_breaks_on_host_order_deterministically(tmp_path):
    now = utcnow()
    write_lock(
        tmp_path, "ai-bundles", "AAA-HOST", MODE_CLAIM, "run-1",
        compares="a+b", created=now,
    )
    mine = write_lock(
        tmp_path, "ai-bundles", "ZZZ-HOST", MODE_CLAIM, "run-2",
        compares="a+b", created=now,
    )
    outcome = resolve_claim(tmp_path, mine)
    assert outcome.won is False
    assert outcome.winner.host == "AAA-HOST"
    assert "tie" in outcome.reason


def test_claims_over_different_input_sets_do_not_compete(tmp_path):
    """Two meta audits of the same domain over different participants are
    different statements, so neither blocks the other."""
    now = utcnow()
    write_lock(
        tmp_path, "ai-bundles", "WORKSTATION-LG", MODE_CLAIM, "run-w",
        compares="a+b", created=now - timedelta(seconds=30),
    )
    mine = write_lock(
        tmp_path, "ai-bundles", "ASUS-GEI", MODE_CLAIM, "run-a",
        compares="a+b+c", created=now,
    )
    assert resolve_claim(tmp_path, mine).won is True


def test_expired_locks_drop_out_of_listings(tmp_path):
    write_lock(
        tmp_path, "ai-bundles", "OLD-HOST", MODE_PRESENCE, "run-old",
        expires_after="1h", created=utcnow() - timedelta(hours=3),
    )
    assert list_locks(tmp_path) == []
    assert len(list_locks(tmp_path, include_expired=True)) == 1


def test_active_foreign_lock_is_never_overwritten(tmp_path):
    write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-1")
    with pytest.raises(LockError):
        write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-2")


def test_expired_own_lock_may_be_replaced(tmp_path):
    write_lock(
        tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-1",
        expires_after="1h", created=utcnow() - timedelta(hours=5),
    )
    fresh = write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-2")
    assert read_lock(fresh.path).run_id == "run-2"


def test_unparsable_foreign_lock_does_not_break_listing(tmp_path):
    (tmp_path / "LOCK.audit.broken.HOST-X.txt").write_text("garbage", encoding="utf-8")
    write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-1")
    assert [item.host for item in list_locks(tmp_path)] == ["HOST-A"]


def test_release_is_idempotent(tmp_path):
    lock = write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-1")
    assert release(lock) is True
    assert release(lock.path) is True


def test_created_is_second_granular(tmp_path):
    """Minute granularity would push most races into the host tiebreak, where
    the same host would lose structurally, every time."""
    lock = write_lock(tmp_path, "ai-bundles", "HOST-A", MODE_PRESENCE, "run-1")
    created_line = [
        line for line in lock.path.read_text(encoding="utf-8").splitlines()
        if line.startswith("created:")
    ][0]
    assert created_line.count(":") == 3  # key + hh:mm:ss


def test_unknown_mode_is_rejected(tmp_path):
    with pytest.raises(LockError):
        write_lock(tmp_path, "area", "HOST", "whatever", "run")


def test_minute_granular_timestamps_still_parse():
    """Base-format locks written by other tools must remain readable."""
    lock = AuditLock.from_text(
        "host: H\narea: a\ncreated: 2026-08-15T10:00\naudit_mode: presence\n"
    )
    assert lock.created.year == 2026
