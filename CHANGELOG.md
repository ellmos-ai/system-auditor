# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.2.0] - 2026-08-15

Token-Modell und Aggregationsleiter. Ersetzt das gleitende Gueltigkeitsfenster aus 0.1.0
durch diskrete, aus der Config abgeleitete Zeitraeume -- jede Maschine leitet fuer
denselben Moment denselben Token ab, ohne Abstimmung.

### Hinzugefuegt

- **Vier Token je Audit** (`tokens.py`): time, domain, system, auditor. Zwei Audits mit
  identischen vier Token sind dieselbe Aussage, korrigiert -- die neuere ersetzt die
  aeltere.
- **Zeitraster** (`TimeGrid`) aus period + anchor, plus optionale explizite Tabelle
  (`TimeTable`) fuer Kalender, die eine Regel nicht ausdruecken kann. Ein Moment ausserhalb
  der Tabelle faellt auf das Raster zurueck.
- **Aggregationsleiter**: `interrater` (Modelle auf einer Maschine, mit
  Uebereinstimmungsquote), `cross-system` (Maschinen), `cross-domain` (Domaenen, verglichen
  ueber die REGEL statt ueber den Ort).
- **Achsenabhaengige Darstellung**: dieselbe Klasse heisst je nach Achse "systemweit",
  "alle Auditoren einig" oder "in allen Domaenen".
- CLI: `time-token`, `stale`, `meta-plan --aggregation`; `next-area` -> `next-domain`.

### Geaendert

- **Meta-Audits werden im Zeitfenster ueberschrieben statt archiviert.** Der Dateiname
  traegt den Zeittoken und keinen Host (`META-<kind>-<time>[-<scope>].md`), also gibt es
  je Fenster und Scope genau eine gueltige Antwort. Die Historie steckt im Token: das
  letzte Fenster ist eine andere Datei und bleibt unberuehrt.
- Archivierung ist damit kein Teil des Normalflusses mehr; `archive()` bleibt fuer
  bewusstes Aufraeumen laengst vergangener Fenster.
- Berichtsfelder `area`/`host` heissen jetzt `domain`/`system`, passend zu den Token.

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
