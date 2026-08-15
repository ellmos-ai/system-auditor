# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.1.0] - 2026-08-15

Erste Fassung. Herausgeloest aus der Rolle SIG-TU/TICKET-WRITER des Ticketsystems,
nachdem deren Architektur-Vorbehalt vom 2026-07-31 ("moeglicherweise kein Ticket-Modul,
sondern eine eigene Domaene") zur Deckung mit dem Bedarf an Mehrsystem-Audits kam.

### Hinzugefuegt

- **Audit-Host-Lock v1** (`protocols/audit-host-lock/SPEC.md`, `audit_lock.py`):
  Modus `presence` als reines Anwesenheitssignal, das niemanden ausschliesst, und
  `claim` als Reservierung ausschliesslich fuer Meta-Audits. Deterministische
  Verlierer-Regel (fruehestes `created`, Host-Ordnung als Tiebreak), sekundengenaue
  Zeitstempel als dokumentierte Abweichung vom minutengenauen Basisformat.
- **Berichte** (`report.py`): maschinenlesbarer Kopf mit `finished_utc`, `coverage`,
  `clean`, `evidence_level`, `valid_until`; Rotation je Host; Rueckwaertskompatibilitaet
  zu `SIG-TU-*.md`-Bestandsberichten.
- **Meta-Audit** (`compare.py`): Klassifikation ueber beliebig viele Systeme in
  `systemwide` / `host_specific` / `inverse` / `divergent` / `unverifiable`,
  Home-Pfad-Normalisierung, Vergleichbarkeits-Gate.
- **Meta-Lebenszyklus** (`meta.py`): Gueltigkeitsfenster, neuestes Audit je System,
  `meta-N` ersetzt `meta-(N-1)`, Archivierung statt Loeschung, Erneuerung nur durch
  den Host, der das Audit erzeugt hat.
- **Erkennungskaskade** (`discovery.py`): konfiguriert, Modul-Probe, Konvention, nichts.
- **Senken** (`sinks.py`): Datei-Senke, Kommando-Senke mit automatischem Rueckfall.
- **CLI** (`cli.py`) und Rollen-Prompt (`prompts/AUDITOR.de.md`).

### Nicht enthalten (bewusst)

Ticket-IDs, Ticket-Kategorien und Modell-Routing bleiben beim Ticketsystem;
Kartenerzeugung bleibt beim Explorer; ein zentrales Cursor-Register wurde nicht gebaut.
