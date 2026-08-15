# TODO — system-auditor

Stand: 2026-08-15 · Version 0.2.0 · 86 Tests grün, ruff sauber, keine Abhängigkeiten

## Was v0.2.0 wirklich kann

- [x] **Vier Token je Audit** — `time`, `domain`, `system`, `auditor`. Identische Token =
      dieselbe Aussage, korrigiert; die neuere ersetzt die ältere (auf Dateiebene, weil der
      Name aus den Token gebildet wird).
- [x] **Zeitraster als Heartbeat** — `TimeGrid` (period + anchor) und optionale explizite
      `TimeTable`. Jede Maschine leitet denselben Token aus der Uhr ab, ohne Abstimmung.
- [x] **Aggregationsleiter** — `interrater` (Modelle, mit Übereinstimmungsquote),
      `cross-system` (Maschinen), `cross-domain` (Domänen, verglichen über die Regel statt
      über den Ort).
- [x] **Ein Meta-Audit je Fenster** — wird bei wechselnder Teilnehmerzahl in derselben
      Datei überschrieben (meta-2 → meta-3). Historie steckt im Zeittoken.
- [x] **Klassifikation** — `systemwide` / `host_specific` / `inverse` / `divergent` /
      `unverifiable`, mit Home-Pfad-Normalisierung und Vergleichbarkeits-Gate.
      Überschriften folgen der Achse.
- [x] **Audit-Host-Lock v1** — `presence` (Signal, schließt nie aus), `claim` (nur für
      Meta-Audits) mit deterministischer Verlierer-Regel.
- [x] **Erkennungskaskade** für Regelquellen — konfiguriert → Modul-Probe → Konvention →
      nichts (dann Beobachtungen statt Maßnahmen).
- [x] **Senken** — Datei-Senke, Kommando-Senke mit automatischem Rückfall.
- [x] **CLI** — `time-token`, `next-domain`, `claim`, `release`, `locks`, `meta-plan`,
      `reports`, `stale`, `discover`.

## Offen — der wichtigste Punkt zuerst

- [ ] **`meta-build`: die Pipeline ist noch nicht geschlossen.** `meta-plan` entscheidet
      zuverlässig, *ob* ein Meta-Audit fällig ist, und `build_meta()` klassifiziert
      korrekt — aber **nichts extrahiert Findings aus geschriebenen Berichten**, die sind
      Prosa. Der Agent stellt sie heute selbst zusammen. Voraussetzung für die
      Schließung: strukturierte Fundliste im Berichtskopf (siehe nächster Punkt).
- [ ] **Findings maschinenlesbar im Bericht** — `findings_detail: [{locator, rule, title}]`
      neben der Prosa, damit Meta-Audits ohne Nachlesen des Fließtexts gebaut werden können.

## Offen — vor einer Veröffentlichung

- [ ] **`prompts/AUDITOR.en.md`** — Sprachstufe Core (DE+EN) ist für veröffentlichte Repos
      Pflicht (P-006). Aktuell liegt nur die deutsche Fassung vor.
- [ ] `PRIVATE.txt`-Gate bewusst setzen oder Freigabe einholen — `visibility: private`.
- [ ] Remote anlegen und pushen (bisher nur lokal committet).

## Offen — Integration

- [ ] **`locks_dir` in die Scan-Roots** des Lock-Systems eintragen. Ohne das ist der
      Audit-Lock für Scanner und Watcher unsichtbar — genau die Lücke, aus der im Ökosystem
      am 2026-07-25 schon einmal ein Parallelsystem entstand. **Erster Schritt bei
      Übernahme, nicht später.**
- [ ] **`lock_utils.is_audit_lock()`** im Lock-System ergänzen und Audit-Locks in
      Scan/Watcher/GUI als *advisory* ausweisen.
- [ ] **Bestandsberichte** (`SIG-TU-*.md`) werden gelesen und als `legacy` geführt, tragen
      aber weder Token noch `coverage`/`clean` — sie können deshalb nicht in ein Meta-Audit
      eingehen. Beim ersten Lauf je Host mit Kopf nachziehen oder auslaufen lassen.

## Offen — Ausbau

- [ ] **Explorer-Adapter** (Beleg-A-Stufe 2/3): Coverage-/Kartenausgabe als Einstieg,
      Receipts als Beleg. Rein additiv hinter `enabled_probe`.
- [ ] **Weitere Aggregationsstufen?** Die Leiter ist generisch (fixed/varying), also wären
      z. B. „gleiche Domäne über mehrere Fenster" (Zeitreihe) oder „ein Modell über alle
      Maschinen" ohne Codeänderung definierbar. Erst bauen, wenn ein konkreter Bedarf da
      ist — nicht auf Vorrat.
- [ ] JSON-Schema für den Berichtskopf (`audit-report.v1.schema.json`).
- [ ] Protokoll `protocols/audit-host-lock/` in ein eigenes Repo heben — **erst wenn ein
      dritter Konsument existiert.** Der Schnitt liegt bereits so, dass das ein Verschieben
      ist, kein Umbau.

## Bewusst nicht gebaut

- **Gleitendes Gültigkeitsfenster.** Ersetzt durch diskrete Zeitraster: Überlappung wird
  damit zum Stringvergleich statt zur Gradfrage, die jede Maschine einzeln beurteilen muss.
- **Archivierung im Normalfluss.** Der Zeittoken im Dateinamen trägt die Historie.
  `archive()` bleibt für bewusstes Aufräumen alter Fenster.
- **Zentrales Cursor-Register.** Der Bericht *ist* der Rotationsanker; eine geteilte
  Schreibdatei wäre die Bauform, die dieses Ökosystem schon zweimal zurückbauen musste.
- **Ticket-IDs, Kategorien, Routing.** Hoheit des Ticketsystems.
- **Eigene Kartenerzeugung.** Hoheit des Explorers.
