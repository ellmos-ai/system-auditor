# Security Policy

[English](#english) | [Deutsch](#deutsch)

---

## English

### Supported Versions

The following versions of `system-auditor` currently receive security updates and maintenance:

| Version | Supported          | Status                                 |
| ------- | ------------------ | -------------------------------------- |
| `0.9.x` | :white_check_mark: | Active release & security maintenance  |
| `< 0.9` | :x:                | Superseded; please upgrade             |

---

### Core Security & Privacy Invariants

`system-auditor` is engineered from the ground up for strict local-first and high-assurance multi-host environments:

1. **100% Local-First & Zero-Egress**:
   - `system-auditor` executes entirely offline using Python's standard library.
   - It contains zero network dependencies, zero telemetry, zero analytics tracking, and zero remote logging.
   - No data, tokens, file paths, or audit metrics are ever transmitted over external networks.

2. **Unprivileged User-Mode Execution (Non-Elevation)**:
   - `system-auditor` operates strictly within standard unprivileged user permissions.
   - It does not require administrative or root privileges, and does not perform kernel-level interventions or system modifications.

3. **Safe File System Boundaries & Secret Isolation**:
   - The auditor parses configuration files and structured report markdown headers.
   - It does not parse or export API tokens, SSH keys, credentials, or private cryptographic material.
   - Audited paths are treated defensively as read-only inspection targets.

4. **Write-Guard Race Protection (Zero-Lock Coordination)**:
   - Parallel audits across hosts are the premise of meta-auditing, not a collision.
   - When saving aggregated meta-reports via `write_meta`, the tool re-reads the destination file and rejects writes if on-disk data already rests on a superset of planned inputs. This prevents stale overwrite races without introducing external lock daemons.

5. **Meeting Point (`reports_dir`) Hygiene**:
   - The shared reports directory should reside in a trusted, access-controlled synchronization folder shared among authorized host machines.

---

### Reporting a Vulnerability

If you discover a potential security vulnerability, privilege escalation path, or data isolation issue in `system-auditor`:

- **Maintainer Contact**: `security@ellmos.ai`
- **Umbrella Security**: `lukas@open-bricks.org` / `support@lukasgeiger.com`
- **GitHub Security Advisory**: [Report a Vulnerability](https://github.com/ellmos-ai/system-auditor/security/advisories)

Please include:
1. Steps to reproduce or a minimal proof-of-concept.
2. Operating system, Python version, and `system-auditor` version.
3. Impact assessment and suggested remediation if known.

We acknowledge incoming reports within **24 to 48 hours** and coordinate coordinated disclosure and patch releases via GitHub Security Advisories.

---

## Deutsch

### Unterstützte Versionen

Folgende Versionen von `system-auditor` erhalten aktiv Sicherheits- und Wartungsaktualisierungen:

| Version | Unterstützt        | Status                                      |
| ------- | ------------------ | ------------------------------------------- |
| `0.9.x` | :white_check_mark: | Aktive Version & Sicherheitswartung         |
| `< 0.9` | :x:                | Abgelöst; bitte auf aktuelle Version heben  |

---

### Sicherheits- und Datenschutz-Invarianten

`system-auditor` folgt strengen Grundsätzen für belegbare, lokale Multi-Host-Sicherheit:

1. **100% Local-First & Zero-Egress**:
   - `system-auditor` läuft vollständig offline und nutzt ausschließlich die Python-Standardbibliothek.
   - Keine Netzwerkabhängigkeiten, keine Telemetrie, keine Nutzungsstatistiken und keine externen Serveranfragen.
   - Keine Daten, Dateipfade, Token oder Audit-Befunde verlassen jemals die lokale Umgebung.

2. **Unprivilegierter User-Mode (Non-Elevation)**:
   - `system-auditor` benötigt keinerlei Administrator- oder Root-Rechte.
   - Es greift nicht modifizierend in Systemkerne oder privilegierte Systembereiche ein.

3. **Dateisystem-Grenzen & Geheimnisschutz**:
   - Der Auditor liest Konfigurationen und strukturierte Markdown-Berichtsköpfe.
   - Es werden keine API-Schlüssel, Passwörter, SSH-Keys oder kryptographische Geheimnisse verarbeitet oder exportiert.
   - Geprüfte Domänen werden grundsätzlich nur lesend inspiziert.

4. **Schreibsicherung gegen Race Conditions (Write-Guard)**:
   - Parallele Audits verschiedener Rechner sind die Voraussetzung für Meta-Audits, keine Kollision.
   - Vor dem Schreiben eines aggregierten Berichts (`write_meta`) liest das Werkzeug den Zielstand erneut und verweigert die Ausgabe, falls auf der Platte bereits eine Obermenge der Eingaben vorliegt. Dies schützt vor Überschreibungen ohne externe Lock-Dienste.

5. **Treffpunkt-Hygiene (`reports_dir`)**:
   - Das geteilte Berichtsverzeichnis sollte in einem vertrauenswürdigen, zugriffsgeschützten Synchronisationsordner liegen.

---

### Sicherheitslücke melden

Wenn Sie eine Sicherheitslücke oder ein Datenschutzproblem in `system-auditor` feststellen:

- **Maintainer-Kontakt**: `security@ellmos.ai`
- **Dachverband-Kontakt**: `lukas@open-bricks.org` / `support@lukasgeiger.com`
- **GitHub Security Advisory**: [Sicherheitslücke melden](https://github.com/ellmos-ai/system-auditor/security/advisories)

Erstmeldungen werden innerhalb von **24 bis 48 Stunden** gesichtet und Patches über GitHub Security Advisories koordiniert bereitgestellt.
