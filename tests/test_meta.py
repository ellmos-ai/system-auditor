"""Meta lifecycle: one current answer per fixed key, overwritten as it grows."""

from datetime import timedelta

from system_auditor.meta import (
    ACTION_CREATE,
    ACTION_SKIP,
    ACTION_UPDATE,
    MODE_ALWAYS,
    MODE_ON_DEMAND,
    current_single_audits,
    due_aggregations,
    existing_meta,
    plan_all,
    plan_meta,
    plan_metas,
    resolve_policy,
    stale_windows,
)
from system_auditor.report import MODE_META, ReportHeader, write_report
from system_auditor.tokens import (
    CROSS_DOMAIN,
    FULL_SYSTEM,
    INTERRATER,
    TIMESERIES,
    TIMESERIES_RATER,
    utcnow,
)

WINDOW = "20260810"
DOMAIN = "bundles"


def _single(tmp_path, system, domain=DOMAIN, time_token=WINDOW, auditor="opus",
            minutes_ago=0, run_id=None):
    header = ReportHeader(
        domain=domain,
        system=system,
        auditor=auditor,
        time_token=time_token,
        run_id=run_id or f"{system}-{auditor}-{domain}-{time_token}",
        finished_utc=utcnow() - timedelta(minutes=minutes_ago),
    )
    write_report(tmp_path, header, "body")
    return header


def _meta(tmp_path, level, inputs, aggregation="cross-system", key=None,
          system="H2"):
    header = ReportHeader(
        domain="",
        system=system,
        time_token=WINDOW,
        audit_mode=MODE_META,
        aggregation=aggregation,
        meta_level=level,
        inputs=inputs,
        scope=key if key is not None else [WINDOW, DOMAIN],
        finished_utc=utcnow(),
    )
    write_report(tmp_path, header, "meta body")
    return header


# --- cross-system -----------------------------------------------------------

def test_two_machines_in_one_window_make_a_meta_due(tmp_path):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")

    plans = plan_metas(tmp_path, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].action == ACTION_CREATE
    assert plans[0].level == 2
    assert plans[0].participants == ["H1", "H2"]
    assert plans[0].target == "META-cross-system--20260810--bundles.md"


def test_one_machine_is_not_a_bundle(tmp_path):
    _single(tmp_path, "H1")
    assert plan_metas(tmp_path, time_token=WINDOW) == []


def test_audits_from_another_window_do_not_join(tmp_path):
    """Bundling last window's statement with this one would fabricate a
    difference between machines that is really a difference in time."""
    _single(tmp_path, "H1", time_token=WINDOW)
    _single(tmp_path, "H2", time_token="20260803")
    assert plan_metas(tmp_path, time_token=WINDOW) == []


def test_third_machine_updates_the_key_in_place(tmp_path):
    """Within a key the artefact is overwritten, so there is exactly one
    current answer -- not meta-2 beside meta-3."""
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


def test_unchanged_participants_need_no_rewrite(tmp_path):
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    _meta(tmp_path, 2, ["r1", "r2"])

    plan = plan_metas(tmp_path, time_token=WINDOW)[0]
    assert plan.action == ACTION_SKIP
    assert "already rests on exactly these" in plan.reason


def test_uncontrolled_auditor_is_reported_not_blocked(tmp_path):
    """In a fleet where each machine runs its own model, refusing the
    comparison would mean never comparing machines at all."""
    _single(tmp_path, "H1", auditor="opus")
    _single(tmp_path, "H2", auditor="sonnet")

    plan = plan_metas(tmp_path, time_token=WINDOW)[0]
    assert plan.should_write
    assert "auditor" in plan.uncontrolled
    assert plan.uncontrolled["auditor"] == ["opus", "sonnet"]


# --- full-system (Fall A) ---------------------------------------------------

def test_full_system_bundles_all_domains_and_raters_of_one_machine(tmp_path):
    """Fall A: time and system fixed, domain and auditor may both vary."""
    _single(tmp_path, "H1", domain="bundles", auditor="opus", run_id="r1")
    _single(tmp_path, "H1", domain="skills", auditor="opus", run_id="r2")
    _single(tmp_path, "H1", domain="bundles", auditor="sonnet", run_id="r3")
    _single(tmp_path, "H2", domain="bundles", auditor="opus", run_id="r4")

    plans = plan_metas(tmp_path, aggregation=FULL_SYSTEM, time_token=WINDOW)
    by_key = {plan.target: plan for plan in plans}

    h1 = by_key["META-full-system--20260810--H1.md"]
    assert h1.level == 3  # bundles/opus, skills/opus, bundles/sonnet
    assert h1.counts == {"domain": 2, "auditor": 2}
    assert h1.inputs == ["r1", "r2", "r3"]
    assert "META-full-system--20260810--H2.md" not in by_key  # only one participant


