"""Unlesbare Berichte gehen nicht still verloren (T-20261101-652385135, Muster P4).

Auf WORKSTATION-LG lieferten am 2026-11-01 zwei Dateien im geteilten reports_dir beim Lesen
``OSError: [Errno 22]`` (OneDrive-Online-Platzhalter). ``read_report`` gab dann ``None``,
``list_reports`` ueberging die Datei lautlos, und Rotation, Meta-Plan und Schreibschutz hielten
den Bericht fuer nicht vorhanden. "Nicht befragt" ist aber kein "nichts gefunden": solche
Dateien muessen als ``unavailable`` benannt werden.
"""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from system_auditor import cli
from system_auditor.meta import (
    ACTION_BLOCKED,
    ACTION_CREATE,
    plan_all,
    plan_metas,
    write_meta,
)
from system_auditor.report import (
    MODE_META,
    ReportHeader,
    UnreadableReport,
    latest_report,
    list_reports,
    next_domain,
    write_report,
)
from system_auditor.tokens import utcnow

DOMAINS = ["modules-control", "sync-register", "control-center", "bundles"]
WINDOW = "20260810"
DOMAIN = "bundles"


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    cli._CONFIG_CACHE.clear()
    yield
    cli._CONFIG_CACHE.clear()


def _single(tmp_path, system, domain=DOMAIN, minutes_ago=0, run_id=None):
    header = ReportHeader(
        domain=domain, system=system, auditor="opus", time_token=WINDOW,
        run_id=run_id or f"{system}-{domain}",
        finished_utc=utcnow() - timedelta(minutes=minutes_ago),
    )
    return header, write_report(tmp_path, header, "body")


def _meta_header(inputs, level=2):
    return ReportHeader(
        domain="", system="H1", time_token=WINDOW, audit_mode=MODE_META,
        aggregation="cross-system", meta_level=level, inputs=inputs,
        scope=[WINDOW, DOMAIN], finished_utc=utcnow(),
    )


def make_unreadable(monkeypatch, *names):
    """Reading these files fails the way an OneDrive online-only placeholder does."""
    real = Path.read_text

    def fake(self, *args, **kwargs):
        if self.name in names:
            raise OSError(22, "Invalid argument")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake)


# --- report.py ---------------------------------------------------------------------------------

def test_list_reports_hands_back_the_unreadable_audit_files(tmp_path, monkeypatch):
    _, ok = _single(tmp_path, "H1")
    _, broken = _single(tmp_path, "H2")
    make_unreadable(monkeypatch, broken.name)
    bag: list[UnreadableReport] = []

    reports = list_reports(tmp_path, unreadable=bag)

    assert [item.path.name for item in reports] == [ok.name]
    assert [item.path.name for item in bag] == [broken.name]
    assert "Invalid argument" in bag[0].reason


def test_list_reports_without_the_new_argument_behaves_as_before(tmp_path, monkeypatch):
    _, ok = _single(tmp_path, "H1")
    _, broken = _single(tmp_path, "H2")
    make_unreadable(monkeypatch, broken.name)

    assert [item.path.name for item in list_reports(tmp_path)] == [ok.name]


def test_files_that_are_not_audits_are_never_reported_as_unreadable(tmp_path, monkeypatch):
    _single(tmp_path, "H1")
    (tmp_path / "README.md").write_text("not an audit", encoding="utf-8")
    make_unreadable(monkeypatch, "README.md")
    bag: list[UnreadableReport] = []

    list_reports(tmp_path, unreadable=bag)

    assert bag == []


def test_a_stat_error_on_one_file_neither_crashes_nor_hides_it(tmp_path, monkeypatch):
    """Errno 22 kann schon beim Stat auftreten; das darf list_reports nicht abbrechen."""
    _, ok = _single(tmp_path, "H1")
    _, broken = _single(tmp_path, "H2")
    real = Path.is_file

    def fake(self, *args, **kwargs):
        if self.name == broken.name:
            raise OSError(22, "Invalid argument")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", fake)
    bag: list[UnreadableReport] = []

    assert [item.path.name for item in list_reports(tmp_path, unreadable=bag)] == [ok.name]
    assert [item.path.name for item in bag] == [broken.name]


def test_the_audit_mode_filter_applies_to_unreadable_files_too(tmp_path, monkeypatch):
    _, own = _single(tmp_path, "H1")
    meta_path = write_report(tmp_path, _meta_header(["r1", "r2"]), "meta")
    make_unreadable(monkeypatch, own.name, meta_path.name)
    own_bag: list[UnreadableReport] = []
    meta_bag: list[UnreadableReport] = []

    list_reports(tmp_path, audit_mode="self", unreadable=own_bag)
    list_reports(tmp_path, audit_mode=MODE_META, unreadable=meta_bag)

    assert [item.path.name for item in own_bag] == [own.name]
    assert [item.path.name for item in meta_bag] == [meta_path.name]


