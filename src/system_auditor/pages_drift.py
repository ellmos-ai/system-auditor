"""Deterministischer Katalog-gegen-Pages-Vergleich für die Domäne pages-drift."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


class PagesDriftError(ValueError):
    """Die Domäne konnte nicht vollständig und belastbar gelesen werden."""


@dataclass
class PagesDriftResult:
    expected_counts: dict[str, int]
    site_counts: dict[str, int | None]
    expected_public_module_ids: list[str]
    site_module_ids: list[str]
    released_bundle_ids: list[str]
    findings: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {
            "domain": "pages-drift",
            "ok": self.ok,
            "expected_counts": self.expected_counts,
            "site_counts": self.site_counts,
            "expected_public_module_ids": self.expected_public_module_ids,
            "site_module_ids": self.site_module_ids,
            "released_bundle_ids": self.released_bundle_ids,
            "findings": self.findings,
        }


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PagesDriftError(f"JSON nicht lesbar: {path} ({exc.__class__.__name__})") from exc
    if not isinstance(value, dict):
        raise PagesDriftError(f"JSON-Wurzel ist kein Objekt: {path}")
    return value


def _required_list(data: dict, key: str, path: Path) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise PagesDriftError(f"{path} enthält kein {key}[]")
    return value


def _json_array_after(text: str, prefix: str, path: Path) -> list:
    start = text.find(prefix)
    if start < 0:
        raise PagesDriftError(f"Datenblock {prefix!r} fehlt in {path}")
    tail = text[start + len(prefix) :].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise PagesDriftError(f"Datenblock {prefix!r} ist ungültig in {path}") from exc
    if not isinstance(value, list):
        raise PagesDriftError(f"Datenblock {prefix!r} ist keine Liste in {path}")
    return value


def _const_segment(text: str, name: str, path: Path) -> str:
    marker = f"const {name} = ["
    start = text.find(marker)
    if start < 0:
        raise PagesDriftError(f"{marker!r} fehlt in {path}")
    end = text.find("\n];", start)
    if end < 0:
        raise PagesDriftError(f"Ende von const {name} fehlt in {path}")
    return text[start : end + 3]


def _layer_count(index: str, layer_id: str, path: Path) -> int | None:
    layers = _const_segment(index, "LAYERS", path)
    start = layers.find(f'{{id:"{layer_id}"')
    if start < 0:
        return None
    candidates = [
        position
        for position in (layers.find("\n {id:", start + 1), layers.find("\n];", start + 1))
        if position >= 0
    ]
    end = min(candidates) if candidates else len(layers)
    block = layers[start:end]
    summary = re.search(r"s:\{(.*?)\}", block, flags=re.DOTALL)
    if not summary:
        return None
    number = re.search(r"\d+", summary.group(1))
    return int(number.group()) if number else None


def _projected_public_ids(modules: list[dict]) -> list[str]:
    return sorted(
        str(module.get("display_name") or module.get("id"))
        for module in modules
        if module.get("visibility") == "public"
    )


def _normalise_ref(component: dict) -> tuple[str, str] | None:
    kind = component.get("t") or component.get("type")
    ref = component.get("ref") or component.get("id")
    if isinstance(ref, dict):
        ref = ref.get("ref")
    if not isinstance(ref, str):
        return None
    if ":" in ref:
        prefix, identifier = ref.split(":", 1)
        kind = kind or prefix
    else:
        identifier = ref
    return str(kind or ""), identifier


def audit_pages_drift(
    modules_catalog: Path,
    skills_registry: Path,
    bundles_catalog: Path,
    site_dir: Path,
) -> PagesDriftResult:
    modules = _required_list(_read_json(modules_catalog), "modules", modules_catalog)
    skills = _required_list(_read_json(skills_registry), "components", skills_registry)
    bundles = _required_list(_read_json(bundles_catalog), "bundles", bundles_catalog)

    index_path = site_dir / "index.html"
    skills_path = site_dir / "skills.html"
    bundles_path = site_dir / "bundles.html"
    try:
        index = index_path.read_text(encoding="utf-8")
        skills_html = skills_path.read_text(encoding="utf-8")
        bundles_html = bundles_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PagesDriftError(f"Site-Artefakt nicht lesbar: {exc}") from exc

    module_segment = _const_segment(index, "MODULES", index_path)
    site_module_ids = sorted(re.findall(r'\{id:"([^"]+)"', module_segment))
    site_skills = _json_array_after(skills_html, "const SKILLS=", skills_path)
    site_bundles = _json_array_after(bundles_html, "const BUNDLES=", bundles_path)

    expected_counts = {
        "modules": len(modules),
        "skills": len(skills),
        "bundles": len(bundles),
    }
    site_counts = {
        "modules": _layer_count(index, "modules", index_path),
        "skills": _layer_count(index, "skills", index_path),
        "bundles": _layer_count(index, "bundles", index_path),
        "skills_page": len(site_skills),
        "released_bundles_page": len(site_bundles),
    }
    expected_public = _projected_public_ids(modules)
    released_ids = sorted(
        str(bundle.get("id")) for bundle in site_bundles if isinstance(bundle, dict)
    )
    result = PagesDriftResult(
        expected_counts=expected_counts,
        site_counts=site_counts,
        expected_public_module_ids=expected_public,
        site_module_ids=site_module_ids,
        released_bundle_ids=released_ids,
    )

    for name in ("modules", "skills", "bundles"):
        if site_counts[name] != expected_counts[name]:
            result.findings.append(
                {
                    "rule": "PAGES-COUNT-PARITY",
                    "subject": name,
                    "expected": expected_counts[name],
                    "actual": site_counts[name],
                }
            )
    if site_counts["skills_page"] != expected_counts["skills"]:
        result.findings.append(
            {
                "rule": "PAGES-SKILL-REGISTRY-PARITY",
                "expected": expected_counts["skills"],
                "actual": site_counts["skills_page"],
            }
        )

    missing = sorted(set(expected_public) - set(site_module_ids))
    extra = sorted(set(site_module_ids) - set(expected_public))
    if missing or extra:
        result.findings.append(
            {
                "rule": "PAGES-PUBLIC-MODULE-ID-PARITY",
                "missing": missing,
                "extra": extra,
            }
        )

    catalog_bundle_ids = {str(bundle.get("id")) for bundle in bundles if bundle.get("id")}
    unknown_releases = sorted(set(released_ids) - catalog_bundle_ids)
    if unknown_releases:
        result.findings.append(
            {
                "rule": "PAGES-RELEASED-BUNDLE-RESOLVES",
                "unknown_bundle_ids": unknown_releases,
            }
        )

    modules_by_id = {str(module.get("id")): module for module in modules if module.get("id")}
    for recipe in site_bundles:
        if not isinstance(recipe, dict):
            continue
        recipe_id = str(recipe.get("id") or "(ohne-id)")
        components = recipe.get("comps") or recipe.get("components") or []
        for component in components:
            if not isinstance(component, dict):
                continue
            normalised = _normalise_ref(component)
            if not normalised:
                continue
            kind, module_id = normalised
            if kind != "module":
                continue
            module = modules_by_id.get(module_id)
            if module is None:
                result.findings.append(
                    {
                        "rule": "PAGES-RECIPE-MODULE-RESOLVES",
                        "recipe": recipe_id,
                        "module": module_id,
                    }
                )
            elif module.get("visibility") != "public":
                result.findings.append(
                    {
                        "rule": "PAGES-RELEASED-RECIPE-PUBLIC-MODULE",
                        "recipe": recipe_id,
                        "module": module_id,
                        "visibility": module.get("visibility"),
                    }
                )
    return result
