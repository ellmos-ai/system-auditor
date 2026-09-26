# Third-Party Licenses & Software Inventory

> **Project:** `ellmos-ai/system-auditor` (Evidence-based system audits across machines with meta-audit bundling)<br>
> **Audited:** 2026-09-26 (Pfad B Re-Audit)<br>
> **Repository License:** [MIT License](LICENSE) | [Attribution Notice](NOTICE)<br>
> **Architecture & Privacy:** 100% Local-First, Zero-Egress, Unprivileged User-Mode (`RunAsInvoker`)

---

## Executive Summary & Compliance Assurance

`system-auditor` is engineered from the ground up as a **100% local-first, zero-egress, zero-external-dependency** system audit and meta-bundling engine.
It operates under the unprivileged `RunAsInvoker` security posture and guarantees 0% copyleft contamination at runtime.

### Zero-Runtime-Dependency Guarantee

| Package | Version Spec | License | Type | Purpose |
|---------|-------------|---------|------|---------|
| *None* | `n/a` | `n/a` | External | `system-auditor` has **0** external runtime dependencies (`dependencies = []` in `pyproject.toml`). |
| *Python Standard Library* | `>=3.10` | PSF License | Built-in | `argparse`, `dataclasses`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `re`, `sys`, `typing` |

All network access, telemetry, remote logging, and privileged operations are strictly prohibited by design.

---

## Level 1 SBOM & Governance Invariant Cross-Reference Matrix

`system-auditor` affirms, implements, and certifies ten core governance and runtime invariants:

| Invariant | Category | Description | Verification Method | Status |
|---|---|---|---|---|
| `INV-LOCAL-01` | Local-First & Zero-Egress | 100% offline-ready; audit generation, aggregation, and report persistence reside strictly on local disk with zero external network egress. | `tests/test_metadata.py` (`test_offline_and_zero_egress_invariants`) | VERIFIED |
| `INV-UNPRIV-02` | Unprivileged Non-Elevation | Strict `RunAsInvoker` user-mode execution; zero administrator, root elevation, or UAC prompts required. | `SECURITY.md` & `pyproject.toml` | VERIFIED |
| `INV-DETERM-03` | Deterministic Classification | Identical inputs produce bit-for-bit identical multi-host audit verdicts and canonical findings sorting. | `system_auditor.meta` & `tests/test_meta.py` | VERIFIED |
| `INV-IDENT-04` | Identifiability Guard | Invariant that aggregations with >1 varying dimension cannot emit causal verdicts (enforced in constructor). | `system_auditor.tokens` & `tests/test_tokens.py` | VERIFIED |
| `INV-RACE-05` | Write-Guard Race Protection | Safe concurrent runs across machines without centralized lock daemons; skips overwrite if disk has superset. | `system_auditor.report` & `tests/test_report.py` | VERIFIED |
| `INV-WINDOW-06` | Discrete Window Tokens | Deterministic temporal alignment without distributed consensus protocols via config-driven calendar grid. | `system_auditor.tokens` & `tests/test_tokens.py` | VERIFIED |
| `INV-SINGLE-07` | One Current Answer Per Window | Single authoritative multi-host answer per window; historical versions preserve themselves via window tokens. | `system_auditor.meta` & `tests/test_meta.py` | VERIFIED |
| `INV-COVER-08` | Coverage Transparency Floor | Honest absence-of-proof prevents uninspected paths from masquerading as divergence (`unverifiable` tier). | `system_auditor.compare` & `tests/test_compare.py` | VERIFIED |
| `INV-LOCK-09` | Multi-Host & Lock Hardening | Immune to cloud-sync conflict files and multi-agent lock contamination (`LOCK.*`, `*-conflict-*`). | `tests/test_metadata.py` (`test_gitignore_hygiene_patterns`) | VERIFIED |
| `INV-SLA-10` | 48h Security & 5-Day Triage SLA | Committed vulnerability disclosure response and transparent patch lifecycle; zero-copyleft permissive MIT license. | `SECURITY.md`, `README.md`, `[NOTICE](NOTICE)` | VERIFIED |

---

## Development & Test Dependencies

The following tools and libraries are utilized exclusively during development, linting, packaging, and automated test execution:

| Package / Tool | Version Spec | License | Scope | Purpose |
|----------------|-------------|---------|-------|---------|
| [pytest](https://pytest.org/) | `>=8.0` | MIT | `[dev]` | Automated unit, contract, and regression test runner |
| [ruff](https://github.com/astral-sh/ruff) | `>=0.6` | MIT OR Apache-2.0 | `[dev]` | High-performance Python linter and code formatting validation |
| [setuptools](https://github.com/pypa/setuptools) | `>=77.0` | MIT | `[build-system]` | Standard Python packaging and build backend |
| [build](https://github.com/pypa/build) | `>=1.2` | MIT | `[dev]` | PEP 517 build frontend and package artifact verification |

---

## License Texts & Attribution

### MIT License (`system-auditor`, `pytest`, `setuptools`, `build`, `ruff`)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Apache License 2.0 (`ruff` dual-license option)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

### Python Software Foundation License (PSF) (Python Standard Library)

1. This LICENSE AGREEMENT is between the Python Software Foundation ("PSF"), and
   the Individual or Organization ("Licensee") accessing and otherwise using Python
   software in source or binary form and its associated documentation.

2. Subject to the terms and conditions of this License Agreement, PSF hereby
   grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,
   analyze, test, perform and/or display publicly, prepare derivative works, distribute,
   and otherwise use Python alone or in any derivative version, provided, however, that
   PSF's License Agreement and PSF's notice of copyright, i.e., "Copyright (c) 2001-2026
   Python Software Foundation; All Rights Reserved" are retained in Python alone or
   in any derivative version prepared by Licensee.
