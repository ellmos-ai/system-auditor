# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.7.0] - 2026-08-16

Nutzerentscheidung eingearbeitet: Das Meta-Audit ist modellmanuell -- der
Auditor interpretiert selbst; das Werkzeug entscheidet Faelligkeit und liefert
Kontrolle. Und die Berichte brauchen einen physischen Treffpunkt.

### Hinzugefuegt

- **`templates/AUDIT-BERICHT.de.md` + `templates/META-BERICHT.de.md`** -- der
  Vertrag des modellmanuellen Wegs. Front Matter exakt im Format von
  `parse_front_matter` (testgesichert), inkl. `window_start_utc` (traegt die
  Chronologie) und `findings_detail:` (`locator | regel | titel` je Zeile) als
  Anschlusspunkt fuer eine spaetere maschinelle Kontrolle.
- **Cloud-Treffpunkt:** Beispiel-Config zeigt `reports_dir`/`findings_dir` auf
  den cloud-geteilten OneDrive-Modulordner; `config` warnt, wenn `reports_dir`
  host-lokal aussieht (`_looks_shared`-Heuristik -- Note, nie Gate).

### Geaendert

- Prompt (f)/(g): Bericht nach Template; Meta-Schritt ist Pflichtpruefung nach
  jedem Bericht und ausdruecklich die **Interpretation des Auditors** --
  `meta-plan` entscheidet ob, `build_meta` kontrolliert, das Modell ordnet ein.
- TODO: "Torso"-Einordnung des Fable-Reviews als gegenstandslos aufgeloest
  (die fehlende Maschinen-Extraktion war nie der Plan); Betriebsfrage
  "wo treffen sich die Berichte?" beantwortet.

## [0.6.0] - 2026-08-15

Behebt die Funde des Fable-Reviews (`_review/FABLE-REVIEW_2026-08-15.md`) --
Fokus Benutzbarkeit statt Robustheit oder Logik. Alle Funde neu, keiner der
beiden Codex-Runden.

### Behoben -- funktionsbrechend

- **Die Konfiguration wurde von nichts gelesen.** Kein `json.load` im Modul, kein
  `--config`-Flag: Zeitraster, Aggregations-Politik, Regelquellen, Domaenenliste
  und Massnahmen-Senke waren ueber die CLI wirkungslos, die Discovery-Stufen 1
  und 2 unerreichbar. Eine Konfigurationsdatei, die nichts liest, ist schlechter
  als keine -- sie behauptet etwas ueber das Verhalten des Werkzeugs.
  Neu: `config.py`, globales `--config`, Auffinden ueber
  `SYSTEM_AUDITOR_CONFIG`/`./`/`./config/`/`~/.system-auditor/`, und ein Kommando
  `system-auditor config`, das zeigt, was tatsaechlich gelesen wurde.
- **Der CLI-Anker zerstoerte das Zeitfenster.** Default war Mitternacht des
  AUFRUFTAGS statt des festen Rasterankers -- damit ergaben Montag und Mittwoch
  derselben Woche verschiedene Tokens, ein 7-Tage-Fenster degenerierte zu
  Tagesfenstern, und `meta-plan` buendelte nie tagesuebergreifend. Der Anker
  fixiert die *Phase* des Rasters und muss konstant sein.
- **`.github` wurde als `.git`-Praefix uebersprungen** -- ausgerechnet das
  Verzeichnis, in dem ein Repository seine Regeln fuehrt. Ganze Namen statt
  `startswith`.
- **`build_meta()` klassifizierte Zeitreihen** und lieferte `systemwide` ueber
  Fenster -- genau der Unsinn, den `timeseries.py` selbst benennt. Wird jetzt
  abgewiesen mit Verweis auf `build_timeseries()`.
- **`write_meta` stand in `__all__`, war aber nicht importiert**:
  `from system_auditor import *` warf `AttributeError`.

### Geaendert

- `next-domain` und `discover` nehmen Domaenen und Regelquellen aus der Config,
  wenn keine Argumente gegeben sind.
- `llms.txt` und `TODO.md` hingen drei Versionen zurueck (Idempotenz-Behauptung
  ohne Schreibsicherung, `audit_lock` noch gelistet, TODO auf v0.2.0). Der
  Prompt nennt jetzt die Schreibsicherung und den Config-Check als ersten
  Schritt; `report.py` zeigt das aktuelle Dateinamensmuster.

