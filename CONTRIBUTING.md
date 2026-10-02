# Contributing to system-auditor

Thank you for your interest in contributing to **system-auditor** (`ellmos-ai/system-auditor`), the evidence-based multi-host system audit engine with deterministic meta-audit bundling, discrete calendar windows, and write-guard concurrency protection.

[English](#english) | [Deutsch](#deutsch)

---

<a id="english"></a>
## English

### 1. Architectural Principles & Invariants

Every contribution must preserve our 10 foundational system and operational invariants:

- **100% Local-First & Zero-Egress (`INV-LOCAL-01`)**: Zero unauthorized network sockets, telemetry, analytics beacons, or remote cloud connections. The engine operates completely air-gapped.
- **Unprivileged Non-Elevation Execution (`INV-UNPRIV-02`)**: Executes strictly in user-mode (`RunAsInvoker`), never requiring administrative, root elevation, or UAC prompts.
- **Deterministic Classification (`INV-DETERM-03`)**: Identical inputs produce bit-for-bit identical multi-host audit verdicts and canonical findings ordering.
- **Identifiability Guard (`INV-IDENT-04`)**: Invariant that aggregations with more than one varying dimension cannot emit causal verdicts (strictly enforced in constructor).
- **Write-Guard Race Protection (`INV-RACE-05`)**: Concurrent audits across machines never conflict; pre-write disk inspection safely avoids redundant rewrites when an on-disk superset exists.
- **Discrete Window Tokens (`INV-WINDOW-06`)**: Deterministic temporal alignment without distributed consensus protocols via config-driven calendar window calculation.
- **One Current Answer Per Window (`INV-SINGLE-07`)**: Single authoritative multi-host answer per window, avoiding stale duplicate reports while preserving history.
- **Coverage Transparency Floor (`INV-COVER-08`)**: Honest absence-of-proof floor prevents uninspected paths from masquerading as divergence (`unverifiable` tier).
- **Multi-Host & Lock Hardening (`INV-LOCK-09`)**: Immune to cloud-sync conflict files and multi-agent lock contamination (`LOCK.*`, `*-conflict-*`).
- **Audit Trails & Security SLA (`INV-SLA-10`)**: Immutable audit reports, Level 1 SBOM transparency, and a binding 48h Security Response SLA.

### 2. Local Development & Setup

1. **Clone the repository** (Plan D canonical clone):
   ```bash
   git clone https://github.com/ellmos-ai/system-auditor.git
   cd system-auditor
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install development dependencies**:
   ```bash
   pip install -e ".[dev]"
   pip install ruff
   ```

### 3. Testing & Verification Gates

Before submitting any Pull Request or pushing changes, verify that all quality gates pass cleanly:

1. **Run full automated test suite**:
   ```bash
   pytest
   ```
   All contract, unit, and metadata tests must pass (100% green).
2. **Run Ruff static analysis**:
   ```bash
   ruff check .
   ```
3. **Verify Python compilation**:
   ```bash
   python -m compileall src tests
   ```
4. **Verify git diff cleanliness**:
   ```bash
   git diff --check
   ```

### 4. Version Freeze & Release Discipline

- **Version Freeze (`T-20260920-167562623`)**: Do not increment or bump the package version in `pyproject.toml`, `src/system_auditor/__init__.py`, `ellmos-module.v2.json`, or code manifests. Version bumps are strictly governed by coordinated release procedures. All additions must be documented under `## [Unreleased]` in `CHANGELOG.md`.
- **Conventional Commits**: Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).

### 5. Reporting Security Vulnerabilities

Please do not open public GitHub issues for security vulnerabilities. Instead, refer to our [Security Policy](SECURITY.md) and report via `security@open-bricks.org` or `security@ellmos.ai` in accordance with our binding 48-hour response SLA.

### 6. Statutory Disclaimer (§ 521 BGB)

This software is provided free of charge under the MIT License as open-source software. In accordance with § 521 of the German Civil Code (BGB - Schenkungs- und Gefälligkeitsrecht), liability for defects in quality and title is strictly limited to intent and gross negligence.

---

<a id="deutsch"></a>
## Deutsch

### 1. Architektonische Prinzipien & Invarianten

Jeder Beitrag muss unsere 10 grundlegenden System- und Betriebsinvarianten wahren:

- **100% Local-First & Zero-Egress (`INV-LOCAL-01`)**: Keine ausgehenden Netzwerk-Sockets, Telemetrie, Analyse-Beacons oder Cloud-Verbindungen. Die Engine arbeitet vollständig offline.
- **Nicht-privilegierte Ausführung (`INV-UNPRIV-02`)**: Strikter Benutzermodus (`RunAsInvoker`), niemals Administrator- oder Root-Rechte erforderlich.
- **Deterministische Klassifikation (`INV-DETERM-03`)**: Identische Eingaben erzeugen bit-für-bit identische Multi-Host-Auditurteile und kanonische Befund-Sortierung.
- **Identifizierbarkeits-Wächter (`INV-IDENT-04`)**: Aggregationen mit mehr als einer variierenden Dimension dürfen keine Kausalurteile abgeben (im Konstruktor erzwungen).
- **Schreibschutz-Rennverhinderung (`INV-RACE-05`)**: Parallele Audits kollidieren nicht; Vorab-Prüfung verhindert Überschreiben, wenn bereits eine Obermenge existiert.
- **Diskrete Zeitfenster-Token (`INV-WINDOW-06`)**: Deterministische zeitliche Ausrichtung ohne verteilten Konsens über konfigurierte Kalenderfenster.
- **Eine gültige Antwort je Fenster (`INV-SINGLE-07`)**: Einzelne autoritative Multi-Host-Antwort je Fenster verhindert veraltete Duplikate bei Erhalt der Historie.
- **Transparente Abdeckungsgrenze (`INV-COVER-08`)**: Ehrliche Abwesenheit von Belegen verhindert Fehlalarme (`unverifiable`-Klasse).
- **Multi-Host- & Lock-Härtung (`INV-LOCK-09`)**: Immun gegen Cloud-Sync-Konfliktdateien und Lock-Kontamination (`LOCK.*`, `*-conflict-*`).
- **Revisionssicherheit & 48h SLA (`INV-SLA-10`)**: Unveränderliche Auditberichte, Level 1 SBOM Transparenz und verbindliche 48h Sicherheits-Reaktions-SLA.

### 2. Lokale Entwicklung & Setup

1. **Repository klonen** (Plan D kanonischer Klon):
   ```bash
   git clone https://github.com/ellmos-ai/system-auditor.git
   cd system-auditor
   ```

2. **Virtuelle Umgebung anlegen und aktivieren**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Entwicklungs-Abhängigkeiten installieren**:
   ```bash
   pip install -e ".[dev]"
   pip install ruff
   ```

### 3. Test- & Verifikations-Gates

Vor jedem Commit oder Pull Request müssen alle Qualitäts-Gates erfolgreich durchlaufen:

1. **Automatisierte Testsuite ausführen**:
   ```bash
   pytest
   ```
   Alle Tests müssen zu 100% grün sein.
2. **Ruff statische Code-Analyse**:
   ```bash
   ruff check .
   ```
3. **Python-Kompilierung prüfen**:
   ```bash
   python -m compileall src tests
   ```
4. **Git-Diff auf Whitespace-Fehler prüfen**:
   ```bash
   git diff --check
   ```

### 4. Version-Freeze-Disziplin

- **Version-Freeze (`T-20260920-167562623`)**: Die Versionsnummer in `pyproject.toml`, `src/system_auditor/__init__.py`, `ellmos-module.v2.json` oder Code-Manifesten darf nicht erhöht werden. Version-Bumps unterliegen zentralen Release-Verfahren. Alle Neuerungen werden unter `## [Unreleased]` in `CHANGELOG.md` dokumentiert.
- **Conventional Commits**: Konventionelle Commit-Präfixe verwenden (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).

### 5. Meldung von Sicherheitslücken

Sicherheitsrelevante Schwachstellen bitte nicht über öffentliche GitHub-Issues melden. Bitte die [Sicherheitsrichtlinie](SECURITY.md) beachten und Meldungen an `security@open-bricks.org` oder `security@ellmos.ai` senden (verbindliche 48h Reaktions-SLA).

### 6. Gesetzlicher Haftungsausschluss (§ 521 BGB)

Diese Software wird im Rahmen von Open-Source unentgeltlich bereitgestellt. Gemäß § 521 BGB (Schenkungs- und Gefälligkeitsrecht) ist die Haftung für Sach- und Rechtsmängel auf Vorsatz und grobe Fahrlässigkeit beschränkt.
