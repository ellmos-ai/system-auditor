# FABLE-Review: Benutzbarkeit und Betriebsreife von system-auditor v0.5.0

**Datum:** 2026-08-15
**Scope:** Benutzbarkeit (Prompt ↔ CLI ↔ Bibliothek), die ungeschlossene Findings-Schleife, Benennung, Betriebslücken, Doku-Ehrlichkeit. Ausdrücklich **nicht** erneut geprüft: die 24 Funde aus `_review/CODEX-REVIEW_2026-08-15.md` und `_review/CODEX-REVIEW-2_2026-08-15.md` (beide gelesen; Stichproben bestätigen, dass die Fixes im Code stehen und getestet sind).
**Verifikation:** `python -m pytest -q` → 123 bestanden. Alle als „verifiziert" markierten Funde wurden zusätzlich mit isolierten Python-Sonden reproduziert. Nicht geprüft: echtes Mehr-Host-Verhalten auf einem synchronisierten Ordner und der Kommando-Senkenpfad gegen ein reales Ticketsystem — dafür fehlt in dieser Umgebung das Gegenüber.

---

## 1. Ist das Ding benutzbar?

Kurzantwort: Als **Bibliothek** ja, als **Werkzeug für einen Agenten mit dem Prompt** nein — und zwar nicht an einer Stelle, sondern an drei aufeinanderfolgenden.

### Fund 1 — Die Config wird von nichts geladen (kritisch)

