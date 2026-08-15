"""Meta lifecycle: validity, bundling, supersession, renewal."""

from datetime import timedelta

from system_auditor.audit_lock import utcnow
from system_auditor.meta import (
    archive,
    current_meta,
    plan_meta,
    renew_own_audits,
    supersede,
    valid_single_audits,
)
from system_auditor.report import MODE_META, ReportHeader, write_report

AREA = "ai-bundles"


def _single(tmp_path, host, days_ago=0, run_id=None):
    finished = utcnow() - timedelta(days=days_ago)
    header = ReportHeader(
        area=AREA, host=host, run_id=run_id or f"{host}-run", finished_utc=finished
    )
    write_report(tmp_path, header, "body")
    return header


def _meta(tmp_path, host, level, inputs, days_ago=0):
    header = ReportHeader(
        area=AREA,
        host=host,
        run_id=f"{host}-meta{level}",
        audit_mode=MODE_META,
        meta_level=level,
        inputs=inputs,
        finished_utc=utcnow() - timedelta(days=days_ago),
    )
    write_report(tmp_path, header, "meta body")
    return header


def test_stale_audits_are_excluded_and_named(tmp_path):
    """Bundling last month's statement with today's would fabricate a
    'difference between systems' that is really a difference in time."""
    _single(tmp_path, "H1", days_ago=1)
    _single(tmp_path, "H2", days_ago=40)

    valid, stale = valid_single_audits(tmp_path, AREA, validity="14d")
    assert [item.host for item in valid] == ["H1"]
    assert [item.host for item in stale] == ["H2"]

    plan = plan_meta(tmp_path, AREA, validity="14d")
    assert plan.action == "skip"
    assert any("H2" in entry for entry in plan.stale_excluded)


def test_only_the_newest_audit_per_system_counts(tmp_path):
    _single(tmp_path, "H1", days_ago=5, run_id="H1-old")
    _single(tmp_path, "H1", days_ago=1, run_id="H1-new")
    _single(tmp_path, "H2", days_ago=1)

    valid, _ = valid_single_audits(tmp_path, AREA)
    assert len(valid) == 2
    assert {item.run_id for item in valid} == {"H1-new", "H2-run"}


def test_meta_2_is_planned_once_two_systems_have_audited(tmp_path):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")

    plan = plan_meta(tmp_path, AREA)
    assert plan.should_create
    assert plan.level == 2
    assert plan.participants == ["H1", "H2"]
    assert plan.supersedes is None


def test_single_audit_alone_does_not_justify_a_meta(tmp_path):
    _single(tmp_path, "H1")
    plan = plan_meta(tmp_path, AREA)
    assert plan.action == "skip"
    assert "needs 2" in plan.reason


def test_third_system_triggers_meta_3_superseding_meta_2(tmp_path):
    """The user's scenario: a third system adds its audit, sees only a meta-2,
    and builds the meta-3 that replaces it."""
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    meta2 = _meta(tmp_path, "H2", 2, ["r1", "r2"])

    _single(tmp_path, "H3", run_id="r3")
    plan = plan_meta(tmp_path, AREA, host="H3")

    assert plan.should_create
    assert plan.level == 3
    assert plan.inputs == ["r1", "r2", "r3"]
    assert plan.supersedes == meta2.path
    assert "supersedes meta-2" in plan.reason


def test_no_new_meta_when_inputs_are_unchanged(tmp_path):
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    _meta(tmp_path, "H2", 2, ["r1", "r2"])

    plan = plan_meta(tmp_path, AREA)
    assert plan.action == "skip"
    assert "already rests on exactly these" in plan.reason


def test_expiring_input_makes_a_new_meta_due(tmp_path):
    """A meta audit is only as current as its inputs."""
    _single(tmp_path, "H1", days_ago=1, run_id="r1")
    _single(tmp_path, "H2", days_ago=20, run_id="r2")
    _single(tmp_path, "H3", days_ago=1, run_id="r3")
    _meta(tmp_path, "H2", 3, ["r1", "r2", "r3"])

    plan = plan_meta(tmp_path, AREA, validity="14d")
    assert plan.should_create
    assert plan.inputs == ["r1", "r3"]
    assert any("H2" in entry for entry in plan.stale_excluded)


def test_supersede_marks_and_archives_without_deleting(tmp_path):
    meta2 = _meta(tmp_path, "H2", 2, ["r1", "r2"])
    moved = supersede(meta2, "META-3-20260815-ai-bundles.H3.md")

    assert moved is not None and moved.exists()
    assert not meta2.path.exists()
    assert "superseded_by:" in moved.read_text(encoding="utf-8")
    assert current_meta(tmp_path, AREA) is None


def test_current_meta_prefers_the_highest_level(tmp_path):
    _meta(tmp_path, "H1", 2, ["r1", "r2"], days_ago=1)
    _meta(tmp_path, "H3", 3, ["r1", "r2", "r3"])
    assert current_meta(tmp_path, AREA).meta_level == 3


def test_renewal_touches_only_our_own_stale_audits(tmp_path):
    """No system may retire another's statement about a machine it cannot see."""
    mine = _single(tmp_path, "H1", days_ago=40)
    theirs = _single(tmp_path, "H2", days_ago=40)

    archived = renew_own_audits(tmp_path, AREA, "H1", validity="14d")
    assert len(archived) == 1
    assert not mine.path.exists()
    assert theirs.path.exists()


def test_plan_flags_our_own_stale_audit_for_renewal(tmp_path):
    _single(tmp_path, "H1", days_ago=40)
    _single(tmp_path, "H2", days_ago=1)
    plan = plan_meta(tmp_path, AREA, host="H1", validity="14d")
    assert plan.renew_needed == ["H1"]


def test_archive_never_overwrites(tmp_path):
    first = _single(tmp_path, "H1", run_id="r1")
    moved_one = archive(first.path)
    second = _single(tmp_path, "H1", run_id="r2")
    moved_two = archive(second.path)

    assert moved_one.exists() and moved_two.exists()
    assert moved_one != moved_two
