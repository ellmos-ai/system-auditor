"""Meta lifecycle: one current answer per window, overwritten as participants change."""

from datetime import timedelta

from system_auditor.audit_lock import utcnow
from system_auditor.meta import (
    ACTION_CREATE,
    ACTION_SKIP,
    ACTION_UPDATE,
    current_single_audits,
    existing_meta,
    plan_meta,
    plan_metas,
    stale_windows,
)
from system_auditor.report import MODE_META, ReportHeader, write_report
from system_auditor.tokens import CROSS_DOMAIN, INTERRATER

WINDOW = "20260810"
DOMAIN = "bundles"


def _single(tmp_path, system, domain=DOMAIN, time_token=WINDOW, auditor="opus",
            minutes_ago=0, run_id=None):
    header = ReportHeader(
        domain=domain,
        system=system,
        auditor=auditor,
        time_token=time_token,
        run_id=run_id or f"{system}-{auditor}-{time_token}",
        finished_utc=utcnow() - timedelta(minutes=minutes_ago),
    )
    write_report(tmp_path, header, "body")
    return header


def _meta(tmp_path, level, inputs, aggregation="cross-system", scope=None,
          time_token=WINDOW, system="H2"):
    header = ReportHeader(
        domain="",
        system=system,
        time_token=time_token,
        audit_mode=MODE_META,
        aggregation=aggregation,
        meta_level=level,
        inputs=inputs,
        scope=scope if scope is not None else [DOMAIN],
        finished_utc=utcnow(),
    )
    write_report(tmp_path, header, "meta body")
    return header


def test_two_machines_in_one_window_make_a_meta_due(tmp_path):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")

    plans = plan_metas(tmp_path, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].action == ACTION_CREATE
    assert plans[0].level == 2
    assert plans[0].participants == ["H1", "H2"]
    assert plans[0].target == "META-cross-system-20260810-bundles.md"


def test_one_machine_is_not_a_bundle(tmp_path):
    _single(tmp_path, "H1")
    assert plan_metas(tmp_path, time_token=WINDOW) == []


def test_audits_from_another_window_do_not_join(tmp_path):
    """Bundling last window's statement with this one would fabricate a
    difference between machines that is really a difference in time."""
    _single(tmp_path, "H1", time_token=WINDOW)
    _single(tmp_path, "H2", time_token="20260803")
    assert plan_metas(tmp_path, time_token=WINDOW) == []


def test_third_machine_updates_the_windows_meta_in_place(tmp_path):
    """The user's rule: within a window the meta audit is overwritten, so there
    is exactly one current answer -- not meta-2 beside meta-3."""
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    previous = _meta(tmp_path, 2, ["r1", "r2"])

    _single(tmp_path, "H3", run_id="r3")
    plan = plan_metas(tmp_path, time_token=WINDOW)[0]

    assert plan.action == ACTION_UPDATE
    assert plan.level == 3
    assert plan.previous_level == 2
    assert plan.inputs == ["r1", "r2", "r3"]
    assert plan.replaces == previous.path
    assert plan.target == previous.path.name  # same file, rewritten
    assert "rewritten in place" in plan.reason


def test_unchanged_participants_need_no_rewrite(tmp_path):
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    _meta(tmp_path, 2, ["r1", "r2"])

    plan = plan_metas(tmp_path, time_token=WINDOW)[0]
    assert plan.action == ACTION_SKIP
    assert "already rests on exactly these" in plan.reason


