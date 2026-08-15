"""Reports: token-carrying artefacts; rotation must not depend on names or mtimes."""

from datetime import timedelta

from system_auditor.report import (
    MODE_META,
    MODE_SELF,
    ReportHeader,
    latest_report,
    list_reports,
    meta_filename,
    next_domain,
    read_report,
    write_report,
)
from system_auditor.tokens import utcnow

DOMAINS = ["modules-control", "sync-register", "control-center", "modules-memory", "bundles"]

W0810 = "20260810"
SPRINT9, SPRINT10 = "sprint-9", "sprint-10"


def _write(tmp_path, domain, system, minutes_ago=0, time_token=W0810, **kwargs):
    finished = utcnow() - timedelta(minutes=minutes_ago)
    header = ReportHeader(
        domain=domain,
        system=system,
        time_token=time_token,
        run_id=f"{system}-{domain}",
        finished_utc=finished,
        started_utc=finished - timedelta(minutes=30),
        **kwargs,
    )
    write_report(tmp_path, header, f"# {domain}\n\nbody")
    return header


def test_front_matter_roundtrip_carries_all_four_tokens(tmp_path):
    header = _write(
        tmp_path,
        "bundles",
        "ASUS-GEI",
        time_token=W0810,
        auditor="opus-5",
        next_domain="skills",
        findings=2,
        measures=["T-1", "T-2"],
        evidence_level=2,
        coverage=["<HOME>/OneDrive/.TOPICS/.AI/.BUNDLES"],
        clean=["<HOME>/OneDrive/x/AGENTS.md"],
    )
    parsed = read_report(header.path)
    assert parsed.identity.time == "20260810"
    assert parsed.identity.domain == "bundles"
    assert parsed.identity.system == "ASUS-GEI"
    assert parsed.identity.auditor == "opus-5"
    assert parsed.next_domain == "skills"
    assert parsed.measures == ["T-1", "T-2"]
    assert parsed.coverage and parsed.clean
    assert parsed.legacy is False


def test_auditor_appears_in_the_filename_so_raters_do_not_overwrite(tmp_path):
    """Without the auditor token, a second model would silently replace the
    first one's audit -- and interrater comparison would be impossible."""
    one = _write(tmp_path, "bundles", "H1", auditor="opus")
    two = _write(tmp_path, "bundles", "H1", auditor="sonnet")
    assert one.path != two.path
    assert len(list_reports(tmp_path)) == 2


def test_restating_the_same_identity_overwrites(tmp_path):
    """Same four tokens = a correction of one statement, not a second one."""
    first = _write(tmp_path, "bundles", "H1", auditor="opus", findings=1)
    second = _write(tmp_path, "bundles", "H1", auditor="opus", findings=7)
    assert first.path == second.path
    assert len(list_reports(tmp_path)) == 1
    assert read_report(second.path).findings == 7


def test_same_day_order_follows_finished_utc_not_file_name(tmp_path):
    """The measured failure of 2026-08-15: alphabetical file order was the
    reverse of the real chronology, and mtime was unreliable across the sync."""
    _write(tmp_path, "sync-register", "H1", minutes_ago=30)
    _write(tmp_path, "control-center", "H1", minutes_ago=20)
    _write(tmp_path, "modules-memory", "H1", minutes_ago=10)

    assert latest_report(tmp_path).domain == "modules-memory"
    assert next_domain(DOMAINS, tmp_path) == "bundles"


def test_rotation_is_per_system(tmp_path):
    """Several machines legitimately audit the same domain, so a foreign run
    must not push this one forward in its own cycle."""
    _write(tmp_path, "bundles", "WORKSTATION-LG", minutes_ago=5)
    _write(tmp_path, "sync-register", "ASUS-GEI", minutes_ago=60)

    assert next_domain(DOMAINS, tmp_path, system="ASUS-GEI") == "control-center"
    assert next_domain(DOMAINS, tmp_path, system="WORKSTATION-LG") == DOMAINS[0]


def test_declared_next_domain_wins(tmp_path):
    _write(tmp_path, "control-center", "H1", next_domain="bundles")
    assert next_domain(DOMAINS, tmp_path) == "bundles"


def test_empty_reports_dir_starts_at_first_domain(tmp_path):
    assert next_domain(DOMAINS, tmp_path) == DOMAINS[0]


def test_legacy_sig_tu_report_is_read_and_flagged(tmp_path):
    """Existing SIG-TU reports keep the rotation working across the changeover."""
    (tmp_path / "SIG-TU-20260812-modules-control.md").write_text(
        "# alter Bericht\n", encoding="utf-8"
    )
    parsed = list_reports(tmp_path)
    assert len(parsed) == 1
    assert parsed[0].domain == "modules-control"
    assert parsed[0].legacy is True
    assert next_domain(DOMAINS, tmp_path) == "sync-register"


def test_meta_filename_is_stable_and_hostless():
    """One artefact per aggregation and fixed key -- the author is in the
    header, not in the name, otherwise every machine would keep its own copy."""
    first = meta_filename("cross-system", ["20260810", "bundles"])
    second = meta_filename("cross-system", ["20260810", "bundles"])
    assert first == second == "META-cross-system--20260810--bundles.md"
    assert "ASUS" not in first


