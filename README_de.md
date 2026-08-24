<img src="assets/banner.png" width="100%" alt="system-auditor banner">

# system-auditor

[![CI](https://github.com/ellmos-ai/system-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/ellmos-ai/system-auditor/actions/workflows/ci.yml)
[![tests](https://img.shields.io/badge/pytest-158%20bestanden%20%7C%20100%25-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](pyproject.toml)
[![privacy](https://img.shields.io/badge/datenschutz-100%25%20Local--First%20%7C%20Zero--Egress-brightgreen)](SECURITY.md)
[![security](https://img.shields.io/badge/sicherheit-Bilinguale%20Policy%20%7C%20Write--Guarded-blue)](SECURITY.md)
[![license](https://img.shields.io/badge/lizenz-MIT-green)](LICENSE)
[![dependencies](https://img.shields.io/badge/abh%C3%A4ngigkeiten-keine%20(stdlib)-lightgrey)](pyproject.toml)
[![ecosystem](https://img.shields.io/badge/ecosystem-ellmos--ai-purple)](https://github.com/ellmos-ai)
[![umbrella](https://img.shields.io/badge/umbrella-open--bricks-blueviolet)](https://github.com/open-bricks/open-bricks)
[![version](https://img.shields.io/badge/version-0.9.1-orange)](pyproject.toml)
[![llms.txt](https://img.shields.io/badge/llms.txt-Discovery%20Context-informational)](llms.txt)

**Belegbasierte Systemaudits über mehrere Maschinen — mit Meta-Bündelung.**

*[English version: `README.md`](README.md)*

---

## 🧭 Schnellnavigation

- [Wozu dieses Modul existiert](#wozu-dieses-modul-existiert)
- [Architektur & Systemfluss](#architektur--systemfluss)
- [Die drei Stufen](#die-drei-stufen)
- [Vier Token & Diskrete Zeitfenster](#vier-token--diskrete-zeitfenster)
- [Die Aggregationsleiter](#die-aggregationsleiter)
- [Kernfähigkeiten & Governance-Invarianten](#kernfähigkeiten--governance-invarianten)
- [Eine gültige Antwort je Zeitfenster](#eine-gültige-antwort-je-zeitfenster)
- [Schreibsicherung gegen Race Conditions](#schreibsicherung-gegen-race-conditions)
- [End-to-End Audit-Lebenszyklus](#end-to-end-audit-lebenszyklus)
- [Geschwisterwerkzeuge & Ökosystem-Matrix](#geschwisterwerkzeuge--ökosystem-matrix)
- [Installation & CLI-Nutzung](#installation--cli-nutzung)
- [Konfiguration](#konfiguration)
- [Sicherheit & Datenschutz](#sicherheit--datenschutz)
- [Entwicklung & Verifikation](#entwicklung--verifikation)
- [Lizenz](#lizenz)

---

## Wozu dieses Modul existiert

Der Auditor prüft ein komponiertes System in **drei Richtungen**:

1. **Regeltreue:** Verletzt ein beobachteter Systemzustand eine deklarierte Policy oder Konvention?
2. **Integration (Prüfklassen I1–I7):** Arbeiten Softwaremodule, Manifeste, Bundles und Bindings in der Praxis tatsächlich wie deklariert zusammen?
3. **Steuerungs-Konsistenz (Prüfklassen K1–K4):** Sind Steuerdateien, Register, Policies und bisherige Architekturentscheidungen untereinander widerspruchsfrei?

Das leitende Prinzip ist **Konvergenz**: Jeder Fund endet mit einer klaren Richtung — Realität an die Regel anpassen (eine konkrete Maßnahme) oder Regel an die Realität anpassen (eine Entscheidungsvorlage).

Zwei Maschinen, die dieselbe Domäne auditieren, kommen **nicht** zum selben Ergebnis. Das ist kein Mangel — es ist das Nützlichste daran, das Audit auf mehreren Systemen auszuführen.

### Ein gemessenes Beispiel

> **Befund:** *„Gardener-Governance hartkodiert den Laptop-Home-Pfad"* — `AGENTS.md` verweist auf `C:\Users\alice\…`.
>
> Auf **WORKSTATION-LG** ist das real: Der Pfad existiert dort nicht.
> Auf dem **Laptop** ist dieselbe Zeile korrekt und ergibt gar keinen Befund.

Eine einzelne Maschine sieht davon immer nur die Hälfte. Der Vergleich der gültigen Audits aller beteiligten Systeme liefert eine belegbare Einordnung, die ein Einzellauf strukturell nicht erzeugen kann:

| Klasse | Bedeutung | Auswirkung |
|---|---|---|
| `systemwide` | Alle Teilnehmer fanden es | Echte Systeminkonsistenz oder gebrochene Invariante |
| `host_specific` | Manche fanden es, andere haben fehlerfrei geprüft | Konfigurationsdrift oder Rechner-Divergenz |
| `inverse` | Hier ein Mangel, dort ausdrücklich in Ordnung | Host-Abhängigkeit (z. B. hartkodierter Pfad) |
| `divergent` | Gleicher Ort, *verschiedene* Regeln verletzt | Sync-Differenz oder divergierende Regelauslegung |
| `unverifiable` | Ein Teilnehmer hat dort nie geprüft | Ehrliche Nicht-Belegbarkeit (verhindert Schein-Drift) |

> [!NOTE]
> `unverifiable` ist die ehrliche Klasse. Ohne sie würde jede Lücke in der Prüfabdeckung eines Teilnehmers stillschweigend als echter Rechner-Unterschied erscheinen.

---

## Architektur & Systemfluss

```mermaid
flowchart TD
    subgraph S1["1. Inspektion & Entdeckung"]
        A1["Domänen-Ziel / Codebasis"] --> D1["discover() Sinks & Manifeste"]
        D1 --> M1["Manifeste & Richtlinien\nellmos-module.v2 / bundle.v1 / AGENTS.md"]
    end

    subgraph S2["2. Multi-Host Audit-Erzeugung"]
        M1 --> R1["Host 1 Einzellauf\n(time, domain, sys1, modelA)"]
        M1 --> R2["Host 2 Einzellauf\n(time, domain, sys2, modelB)"]
        R1 --> P1["templates/AUDIT-BERICHT\nEinzelne Markdown-Berichte"]
        R2 --> P1
    end

    subgraph S3["3. Aggregationsleiter & Meta-Bündelung"]
        P1 --> G1["shared reports_dir\n(Sync-Treffpunkt)"]
        G1 --> AP["Aggregations-Engine\n(interrater | cross-system | cross-domain | timeseries)"]
        AP --> CL["Klassifikations-Kern\nsystemwide | host_specific | inverse | divergent | unverifiable"]
    end

    subgraph S4["4. Schreibsicherung & Konvergenz"]
        CL --> WG{"write_meta\nSchreibsicherungs-Prüfung"}
        WG -->|"Platte hat Obermenge"| SK["Überschreiben überspringen\n(Keine Race Conditions)"]
        WG -->|"Neue Evidenz"| MR["Atomarer Meta-Bericht\n(templates/META-BERICHT)"]
        MR --> AC["Konvergenz-Richtung\nMaßnahme vs. Entscheidungsvorlage"]
    end

    style S1 fill:#f8fafc,stroke:#64748b,stroke-width:1px
    style S2 fill:#f0fdf4,stroke:#22c55e,stroke-width:1px
    style S3 fill:#eff6ff,stroke:#3b82f6,stroke-width:1px
    style S4 fill:#fdf4ff,stroke:#a855f7,stroke-width:1px
```

---

## Die drei Stufen

```text
Karte     Was ist da?              ->  system-explorer   (optional)
Urteil    Was ist daran falsch?    ->  system-auditor    (dieses Modul)
Maßnahme  Was tun wir?             ->  Ticketsystem      (optional)
```

Eine Karte ist wertfrei, ein Ticket ist eine Handlung. Dazwischen liegt das Urteil: *welche Regel ist verletzt, was empfehlen wir, und ist die Regel selbst noch richtig?*

**Kein Nachbar ist Voraussetzung.** Erkannt werden sie genutzt; fehlen sie, liest der Auditor direkt und schreibt Dateien. In jede Richtung dasselbe Prinzip: *kennt sie, braucht sie nicht.*

---

## Vier Token & Diskrete Zeitfenster

Jedes Audit beantwortet vier Fragen, und jede Antwort ist ein unveränderlicher Token:

| Token | Frage | Beschreibung |
|---|---|---|
| `time` | *Wann?* | Das diskrete Zeitfenster, zu dem die Aussage gehört (z. B. `20260817`) |
| `domain` | *Was?* | Die auditierten Domäne (z. B. `bundles`, `skills`, `mcp`) |
| `system` | *Wo?* | Der Rechnername oder die geprüfte Umgebung (z. B. `WORKSTATION-LG`) |
| `auditor` | *Wer?* | Die Modell- oder Agentenidentität des Prüfers (z. B. `claude-3-5-sonnet`) |

### Warum diskrete Fenster statt gleitender Spannen

Ein gleitendes Fenster („gilt 14 Tage ab Lauf") macht Überlappung zur Gradfrage — jede Maschine müsste Paare vergleichen. Ein aus der Konfiguration abgeleitetes **Raster** macht daraus eine direkte Abfrage: Uhr fragen, Token bekommen. Zwei Maschinen, die nie direkt miteinander sprechen, leiten für denselben Moment denselben Token ab; „gleicher Zeitraum" wird zum einfachen Stringvergleich statt zum verteilten Konsensproblem.

---

## Die Aggregationsleiter

Einige Token festhalten, den Rest variieren lassen. **Eine Ursache darf eine Aggregation nur dann zuschreiben, wenn genau eine Dimension variiert** — sonst ist ein Unterschied mathematisch nicht identifizierbar. Diese Regel wird im Konstruktor erzwungen.

| Aggregation | Feste Dimensionen | Variierende Dimension | Was sie identifiziert |
|---|---|---|---|
| `interrater` | `time` + `domain` + `system` | **`auditor`** | Sind sich zwei Modelle auf demselben Rechner einig? |
| `cross-system-rater` | `time` + `domain` + `auditor` | **`system`** | Ein sauberer, modellkontrollierter Host-Effekt |
| `cross-system` | `time` + `domain` | **`system`** | Rechner-Unterschiede (Modell unkontrolliert; praxisnah) |
| `cross-domain` | `time` + `system` + `auditor` | **`domain`** | Bricht dieselbe Regel über verschiedene Domänen hinweg? |
| `timeseries` | `system` + `domain` | **`time`** | Wie hat sich die Domäne über aufeinanderfolgende Fenster entwickelt? |
| `timeseries-rater` | `system` + `domain` + `auditor` | **`time`** | Entwicklungskurve aus Sicht eines einzelnen Modells |
| `full-system` | `time` + `system` | `domain` **+** `auditor` | **Nur deskriptiv** — Bestandsaufnahme (`build_inventory`), kein Urteil |

---

## Kernfähigkeiten & Governance-Invarianten

| Fähigkeit / Invariante | Garantie | Technische Umsetzung |
|---|---|---|
| **Deterministische Klassifikation** | Gleiche Eingangsberichte erzeugen bitgenau identische Klassifikationen | Kanonische Vorabsortierung aller Befunde und Eingaben |
| **Identifizierbarkeits-Wächter** | Aggregationen mit >1 variierender Dimension dürfen keine Kausalurteile fällen | `Aggregation`-Klasse prüft Varianz-Arität im Konstruktor |
| **Lock-freie Koordination** | Multi-Host-Audits laufen asynchron ohne zentrale Locking-Server | Schreibsicherung liest Zieldatei vor dem Schreiben auf Obermengen |
| **Zero Network Egress** | 100% offline; null Telemetrie oder externer HTTP-Datenverkehr | Reine Standardbibliothek; durch statische AST-Tests abgesichert |
| **Bilinguale Governance** | Deutsch und Englisch in Berichten, Prompts und Dokumentation | Parallele Templates in `templates/` und Prompts in `prompts/` |
| **Transparente Abdeckung** | Ungeprüfte Bereiche werden explizit als `unverifiable` ausgewiesen | `MetaResult` führt nachweisbare Präsenz, Absenz und Lücken getrennt |

---

## Eine gültige Antwort je Zeitfenster

```text
System A auditiert `bundles`   ->  Einzelaudit
System B auditiert `bundles`   ->  meta-2  (angelegt)
System C auditiert `bundles`   ->  meta-3  (dieselbe Datei, neu geschrieben)
```

Innerhalb eines Fensters wird das Meta-Audit **überschrieben, nicht archiviert**: „Was wissen wir über diese Domäne in diesem Fenster" hat eine gültige autoritative Antwort. `meta-2` neben `meta-3` stehen zu lassen würde zwei widersprüchliche Antworten hinterlassen.

**Die Historie ergibt sich von selbst.** Das vorherige Fenster hat einen anderen Zeit-Token, folglich einen anderen Dateinamen, und bleibt unberührt.

---

## Schreibsicherung gegen Race Conditions

Parallele Audits einer Domäne sind die *Voraussetzung* eines Meta-Audits, keine Kollision. Es gibt nichts auszuschließen, deshalb hält dieses Modul keine verteilten Locks.

- **Das Audit selbst ist read-only.** In der geprüften Domäne wird nichts verändert.
- **Die Klassifikation ist deterministisch.** Gleiche Eingaben erzeugen identischen Markdown-Text.
- **Schreibsicherungs-Prüfung:** `write_meta` liest das Ziel auf der Festplatte erneut. Liegt dort bereits eine Obermenge der geplanten Eingaben vor, wird das Neuschreiben sicher übersprungen.

---

## End-to-End Audit-Lebenszyklus

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Auditor / Agent
    participant CLI as system-auditor CLI
    participant Disk as Lokales / Geteiltes reports_dir
    participant Engine as Meta-Aggregator

    Dev->>CLI: system-auditor time-token
    CLI-->>Dev: Liefert aktuellen Fenster-Token (z. B. 20260817)

    Dev->>CLI: system-auditor next-domain --domains "bundles,skills,mcp"
    CLI-->>Dev: Wählt die am längsten unberührte Domäne

    Dev->>CLI: system-auditor discover --domain-path /pfad/zur/domaene
    CLI-->>Dev: Listet Manifeste, Regeln und Richtlinien-Quellen auf

    Note over Dev: Auditor führt Inspektion durch (Regeln, Integration I1-I7, Governance K1-K4)
    Dev->>Disk: Schreibt Einzelaudit (AUDIT-BERICHT.de.md / AUDIT-REPORT.en.md)

    Dev->>CLI: system-auditor meta-plan --reports ./reports --aggregation cross-system
    CLI->>Disk: Prüft Fremdberichte im selben Zeitfenster

    alt Meta-Audit fällig (Neue Fremdeingaben vorhanden)
        CLI-->>Dev: Plan-Aktion: CREATE / UPDATE
        Dev->>Engine: build_meta(runs, aggregation)
        Engine->>Engine: Klassifiziert (systemwide, host_specific, inverse, divergent, unverifiable)
        Engine->>Disk: write_meta (Verifiziert Platten-Obermenge vor atomarem Schreiben)
        Disk-->>Dev: Meta-Bericht aktualisiert
    else Bereits aktuell
        CLI-->>Dev: Plan-Aktion: SKIP (Obermenge liegt bereits vor)
    end
```

---

## Geschwisterwerkzeuge & Ökosystem-Matrix

`system-auditor` ist Teil des `ellmos-ai`-Ökosystems unter dem Dachverband `open-bricks`:

| Repositorium | Fokus | Integrationsrolle mit `system-auditor` |
|---|---|---|
| [`ellmos-ai/system-explorer`](https://github.com/ellmos-ai/system-explorer) | System-Kartierung | Liefert strukturierte Bestandsaufnahmen („Was ist da?") |
| [`ellmos-ai/system-auditor`](https://github.com/ellmos-ai/system-auditor) | Audit & Urteil | Bewertet Regeltreue, Integration und Steuerungs-Konsistenz |
| [`ellmos-ai/ellmos-controlcenter-mcp`](https://github.com/ellmos-ai/ellmos-controlcenter-mcp) | MCP Control Plane | Kontext-Packer, Werkzeug-Routing und Fähigkeits-Erkennung |
| [`ellmos-ai/ellmos-delegation-authority`](https://github.com/ellmos-ai/ellmos-delegation-authority) | Kryptographische Autorität | Nonce-basierte kryptographische Delegations-Grants |
| [`ellmos-ai/sqlite-transit-sync`](https://github.com/ellmos-ai/sqlite-transit-sync) | Datenbank-Transit | Zero-Egress SQLite-Replikation mit WAL-Checkpointing |
| [`dev-bricks/automation-master`](https://github.com/dev-bricks/automation-master) | Aufgaben-Automatisierung | Orchestriert automatisierte Batch-Wartungsworkflows |
| [`dev-bricks/automizer-for-claude-desktop`](https://github.com/dev-bricks/automizer-for-claude-desktop) | Prozess-Diskriminierung | Atomare Konfigurations-Snapshots & sichere Staging-Queues |
| [`file-bricks/ProSync`](https://github.com/file-bricks/ProSync) | Lokale Datensicherung | Sicherer Profilabgleich mit SQLite-WAL-Checkpoint-Schutz |
| [`doc-bricks/CleanMarkdown`](https://github.com/doc-bricks/CleanMarkdown) | Dokumenten-AST | Hochpräzise Markdown-AST-Validierung und Rendering |
| [`open-bricks/open-bricks`](https://github.com/open-bricks/open-bricks) | Dachverband | Übergreifende Architekturstandards, Governance & Lizenzierung |

---

## Installation & CLI-Nutzung

```bash
# Entwicklungsinstallation
python -m pip install -e .

# Aktive Konfiguration und aufgelöstes Berichtsverzeichnis anzeigen
system-auditor config

# Aktuellen diskreten Zeitfenster-Token ermitteln
system-auditor time-token

# Nächste fällige Domäne in der Rotation ermitteln
system-auditor next-domain --domains "bundles,skills,mcp" --reports ./reports --system $HOSTNAME

# Konventionen, Manifeste und Richtlinien-Quellen einer Domäne entdecken
system-auditor discover --domain-path /pfad/zur/domaene

# Ausstehende Meta-Audits im aktuellen Fenster planen
system-auditor meta-plan --reports ./reports --aggregation cross-system
system-auditor meta-plan --reports ./reports --aggregation interrater

# Einzelaudits aus früheren Zeitfenstern identifizieren
system-auditor stale --reports ./reports --system $HOSTNAME
```

---

## Konfiguration

```bash
cp config/system-auditor.config.example.json system-auditor.config.json
system-auditor config          # zeigt aufgelöste Konfiguration
```

Suchreihenfolge: `--config`, `SYSTEM_AUDITOR_CONFIG`, `./`, `./config/`, `~/.system-auditor/`.

```json
{
  "time_grid": {
    "unit": "weeks",
    "step": 1,
    "anchor": "2026-01-05"
  },
  "reports_dir": "./reports",
  "policy": {
    "cross-system": "always",
    "interrater": "always",
    "cross-domain": "on-demand"
  }
}
```

> [!IMPORTANT]
> `reports_dir` ist der Treffpunkt aller Maschinen. Er muss in einem cloud-synchronisierten Ordner liegen, den alle teilnehmenden Systeme teilen. In einem rein host-lokalen Verzeichnis können keine Meta-Audits entstehen.

---

## Sicherheit & Datenschutz

`system-auditor` folgt einem strikten **Local-First- & Zero-Egress**-Modell. Es enthält null Telemetrie, erfordert keine Internetverbindung, operiert rein mit unprivilegierten Benutzerrechten und setzt auf deterministische Schreibsicherungen.

Vollständige Details, unterstützte Versionen und Sicherheitskontakte finden Sie in [`SECURITY.md`](SECURITY.md).

---

## Entwicklung & Verifikation

```bash
# Testsuite ausführen (inklusive Metadaten-Vertragstests)
python -m pytest -q

# Ruff-Linter ausführen
ruff check src tests
```

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
