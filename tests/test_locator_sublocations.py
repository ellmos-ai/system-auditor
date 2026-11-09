"""Fragment- und Zeilen-Locators gehoeren zur Datei (T-20261101-652385135, Muster P4).

Belegter Fall: Ein Auditor fuehrt ``datei.json`` als ``clean``, der Partner meldet einen Fund an
``datei.json#pillars.omissions``. ``declares_clean`` und ``_is_under`` kannten nur exakte Pfade
bzw. ``/``-Grenzen, der Widerspruch landete deshalb als ``unverifiable`` statt als ``inverse``.
"""
from system_auditor.compare import (
    HOST_SPECIFIC,
    INVERSE,
    UNVERIFIABLE,
    AuditRun,
    Finding,
    build_meta,
    normalize_locator,
)
from system_auditor.report import ReportHeader
from system_auditor.tokens import CROSS_SYSTEM, utcnow

CATALOG = "<HOME>/OneDrive/.BUNDLES/bundles.catalog.v1.json"


def _run(system, findings=(), coverage=(), clean=()):
    header = ReportHeader(
        domain="bundles", system=system, auditor="opus", time_token="20260810",
        run_id=f"{system}-run", finished_utc=utcnow(),
        coverage=list(coverage), clean=list(clean),
    )
    return AuditRun(header, list(findings))


def _only_item(*runs):
    result = build_meta(list(runs), CROSS_SYSTEM)
    assert len(result.items) == 1
    return result.items[0]


def test_clean_file_contradicts_a_finding_at_a_fragment_of_that_file():
    """Der belegte Fall: der Widerspruch muss als inverse sichtbar werden."""
    finder = _run("H1", [Finding(f"{CATALOG}#pillars.omissions", "omission")], coverage=[CATALOG])
    denier = _run("H2", coverage=[CATALOG], clean=[CATALOG])

    item = _only_item(finder, denier)

    assert item.classification == INVERSE
    assert item.clean_on == ["H2"]


def test_a_json_pointer_fragment_belongs_to_its_file_too():
    """Nach dem ersten ``#`` ist alles Unterort, auch wenn ``/`` folgt."""
    finder = _run("H1", [Finding(f"{CATALOG}#/pillars/omissions", "omission")], coverage=[CATALOG])
    denier = _run("H2", coverage=[CATALOG], clean=[CATALOG])

    assert _only_item(finder, denier).classification == INVERSE


def test_clean_file_contradicts_a_finding_at_a_line_of_that_file():
    finder = _run("H1", [Finding(f"{CATALOG}:42", "omission")], coverage=[CATALOG])
    denier = _run("H2", coverage=[CATALOG], clean=[CATALOG])

    assert _only_item(finder, denier).classification == INVERSE


def test_a_line_range_counts_as_a_sublocation_too():
    finder = _run("H1", [Finding(f"{CATALOG}:42-57", "omission")], coverage=[CATALOG])
    denier = _run("H2", coverage=[CATALOG], clean=[CATALOG])

    assert _only_item(finder, denier).classification == INVERSE


def test_coverage_of_a_file_covers_its_fragments_and_lines():
    """Ohne das gilt "geprueft, nichts gefunden" faelschlich als "nie geschaut"."""
    finder = _run("H1", [Finding(f"{CATALOG}#pillars.omissions", "omission")], coverage=[CATALOG])
    looked = _run("H2", coverage=[CATALOG])

    item = _only_item(finder, looked)

    assert item.classification == HOST_SPECIFIC
    assert item.absent_on == ["H2"]


def test_coverage_of_a_directory_covers_a_fragment_of_a_file_below_it():
    finder = _run("H1", [Finding(f"{CATALOG}#pillars", "omission")], coverage=[CATALOG])
    looked = _run("H2", coverage=["<HOME>/OneDrive/.BUNDLES"])

    assert _only_item(finder, looked).classification == HOST_SPECIFIC


