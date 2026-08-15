"""Classification across participants -- machines, models or domains."""

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
    render_markdown,
)
from system_auditor.report import ReportHeader
from system_auditor.tokens import CROSS_DOMAIN, CROSS_SYSTEM, INTERRATER

GARDENER = "<HOME>/OneDrive/.TOPICS/.AI/.MODULES/.MEMORY/gardener/AGENTS.md"
DEFAULT_COVERAGE = ["<HOME>/OneDrive/.TOPICS/.AI"]


def _run(system="H1", findings=None, domain="modules-memory", auditor="opus",
         coverage=None, clean=None, **kwargs):
    header = ReportHeader(
        domain=domain,
        system=system,
        auditor=auditor,
        time_token="20260810",
        run_id=f"{system}-{auditor}-run",
        finished_utc=utcnow(),
        coverage=DEFAULT_COVERAGE if coverage is None else coverage,
        clean=clean or [],
        **kwargs,
    )
    return AuditRun(header, findings or [])


def test_home_paths_are_folded_so_machines_are_comparable():
    """Without this, C:\\Users\\lukas never matches C:\\Users\\User and every
    finding would look host-specific."""
    a = normalize_locator(r"C:\Users\lukas\OneDrive\x\AGENTS.md")
    b = normalize_locator("C:/Users/User/OneDrive/x/AGENTS.md")
    assert a == b == "<home>/onedrive/x/agents.md"


def test_systemwide_when_every_participant_found_it():
    runs = [
        _run("H1", [Finding(GARDENER, "pointer-drift", "Pointer nennt altes Ziel")]),
        _run("H2", [Finding(GARDENER, "pointer-drift")]),
        _run("H3", [Finding(GARDENER, "pointer-drift")]),
    ]
    result = build_meta(runs, CROSS_SYSTEM)
    assert result.level == 3
    assert result.items[0].classification == SYSTEMWIDE
    assert result.items[0].present_on == ["H1", "H2", "H3"]


def test_host_specific_when_others_covered_and_found_nothing():
    """The measured case T-20260815-08: a hardcoded C:\\Users\\User path is a
    real finding on one machine and correct on the other."""
    runs = [
        _run("WORKSTATION-LG",
             [Finding(GARDENER, "hostpath-hardcoded", "Laptop-Home hartkodiert")]),
        _run("ASUS-GEI", []),
    ]
    item = build_meta(runs, CROSS_SYSTEM).items[0]
    assert item.classification == HOST_SPECIFIC
    assert item.present_on == ["WORKSTATION-LG"]
    assert item.absent_on == ["ASUS-GEI"]


def test_inverse_when_another_participant_declared_it_clean():
    runs = [
        _run("WORKSTATION-LG", [Finding(GARDENER, "hostpath-hardcoded")]),
        _run("ASUS-GEI", [], clean=[GARDENER]),
    ]
    item = build_meta(runs, CROSS_SYSTEM).items[0]
    assert item.classification == INVERSE
    assert item.clean_on == ["ASUS-GEI"]


def test_divergent_when_same_locator_breaks_different_rules():
    runs = [
        _run("H1", [Finding(GARDENER, "hostpath-hardcoded")]),
        _run("H2", [Finding(GARDENER, "stale-pointer")]),
    ]
    result = build_meta(runs, CROSS_SYSTEM)
    assert all(item.classification == DIVERGENT for item in result.items)


def test_unverifiable_when_a_participant_never_looked_there():
    """The honest rung: without it, every coverage gap would masquerade as a
    real difference."""
    runs = [
        _run("H1", [Finding(GARDENER, "hostpath-hardcoded")]),
        _run("H2", [], coverage=["<HOME>/OneDrive/.SYNC"]),
    ]
    item = build_meta(runs, CROSS_SYSTEM).items[0]
    assert item.classification == UNVERIFIABLE
    assert item.unknown_on == ["H2"]


