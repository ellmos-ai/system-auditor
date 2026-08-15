"""Time windows and aggregation -- the part two machines must agree on
without talking to each other."""

from datetime import datetime, timedelta, timezone

import pytest

from system_auditor.tokens import (
    CROSS_DOMAIN,
    CROSS_SYSTEM,
    FULL_SYSTEM,
    GROUP_BY_LOCATOR,
    GROUP_BY_RULE,
    INTERRATER,
    TIMESERIES,
    TIMESERIES_RATER,
    AuditIdentity,
    TimeGrid,
    TimeTable,
    find_bundles,
    newest_per_identity,
    parse_period,
    resolve_time_token,
)

ANCHOR = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday


def test_same_moment_yields_the_same_token_everywhere():
    """The whole point: no coordination needed. Two machines with the same
    config derive the same window from the clock alone."""
    grid_a = TimeGrid(period="7d", anchor=ANCHOR)
    grid_b = TimeGrid(period="7d", anchor=ANCHOR)
    moment = datetime(2026, 8, 15, 18, 30, tzinfo=timezone.utc)
    assert grid_a.token(moment) == grid_b.token(moment)


def test_moments_inside_one_window_share_a_token():
    grid = TimeGrid(period="7d", anchor=ANCHOR)
    start, end = grid.window(datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert grid.token(start) == grid.token(end - timedelta(seconds=1))


def test_boundary_separates_windows():
    """The accepted price of discretisation: minutes apart, different windows.
    Determinism across machines is worth more than smoothness at the edge."""
    grid = TimeGrid(period="7d", anchor=ANCHOR)
    start, end = grid.window(datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert grid.token(end - timedelta(minutes=2)) != grid.token(end + timedelta(minutes=2))


def test_token_is_sortable_and_filename_safe():
    grid = TimeGrid(period="7d", anchor=ANCHOR)
    earlier = grid.token(datetime(2026, 7, 1, tzinfo=timezone.utc))
    later = grid.token(datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert earlier < later
    assert all(char.isalnum() for char in later)


def test_hourly_grid_keeps_the_hour():
    grid = TimeGrid(period="6h", anchor=ANCHOR)
    assert "T" in grid.token(datetime(2026, 8, 15, 13, tzinfo=timezone.utc))


def test_explicit_table_wins_where_it_applies():
    table = TimeTable(
        entries=[{"token": "sprint-42", "from": "2026-08-10", "to": "2026-08-24"}]
    )
    moment = datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert resolve_time_token(moment, TimeGrid(anchor=ANCHOR), table) == "sprint-42"


def test_moment_outside_the_table_falls_back_to_the_grid():
    """An audit must never fail because the calendar has a hole."""
    table = TimeTable(
        entries=[{"token": "sprint-42", "from": "2026-01-01", "to": "2026-01-08"}]
    )
    grid = TimeGrid(period="7d", anchor=ANCHOR)
    moment = datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert resolve_time_token(moment, grid, table) == grid.token(moment)


def test_invalid_period_is_rejected():
    with pytest.raises(ValueError):
        parse_period("fortnight")


def test_naive_anchor_is_treated_as_utc():
    grid = TimeGrid(period="1d", anchor=datetime(2026, 1, 5))
    assert grid.anchor.tzinfo is not None


def _identity(time="W1", domain="bundles", system="H1", auditor="opus"):
    return AuditIdentity(time=time, domain=domain, system=system, auditor=auditor)


def test_cross_system_bundles_by_period_and_domain():
    identities = [
        _identity(system="H1"),
        _identity(system="H2"),
        _identity(system="H3"),
    ]
    bundles = find_bundles(identities, CROSS_SYSTEM)
    assert len(bundles) == 1
    assert bundles[0].level == 3
    assert bundles[0].varying_values == ["H1", "H2", "H3"]


def test_different_windows_never_bundle_together():
    """Bundling last month's statement with today's would fabricate a
    difference between systems that is really a difference in time."""
    identities = [_identity(time="W1", system="H1"), _identity(time="W2", system="H2")]
    assert find_bundles(identities, CROSS_SYSTEM) == []


def test_different_domains_do_not_bundle_cross_system():
    identities = [
        _identity(domain="bundles", system="H1"),
        _identity(domain="skills", system="H2"),
    ]
    assert find_bundles(identities, CROSS_SYSTEM) == []


def test_interrater_bundles_models_on_one_machine():
    identities = [
        _identity(system="H1", auditor="opus"),
        _identity(system="H1", auditor="sonnet"),
    ]
    bundles = find_bundles(identities, INTERRATER)
    assert len(bundles) == 1
    assert bundles[0].varying_values == ["opus", "sonnet"]


def test_interrater_does_not_bundle_across_machines():
    identities = [
        _identity(system="H1", auditor="opus"),
        _identity(system="H2", auditor="sonnet"),
    ]
    assert find_bundles(identities, INTERRATER) == []


def test_cross_domain_holds_machine_and_model_constant():
    """Comparing domains across machines would vary two things at once and
    leave the result uninterpretable."""
    identities = [
        _identity(domain="bundles", system="H1"),
        _identity(domain="skills", system="H1"),
    ]
    bundles = find_bundles(identities, CROSS_DOMAIN)
    assert len(bundles) == 1
    assert bundles[0].varying_values == ["bundles", "skills"]

    across_machines = [
        _identity(domain="bundles", system="H1"),
        _identity(domain="skills", system="H2"),
    ]
    assert find_bundles(across_machines, CROSS_DOMAIN) == []


def test_full_system_lets_two_dimensions_vary_at_once():
    """Fall A: one machine in one window, over all its domains and models."""
    identities = [
        _identity(domain="bundles", auditor="opus"),
        _identity(domain="skills", auditor="opus"),
        _identity(domain="bundles", auditor="sonnet"),
    ]
    bundles = find_bundles(identities, FULL_SYSTEM)
    assert len(bundles) == 1
    assert bundles[0].level == 3           # participant = domain / auditor
    assert bundles[0].counts() == {"domain": 2, "auditor": 2}


def test_uncontrolled_dimensions_are_named():
    """cross-system does not pin the model, and says so rather than pretending
    the comparison is clean."""
    assert CROSS_SYSTEM.uncontrolled == ("auditor",)
    assert FULL_SYSTEM.uncontrolled == ()

    spread = find_bundles(
        [_identity(system="H1", auditor="opus"), _identity(system="H2", auditor="sonnet")],
        CROSS_SYSTEM,
    )[0].uncontrolled_spread()
    assert spread == {"auditor": ["opus", "sonnet"]}


def test_timeseries_varies_time_and_is_marked_as_such():
    """Fall B: the snapshot classes would be nonsense over windows."""
    identities = [_identity(time="W1"), _identity(time="W2")]
    bundles = find_bundles(identities, TIMESERIES)
    assert TIMESERIES.is_timeseries is True
    assert bundles[0].varying_values == ["W1", "W2"]

    # Fall C: pinning the auditor separates the models into their own series
    mixed = [
        _identity(time="W1", auditor="opus"),
        _identity(time="W2", auditor="opus"),
        _identity(time="W2", auditor="sonnet"),
    ]
    series = find_bundles(mixed, TIMESERIES_RATER)
    assert len(series) == 1
    assert series[0].varying_values == ["W1", "W2"]


def test_cross_domain_matches_by_rule_not_by_place():
    """Across domains there is no shared location -- what carries meaning is
    whether the same rule is broken in unrelated corners."""
    assert CROSS_DOMAIN.group_by == GROUP_BY_RULE
    assert CROSS_SYSTEM.group_by == GROUP_BY_LOCATOR


def test_a_single_participant_is_not_a_bundle():
    assert find_bundles([_identity()], CROSS_SYSTEM) == []


def test_repeated_statement_collapses_to_the_newest():
    """Same four tokens = the same statement, corrected. Not a second opinion."""
    identity = _identity()
    entries = [(identity, {"t": 1}), (identity, {"t": 5}), (identity, {"t": 3})]
    kept = newest_per_identity(entries, sort_key=lambda payload: payload["t"])
    assert len(kept) == 1
    assert kept[0][1]["t"] == 5


def test_the_default_anchor_is_a_constant_not_today():
    """Fable-Review: Die CLI setzte den Anker auf Mitternacht des AUFRUFTAGS.
    Damit ergaben Montag und Mittwoch derselben Woche verschiedene Tokens -- das
    7-Tage-Fenster degenerierte zu Tagesfenstern und meta-plan buendelte nie
    tagesuebergreifend. Der Anker fixiert die PHASE des Rasters und muss darum
    konstant sein."""
    grid = TimeGrid(period="7d")
    monday = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    wednesday = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    assert grid.token(monday) == grid.token(wednesday)

    # Gegenprobe: der fehlerhafte Aufruftags-Anker trennt sie
    per_day_monday = TimeGrid(period="7d", anchor=monday.replace(hour=0)).token(monday)
    per_day_wednesday = TimeGrid(period="7d", anchor=wednesday.replace(hour=0)).token(wednesday)
    assert per_day_monday != per_day_wednesday