### Offen und benannt

Die Extraktion von Findings aus Prosa-Berichten fehlt weiterhin -- das Fable-
Review nennt das Modul deshalb einen "Torso mit exzellenten Einzelteilen", und
das trifft zu. Ebenso offen: wo sich die Berichte mehrerer Maschinen physisch
treffen (ohne diese Entscheidung kann strukturell kein Meta-Audit entstehen),
unsichtbare ausgefallene Fenster, unbegrenzt wachsendes `stale`. Siehe TODO.md.

136 Tests (+13), ruff sauber.

## [0.5.0] - 2026-08-15

Setzt die Modell-Funde aus Review 2 um. Leitsatz, jetzt im Konstruktor erzwungen
statt bloss dokumentiert: **Eine Ursache darf nur zuschreiben, wer genau eine
Dimension variieren laesst.**

### Geaendert -- Identifizierbarkeit

- **`full-system` ist deskriptiv** (Fund 2, kritisch). Variieren Domaene UND
  Auditor, laesst sich ein Unterschied weder der einen noch dem anderen noch
  ihrem Zusammenspiel zuordnen; die fuenf Klassen waren dort nicht
  interpretierbar. Neu: `build_inventory()` liefert eine Bestandsaufnahme
  (Belegung, Regelhaeufigkeit, Hinweis auf unvollstaendiges Raster).
  `build_meta()` auf einer deskriptiven Stufe wirft.
- **`cross-system-rater` ergaenzt** (Fund 1): Zeit+Domaene+Auditor fest, System
  variiert -- der saubere Host-Effekt. `cross-system` bleibt, sagt aber im
  Ergebnis, dass das Modell unkontrolliert ist.
- **Die stehende Stufe ist jetzt die kontrollierte** (Fund 12). Bisher war
  ausgerechnet die konfundierte Variante `always` und veroeffentlichte etwas als
  Host-Effekt, was keiner war.
- `Aggregation.__post_init__` weist inferenzielle Aggregationen mit mehr als
  einer variierenden Dimension zurueck.

### Geaendert -- ehrlichere Aussagen

- **`agreement` heisst jetzt `unanimity`** (Fund 8), dazu `pairwise_jaccard`.
  Der Nenner enthaelt nur Schluessel, die jemand gemeldet hat -- gemeinsames
  Schweigen ueber saubere Stellen geht mangels Item-Universum nicht ein. Cohens
  Kappa waere aus demselben Grund nicht berechenbar.
- **`cross-domain` behauptet keine Abwesenheit mehr** (Fund 4). Wer eine Regel
  nicht meldet, haette den fremden Ort nie abdecken koennen; solche Faelle sind
  `unverifiable` und nennen den Grund.
- **`new` und `persistent` sagen, was beobachtet wurde** (Fund 6): neues Flag
  `first_absence_verified` neben `continuity_verified`.
- **Die Richtungsangabe zaehlt den letzten Schritt** (Fund 7). `net_change` kam
  aus kumulativen Lebenslaufklassen -- ein zehn Fenster altes `resolved` zaehlte
  weiter mit. Neu: `transitions` (appeared/disappeared/unchanged) zwischen den
  letzten beiden Fenstern.
- **Nebenbefunde werden mitgefuehrt** (Fund 3): Die Klassen sind eine
  Prioritaetsprojektion, keine Partition. `MetaFinding.also` nennt die
  gleichzeitig vorliegenden Evidenzzustaende, statt die staerkere
  Negativbestaetigung zu verschweigen.
- **Die Historienbehauptung ist eingegrenzt** (Fund 11): "Historie steckt im
  Zeittoken" gilt fuer Snapshots ueber Fenstergrenzen -- nicht fuer Zeitreihen
  und nicht innerhalb eines Fensters. Wer den Trail braucht, archiviert.

123 Tests (+8), ruff sauber.

## [0.4.1] - 2026-08-15

Behebt die kritischen Funde des zweiten Codex-Reviews
(`_review/CODEX-REVIEW-2_2026-08-15.md`, Fokus Logik statt Robustheit).

### Behoben -- kritisch

