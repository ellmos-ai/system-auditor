"""Reports: the rotation anchor must not depend on file names or mtimes."""

from datetime import timedelta

from system_auditor.audit_lock import utcnow
from system_auditor.report import (
    MODE_META,
    MODE_SELF,
    ReportHeader,
    latest_report,
    list_reports,
    next_area,
    read_report,
    write_report,
)

AREAS = ["ai-modules-control", "sync-register", "control-center", "ai-modules-memory", "ai-bundles"]


def _write(tmp_path, area, host, minutes_ago=0, **kwargs):
    finished = utcnow() - timedelta(minutes=minutes_ago)
    header = ReportHeader(
        area=area,
        host=host,
        run_id=f"{host}-{area}",
        finished_utc=finished,
        started_utc=finished - timedelta(minutes=30),
        **kwargs,
    )
    write_report(tmp_path, header, f"# {area}\n\nbody")
    return header


def test_front_matter_roundtrip(tmp_path):
    header = _write(
        tmp_path,
        "ai-bundles",
        "ASUS-GEI",
        next_area="ai-skills",
        findings=2,
        measures=["T-1", "T-2"],
        evidence_level=2,
        coverage=["<HOME>/OneDrive/.TOPICS/.AI/.BUNDLES"],
        clean=["<HOME>/OneDrive/x/AGENTS.md"],
    )
    parsed = read_report(header.path)
    assert parsed.area == "ai-bundles"
    assert parsed.next_area == "ai-skills"
    assert parsed.measures == ["T-1", "T-2"]
    assert parsed.evidence_level == 2
    assert parsed.coverage and parsed.clean
    assert parsed.legacy is False


def test_same_day_order_follows_finished_utc_not_file_name(tmp_path):
    """The measured failure of 2026-08-15: alphabetical file order was the
    reverse of the real chronology (sync-register 17:19, control-center 17:26,
    ai-modules-memory 17:34), and mtime was unreliable across the sync."""
    _write(tmp_path, "sync-register", "H1", minutes_ago=30)
    _write(tmp_path, "control-center", "H1", minutes_ago=20)
    _write(tmp_path, "ai-modules-memory", "H1", minutes_ago=10)

    assert latest_report(tmp_path).area == "ai-modules-memory"
    assert next_area(AREAS, tmp_path) == "ai-bundles"


def test_next_area_prefers_declared_next(tmp_path):
    _write(tmp_path, "control-center", "H1", next_area="ai-bundles")
    assert next_area(AREAS, tmp_path) == "ai-bundles"


def test_rotation_is_per_host(tmp_path):
    """Several systems legitimately audit the same domain, so a foreign run
    must not push this host forward in its own cycle."""
    _write(tmp_path, "ai-bundles", "WORKSTATION-LG", minutes_ago=5)
    _write(tmp_path, "sync-register", "ASUS-GEI", minutes_ago=60)

    assert next_area(AREAS, tmp_path, host="ASUS-GEI") == "control-center"
    assert next_area(AREAS, tmp_path, host="WORKSTATION-LG") == AREAS[0]


def test_empty_reports_dir_starts_at_first_area(tmp_path):
    assert next_area(AREAS, tmp_path) == AREAS[0]


def test_legacy_sig_tu_report_is_read_and_flagged(tmp_path):
    """Existing SIG-TU reports must keep the rotation working across the
    changeover -- they have no host token and no front matter."""
    (tmp_path / "SIG-TU-20260812-ai-modules-control.md").write_text(
        "# alter Bericht\n", encoding="utf-8"
    )
    parsed = list_reports(tmp_path)
    assert len(parsed) == 1
    assert parsed[0].area == "ai-modules-control"
    assert parsed[0].legacy is True
    assert next_area(AREAS, tmp_path) == "sync-register"


def test_meta_report_filename_carries_level(tmp_path):
    header = ReportHeader(
        area="ai-bundles",
        host="ASUS-GEI",
        audit_mode=MODE_META,
        meta_level=3,
        inputs=["a", "b", "c"],
        finished_utc=utcnow(),
    )
    path = write_report(tmp_path, header, "meta body")
    assert path.name.startswith("META-3-")

    parsed = read_report(path)
    assert parsed.audit_mode == MODE_META
    assert parsed.meta_level == 3
    assert parsed.inputs == ["a", "b", "c"]


def test_listing_filters_by_mode(tmp_path):
    _write(tmp_path, "ai-bundles", "H1")
    write_report(
        tmp_path,
        ReportHeader(area="ai-bundles", host="H1", audit_mode=MODE_META,
                     meta_level=2, finished_utc=utcnow()),
        "meta",
    )
    assert len(list_reports(tmp_path, audit_mode=MODE_SELF)) == 1
    assert len(list_reports(tmp_path, audit_mode=MODE_META)) == 1
    assert len(list_reports(tmp_path)) == 2


def test_validity_window(tmp_path):
    header = _write(tmp_path, "ai-bundles", "H1", minutes_ago=60 * 24 * 20)
    assert header.is_valid(validity="30d") is True
    assert header.is_valid(validity="14d") is False


def test_non_report_files_are_ignored(tmp_path):
    (tmp_path / "README.md").write_text("not a report", encoding="utf-8")
    assert list_reports(tmp_path) == []
