"""Classification across participants -- machines, models or domains."""

import pytest

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
from system_auditor.tokens import CROSS_DOMAIN, CROSS_SYSTEM, INTERRATER, utcnow

GARDENER = "<HOME>/OneDrive/.TOPICS/.AI/.MODULES/.MEMORY/gardener/AGENTS.md"
DEFAULT_COVERAGE = ["<HOME>/OneDrive/.TOPICS/.AI"]

WINDOW = "20260810"


def _run(system="H1", findings=None, domain="modules-memory", auditor="opus",
         coverage=None, clean=None, **kwargs):
    header = ReportHeader(
        domain=domain,
        system=system,
        auditor=auditor,
        time_token=WINDOW,
        run_id=f"{system}-{auditor}-run",
        finished_utc=utcnow(),
        coverage=DEFAULT_COVERAGE if coverage is None else coverage,
        clean=clean or [],
        **kwargs,
    )
    return AuditRun(header, findings or [])


def test_home_paths_are_folded_so_machines_are_comparable():
    """Without this, C:\\Users\\alice never matches C:\\Users\\bob and every
    finding would look host-specific."""
    a = normalize_locator(r"C:\Users\alice\OneDrive\x\AGENTS.md")
    b = normalize_locator("C:/Users/bob/OneDrive/x/AGENTS.md")
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
    """The measured case T-20260815-08: a hardcoded C:\\Users\\bob path is a
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


def test_unanimity_is_reported_under_its_honest_name():
    """Nicht 'Agreement': Der Nenner enthaelt nur Schluessel, die mindestens ein
    Auditor gemeldet hat -- gemeinsames Schweigen ueber saubere Stellen geht
    mangels definierter Item-Menge nicht ein (Review 2, Fund 8)."""
    runs = [
        _run("H1", [Finding(GARDENER, "a"), Finding(GARDENER + "/x", "b")], auditor="opus"),
        _run("H1", [Finding(GARDENER, "a")], auditor="sonnet"),
    ]
    result = build_meta(runs, INTERRATER)
    assert result.unanimity == 0.5
    assert result.pairwise_jaccard is not None


def test_unanimity_is_none_when_nothing_is_decidable():
    runs = [
        _run("H1", [Finding(GARDENER, "a")], coverage=[]),
        _run("H1", [], coverage=[], auditor="sonnet"),
    ]
    assert build_meta(runs, INTERRATER).unanimity is None


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


# --- Regressionen aus dem Codex-Review 2026-08-15 ---------------------------

def test_coverage_respects_path_segments(tmp_path):
    """Codex-Fund 4: 'startswith' liess die Abdeckung /repo/foo den Ort
    /repo/foobar/AGENTS.md verschlucken -- und Abdeckung entscheidet zwischen
    'geprueft, nichts gefunden' und 'nie hingeschaut'."""
    runs = [
        _run("H1", [Finding("/repo/foobar/AGENTS.md", "drift")], coverage=["/repo"]),
        _run("H2", [], coverage=["/repo/foo"]),
    ]
    item = build_meta(runs, CROSS_SYSTEM).items[0]
    assert item.classification == UNVERIFIABLE
    assert item.unknown_on == ["H2"]


def test_case_is_preserved_on_case_sensitive_paths():
    """Codex-Fund 10: Globales Kleinschreiben machte /srv/Repo/X und
    /srv/repo/x gleich -- auf Linux zwei verschiedene Dateien."""
    assert normalize_locator("/srv/Repo/X") != normalize_locator("/srv/repo/x")
    # Windows-Namensraeume bleiben case-insensitiv
    assert normalize_locator(r"C:\Users\alice\A.md") == normalize_locator("C:/USERS/ALICE/a.md")


def test_unc_and_posix_paths_stay_distinct():
    """Codex-Fund 10: Das Zusammenziehen von '//' machte aus dem UNC-Pfad
    denselben String wie aus dem POSIX-Pfad -- zwei verschiedene Namensraeume."""
    backslash = chr(92)
    unc = backslash * 2 + "server" + backslash + "share" + backslash + "x"
    assert normalize_locator(unc) != normalize_locator("/server/share/x")
    assert normalize_locator(unc).startswith("unc:")


# --- Regressionen aus dem Codex-Logik-Review -------------------------------

def test_the_same_set_in_a_different_order_yields_identical_output():
    """Fund 10: build_meta sortierte die Laeufe nicht -- dieselbe MENGE in
    anderer Reihenfolge ergab einen anderen repraesentativen Titel und eine
    andere present_on-Reihenfolge. 'Deterministisch' war damit nicht
    'bitgleich', was der Idempotenz-Anspruch aber verlangt."""
    a = _run("H1", [Finding(GARDENER, "r", "Titel A")])
    b = _run("H2", [Finding(GARDENER, "r", "Titel B")])
    forward = render_markdown(build_meta([a, b], CROSS_SYSTEM), "x")
    backward = render_markdown(build_meta([b, a], CROSS_SYSTEM), "x")
    assert forward == backward


def test_full_system_refuses_to_classify():
    """Review 2, Fund 2 (kritisch): Variieren Domaene UND Auditor, ist ein
    Unterschied keiner Ursache zuzuordnen. Die fuenf Klassen sind dort nicht
    interpretierbar -- die Aggregation ist deskriptiv."""
    from system_auditor.tokens import FULL_SYSTEM

    runs = [
        _run("H1", [Finding("<HOME>/a/x.md", "drift")], domain="bundles", auditor="opus"),
        _run("H1", [Finding("<HOME>/b/y.md", "drift")], domain="skills", auditor="sonnet"),
    ]
    with pytest.raises(ValueError, match="descriptive"):
        build_meta(runs, FULL_SYSTEM)


def test_full_system_yields_an_inventory_instead():
    from system_auditor.compare import build_inventory, render_inventory
    from system_auditor.tokens import FULL_SYSTEM

    runs = [
        _run("H1", [Finding("<HOME>/a/x.md", "drift")], domain="bundles", auditor="opus"),
        _run("H1", [Finding("<HOME>/b/y.md", "drift")], domain="skills", auditor="opus"),
    ]
    result = build_inventory(runs, FULL_SYSTEM)
    assert result.participants == ["bundles / opus", "skills / opus"]
    assert result.total_findings == 2
    assert result.rule_frequency() == {"drift": 2}
    assert any("keiner Ursache zuzuordnen" in note for note in result.caveats)

    rendered = render_inventory(result, "H1")
    assert "Bestandsaufnahme" in rendered
    assert "Systemweit" not in rendered  # keine Inferenz-Ueberschriften


def test_an_incomplete_grid_is_named():
    """Zwei nur diagonal besetzte Zellen sind kein vollstaendiges Raster."""
    from system_auditor.compare import build_inventory
    from system_auditor.tokens import FULL_SYSTEM

    runs = [
        _run("H1", [], domain="bundles", auditor="opus"),
        _run("H1", [], domain="skills", auditor="sonnet"),
    ]
    result = build_inventory(runs, FULL_SYSTEM)
    assert any("Raster unvollstaendig" in note for note in result.caveats)


def test_a_controlled_system_comparison_exists():
    """Review 2, Fund 1: cross-system laesst den Auditor unkontrolliert. Fuer
    einen belegten Host-Effekt braucht es die Stufe, die das Modell festhaelt."""
    from system_auditor.tokens import CROSS_SYSTEM, CROSS_SYSTEM_RATER

    assert CROSS_SYSTEM_RATER.uncontrolled == ()
    assert CROSS_SYSTEM.uncontrolled == ("auditor",)

    runs = [
        _run("H1", [Finding(GARDENER, "drift")], auditor="opus"),
        _run("H2", [Finding(GARDENER, "drift")], auditor="opus"),
    ]
    result = build_meta(runs, CROSS_SYSTEM_RATER)
    assert result.items[0].classification == SYSTEMWIDE
    assert result.comparability.caveats == []  # nichts unkontrolliert


def test_absence_is_not_claimed_when_matching_by_rule():
    """Review 2, Fund 4: Bei Regel-Matching kann ein Teilnehmer den fremden Ort
    gar nicht abgedeckt haben -- 'geprueft, nichts gefunden' ist dort nicht
    beobachtbar."""
    runs = [
        _run("H1", [Finding("<HOME>/d1/x.md", "drift")], domain="d1", coverage=["<HOME>/d1"]),
        _run("H1", [], domain="d2", coverage=["<HOME>/d2"]),
    ]
    item = build_meta(runs, CROSS_DOMAIN).items[0]
    assert item.absent_on == []
    assert item.classification == UNVERIFIABLE
    assert any("not observable" in note for note in item.also)


def test_build_meta_refuses_a_timeseries():
    """Fable-Review: build_meta(runs, TIMESERIES) lieferte 'systemwide' ueber
    Zeitfenster -- genau der Unsinn, den timeseries.py selbst benennt: 'alle
    Fenster haben es gefunden' ist anhaltend, nicht systemweit."""
    from system_auditor.tokens import TIMESERIES

    runs = [_run("H1", [Finding(GARDENER, "drift")]), _run("H2", [Finding(GARDENER, "drift")])]
    with pytest.raises(ValueError, match="build_timeseries"):
        build_meta(runs, TIMESERIES)