- **Ein veralteter Schreiber konnte ein neueres Meta-Audit zerstoeren** (Fund 9).
  Reproduziert: Lauf A plant meta-3 aus `r1,r2,r3`; Lauf B sieht inzwischen `r4`
  und schreibt meta-4; danach schreibt A sein altes meta-3 darueber -- der
  veroeffentlichte Stand verliert `r4`. `ACTION_SKIP` konnte das nie verhindern,
  weil es nur einen Lauf stoppt, der NACH dem neueren Artefakt startet, nicht
  einen, der frueher geplant und spaeter schreibt.

  **Damit war die Begruendung fuer den vollstaendigen Lock-Verzicht in 0.4.0
  unvollstaendig.** Sie stimmte fuer die Klassifikation (deterministisch) und
  nicht fuer den Schreibvorgang. Neu: `write_meta()` liest das Ziel vor dem
  Schreiben erneut und verweigert, wenn die Datei bereits auf einer Obermenge
  der geplanten Eingaben ruht. Eine Schreibsicherung, kein Lock: ein
  Lesevorgang, blockiert niemanden, braucht keine Abstimmung.
- **`full-system` verglich Rater ueber die Regel statt ueber den Ort** (Fund 5).
  Die Aggregation deklariert `group_by=rule`, weil die Domaene variieren DARF.
  Sind die konkreten Teilnehmer aber zwei Modelle EINER Domaene, wurde
  "dieselbe Regel an verschiedenen Orten" faelschlich als Uebereinstimmung
  gewertet. `effective_group_by()` entscheidet jetzt nach dem, was in den Daten
  tatsaechlich variiert -- die deklarierte Achse sagt, was variieren darf, erst
  die Daten sagen, was variiert.

### Behoben -- wichtig

- **Dieselbe Menge in anderer Reihenfolge ergab ein anderes Artefakt** (Fund 10):
  repraesentativer Titel und `present_on`-Reihenfolge haengen von der
  Eingabereihenfolge ab. `build_meta()` ordnet die Laeufe jetzt kanonisch.
  "Deterministisch" war ohne das nicht "bitgleich".

### Offen (dem Eigentuemer vorgelegt, nicht im Alleingang geaendert)

Fund 1 (`cross-system-rater` fehlt), Fund 2 (`full-system` als Inferenz nicht
identifizierbar -- Vorschlag: nur noch deskriptive Matrix), Fund 3 (Klassen sind
Prioritaetsprojektion statt disjunkt), Fund 4 (Regelmatching kann Abwesenheit
nicht belegen), Fund 6 (`new`/`persistent` behaupten mehr als beobachtet),
Fund 7 (`net_change` zaehlt Lebenslaufklassen statt Uebergaenge), Fund 8
(Agreement ist positive Unanimity, nicht Interrater-Agreement), Fund 11
(Historienbehauptung gilt nicht fuer Zeitreihen), Fund 12 (die einzige
`always`-Stufe ist die konfundierteste).

## [0.4.0] - 2026-08-15

### Entfernt

- **Das gesamte Lock-Protokoll** (`audit_lock.py`, `protocols/audit-host-lock/`,
  die CLI-Kommandos `claim`/`claim-resolve`/`release`/`locks`).

  Gemessene Begruendung, nicht Geschmack: Die Kernlogik benutzte es nie
  (`meta.py` und `timeseries.py`: null Treffer; einziger Aufrufer war die CLI).
  Ein doppelt gerechnetes Meta-Audit ist **idempotent** -- zwei Maschinen
  erzeugen bitgleiche Klassifikation im selben Dateinamen, unterschiedlich ist
  nur das Autorenfeld. Und Doppelarbeit verhindert bereits `plan_metas` mit
  `ACTION_SKIP`, sobald das Artefakt auf denselben Eingaben ruht. Der Claim
  schuetzte damit Rechenzeit und eine moegliche Konfliktkopie, nicht die
  Korrektheit.

  Der Mechanismus ist **nicht weggeworfen, sondern verlegt**: nach
  `ellmos-ai/lock-master` (`pure-locking/contested.py`, Merge `f3dc2b7`). Dort
  ist Ausschluss der Zweck statt ein Aergernis, und dort fehlte er nachweislich
  -- `lock_create.py` legte Locks mit check-then-write an, ohne Recheck und ohne
  Konfliktregel.

### Geaendert