def test_restated_audit_replaces_its_predecessor_and_forces_a_rebuild(tmp_path):
    """A re-run with identical tokens is a correction, so the meta audit of
    that window has to be rebuilt.

    Note the replacement needs no bookkeeping: identical tokens produce an
    identical file name, so the correction simply lands on top of its
    predecessor. Only the meta audit has to notice.
    """
    _single(tmp_path, "H1", run_id="r1-old", minutes_ago=60)
    _single(tmp_path, "H2", run_id="r2")
    _meta(tmp_path, 2, ["r1-old", "r2"])

    _single(tmp_path, "H1", run_id="r1-new")  # same identity, newer
    current, _restated = current_single_audits(tmp_path, WINDOW)

    assert len(current) == 2
    assert {header.run_id for header in current} == {"r1-new", "r2"}

    plan = plan_metas(tmp_path, time_token=WINDOW)[0]
    assert plan.action == ACTION_UPDATE
    assert plan.inputs == ["r1-new", "r2"]


def test_duplicate_identity_across_naming_schemes_is_deduplicated(tmp_path):
    """The migration case: a legacy report and a new one describe the same
    statement under different file names. Only the newer one counts, and the
    replacement is named so it does not look like a lost audit."""
    (tmp_path / f"SIG-TU-{WINDOW}-{DOMAIN}.H1.md").write_text(
        "# alter Bericht ohne Kopf\n", encoding="utf-8"
    )
    _single(tmp_path, "H1", auditor="unspecified", run_id="r-new")
    _single(tmp_path, "H2", auditor="unspecified", run_id="r2")

    current, restated = current_single_audits(tmp_path, WINDOW)
    assert {header.run_id for header in current} == {"r-new", "r2"}
    assert restated == ["H1/unspecified"]


def test_interrater_bundle_is_found_on_one_machine(tmp_path):
    _single(tmp_path, "H1", auditor="opus", run_id="r-opus")
    _single(tmp_path, "H1", auditor="sonnet", run_id="r-sonnet")

    plans = plan_metas(tmp_path, aggregation=INTERRATER, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].participants == ["opus", "sonnet"]
    assert plans[0].scope == [DOMAIN, "H1"]
    assert plans[0].target == "META-interrater-20260810-bundles-H1.md"


def test_cross_domain_bundle_spans_domains_in_one_window(tmp_path):
    _single(tmp_path, "H1", domain="bundles", run_id="r-b")
    _single(tmp_path, "H1", domain="skills", run_id="r-s")

    plans = plan_metas(tmp_path, aggregation=CROSS_DOMAIN, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].participants == ["bundles", "skills"]
    assert plans[0].scope == []
    assert plans[0].target == "META-cross-domain-20260810.md"


def test_separate_domains_get_separate_cross_system_metas(tmp_path):
    for domain in ("bundles", "skills"):
        _single(tmp_path, "H1", domain=domain, run_id=f"r1-{domain}")
        _single(tmp_path, "H2", domain=domain, run_id=f"r2-{domain}")

    plans = plan_metas(tmp_path, time_token=WINDOW)
    assert len(plans) == 2
    assert {plan.target for plan in plans} == {
        "META-cross-system-20260810-bundles.md",
        "META-cross-system-20260810-skills.md",
    }


def test_plan_meta_convenience_finds_one_domain(tmp_path):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")
    assert plan_meta(tmp_path, DOMAIN, WINDOW).level == 2
    assert plan_meta(tmp_path, "nonexistent", WINDOW) is None


def test_existing_meta_is_matched_by_window_and_scope(tmp_path):
    _meta(tmp_path, 2, ["r1", "r2"])
    assert existing_meta(tmp_path, "cross-system", WINDOW, [DOMAIN]) is not None
    assert existing_meta(tmp_path, "cross-system", "20260817", [DOMAIN]) is None


def test_earlier_windows_are_listed_but_untouched(tmp_path):
    """A past window's audit stays as the record of that window -- and only its
    own machine may restate it."""
    old = _single(tmp_path, "H1", time_token="20260803")
    _single(tmp_path, "H2", time_token=WINDOW)

    stale = stale_windows(tmp_path, WINDOW)
    assert [item.time_token for item in stale] == ["20260803"]
    assert old.path.exists()

    mine = stale_windows(tmp_path, WINDOW, system="H2")
    assert mine == []