def test_meta_filename_omits_participant_counts():
    """Counts change whenever a participant joins. A changing name would defeat
    the overwrite rule that guarantees one current answer -- so counts live in
    the header and the title, never in the file name."""
    two = meta_filename("full-system", ["20260810", "H1"])
    three = meta_filename("full-system", ["20260810", "H1"])
    assert two == three == "META-full-system--20260810--H1.md"
    assert "2" not in two.replace("20260810", "")


def test_timeseries_filename_carries_no_period():
    """A time series spans windows by design -- it is always "as of now"."""
    name = meta_filename("timeseries", ["H1", "bundles"])
    assert name == "META-timeseries--H1--bundles.md"


def test_meta_report_overwrites_within_the_same_window(tmp_path):
    def _meta(level, participants, system):
        return write_report(
            tmp_path,
            ReportHeader(
                domain="", system=system, time_token=W0810,
                audit_mode=MODE_META, aggregation="cross-system",
                meta_level=level, participants=participants,
                scope=["20260810", "bundles"], finished_utc=utcnow(),
            ),
            "meta body",
        )

    two = _meta(2, ["H1", "H2"], "H2")
    three = _meta(3, ["H1", "H2", "H3"], "H3")
    assert two == three
    assert len(list_reports(tmp_path, audit_mode=MODE_META)) == 1
    assert read_report(three).meta_level == 3


def test_different_windows_produce_different_meta_files():
    """History keeps itself: last window is a different token, hence a
    different file. Nothing needs archiving."""
    assert meta_filename("cross-system", ["20260810", "bundles"]) != meta_filename(
        "cross-system", ["20260817", "bundles"]
    )


def test_listing_filters_by_mode(tmp_path):
    _write(tmp_path, "bundles", "H1")
    write_report(
        tmp_path,
        ReportHeader(domain="", system="H1", time_token=W0810,
                     audit_mode=MODE_META, aggregation="cross-system",
                     meta_level=2, scope=["20260810", "bundles"],
                     finished_utc=utcnow()),
        "meta",
    )
    assert len(list_reports(tmp_path, audit_mode=MODE_SELF)) == 1
    assert len(list_reports(tmp_path, audit_mode=MODE_META)) == 1
    assert len(list_reports(tmp_path)) == 2


def test_non_report_files_are_ignored(tmp_path):
    (tmp_path / "README.md").write_text("not a report", encoding="utf-8")
    assert list_reports(tmp_path) == []


def test_different_fixed_keys_never_share_a_filename():
    """The invariant needs its converse: "same key -> same name" is useless if
    different keys can also collide. Reproduced by Codex on 2026-08-15 with
    ['a-b', 'c'] against ['a', 'b-c']."""
    assert meta_filename("x", ["a-b", "c"]) != meta_filename("x", ["a", "b-c"])
    assert meta_filename("x", ["ab", "c"]) != meta_filename("x", ["a", "bc"])


def test_unicode_domain_survives_the_write_read_roundtrip(tmp_path):
    """The writer used to keep non-ASCII while the reader only accepted ASCII,
    so a report vanished from rotation right after being written."""
    header = _write(tmp_path, "münchen", "H1", auditor="opus")
    parsed = read_report(header.path)
    assert parsed is not None
    assert parsed.domain == "münchen"
    assert len(list_reports(tmp_path)) == 1


def test_a_malformed_neighbour_report_never_aborts_the_listing(tmp_path):
    """One hostile or truncated foreign file must not stop this host, exactly
    like the lock parser already behaves."""
    _write(tmp_path, "bundles", "H1")
    (tmp_path / "AUDIT-20260810--broken.H9.md").write_text(
        "---\nfindings: nope\nevidence_level: also-nope\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / "AUDIT-20260810--truncated.H8.md").write_text(
        "---\nrun_id: x\nfindings: 3\n", encoding="utf-8"  # no closing delimiter
    )
    reports = list_reports(tmp_path)
    assert len(reports) == 3
    broken = [item for item in reports if item.domain == "broken"][0]
    assert broken.findings == 0  # fell back instead of raising


def test_window_start_drives_chronology_not_the_token(tmp_path):
    """An explicit period table may use "sprint-10", which sorts before
    "sprint-9". The token is an identity, not a timestamp."""
    from system_auditor.compare import AuditRun, Finding
    from system_auditor.timeseries import build_timeseries
    from system_auditor.tokens import TIMESERIES

    early = ReportHeader(
        domain="bundles", system="H1", time_token=SPRINT9,
        window_start_utc=utcnow() - timedelta(days=14), finished_utc=utcnow(),
        coverage=["/x"],
    )
    late = ReportHeader(
        domain="bundles", system="H1", time_token=SPRINT10,
        window_start_utc=utcnow(), finished_utc=utcnow(), coverage=["/x"],
    )
    result = build_timeseries(
        [AuditRun(late, []), AuditRun(early, [Finding("/x/a.md", "drift")])],
        TIMESERIES,
    )
    assert result.windows == ["sprint-9", "sprint-10"]
    assert result.items[0].classification == "resolved"  # not "new"
