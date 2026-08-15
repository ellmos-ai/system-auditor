"""Development over time -- new, persistent, resolved, recurring."""

from system_auditor.audit_lock import utcnow
from system_auditor.compare import AuditRun, Finding
from system_auditor.report import ReportHeader
from system_auditor.timeseries import (
    NEW,
    PERSISTENT,
    RECURRING,
    RESOLVED,
    UNVERIFIABLE,
    build_timeseries,
    render_markdown,
)
from system_auditor.tokens import TIMESERIES, TIMESERIES_RATER

PLACE = "<HOME>/x/AGENTS.md"
COVERAGE = ["<HOME>/x"]


def _run(window, findings=None, coverage=None, auditor="opus", system="H1"):
    header = ReportHeader(
        domain="bundles",
        system=system,
        auditor=auditor,
        time_token=window,
        run_id=f"{system}-{window}",
        finished_utc=utcnow(),
        coverage=COVERAGE if coverage is None else coverage,
    )
    return AuditRun(header, findings or [])


def test_new_when_it_first_appears_in_the_latest_window():
    runs = [_run("W1"), _run("W2", [Finding(PLACE, "drift")])]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == NEW
    assert item.first_seen == "W2"


def test_persistent_across_every_window_since_it_appeared():
    finding = [Finding(PLACE, "drift")]
    runs = [_run("W1", finding), _run("W2", finding), _run("W3", finding)]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == PERSISTENT
    assert item.age_in_windows == 3


def test_resolved_only_when_the_latest_run_actually_looked():
    """A finding that merely stopped being checked looks exactly like a fixed
    one -- so coverage decides."""
    runs = [_run("W1", [Finding(PLACE, "drift")]), _run("W2")]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == RESOLVED
    assert item.last_seen == "W1"


def test_uncovered_latest_window_is_unverifiable_not_resolved():
    """The honest rung applied to time instead of participants."""
    runs = [
        _run("W1", [Finding(PLACE, "drift")]),
        _run("W2", coverage=["<HOME>/elsewhere"]),
    ]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == UNVERIFIABLE
    assert "gone and merely unchecked look identical" in item.rationale


def test_recurring_after_a_gap():
    finding = [Finding(PLACE, "drift")]
    runs = [_run("W1", finding), _run("W2"), _run("W3", finding)]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == RECURRING
    assert item.windows_absent == ["W2"]


def test_a_single_window_is_not_a_series():
    result = build_timeseries([_run("W1", [Finding(PLACE, "drift")])], TIMESERIES)
    assert result.items == []
    assert "at least two windows" in result.caveats[0]


def test_net_change_shows_the_direction():
    runs = [
        _run("W1", [Finding(PLACE, "old")]),
        _run("W2", [Finding(PLACE + "/a", "new1"), Finding(PLACE + "/b", "new2")]),
    ]
    result = build_timeseries(runs, TIMESERIES)
    assert result.counts[NEW] == 2
    assert result.counts[RESOLVED] == 1
    assert result.net_change == 1  # more new than resolved


def test_uncontrolled_auditor_is_flagged_in_a_plain_timeseries():
    """TIMESERIES leaves the auditor free, so a model change can masquerade as
    a change in the system."""
    runs = [
        _run("W1", [Finding(PLACE, "drift")], auditor="opus"),
        _run("W2", auditor="sonnet"),
    ]
    result = build_timeseries(runs, TIMESERIES)
    assert any("auditor is not held constant" in note for note in result.caveats)


def test_timeseries_rater_holds_the_model_constant():
    runs = [
        _run("W1", [Finding(PLACE, "drift")], auditor="opus"),
        _run("W2", [Finding(PLACE, "drift")], auditor="opus"),
    ]
    result = build_timeseries(runs, TIMESERIES_RATER)
    assert result.caveats == []
    assert result.items[0].classification == PERSISTENT


def test_finding_present_in_any_run_of_a_window_counts_for_that_window():
    """With the auditor uncontrolled, one of two models seeing it is enough to
    say the window saw it."""
    runs = [
        _run("W1", [Finding(PLACE, "drift")], auditor="opus"),
        _run("W2", auditor="opus"),
        _run("W2", [Finding(PLACE, "drift")], auditor="sonnet"),
    ]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == PERSISTENT


def test_rendering_names_the_direction():
    runs = [_run("W1"), _run("W2", [Finding(PLACE, "drift", "Titel")])]
    rendered = render_markdown(build_timeseries(runs, TIMESERIES), "H1 / bundles")
    assert "Zeitreihe" in rendered
    assert "Neu (erstmals" in rendered
    assert "W1 -> W2" in rendered


def test_an_uncovered_middle_window_does_not_claim_continuity():
    """Codex-Fund 5: W1 vorhanden, W2 nicht abgedeckt, W3 vorhanden ergab
    'persistent' mit der Begruendung 'present in every window' -- eine
    Behauptung ueber eine Beobachtung, die nie stattfand."""
    finding = [Finding(PLACE, "drift")]
    runs = [
        _run("W1", finding),
        _run("W2", coverage=["<HOME>/elsewhere"]),
        _run("W3", finding),
    ]
    item = build_timeseries(runs, TIMESERIES).items[0]
    assert item.classification == PERSISTENT
    assert item.continuity_verified is False
    assert "not covered" in item.rationale
    assert "W2" in item.rationale


def test_uninterrupted_series_still_claims_continuity():
    finding = [Finding(PLACE, "drift")]
    item = build_timeseries([_run("W1", finding), _run("W2", finding)], TIMESERIES).items[0]
    assert item.continuity_verified is True