- Zeitstempel-Helfer (`utcnow`, `format_ts`, `parse_ts`) liegen jetzt in
  `tokens.py` statt im entfernten Lock-Modul. Sie waren nie Lock-Logik.
- Prompt, READMEs, Config und Manifest tragen die Begruendung "kein Lock noetig"
  statt der Lock-Beschreibung; veraltete CLI-Aufrufe in der Doku korrigiert.

## [0.3.1] - 2026-08-15

Behebt die Funde eines externen Reviews (Codex, `_review/CODEX-REVIEW_2026-08-15.md`:
12 Funde, davon 2 kritisch). Alle Fixes sind durch Regressionstests abgesichert.

### Behoben -- kritisch

- **Die dokumentierte Claim-Quarantaene wurde vom CLI uebersprungen.** `claim` schrieb den
  Lock und loeste sofort auf -- genau das Rennen, das SPEC-Abschnitt 6 beilegen soll: Bei
  nicht synchronisierten Verzeichnissichten sieht jeder nur seinen eigenen Lock, beide
  gewinnen. Jetzt wartet `claim` tatsaechlich (`--quarantine`, Default 300 s statt 120 s,
  weil die Spec selbst 30 s - 5 min Latenz nennt) oder gibt mit `--no-wait` an das neue
  Kommando `claim-resolve` ab.
- **Ein abgelaufener eigener Claim konnte gewinnen.** Konkurrenten wurden nach Ablauf
  gefiltert, der eigene Lock aber ungeprueft in die Sortierung gesetzt. Ein pausierter
  Prozess sah sich als fruehesten Claimant, der Gegenhost hatte ihn laengst herausgefiltert
  -- zwei Gewinner bei identischer Datenlage, ganz ohne Sync-Verzoegerung.

### Behoben -- wichtig

- `compares` wird kanonisiert: `a+b` und `b+a` bezeichnen dieselbe Menge und konkurrieren
  jetzt auch, statt beide zu gewinnen.
- **Abdeckung respektiert Pfadsegmente.** `startswith` liess `/repo/foo` den Ort
  `/repo/foobar/AGENTS.md` verschlucken -- und Abdeckung entscheidet zwischen `host_specific`
  und `unverifiable` beziehungsweise `resolved` und `unverifiable`.
- **Eine nicht abgedeckte Zwischenperiode behauptet keine Kontinuitaet mehr.** W1 vorhanden,
  W2 ungeprueft, W3 vorhanden ergab `persistent` mit der Begruendung "present in every
  window". Neues Feld `continuity_verified` und ehrliche Begruendung.
- **Chronologie folgt `window_start_utc`, nicht dem Token.** Bei expliziten Zeittabellen
  sortiert "sprint-10" vor "sprint-9"; ein alter Befund wurde dadurch als `new` gefuehrt.
- **Die Dateinamensabbildung ist jetzt injektiv.** Komponenten werden mit `--` verbunden,
  Einzelbindestriche bleiben erhalten: `["a-b","c"]` und `["a","b-c"]` ergaben denselben
  Namen und ueberschrieben sich still.
- **Unicode-Tokens ueberleben den Roundtrip.** Der Writer behielt Nicht-ASCII, der Reader
  akzeptierte nur ASCII -- ein Bericht verschwand direkt nach dem Schreiben aus Rotation
  und Buendelung.
- **Ein kaputter Fremdbericht bricht das Listing nicht mehr ab.** `findings: nope` warf
  einen `ValueError` durch `list_reports()`. Fehlt der schliessende Frontmatter-Delimiter,
  gilt der Block nicht mehr als Frontmatter.
- **Pfadsemantiken werden nicht mehr vermischt.** Kleinschreibung nur noch fuer
  case-insensitive Namensraeume (Laufwerk, UNC, gefaltetes `<HOME>`); UNC bleibt von POSIX
  unterscheidbar. Nicht aufgeloest und ausdruecklich dokumentiert: Symlinks, `..`, `~`, WSL.
- **Naive Zeitstempel gelten als UTC** statt als lokale Zeit -- sonst leiten zwei Maschinen
  mit identischer Konfiguration verschiedene Tokens ab.

### Behoben -- klein

- Zu grosse Perioden werden beim Anlegen des Rasters abgewiesen statt beim ersten
  Token-Abruf mit `OverflowError`.

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
