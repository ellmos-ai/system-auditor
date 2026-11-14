"""Templates -- the model-manual path must speak the parser's language.

The meta step is model-manual by design: auditors write their own reports and,
on discovering foreign reports for the same domain and window, write the meta
report themselves as their interpretation. The templates are the contract for
that -- so their front matter must parse with the very reader the tooling uses,
or the manual path produces reports the machinery cannot see.
"""
from pathlib import Path

import pytest

from system_auditor.report import parse_front_matter

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


@pytest.mark.parametrize("name", ["AUDIT-BERICHT.de.md", "AUDIT-REPORT.en.md"])
def test_audit_template_front_matter_parses(name):
    data = parse_front_matter((TEMPLATES / name).read_text(encoding="utf-8"))
    for key in ("run_id", "audit_mode", "time_token", "domain", "system", "auditor",
                "window_start_utc", "coverage", "clean", "evidence_level", "self_check",
                "onedrive", "findings_detail"):
        assert key in data, f"template lost the {key} field"
    assert data["audit_mode"] == "self"
    # findings_detail is a `- item` block: one line per finding, model-readable.
    assert isinstance(data["findings_detail"], list) and data["findings_detail"]


@pytest.mark.parametrize("name", ["AUDIT-BERICHT.de.md", "AUDIT-REPORT.en.md"])
def test_a_report_written_by_the_library_carries_every_template_field(name, tmp_path):
    """One schema, checked from the writer's side (T-20261114-257609608).

    The test above only guards the template. The library writer had drifted away
    from it: `write_report` could not emit `findings_detail` or `onedrive`, so a
    report it produced was never template-conformant. A fully populated header
    must now round-trip every key the template demands.
    """
    from datetime import datetime, timezone

    from system_auditor.report import ReportHeader, read_report, write_report

    template_keys = set(parse_front_matter((TEMPLATES / name).read_text(encoding="utf-8")))
    ts = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    header = ReportHeader(
        domain="control-integration", system="WORKSTATION-LG", time_token="20261109",
        auditor="claude-opus-5-5", run_id="r1", started_utc=ts, finished_utc=ts,
        window_start_utc=ts, next_domain="bundles", findings=2, measures=["M-1"],
        coverage=["<HOME>/x"], clean=["<HOME>/y"], self_check="current", onedrive="on",
        findings_detail=["C:/a/b.json | I7 | dead optional, names", "C:/c | K4 | split"],
    )
    path = write_report(tmp_path, header, "# body")
    written = parse_front_matter(path.read_text(encoding="utf-8"))
    assert template_keys <= set(written), f"writer lacks {sorted(template_keys - set(written))}"
    parsed = read_report(path)
    assert parsed.findings_detail == header.findings_detail, "a comma must not split a finding"
    assert parsed.onedrive == "on"


@pytest.mark.parametrize("name", ["META-BERICHT.de.md", "META-REPORT.en.md"])
def test_meta_template_front_matter_parses(name):
    data = parse_front_matter((TEMPLATES / name).read_text(encoding="utf-8"))
    for key in ("aggregation", "meta_level", "participants", "inputs", "scope"):
        assert key in data, f"template lost the {key} field"
    assert data["audit_mode"] == "meta"


def test_shipped_example_points_reports_at_a_shared_folder():
    """The meeting point: a host-local default structurally prevents meta
    audits, because no second machine ever writes there."""
    import json

    example = Path(__file__).resolve().parents[1] / "config/system-auditor.config.example.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    from system_auditor.config import _looks_shared

    assert _looks_shared(raw["reports_dir"])