def test_a_fragment_is_not_a_path_prefix():
    """Die Segmentgrenze bleibt: foo.json deckt weder foo.json.bak noch foo.jsonl ab."""
    finder = _run("H1", [Finding(f"{CATALOG}.bak#x", "omission")], coverage=[CATALOG])
    other = _run("H2", coverage=[CATALOG], clean=[CATALOG])

    item = _only_item(finder, other)

    assert item.classification == UNVERIFIABLE
    assert item.clean_on == []


def test_clean_on_one_fragment_does_not_clear_another_fragment():
    finder = _run("H1", [Finding(f"{CATALOG}#pillars.b", "omission")], coverage=[CATALOG])
    other = _run("H2", coverage=[CATALOG], clean=[f"{CATALOG}#pillars.a"])

    item = _only_item(finder, other)

    assert item.classification != INVERSE
    assert item.clean_on == []


def test_clean_on_the_exact_fragment_still_clears_it():
    finder = _run("H1", [Finding(f"{CATALOG}#pillars.a", "omission")], coverage=[CATALOG])
    other = _run("H2", coverage=[CATALOG], clean=[f"{CATALOG}#pillars.a"])

    assert _only_item(finder, other).classification == INVERSE


def test_a_finding_on_the_whole_file_is_not_cleared_by_a_clean_fragment():
    finder = _run("H1", [Finding(CATALOG, "omission")], coverage=[CATALOG])
    other = _run("H2", coverage=[CATALOG], clean=[f"{CATALOG}#pillars.a"])

    assert _only_item(finder, other).classification != INVERSE


def test_a_windows_drive_letter_is_not_mistaken_for_a_line_suffix():
    finder = _run("H1", [Finding(r"C:\data\x.json", "omission")], coverage=[r"C:\data"])
    looked = _run("H2", coverage=[r"C:\data"], clean=[r"C:\data\x.json"])

    assert _only_item(finder, looked).classification == INVERSE


def test_distinct_fragments_stay_distinct_locators():
    assert normalize_locator("a.json#x") != normalize_locator("a.json#y")
    assert normalize_locator("a.json:1") != normalize_locator("a.json:2")


def test_hash_in_directory_name_is_not_treated_as_fragment():
    finder = _run("H1", [Finding("/repo/c#/file.py", "omission")], coverage=["/repo/c#"])
    looked = _run("H2", coverage=["/repo/c"])

    item = _only_item(finder, looked)
    assert item.classification == UNVERIFIABLE
    assert item.absent_on == []

    # But # in the basename after the last / IS treated as fragment
    finder_sub = _run(
        "H1", [Finding("/repo/c#/file.py#section", "omission")], coverage=["/repo/c#"]
    )
    looked_sub = _run("H2", coverage=["/repo/c#"])
    item_sub = _only_item(finder_sub, looked_sub)
    assert item_sub.classification == HOST_SPECIFIC
    assert item_sub.absent_on == ["H2"]


def test_host_port_is_not_stripped_as_line_number():
    finder = _run("H1", [Finding("server:80", "down")], coverage=["server:80"])
    looked = _run("H2", coverage=["server"])

    item = _only_item(finder, looked)
    assert item.classification == UNVERIFIABLE
    assert item.absent_on == []

    # But file with extension or slash DOES strip line number
    finder_file = _run("H1", [Finding("file.py:80", "error")], coverage=["file.py"])
    looked_file = _run("H2", coverage=["file.py"])
    item_file = _only_item(finder_file, looked_file)
    assert item_file.classification == HOST_SPECIFIC
    assert item_file.absent_on == ["H2"]

    finder_path = _run("H1", [Finding("dir/server:80", "error")], coverage=["dir/server"])
    looked_path = _run("H2", coverage=["dir/server"])
    item_path = _only_item(finder_path, looked_path)
    assert item_path.classification == HOST_SPECIFIC
    assert item_path.absent_on == ["H2"]

