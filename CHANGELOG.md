# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.3.0] - 2026-08-15

Vollstaendige Aggregations-Systematik plus eine Bau-Politik, damit sie nicht in
Berichtsmuell endet.

### Hinzugefuegt

- **Zwei weitere Aggregationen ueber Momentaufnahmen**: `full-system` (Zeit und
  System fest, Domaene UND Auditor duerfen variieren -- das Gesamtbild einer
  Maschine in einem Fenster) sowie die praezisierte `cross-domain`.
- **Zeitreihen** (`timeseries.py`): eigene Aggregationsart, in der die ZEIT
  variiert. Sie braucht eigene Klassen, weil die Momentaufnahme-Klassen dort
  unsinnig waeren -- "alle Fenster haben es gefunden" ist *persistent*, nicht
  *systemwide*: `new`, `persistent`, `resolved`, `recurring`, `unverifiable`,
  dazu eine Richtungsangabe (neu minus erledigt).
  `resolved` wird nur vergeben, wenn der juengste Lauf den Ort nachweislich
  abgedeckt hat -- sonst sehen "behoben" und "nicht mehr geprueft" gleich aus.
- **Unkontrollierte Dimensionen** werden benannt statt verschwiegen: Was eine
  Aggregation weder festhaelt noch vergleicht, erzeugt einen Vorbehalt, wenn es
  tatsaechlich differiert. `cross-system` haelt das Modell nicht fest -- in einer
  Flotte mit unterschiedlichen Modellen je Maschine waere die Alternative,
  Maschinen nie zu vergleichen.
- **Bau-Politik** (`resolve_policy`, `due_aggregations`, `plan_all`): je
  Aggregation `always` | `on_demand` | `off` mit eigener Teilnehmerschwelle.
  Anlass ist gerechnet: 14 Domaenen x 3 Maschinen x 2 Modelle ergeben ~191
  moegliche Artefakte pro Fenster. Standard ist genau EIN stehendes Artefakt
  (`cross-system`); alles andere ist eine Frage, die jemand stellt.
  Ein `off` geschaltetes Artefakt bleibt auch auf Zuruf aus -- das Einschalten
  ist eine Konfigurationsentscheidung.

### Geaendert

- Dateinamen kommen jetzt aus dem vollstaendigen Fixed-Key
  (`META-<aggregation>-<key...>.md`). Damit traegt eine Zeitreihe bewusst KEINEN
  Zeitraum im Namen -- sie ist immer "bis jetzt" -- und ein Snapshot traegt ihn
  genau dann, wenn die Zeit festgehalten wird.
- **Teilnehmerzahlen stehen NICHT im Dateinamen**, sondern im Kopf und im Titel.
  Ein mitwachsender Name (`meta-3-...`) haette die Ueberschreib-Regel gebrochen,
  die genau eine gueltige Antwort je Schluessel garantiert.
- `cross-domain` haelt jetzt Maschine und Modell fest. Domaenen ueber Maschinen
  hinweg zu vergleichen haette zwei Dinge gleichzeitig variiert.

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