def test_next_domain_names_the_unreadable_own_report_it_could_not_anchor_on(tmp_path, monkeypatch):
    _, anchor = _single(tmp_path, "H1", domain="sync-register")
    make_unreadable(monkeypatch, anchor.name)
    bag: list[UnreadableReport] = []

    chosen = next_domain(DOMAINS, tmp_path, system="H1", unreadable=bag)

    assert chosen == DOMAINS[0]  # the fallback stays, but it is no longer silent
    assert [item.path.name for item in bag] == [anchor.name]
    assert latest_report(tmp_path, system="H1") is None


# --- meta.py ------------------------------------------------------------------------------------

def test_plan_all_names_the_unreadable_audit_and_still_plans_the_rest(tmp_path, monkeypatch):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")
    _, broken = _single(tmp_path, "H3")
    make_unreadable(monkeypatch, broken.name)
    bag: list[UnreadableReport] = []

    plans = plan_all(tmp_path, time_token=WINDOW, unreadable=bag)

    assert [plan.action for plan in plans] == [ACTION_CREATE]
    assert plans[0].participants == ["H1", "H2"]
    assert [item.path.name for item in bag] == [broken.name]


def test_an_unreadable_existing_meta_blocks_the_plan_instead_of_pretending_it_is_new(
    tmp_path, monkeypatch
):
    _single(tmp_path, "H1", run_id="r1")
    _single(tmp_path, "H2", run_id="r2")
    existing = write_report(tmp_path, _meta_header(["r1", "r2"]), "meta")
    make_unreadable(monkeypatch, existing.name)
    bag: list[UnreadableReport] = []

    plan = plan_metas(tmp_path, time_token=WINDOW, unreadable=bag)[0]

    assert plan.action == ACTION_BLOCKED
    assert plan.should_write is False
    assert "unavailable" in plan.reason
    assert plan.target == existing.name
    assert [item.path.name for item in bag] == [existing.name]


def test_write_meta_refuses_to_overwrite_an_unreadable_artefact(tmp_path, monkeypatch):
    first = write_meta(tmp_path, _meta_header(["r1", "r2", "r3", "r4"], level=4), "newer meta")
    assert first.written
    before = first.path.read_bytes()
    make_unreadable(monkeypatch, first.path.name)

    outcome = write_meta(tmp_path, _meta_header(["r1", "r2"]), "older meta")

    assert outcome.written is False
    assert "unavailable" in outcome.reason
    assert first.path.read_bytes() == before


def test_write_meta_still_creates_a_missing_artefact(tmp_path):
    outcome = write_meta(tmp_path, _meta_header(["r1", "r2"]), "meta")
    assert outcome.written


# --- cli.py -------------------------------------------------------------------------------------

def test_cli_next_domain_lists_unavailable_reports(tmp_path, monkeypatch, capsys):
    _, anchor = _single(tmp_path, "H1", domain="sync-register")
    make_unreadable(monkeypatch, anchor.name)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"system": "H1"}), encoding="utf-8")

    code = cli.main(["--json", "--config", str(config), "next-domain", "--reports", str(tmp_path),
                     "--domains", ",".join(DOMAINS), "--system", "H1"])

    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["domain"] == DOMAINS[0]
    assert any(anchor.name in item for item in payload["unavailable"])
    assert "unavailable" in captured.err


def test_cli_meta_plan_lists_unavailable_reports_and_keeps_planning(tmp_path, monkeypatch, capsys):
    _single(tmp_path, "H1")
    _single(tmp_path, "H2")
    _, broken = _single(tmp_path, "H3")
    make_unreadable(monkeypatch, broken.name)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"system": "H1"}), encoding="utf-8")

    code = cli.main(["--json", "--config", str(config), "meta-plan", "--reports", str(tmp_path),
                     "--time-token", WINDOW])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["bundles"] == 1
    assert any(broken.name in item for item in payload["unavailable"])


def test_cli_reports_does_not_count_an_unreadable_file_as_absent(tmp_path, monkeypatch, capsys):
    _, ok = _single(tmp_path, "H1")
    _, broken = _single(tmp_path, "H2")
    make_unreadable(monkeypatch, broken.name)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"system": "H1"}), encoding="utf-8")

    code = cli.main(["--json", "--config", str(config), "reports", "--reports", str(tmp_path)])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["count"] == 1
    assert any(broken.name in item for item in payload["unavailable"])


def test_cli_without_unreadable_reports_has_no_unavailable_noise(tmp_path, capsys):
    _single(tmp_path, "H1")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"system": "H1"}), encoding="utf-8")

    code = cli.main(["--json", "--config", str(config), "next-domain", "--reports", str(tmp_path),
                     "--domains", ",".join(DOMAINS), "--system", "H1"])

    captured = capsys.readouterr()
    assert code == 0
    assert "unavailable" not in json.loads(captured.out)
    assert "unavailable" not in captured.err