def test_findings_only_another_participant_saw_are_reported_too():
    runs = [_run("H1", []), _run("H2", [Finding(GARDENER, "hostpath-hardcoded")])]
    result = build_meta(runs, CROSS_SYSTEM)
    assert len(result.items) == 1
    assert result.items[0].present_on == ["H2"]


def test_interrater_axis_compares_models_on_one_machine():
    runs = [
        _run("H1", [Finding(GARDENER, "pointer-drift")], auditor="opus"),
        _run("H1", [Finding(GARDENER, "pointer-drift")], auditor="sonnet"),
    ]
    result = build_meta(runs, INTERRATER)
    assert result.axis == "auditor"
    assert result.participants == ["opus", "sonnet"]
    assert result.items[0].classification == SYSTEMWIDE


def test_interrater_agreement_is_reported():
    """On the interrater axis a low value is not a system defect but a
    reliability problem of the auditors themselves."""
    runs = [
        _run("H1", [Finding(GARDENER, "a"), Finding(GARDENER + "/x", "b")], auditor="opus"),
        _run("H1", [Finding(GARDENER, "a")], auditor="sonnet"),
    ]
    result = build_meta(runs, INTERRATER)
    assert result.agreement == 0.5


def test_agreement_is_none_when_nothing_is_decidable():
    runs = [
        _run("H1", [Finding(GARDENER, "a")], coverage=[]),
        _run("H1", [], coverage=[], auditor="sonnet"),
    ]
    assert build_meta(runs, INTERRATER).agreement is None


def test_cross_domain_matches_by_rule_across_different_places():
    """Across domains there is no shared location; the same rule broken in
    unrelated corners is a problem of the rule."""
    runs = [
        _run("H1", [Finding("<HOME>/a/AGENTS.md", "hostpath-hardcoded")], domain="bundles"),
        _run("H1", [Finding("<HOME>/b/CLAUDE.md", "hostpath-hardcoded")], domain="skills"),
    ]
    result = build_meta(runs, CROSS_DOMAIN)
    assert result.axis == "domain"
    assert result.items[0].classification == SYSTEMWIDE
    assert result.items[0].present_on == ["bundles", "skills"]


def test_fixed_dimension_mismatch_blocks_the_comparison():
    runs = [_run("H1", domain="bundles"), _run("H2", domain="skills")]
    result = build_meta(runs, CROSS_SYSTEM)
    assert result.comparability.ok is False
    assert "domain" in result.comparability.blockers[0]


def test_two_runs_of_one_participant_are_rejected():
    result = build_meta([_run("H1"), _run("H1")], CROSS_SYSTEM)
    assert result.comparability.ok is False


def test_meta_needs_at_least_two_participants():
    result = build_meta([_run("H1", [Finding(GARDENER, "r")])], CROSS_SYSTEM)
    assert result.comparability.ok is False
    assert result.items == []


def test_missing_coverage_is_a_caveat_not_a_blocker():
    runs = [_run("H1", [Finding(GARDENER, "r")], coverage=[]), _run("H2", [])]
    result = build_meta(runs, CROSS_SYSTEM)
    assert result.comparability.ok is True
    assert any("no coverage" in note for note in result.comparability.caveats)


def test_differing_evidence_levels_are_flagged():
    runs = [_run("H1", evidence_level=1), _run("H2", evidence_level=3)]
    caveats = build_meta(runs, CROSS_SYSTEM).comparability.caveats
    assert any("evidence levels differ" in note for note in caveats)


def test_headings_follow_the_axis():
    runs = [
        _run("H1", [Finding(GARDENER, "r", "Titel")], auditor="opus"),
        _run("H1", [Finding(GARDENER, "r")], auditor="sonnet"),
    ]
    rendered = render_markdown(build_meta(runs, INTERRATER), "modules-memory")
    assert "Uebereinstimmung" in rendered
    assert "Systemweit" not in rendered
