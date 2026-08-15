"""Cross-system classification -- including the real 2026-08-15 example."""

from datetime import timedelta

from system_auditor.audit_lock import utcnow
from system_auditor.compare import (
    DIVERGENT,
    HOST_SPECIFIC,
    INVERSE,
    SYSTEMWIDE,
    UNVERIFIABLE,
    AuditRun,
    Finding,
    build_meta,
    normalize_locator,
)
from system_auditor.report import ReportHeader

GARDENER = "<HOME>/OneDrive/.TOPICS/.AI/.MODULES/.MEMORY/gardener/AGENTS.md"


def _header(host, coverage=None, clean=None, **kwargs):
    return ReportHeader(
        area="ai-modules-memory",
        host=host,
        run_id=f"{host}-run",
        finished_utc=utcnow(),
        coverage=coverage if coverage is not None else ["<HOME>/OneDrive/.TOPICS/.AI"],
        clean=clean or [],
        **kwargs,
    )


def test_home_paths_are_folded_so_hosts_are_comparable():
    """Without this, C:\\Users\\lukas never matches C:\\Users\\User and every
    finding would look host-specific."""
    a = normalize_locator(r"C:\Users\lukas\OneDrive\x\AGENTS.md")
    b = normalize_locator("C:/Users/User/OneDrive/x/AGENTS.md")
    assert a == b == "<home>/onedrive/x/agents.md"


def test_findings_at_same_place_with_same_rule_share_a_key():
    left = Finding(r"C:\Users\lukas\OneDrive\x.md", "hostpath-hardcoded")
    right = Finding("C:/Users/User/OneDrive/x.md", "hostpath-hardcoded")
    assert left.key == right.key


def test_systemwide_when_every_participant_found_it():
    finding = Finding(GARDENER, "pointer-drift", "Pointer nennt altes Ziel")
    runs = [
        AuditRun(_header("H1"), [finding]),
        AuditRun(_header("H2"), [Finding(GARDENER, "pointer-drift")]),
        AuditRun(_header("H3"), [Finding(GARDENER, "pointer-drift")]),
    ]
    result = build_meta(runs)
    assert result.level == 3
    assert result.items[0].classification == SYSTEMWIDE
    assert result.items[0].present_on == ["H1", "H2", "H3"]


def test_host_specific_when_others_covered_and_found_nothing():
    """The measured case T-20260815-08: Gardener hardcodes C:\\Users\\User.
    Real finding on WORKSTATION-LG, non-finding on the laptop where that path
    is correct."""
    runs = [
        AuditRun(
            _header("WORKSTATION-LG"),
            [Finding(GARDENER, "hostpath-hardcoded", "Laptop-Home hartkodiert")],
        ),
        AuditRun(_header("ASUS-GEI"), []),
    ]
    result = build_meta(runs)
    item = result.items[0]
    assert item.classification == HOST_SPECIFIC
    assert item.present_on == ["WORKSTATION-LG"]
    assert item.absent_on == ["ASUS-GEI"]


def test_inverse_when_another_host_declared_the_locator_clean():
    runs = [
        AuditRun(_header("WORKSTATION-LG"), [Finding(GARDENER, "hostpath-hardcoded")]),
        AuditRun(_header("ASUS-GEI", clean=[GARDENER]), []),
    ]
    item = build_meta(runs).items[0]
    assert item.classification == INVERSE
    assert item.clean_on == ["ASUS-GEI"]


def test_divergent_when_same_locator_breaks_different_rules():
    runs = [
        AuditRun(_header("H1"), [Finding(GARDENER, "hostpath-hardcoded")]),
        AuditRun(_header("H2"), [Finding(GARDENER, "stale-pointer")]),
    ]
    result = build_meta(runs)
    assert all(item.classification == DIVERGENT for item in result.items)
    assert result.items[0].divergent_rules


def test_unverifiable_when_the_other_run_never_looked_there():
    """The honest rung: without it, every coverage gap would masquerade as a
    real difference between systems."""
    runs = [
        AuditRun(_header("H1"), [Finding(GARDENER, "hostpath-hardcoded")]),
        AuditRun(_header("H2", coverage=["<HOME>/OneDrive/.SYNC"]), []),
    ]
    item = build_meta(runs).items[0]
    assert item.classification == UNVERIFIABLE
    assert item.unknown_on == ["H2"]


def test_findings_only_the_other_system_saw_are_reported_too():
    runs = [
        AuditRun(_header("H1"), []),
        AuditRun(_header("H2"), [Finding(GARDENER, "hostpath-hardcoded")]),
    ]
    result = build_meta(runs)
    assert len(result.items) == 1
    assert result.items[0].present_on == ["H2"]


def test_meta_needs_at_least_two_systems():
    result = build_meta([AuditRun(_header("H1"), [Finding(GARDENER, "r")])])
    assert result.comparability.ok is False
    assert result.items == []


def test_different_domains_are_not_comparable():
    left = AuditRun(_header("H1"), [])
    right_header = _header("H2")
    right_header.area = "ai-bundles"
    result = build_meta([left, AuditRun(right_header, [])])
    assert result.comparability.ok is False
    assert "different domains" in result.comparability.blockers[0]


def test_two_runs_of_one_system_are_rejected():
    result = build_meta([AuditRun(_header("H1"), []), AuditRun(_header("H1"), [])])
    assert result.comparability.ok is False


def test_missing_coverage_is_a_caveat_not_a_blocker():
    runs = [
        AuditRun(_header("H1", coverage=[]), [Finding(GARDENER, "r")]),
        AuditRun(_header("H2"), []),
    ]
    result = build_meta(runs)
    assert result.comparability.ok is True
    assert any("no coverage" in note for note in result.comparability.caveats)


def test_differing_evidence_levels_are_flagged():
    runs = [
        AuditRun(_header("H1", evidence_level=1), []),
        AuditRun(_header("H2", evidence_level=3), []),
    ]
    caveats = build_meta(runs).comparability.caveats
    assert any("evidence levels differ" in note for note in caveats)


def test_wide_time_span_is_flagged():
    early = _header("H1")
    early.finished_utc = utcnow() - timedelta(days=9)
    runs = [AuditRun(early, []), AuditRun(_header("H2"), [])]
    assert any("span" in note for note in build_meta(runs).comparability.caveats)


def test_counts_and_rendering():
    runs = [
        AuditRun(_header("H1"), [Finding(GARDENER, "r", "Titel")]),
        AuditRun(_header("H2"), [Finding(GARDENER, "r")]),
    ]
    result = build_meta(runs)
    assert result.counts[SYSTEMWIDE] == 1

    from system_auditor.compare import render_markdown

    rendered = render_markdown(result, "ai-modules-memory")
    assert "Meta-2-Audit" in rendered
    assert "Systemweit" in rendered