def test_full_system_title_carries_the_counts_the_filename_omits(tmp_path):
    """The user's naming wish -- kept out of the file name so the overwrite
    rule survives a changing participant count."""
    _single(tmp_path, "H1", domain="bundles", auditor="opus")
    _single(tmp_path, "H1", domain="skills", auditor="sonnet")

    plan = plan_metas(tmp_path, aggregation=FULL_SYSTEM, time_token=WINDOW)[0]
    title = plan.title()
    assert "2 auditor" in title and "2 domain" in title
    assert "H1" in title
    assert plan.target == "META-full-system--20260810--H1.md"


# --- interrater and cross-domain -------------------------------------------

def test_interrater_bundle_is_found_on_one_machine(tmp_path):
    _single(tmp_path, "H1", auditor="opus", run_id="r-opus")
    _single(tmp_path, "H1", auditor="sonnet", run_id="r-sonnet")

    plans = plan_metas(tmp_path, aggregation=INTERRATER, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].participants == ["opus", "sonnet"]
    assert plans[0].target == "META-interrater--20260810--bundles--H1.md"


def test_cross_domain_holds_machine_and_model_constant(tmp_path):
    """Comparing domains across machines would vary two things at once."""
    _single(tmp_path, "H1", domain="bundles", auditor="opus", run_id="r-b")
    _single(tmp_path, "H1", domain="skills", auditor="opus", run_id="r-s")
    _single(tmp_path, "H2", domain="mcp", auditor="opus", run_id="r-m")

    plans = plan_metas(tmp_path, aggregation=CROSS_DOMAIN, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].participants == ["bundles", "skills"]
    assert plans[0].target == "META-cross-domain--20260810--H1--opus.md"


def test_separate_domains_get_separate_cross_system_metas(tmp_path):
    for domain in ("bundles", "skills"):
        _single(tmp_path, "H1", domain=domain, run_id=f"r1-{domain}")
        _single(tmp_path, "H2", domain=domain, run_id=f"r2-{domain}")

    plans = plan_metas(tmp_path, time_token=WINDOW)
    assert {plan.target for plan in plans} == {
        "META-cross-system--20260810--bundles.md",
        "META-cross-system--20260810--skills.md",
    }


# --- time series (Faelle B und C) ------------------------------------------

def test_timeseries_spans_windows_and_ignores_the_window_filter(tmp_path):
    """Fall B: system and domain fixed, time varies. Filtering to one window
    would leave a single window and no series at all."""
    _single(tmp_path, "H1", time_token="20260803", run_id="r1")
    _single(tmp_path, "H1", time_token="20260810", run_id="r2")
    _single(tmp_path, "H1", time_token="20260817", run_id="r3")

    plans = plan_metas(tmp_path, aggregation=TIMESERIES, time_token=WINDOW)
    assert len(plans) == 1
    assert plans[0].level == 3
    assert plans[0].participants == ["20260803", "20260810", "20260817"]
    assert plans[0].target == "META-timeseries--H1--bundles.md"


def test_timeseries_rater_pins_one_model(tmp_path):
    """Fall C: one auditor, one domain, one machine, across windows."""
    _single(tmp_path, "H1", time_token="20260803", auditor="opus", run_id="r1")
    _single(tmp_path, "H1", time_token="20260810", auditor="opus", run_id="r2")
    _single(tmp_path, "H1", time_token="20260810", auditor="sonnet", run_id="r3")

    plans = plan_metas(tmp_path, aggregation=TIMESERIES_RATER)
    targets = {plan.target for plan in plans}
    assert "META-timeseries-rater--H1--bundles--opus.md" in targets
    assert "META-timeseries-rater--H1--bundles--sonnet.md" not in targets  # one window only


def test_timeseries_keeps_no_period_in_its_name(tmp_path):
    """It is always "as of now" and gets rewritten as windows accumulate."""
    _single(tmp_path, "H1", time_token="20260803")
    _single(tmp_path, "H1", time_token="20260810")
    plan = plan_metas(tmp_path, aggregation=TIMESERIES)[0]
    assert "2026" not in plan.target
    assert plan.time_token == ""  # time is not a fixed dimension here


# --- housekeeping -----------------------------------------------------------

