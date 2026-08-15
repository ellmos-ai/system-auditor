"""Templates -- the model-manual path must speak the parser's language.

The meta step is model-manual by design: auditors write their own reports and,
on discovering foreign reports for the same domain and window, write the meta
report themselves as their interpretation. The templates are the contract for
that -- so their front matter must parse with the very reader the tooling uses,
or the manual path produces reports the machinery cannot see.
"""
from pathlib import Path

from system_auditor.report import parse_front_matter

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def test_audit_template_front_matter_parses():
    data = parse_front_matter((TEMPLATES / "AUDIT-BERICHT.de.md").read_text(encoding="utf-8"))
    for key in ("run_id", "audit_mode", "time_token", "domain", "system", "auditor",
                "window_start_utc", "coverage", "clean", "evidence_level", "findings_detail"):
        assert key in data, f"template lost the {key} field"
    assert data["audit_mode"] == "self"
    # findings_detail is a `- item` block: one line per finding, model-readable.
    assert isinstance(data["findings_detail"], list) and data["findings_detail"]


def test_meta_template_front_matter_parses():
    data = parse_front_matter((TEMPLATES / "META-BERICHT.de.md").read_text(encoding="utf-8"))
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
