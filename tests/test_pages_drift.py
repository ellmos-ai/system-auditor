import json

from system_auditor.pages_drift import audit_pages_drift


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixture(tmp_path, *, private_recipe=False, site_bundle_count=1):
    modules = [
        {"id": "public-a", "display_name": "Public A", "visibility": "public"},
        {"id": "private-b", "display_name": "Private B", "visibility": "private"},
    ]
    skills = [{"id": "one"}, {"id": "two"}]
    bundles = [{"id": "released-one"}]
    site = tmp_path / "site"
    site.mkdir()
    site.joinpath("index.html").write_text(
        """const MODULES = [
 {id:"Public A",vis:"pub",d:{de:"x",en:"x"}}
];
const LAYERS = [
 {id:"skills",s:{de:"2 Skills",en:"2 skills"}},
 {id:"modules",s:{de:"2 Module",en:"2 modules"}},
 {id:"bundles",s:{de:"1 Rezept",en:"1 recipe"}}
];
""",
        encoding="utf-8",
    )
    site.joinpath("skills.html").write_text(
        'const SKILLS=[{"id":"one"},{"id":"two"}];', encoding="utf-8"
    )
    module_ref = "private-b" if private_recipe else "public-a"
    site.joinpath("bundles.html").write_text(
        "const BUNDLES="
        + json.dumps(
            [
                {
                    "id": "released-one",
                    "comps": [{"t": "module", "ref": f"module:{module_ref}"}],
                }
            ]
        )
        + ";",
        encoding="utf-8",
    )
    return (
        _write_json(tmp_path / "modules.json", {"modules": modules}),
        _write_json(tmp_path / "skills.json", {"components": skills}),
        _write_json(tmp_path / "bundles.json", {"bundles": bundles}),
        site,
    )


def test_pages_drift_clean_fixture(tmp_path):
    result = audit_pages_drift(*_fixture(tmp_path))
    assert result.ok
    assert result.findings == []


def test_pages_drift_detects_count_and_module_id_drift(tmp_path):
    paths = _fixture(tmp_path)
    index = paths[3] / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8")
        .replace('id:"Public A"', 'id:"Unknown"')
        .replace('de:"2 Skills"', 'de:"9 Skills"'),
        encoding="utf-8",
    )

    result = audit_pages_drift(*paths)
    rules = {finding["rule"] for finding in result.findings}
    assert "PAGES-COUNT-PARITY" in rules
    assert "PAGES-PUBLIC-MODULE-ID-PARITY" in rules


def test_released_recipe_must_not_reference_private_module(tmp_path):
    result = audit_pages_drift(*_fixture(tmp_path, private_recipe=True))
    finding = next(
        item
        for item in result.findings
        if item["rule"] == "PAGES-RELEASED-RECIPE-PUBLIC-MODULE"
    )
    assert finding == {
        "rule": "PAGES-RELEASED-RECIPE-PUBLIC-MODULE",
        "recipe": "released-one",
        "module": "private-b",
        "visibility": "private",
    }