def test_restated_audit_forces_a_rebuild(tmp_path):
    """Identical tokens produce an identical file name, so the correction lands
    on top of its predecessor. Only the meta artefact has to notice."""
    _single(tmp_path, "H1", run_id="r1-old", minutes_ago=60)
    _single(tmp_path, "H2", run_id="r2")
    _meta(tmp_path, 2, ["r1-old", "r2"])

    _single(tmp_path, "H1", run_id="r1-new")
    current, _restated = current_single_audits(tmp_path, WINDOW)

    assert {header.run_id for header in current} == {"r1-new", "r2"}
    plan = plan_metas(tmp_path, time_token=WINDOW)[0]
    assert plan.action == ACTION_UPDATE
    assert plan.inputs == ["r1-new", "r2"]


def test_duplicate_identity_across_naming_schemes_is_deduplicated(tmp_path):
    """The migration case: a legacy report and a new one describe the same
    statement under different file names."""
    (tmp_path / f"SIG-TU-{WINDOW}-{DOMAIN}.H1.md").write_text(
        "# alter Bericht ohne Kopf\n", encoding="utf-8"
    )
    _single(tmp_path, "H1", auditor="unspecified", run_id="r-new")
    _single(tmp_path, "H2", auditor="unspecified", run_id="r2")

    current, restated = current_single_audits(tmp_path, WINDOW)
    assert {header.run_id for header in current} == {"r-new", "r2"}
    assert restated == ["H1/unspecified"]


def test_plan_meta_convenience_finds_one_domain(tmp_path):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")
    assert plan_meta(tmp_path, DOMAIN, WINDOW).level == 2
    assert plan_meta(tmp_path, "nonexistent", WINDOW) is None


def test_existing_meta_is_matched_by_full_key(tmp_path):
    _meta(tmp_path, 2, ["r1", "r2"])
    assert existing_meta(tmp_path, "cross-system", [WINDOW, DOMAIN]) is not None
    assert existing_meta(tmp_path, "cross-system", ["20260817", DOMAIN]) is None


def test_earlier_windows_are_listed_but_untouched(tmp_path):
    """For a snapshot they are past; for a time series they are the material."""
    old = _single(tmp_path, "H1", time_token="20260803")
    _single(tmp_path, "H2", time_token=WINDOW)

    stale = stale_windows(tmp_path, WINDOW)
    assert [item.time_token for item in stale] == ["20260803"]
    assert old.path.exists()
    assert stale_windows(tmp_path, WINDOW, system="H2") == []


# --- Bau-Politik: nicht alles immer ----------------------------------------

def test_only_the_standing_aggregation_is_built_by_default(tmp_path):
    """The ladder is combinatorial -- 14 domains x 3 machines x 2 models yields
    ~191 possible artefacts per window. Building all of them is noise that
    buries the two somebody reads."""
    _single(tmp_path, "H1", auditor="opus")
    _single(tmp_path, "H1", auditor="sonnet")
    _single(tmp_path, "H2", auditor="opus")

    plans = plan_all(tmp_path, time_token=WINDOW)
    assert {plan.aggregation for plan in plans} == {"cross-system"}


def test_an_on_demand_aggregation_is_built_when_asked_for(tmp_path):
    _single(tmp_path, "H1", auditor="opus")
    _single(tmp_path, "H1", auditor="sonnet")

    plans = plan_all(tmp_path, time_token=WINDOW, requested="interrater")
    assert [plan.aggregation for plan in plans] == ["interrater"]


def test_an_off_aggregation_stays_off_even_when_asked_for(tmp_path):
    """Switching it on is a config decision, not something a single call does
    silently."""
    assert due_aggregations(requested="timeseries-rater") == []


def test_config_can_promote_an_aggregation_to_standing():
    policy = resolve_policy({"timeseries": {"mode": MODE_ALWAYS}})
    assert [item.name for item, _ in due_aggregations(policy)] == [
        "cross-system",
        "timeseries",
    ]


def test_thresholds_are_per_aggregation(tmp_path):
    """A series of two windows says almost nothing, while two machines already
    say something -- so the bar differs."""
    _single(tmp_path, "H1", time_token="20260803")
    _single(tmp_path, "H1", time_token="20260810")

    assert plan_all(tmp_path, requested="timeseries") == []  # default needs 3

    lenient = resolve_policy({"timeseries": {"mode": MODE_ON_DEMAND, "min_participants": 2}})
    plans = plan_all(tmp_path, policy=lenient, requested="timeseries")
    assert len(plans) == 1


def test_unknown_config_names_are_ignored():
    assert resolve_policy({"does-not-exist": {"mode": MODE_ALWAYS}}) == resolve_policy()