- **Datei:Zeile:** `src/system_auditor/cli.py` (gesamt — kein `--config`-Flag, `build_parser()` Z. 159–206), `config/system-auditor.config.example.json:1` („Kopieren nach system-auditor.config.json und anpassen")
- **Was passiert:** Es gibt im gesamten `src/` **kein einziges `json.load`** (per Grep verifiziert). Die Bibliothek nimmt config-förmige Dicts entgegen (`resolve_policy(config)`, `discover(policy_stores=…)`), aber nichts liest die Datei, die README (`README.md:179`) und Prompt als Konfigurationsweg benennen. Konsequenzen im Einzelnen:
  - `aggregations` (Config Z. 23–31) wirkungslos: `cmd_meta_plan` (`cli.py:71`) ruft `due_aggregations(requested=…)` ohne Policy → immer `DEFAULT_POLICY`. Wer per Config `timeseries` auf `always` stellt oder `timeseries-rater` einschaltet, ändert über das CLI nichts.
  - `time_grid`/`time_table` (Config Z. 14–21) wirkungslos: siehe Fund 2.
  - `policy_stores`/`decision_stores`/`known_modules`/`convention_max_depth` wirkungslos: `cmd_discover` (`cli.py:140`) ruft `discover(args.domain_path)` ohne alles — die Stufen 1 (konfiguriert) und 2 (Modul-Probe) der eigenen Erkennungskaskade sind **über das CLI unerreichbar**; nur Stufe 3 (Konvention) funktioniert. Der Prompt sagt „`discover … ` bzw. die Config" (`AUDITOR.de.md:73`) — das „bzw. die Config" trägt die ganze Last und ist nicht implementiert.
  - `measure_sink` (Config Z. 82–87), `domain_selector_command` (Z. 50): kein Konsument, kein Subcommand (Grep: `domain_selector` kommt in `src/` nicht vor).
- **Warum schlimm:** Die Config-Datei ist der ausführlichste, sorgfältigst kommentierte Teil der Doku — und sie ist derzeit ein Versprechen ohne Empfänger. Jeder Wert, den ein Nutzer dort einträgt, verpufft still.

### Fund 2 — Der CLI-Default-Anker zerstört genau die Determinismus-Garantie, für die das Zeitraster existiert (kritisch, verifiziert)

- **Datei:Zeile:** `src/system_auditor/cli.py:38` (`anchor = utcnow().replace(hour=0, minute=0, second=0)`) gegen `src/system_auditor/tokens.py:167` (Bibliotheks-Default: fester Montag 2026-01-05)
- **Was passiert:** Der dokumentierte Aufruf `system-auditor time-token --period 7d` (`README.md:162`, `AUDITOR.de.md:38`) baut das Raster mit **Anker = Mitternacht des Aufruftags**. Damit ist der Token immer das Datum des Laufs. Sonde: Für Montag und Mittwoch derselben Woche liefert die Bibliothek `20260810`/`20260810`, der CLI-Weg `20260810`/`20260812`. Zwei Maschinen (oder dieselbe Maschine an zwei Tagen) landen nie im selben Fenster; `cmd_meta_plan` (`cli.py:70`) filtert anschließend auf den Tages-Token und findet folglich **nur gleichtägige** Audits. Das 7-Tage-Fenster degeneriert im dokumentierten Weg zu Ein-Tages-Fenstern.
- **Warum schlimm:** „Zwei Maschinen leiten ohne Abstimmung denselben Token ab" (`tokens.py:17–20`, README Z. 69–74, Config Z. 18) ist das Fundament des Moduls — und der einzige ausgelieferte Aufrufweg bricht es. Die Rettung (`--anchor` auf allen Maschinen identisch setzen) steht in keinem Beispiel und in keinem Prompt-Schritt; die Config, die den Anker trägt, wird nicht gelesen (Fund 1). Kein Test deckt das ab, weil es **keinerlei CLI-Tests** gibt (Grep über `tests/`: kein `cli`-Import).

### Fund 3 — Die protokollkritischen Schritte haben kein Kommando (wichtig)

- **Datei:Zeile:** `cli.py:1–7` (Anspruch: „every subcommand maps to one library function, so an agent … never reimplements protocol logic by hand"), `AUDITOR.de.md:46–47` (a0), `:121–127` (f), `:136–151` (g)
- **Was passiert:** Genau die Schritte, in denen etwas **geschrieben** wird, sind nicht im CLI:
  - **Bericht schreiben** (Prompt-Schritt f): kein Subcommand. Der Agent muss `write_report()` per Python aufrufen oder die Datei von Hand bauen — und weder Prompt noch README nennen das Dateinamensformat oder die Frontmatter-Syntax. Die Doppel-Bindestrich-Konvention steht nur im Code (`report.py:120–124`); wer nach dem **Docstring** desselben Moduls geht (`report.py:7`: `AUDIT-<time>-<domain>…`, einfacher Bindestrich!), erzeugt eine Datei, die die Legacy-Regex fängt und als `legacy` mit Vergleichbarkeits-Vorbehalt führt. „Setze deinen Auditor-Token" (`AUDITOR.de.md:46`) nennt kein Wie.
  - **Maßnahmen ausgeben** (f): `emit()` existiert nur als Bibliothek; `measure_sink` wird nie gelesen (Fund 1).
  - **Meta-Audit bauen und schreiben** (g): kein `meta-build`-Subcommand. Der Weg `build_meta` → `render_markdown` → `write_meta` ist Bibliotheksarbeit — und `write_meta` ist nicht einmal aus der Paketwurzel erreichbar (Fund 4).
- **Warum schlimm:** Der Prompt beschreibt einen Ablauf, von dem das Werkzeug nur die **lesenden** Hälften trägt (`time-token` — mit Fund 2 —, `next-domain`, `discover` Stufe 3, `meta-plan`, `stale`). Der cli.py-Docstring behauptet das Gegenteil dessen, was ausgeliefert ist.

### Fund 4 — `write_meta` steht in `__all__`, wird aber nicht importiert (klein, verifiziert)

- **Datei:Zeile:** `src/system_auditor/__init__.py:44–61` (Importblock ohne `write_meta`/`WriteOutcome`) gegen `__init__.py:171` (`"write_meta"` in `__all__`)
- **Was passiert:** `system_auditor.write_meta` existiert nicht (`hasattr` → False); `from system_auditor import *` bricht mit `AttributeError`. Ausgerechnet die Schreibsicherung — der zentrale Fix aus Review 2, Fund 9 — ist nur über `system_auditor.meta` erreichbar, während das ungeschützte `write_report` prominent exportiert ist. Wer der README folgt („`write_meta` re-reads the target…", `README.md:145–147`) und naheliegend aus dem Paket importiert, scheitert oder weicht auf `write_report` aus — und hat den Guard dann nicht.

---

## 2. Die ungeschlossene Schleife

`TODO.md:30–36` benennt das Problem selbst korrekt („meta-build: die Pipeline ist noch nicht geschlossen … nichts extrahiert Findings aus geschriebenen Berichten"). Meine Aufgabe ist die Bewertung, nicht die Wiederentdeckung. Bewertung:

**Es ist schlimmer, als der TODO-Eintrag klingt, weil die Lücke die Kernversprechen entwertet, nicht nur einen Arbeitsschritt.** Der Berichtskopf trägt `findings` als **Zahl** (`report.py:162`, Roundtrip-Test `tests/test_report.py:44`), die Klassifikation braucht `Finding`-Objekte mit `locator`/`rule` (`compare.py:122–141`). Dazwischen liegt Prosa. Das heißt konkret:

1. **„Deterministisch, byte-gleich" gilt nur unterhalb der Stelle, an der Daten real eintreten.** Zwei Maschinen, die denselben fremden Prosa-Bericht unabhängig in `Finding`-Objekte übersetzen (verschiedene Locator-Schreibweisen, verschiedene Regel-Formulierungen — `norm_rule` ist nur `strip().lower()`, `compare.py:136`), erzeugen verschiedene „deterministische" Artefakte. Die kanonische Ordnung aus 0.4.1 ordnet Läufe, nicht Interpretationen.
2. **Die Schreibsicherung sieht die Divergenz nicht:** `write_meta` vergleicht `inputs` (Run-IDs), nicht Inhalte (`meta.py:360–376`). Zwei inhaltlich verschiedene Meta-3 über denselben drei Run-IDs gelten einander als „already current" bzw. überschreiben sich wechselseitig als vermeintliche Restatements.
3. **Jeder Meta-Bericht ist damit ein Unikat seines Erstellers** — genau die Eigenschaft, die das Modul mit dem Auditor-Token bei Einzelaudits sorgfältig kontrolliert, kehrt beim Meta-Audit unkontrolliert wieder: Wer klassifiziert hat, hängt davon ab, welches Modell die Prosa gelesen hat, und wird nirgends festgehalten (der Meta-Header hat kein Auditor-Feld im Dateinamen, bewusst — aber der Extraktions-Bias existiert trotzdem).

**Ist das Modul ohne den Baustein einsetzbar?** Als Torso mit exzellenten Einzelteilen — ja für Einzelaudits (Tokens, Rotation, Berichte, Discovery, Senken tragen), nein für den beworbenen Zweck. README-Titel und -Kernnutzen („Comparing the valid audits … yields a classification no single run can produce", `README.md:27–29`) beschreiben die Meta-Hälfte, und die ist heute Demonstration, nicht Betrieb. Der TODO-Folgeeintrag (`findings_detail: [{locator, rule, title}]` im Kopf, `TODO.md:35–36`) ist der richtige Fix und sollte **vor** jeder weiteren Modellverfeinerung kommen — jede weitere Review-Runde über Klassifikationsfeinheiten poliert sonst eine Maschine, in die niemand Material einfüllen kann.

---

## 3. Begriffe und Benennung

### Fund 5 — Die Bilanz-Zeile druckt die Rohklassennamen auf jeder Achse (wichtig, verifiziert)

- **Datei:Zeile:** `compare.py:569` (`"**Bilanz:** " + … for name in CLASS_ORDER`), Überschriften-Anpassung dagegen `compare.py:504–535`
- **Was passiert:** Sonde mit `INTERRATER`: Das gerenderte Artefakt enthält wörtlich `**Bilanz:** systemwide: 0 · host_specific: 1 · …` — auf der Auditor-Achse, wo `host_specific` „nur von einzelnen Auditoren gesehen" bedeutet. Die Doku-Antwort „die Überschriften passen sich an" reicht also nicht: Die Bilanz-Zeile, `MetaResult.counts`, `of_class()` und jeder JSON-Konsument sehen die System-Vokabel. Ein Mensch, der im Interrater-Bericht „host_specific: 3" liest, sucht Maschinen-Drift, wo Rater-Divergenz steht.
- **Einordnung zur gestellten Frage:** Ja, das ist eine Falle für jeden, der Feldnamen statt Überschriften liest — und Feldnamen liest jeder, der das Artefakt maschinell weiterverarbeitet, also genau die Zielgruppe eines Ticket-/Dashboard-Anschlusses. Achsenneutrale Klassennamen (`unanimous`/`partial`/`contradicted`/…) oder achsengebundene Aliasse im Header wären tragfähiger als die Konvention „denk dir die Überschrift dazu".

### Fund 6 — `build_meta` akzeptiert die Zeitreihen-Aggregation und liefert dann genau den Unsinn, den das Modul selbst als Unsinn bezeichnet (wichtig, verifiziert)

- **Datei:Zeile:** `compare.py:464–471` (Guard prüft nur `is_inferential`), `tokens.py:99` (`INFERENTIAL_KINDS = (KIND_SNAPSHOT, KIND_TIMESERIES)`), `timeseries.py:4–7` („The snapshot classes would be nonsense here")
- **Was passiert:** Sonde: `build_meta(runs, TIMESERIES)` über zwei Fenster wirft nicht, sondern liefert `('systemwide', 'every participant found it')` mit Teilnehmern `['20260803', '20260810']`. Zusätzlich fällt `headings_for("time")` auf die **System**-Überschriften zurück (`compare.py:534–535`), sodass das Artefakt „Systemweit (echte Systeminkonsistenz)" über Zeitfenster behauptet. Der Konstruktor-Zwang („genau eine Dimension variiert") ist erfüllt — aber die Trennung Snapshot-Klassen vs. Zeitreihen-Klassen, die dieselbe Doku als hart verkauft, ist nur eine Konvention zwischen zwei Funktionen. Symmetrisch fehlt in `build_timeseries` jeder Kind-Check.
- **Fix-Richtung:** `build_meta` sollte `KIND_TIMESERIES` genauso abweisen wie `KIND_DESCRIPTIVE` („use build_timeseries()"), und umgekehrt.

### Fund 7 — Kleinere Benennungsreibungen (klein)

- `ReportHeader.findings` ist eine **Zahl** (`report.py:162`), `AuditRun.findings` eine **Liste von Finding-Objekten** (`compare.py:148`) — dieselbe Vokabel für die beiden Enden der fehlenden Brücke aus Punkt 2. Wer die Schleife eines Tages schließt, stolpert zuerst hierüber.
- Zwei `render_markdown` (Snapshot `compare.py:538`, Zeitreihe `timeseries.py:293`); die Paketwurzel exportiert kommentarlos nur die Snapshot-Variante (`__init__.py:41`).
- Drei unverwandte „mode"-Vokabulare im Paket: `audit_mode` (self/meta), Policy-`mode` (always/on_demand/off), `Sink.kind` — verkraftbar, aber `MODE_SELF` neben `MODE_ALWAYS` im selben Namensraum (`__init__.py`) lädt zum Verwechseln ein.

---

## 4. Was fehlt, das niemand vermisst hat

### Fund 8 — Es gibt keinen Treffpunkt: das dokumentierte `reports_dir` ist host-lokal (kritisch als Konzeptlücke)

- **Datei:Zeile:** `config/system-auditor.config.example.json:37–39` (`reports_dir: <HOME>/.system-auditor/reports`), README/Prompt: keine Silbe zum Transport
- **Was passiert:** Jede Aggregation braucht ≥ 2 Teilnehmer **im selben Verzeichnis** (`meta.py:46`, `find_bundles`). `<HOME>` expandiert pro Host — im ausgelieferten Default sieht keine Maschine je die Audits einer anderen; `meta-plan` liefert strukturell nie ein Bündel. Nirgendwo (README, Prompt, Config, TODO) steht, **wie** die Berichte mehrerer Maschinen zusammenkommen: gemeinsamer Sync-Ordner? Welcher? Wer kopiert? Dabei hängt an der Antwort mehr als Bequemlichkeit: Die Schreibsicherung (`write_meta`, read-then-write) ist auf einem eventual-consistent Sync-Ordner nur so gut wie dessen Sichtbarkeitslatenz — dieselbe Latenzklasse, an der laut Review 1 das Claim-Protokoll scheiterte. Das Modul hat seine stärkste Annahme (ein gemeinsames, hinreichend frisches Verzeichnis) nie ausgesprochen und nie spezifiziert.

### Fund 9 — `stale` wird in Monat drei unbrauchbar (wichtig)

- **Datei:Zeile:** `meta.py:309–323` (`stale_windows`)
- **Was passiert:** Zurückgegeben wird **jedes** Self-Audit mit `time_token != current` — für immer. Ein Audit, das längst durch ein aktuelles Fenster erneuert wurde, bleibt trotzdem gelistet, weil die alte Datei als Historie stehen bleibt (gewollt). Nach 12 Wochen × 3 Domänen × 2 Maschinen listet der Befehl bei jedem Aufruf Dutzende „Kandidaten für einen Refresh", von denen fast alle keine sind. Es fehlt die Deduplizierung „neuestes Audit je (domain, system, auditor), und nur wenn dessen Fenster nicht das aktuelle ist". Gleiche Wachstumsmechanik trifft `list_reports` (`report.py:367–382`): Volltext-Lesen **aller** Dateien bei jedem Kommando, auf einem synchronisierten Ordner zunehmend teuer — und `reports/` kennt keinerlei Kompaktierung im Normalfluss (`archive()` ist bewusst außerhalb, hat aber auch kein CLI).

### Fund 10 — Ein komplett ausgefallenes Fenster ist unsichtbar; „persistent" überspringt es mit `continuity_verified=True` (wichtig, verifiziert)

- **Datei:Zeile:** `timeseries.py:144–148` (Fensterliste entsteht nur aus vorhandenen Läufen)
- **Was passiert:** Sonde: W1 auditiert, W2 **gar nicht auditiert** (kein Lauf), W3 auditiert → Ergebnis `persistent`, `continuity_verified=True`, „present in every window since 20260803 (2 windows)". Der 0.5.0-Fix für unbekannte Zwischenfenster greift nur, wenn für das Fenster ein Lauf existiert, der den Ort nicht abdeckte; ein Fenster ohne jeden Lauf existiert für die Serie nicht. Das ist die realistischere Lücke — Maschinen setzen Wochen aus. Das `TimeGrid` könnte fehlende Fenster benennen (Anker + Periode sind bekannt), wird aber nie befragt. In Monat drei erzählen die Zeitreihen lückenlose Kontinuität über Urlaubswochen.

### Fund 11 — `window_start_utc` wird von niemandem befüllt, also fällt die Chronologie in der Praxis auf den Token zurück (wichtig)

- **Datei:Zeile:** Feld `report.py:154`, Verwendung `timeseries.py:122–132`; Grep über `cli.py`, `prompts/AUDITOR.de.md`, `README.md`, `config/*.json`: **kein Vorkommen**
- **Was passiert:** Der 0.3.1-Fix „Chronologie folgt `window_start_utc`, nicht dem Token" existiert nur, wenn das Feld im Bericht steht. Kein Prompt-Schritt, keine README-Zeile, kein Config-Kommentar weist an, es zu schreiben; `time-token` zeigt `window_start` zwar an (`cli.py:50–56`), sagt aber nicht, dass es in den Berichtskopf gehört. Ein TimeTable-Nutzer mit `sprint-9`/`sprint-10` (das Motivbeispiel des Fixes!) landet ohne dieses Wissen exakt wieder im gefixten Fehler — der Fix ist implementiert, aber nicht in den Nutzungsweg verdrahtet.

### Fund 12 — Die Konventions-Suche überspringt `.github` (klein, verifiziert)

- **Datei:Zeile:** `discovery.py:200` (`entry.name.startswith(_SKIP_DIRS)` — Tupel-startswith als **Präfix**-Test auf Verzeichnisnamen)
- **Was passiert:** `".github".startswith(".git")` → True; das Verzeichnis wird übersprungen. Sonde: `.github/SECURITY.md` wird nicht gefunden, obwohl `SECURITY.md` und `CONTRIBUTING.md` in `CONVENTION_NAMES` stehen (`discovery.py:48–49`) und konventionell genau dort liegen. Gleiches Muster trifft jedes Verzeichnis, dessen Name mit `_archive`, `.venv` etc. nur **beginnt** (`_archive-important` wurde in der Sonde ebenfalls übersprungen). Gemeint war offensichtlich Namensgleichheit, nicht Präfix.

### Fund 13 — Testlücken jenseits der Codex-Listen (klein)

Kein einziger Test importiert `cli` (Grep) — Fund 2 und die toten Config-Pfade konnten deshalb nicht auffallen. Es gibt keinen End-to-End-Test „geschriebener Bericht → Meta-Artefakt": alle `Finding`-Objekte in den Tests werden direkt konstruiert (66 Fundstellen, nie aus einer Datei) — der Test-Korpus spiegelt damit exakt die Lücke aus Punkt 2.

---

## 5. Ist die Dokumentation ehrlich?

Der README ist bemerkenswert ehrlich (die „No lock"-Sektion trägt die eigene Korrekturgeschichte offen, `README.md:131–152`; das Badge „123 passed" stimmt). Die Ehrlichkeit ist aber **ungleich verteilt** — je näher ein Dokument am Agenten ist, desto veralteter:

- **`prompts/AUDITOR.de.md:65` und `:147–149`** wiederholen die vor-0.4.1-Begründung wörtlich: „doppelte Meta-Läufe sind idempotent … Kein Claim nötig … ist das Ergebnis identisch … landet in derselben Datei. Wer später kommt, bekommt … `skip`." Die Schreibsicherung (`write_meta`), die genau diese Aussage laut CHANGELOG 0.4.1 als unvollständig erwiesen hat, kommt im Prompt **nicht vor**. Der Agent, der danach handelt, schreibt mit `write_report` ungeschützt.
- **`AUDITOR.de.md:145–146`**: „Die Historie steckt schon im Zeittoken des Dateinamens — es muss nichts archiviert werden." Von 0.5.0 (Review-2-Fund 11) ausdrücklich eingegrenzt (`meta.py:10–22`: gilt nicht für Zeitreihen, nicht innerhalb eines Fensters); der Prompt trägt die alte Vollversion.
- **`AUDITOR.de.md:131–133` gegen `:180`**: Die ausführbaren Schritte lassen den Agenten `cross-system` und `interrater` abfragen; zwei Absätze später steht korrekt „Stehend ist `cross-system-rater`, nicht `cross-system`". Der Aufruf, der die stehende Stufe baute (`meta-plan` ohne `--aggregation`), kommt im Ablauf nicht vor — wer den Prompt befolgt, baut das Standing-Artefakt nie. Gleiche veraltete Kommandos in `README.md:171–172`.
- **`llms.txt`** behauptet im Kopf „Version: 0.5.0" (Z. 4) und beschreibt dann drei Versionen Vergangenheit: „Einzelaudits haben ein Gueltigkeitsfenster … das alte wird archiviert" (Z. 22–23; Gültigkeits-Spanne und Archivierung sind seit 0.2.0 raus), die ungeschützte Idempotenz-Begründung (Z. 29–31) und `audit_lock` in der Modulliste (Z. 38; seit 0.4.0 gelöscht).
- **`TODO.md:3`**: „Version 0.2.0"; `TODO.md:20–26` führt „Audit-Host-Lock v1" und die CLI-Kommandos `claim`/`release`/`locks` als vorhandene Features — alles in 0.4.0 entfernt.
- **`report.py:7` und `:11`**: Die Docstring-Dateinamensmuster zeigen den **einfachen** Bindestrich (`AUDIT-<time>-<domain>…`, `META-<kind>-<time>…`) — im selben Modul, das drei Bildschirmseiten tiefer den Doppel-Bindestrich als Injektivitäts-Fix einführt (`report.py:120–124`, Regex Z. 44–47). Wer den Docstring als Format-Spezifikation liest (mangels anderer Spezifikation naheliegend, siehe Fund 3), erzeugt Legacy-Dateien.
- **`config/system-auditor.config.example.json:9`**: „Er landet im Dateinamen von Lock und Bericht" — es gibt keinen Lock mehr.

Muster: Der Code und der README wurden durch zwei Review-Runden diszipliniert nachgeführt; **Prompt, llms.txt und TODO haben keine der drei letzten Versionen mitgemacht.** Das ist gefährlicher als gar keine Doku, weil gerade der Prompt das Dokument ist, das ein Agent wörtlich ausführt.

---

## 6. Die eine Frage an den Autor

**„In welchem Verzeichnis begegnen sich die Audits der beteiligten Maschinen — und über welchen Transport mit welcher Sichtbarkeitslatenz?"**

Warum diese Frage: Jede zentrale Designentscheidung — Fenster-Tokens statt Abstimmung, Überschreiben statt Archiv, Schreibsicherung statt Lock, `min_participants ≥ 2` — setzt stillschweigend ein gemeinsames, hinreichend frisch synchronisiertes `reports_dir` voraus. Die ausgelieferte Config zeigt auf ein host-lokales Verzeichnis (Fund 8), in dem der Produktkern strukturell nie eintreten kann; und sobald es ein Sync-Ordner ist, bestimmen dessen Latenz und Konfliktkopien-Verhalten, wie viel die read-then-write-Sicherung von `write_meta` wirklich wert ist — dieselbe Eigenschaft, an der das frühere Claim-Protokoll nachweislich scheiterte. Die Antwort entscheidet, ob das Modul fertig gedacht ist oder ob ihm neben dem Findings-Extraktor (Punkt 2) noch ein zweites, nie erwähntes Fundament fehlt.

---

## Was gut ist

Das Vier-Token-Modell mit erzwungener Identifizierbarkeitsregel im Konstruktor, die Fail-open-Parser, die Ehrlichkeitsmechanik (`unverifiable`, `continuity_verified`/`first_absence_verified`, `also[]`, benannte unkontrollierte Dimensionen) und die getestete Schreibsicherung sind sauber gebaut, und der README dokumentiert eigene Irrtümer offener, als man es je liest — ein Satz genügt: Das Fundament verdient den Ausbau.

---

## Gesamturteil

Nach zwei Runden Robustheit und Logik ist das Innere des Moduls solide, aber der Weg hinein ist es nicht: Die Config wird von nichts gelesen, der CLI-Standardanker bricht die Kern-Garantie identischer Zeittoken, und die schreibenden Protokollschritte (Bericht, Senke, Meta) haben weder Kommando noch dokumentiertes Format — ein Agent mit `AUDITOR.de.md` kann den beschriebenen Lauf heute nicht werkzeuggestützt zu Ende führen und handelt an drei Stellen nach widerrufenen Behauptungen. Die Meta-Hälfte bleibt zudem ein Torso, solange nichts Findings aus Berichten extrahiert und nirgends definiert ist, wo sich die Berichte mehrerer Maschinen physisch treffen; beide Lücken sind bekannt bzw. benennbar, aber sie entwerten derzeit genau die Versprechen (Determinismus, eine gültige Antwort je Fenster), die der README ins Schaufenster stellt. Empfohlene Reihenfolge: erst `findings_detail` + `meta-build` + Config-Loader + fester CLI-Anker und den Prompt auf 0.5.0-Stand heben — dann erst weitere Modellverfeinerung.
