# CODEX-Review: system-auditor v0.3.0

**Datum:** 2026-08-15  
**Umfang:** `tokens`, `report`, `meta`, `compare`, `timeseries`, `audit_lock`, `discovery`, `sinks`, vollständige Testsuite und `protocols/audit-host-lock/SPEC.md`  
**Verifikation:** `python -m pytest -q` → 114 bestanden; `ruff check src tests` → sauber. Die folgenden Grenzfälle wurden zusätzlich mit isolierten Python-Sonden reproduziert.

## Funde

### 1. Die dokumentierte Claim-Quarantäne wird vom CLI nicht ausgeführt

- **Datei:Zeile:** `src/system_auditor/cli.py:80`, `src/system_auditor/cli.py:110`, `protocols/audit-host-lock/SPEC.md:138`
- **Was passiert:** §6 verlangt Schreiben, Quarantäne, erneutes Lesen und erst danach die Entscheidung. `cmd_claim()` schreibt dagegen den Lock und ruft unmittelbar `resolve_claim()` auf. Bei zwei gleichzeitig startenden Hosts mit noch nicht synchronisierten Verzeichnissichten sieht jeder nur den eigenen Lock; beide erhalten `won=True` und beginnen das Meta-Audit. Zusätzlich nennt die Spezifikation 30 Sekunden bis 5 Minuten typische Latenz, setzt die Standardquarantäne aber auf nur 120 Sekunden und bezeichnet sie als länger als die typische Latenz.
- **Warum falsch:** Genau der normale Race-Fall, den §6 lösen soll, bleibt im dokumentierten CLI-Weg ungelöst. Die Aussage „Claims sind gegenseitig exklusiv“ gilt damit nicht.
- **Schweregrad:** **kritisch**

### 2. Ein abgelaufener eigener Claim kann bei identischer Datenlage zwei Gewinner erzeugen

- **Datei:Zeile:** `src/system_auditor/audit_lock.py:327`, `src/system_auditor/audit_lock.py:333`
- **Was passiert:** `list_locks(..., now=...)` entfernt abgelaufene Locks aus den Konkurrenten, `mine` wird anschließend aber ungeprüft wieder in `sorted([mine, *competitors])` eingesetzt. Reproduktion: H1 ist älter und abgelaufen, H2 ist jünger und aktiv. H1 bewertet den eigenen abgelaufenen Lock als frühesten Gewinner; H2 filtert H1 heraus und sieht ebenfalls keinen verlierenden Grund. Ergebnis: `True, True` gegen denselben Verzeichnisstand und denselben Zeitpunkt.
- **Warum falsch:** Das bricht den stärksten Determinismus-Anspruch sogar ohne Sync-Verzögerung. Ein pausierter Prozess, der nach Ablauf seines Locks fortsetzt, darf keine Schreibberechtigung mehr erhalten.
- **Schweregrad:** **kritisch**

### 3. `compares` wird nicht als Eingabemenge kanonisiert oder validiert

- **Datei:Zeile:** `src/system_auditor/cli.py:90`, `src/system_auditor/cli.py:258`, `src/system_auditor/audit_lock.py:328`, `protocols/audit-host-lock/SPEC.md:146`
- **Was passiert:** Die Spezifikation fordert eine sortierte Eingabemenge, CLI und Bibliothek übernehmen aber beliebigen Text und vergleichen ihn bytegenau. `a+b` und `b+a` repräsentieren dieselbe Menge, konkurrieren jedoch nicht; beide Seiten gewinnen. Umgekehrt ist `--compares` optional und standardmäßig leer, sodass Claims über verschiedene, nicht benannte Eingabemengen fälschlich konkurrieren.
- **Warum falsch:** Die Exklusivität hängt von einer ungesicherten Darstellungskonvention ab, obwohl die öffentliche Schnittstelle diese Konvention weder erzwingt noch prüft.
- **Schweregrad:** **wichtig**

**Sauber gelöst:** Sind alle Claims aktiv, sichtbar, gleich kanonisiert und wird derselbe Zeitpunkt verwendet, erzeugt die Sortierung nach `(created, host)` genau einen Gewinner; einen Fall, in dem bei diesem gültigen gemeinsamen Stand beide aufgeben, habe ich nicht gefunden.

### 4. Eine Präfixkollision erzeugt `host_specific` beziehungsweise `resolved` ohne echte Abdeckung

- **Datei:Zeile:** `src/system_auditor/compare.py:108`, `src/system_auditor/compare.py:111`, `src/system_auditor/timeseries.py:117`
- **Was passiert:** `covers()` verwendet `target.startswith(prefix)` ohne Segmentgrenze. Damit gilt die Abdeckung `/repo/foo` auch für den Befund `/repo/foobar/AGENTS.md`. In der Snapshot-Reproduktion wurde der zweite Host deshalb als „geprüft ohne Befund“ gezählt und die Klasse `host_specific` vergeben; korrekt wäre `unverifiable`. Derselbe Fehler kann in der neuesten Zeitreihe `resolved` erzeugen, obwohl der tatsächliche Ort nie geprüft wurde.
- **Warum falsch:** Ein bloßes Zeichenpräfix ist keine Pfadvorfahrbeziehung. Dadurch werden genau die beiden evidenzabhängigen Klassen zu stark vergeben, vor denen das Modul schützen soll.
- **Schweregrad:** **wichtig**

### 5. Eine unbekannte Zwischenperiode wird als durchgehend `persistent` ausgegeben

- **Datei:Zeile:** `src/system_auditor/timeseries.py:177`, `src/system_auditor/timeseries.py:195`
- **Was passiert:** Nur eine unbekannte **neueste** Periode führt zu `unverifiable`. Für W1 = vorhanden, W2 = nicht abgedeckt, W3 = vorhanden prüft `_classify_trend()` ausschließlich echte Abwesenheiten in `absent`; W2 in `unknown` wird ignoriert. Das Ergebnis lautet `persistent` mit der Begründung „present in every window“, obwohl W2 gerade nicht verifiziert ist.
- **Warum falsch:** `persistent` behauptet eine lückenlose Beobachtung, die nicht vorliegt. `recurring` wäre ebenfalls unbelegt; korrekt ist eine unverifizierbare Kontinuität oder eine eigene Klasse mit Vorbehalt.
- **Schweregrad:** **wichtig**

### 6. Zeitreihen bestimmen „neueste Periode“ durch Sortierung des Token-Texts

- **Datei:Zeile:** `src/system_auditor/timeseries.py:94`, `src/system_auditor/tokens.py:149`
- **Was passiert:** `build_timeseries()` sortiert nach `header.time_token`. `TimeTable` erlaubt jedoch beliebige Tokens und speichert keine Sortieranforderung. Deshalb liegt etwa `sprint-10` lexikografisch vor `sprint-9`; in der Reproduktion mit `z-old` und `a-new` wurde ein tatsächlich alter Befund als `new` statt als `resolved` klassifiziert.
- **Warum falsch:** Der Token ist eine Identität, kein verlässlicher Zeitstempel. Sämtliche Aussagen über „latest“, `new` und `resolved` können bei expliziten Tabellen auf die falsche Periode bezogen werden.
- **Schweregrad:** **wichtig**

**Sauber gelöst:** Bei sortierbaren `TimeGrid`-Tokens und korrekt segmentierter Abdeckung vergibt `_classify_trend()` `resolved` nur, wenn die neueste beobachtete Periode den Ort abdeckt und keinen Befund enthält.

### 7. Die Dateinamensabbildung ist nicht injektiv; verschiedene Fixed-Keys überschreiben einander

- **Datei:Zeile:** `src/system_auditor/report.py:116`, `src/system_auditor/report.py:198`, `src/system_auditor/report.py:207`
- **Was passiert:** `_slug()` ersetzt viele verschiedene Zeichen durch `-`, und `meta_filename()` verbindet bereits bindestrichhaltige Komponenten wieder mit `-`; leere Komponenten werden ausgelassen. Reproduzierte Kollisionen sind `a/b` gegen `a?b` sowie die Schlüssel `['a-b', 'c']` gegen `['a', 'b-c']`. Auch `['', '20260810']` und `['20260810', '']` verlieren ihre Positionstrennung. Dieselbe Slug-Kollision betrifft Self-Reports.
- **Warum falsch:** „Gleicher Fixed-Key → gleicher Dateiname“ gilt zwar für harmlose Eingaben, aber die notwendige Umkehrung gilt nicht: verschiedene Fixed-Keys können denselben Dateinamen erhalten und sich still überschreiben.
- **Schweregrad:** **wichtig**

### 8. Ein eigener Report mit Unicode-Token wird geschrieben, danach aber nicht mehr erkannt

- **Datei:Zeile:** `src/system_auditor/report.py:44`, `src/system_auditor/report.py:116`, `src/system_auditor/report.py:236`
- **Was passiert:** `_slug()` behält jedes Unicode-Zeichen bei, für das `isalnum()` gilt; die Erkennungsregex erlaubt nur ASCII. Ein Report mit Domäne `münchen` wird als `AUDIT-20260810-münchen.H1.md` geschrieben, `read_report()` liefert für diese eigene Datei anschließend `None`.
- **Warum falsch:** Writer und Reader akzeptieren unterschiedliche Sprachen. Der Bericht verschwindet aus Rotation, Bundling und Meta-Audit, obwohl das Schreiben erfolgreich war.
- **Schweregrad:** **wichtig**

**Sauber gelöst:** Ein nichtleerer, bereits dateinamenssicherer ASCII-Schlüssel erzeugt stabil denselben Namen; ein Domänenname, der lediglich wie ein Zeittoken aussieht, ist ohne leere oder kollidierende Nachbarkomponente nicht mehrdeutig.

### 9. Ein kaputter Fremdbericht kann das gesamte Listing abbrechen

- **Datei:Zeile:** `src/system_auditor/report.py:82`, `src/system_auditor/report.py:107`, `src/system_auditor/report.py:298`, `src/system_auditor/report.py:317`
- **Was passiert:** I/O- und UTF-8-Fehler werden übersprungen, Typfehler in gültig benannten Dateien aber nicht. `findings: nope` löst bei `int(...)` einen `ValueError` aus, der durch `list_reports()` propagiert und den gesamten Lauf abbricht. Fehlt der schließende Front-Matter-Delimiter, liest der Parser außerdem den Dokumentkörper weiter; ein späteres `findings: nope` überschreibt den zunächst gültigen Wert. Leere skalare Felder werden als Liste `[]` interpretiert und später beispielsweise als String `"[]"` für `run_id` zurückgegeben.
- **Warum falsch:** Ein einzelner unvollständiger oder feindlicher Fremdbericht verletzt die bereits beim Lock-Parser verwendete Fail-open-Regel „kaputte Fremddatei überspringen“. Außerdem ist ein erfolgreich selbst erzeugter leerer Skalar nicht roundtrip-stabil.
- **Schweregrad:** **wichtig**

### 10. `normalize_locator()` vermischt inkompatible Pfadsemantiken

- **Datei:Zeile:** `src/system_auditor/compare.py:56`, `src/system_auditor/compare.py:63`, `src/system_auditor/compare.py:72`
- **Was passiert:** `C:\Users\<name>`, `/Users/<name>` und `/home/<name>` werden sinnvoll auf `<HOME>` gefaltet. Danach wird jedoch jeder Locator kleingeschrieben; auf einem case-sensitiven Linux-Dateisystem werden `/srv/Repo/X` und `/srv/repo/x` dadurch fälschlich gleich. Das Zusammenziehen von `//` macht aus UNC `\\server\share\x` denselben String wie den POSIX-Pfad `/server/share/x`. WSL-Pfade wie `/mnt/c/Users/User`, Extended-Length-Pfade, `~`, relative Pfade, `..` und Symlink-Aliase werden nicht auf dasselbe Ziel gefaltet.
- **Warum falsch:** Es entstehen sowohl falsche Matches als auch verpasste Matches. Da Locator-Gleichheit und Abdeckung die Klassen direkt steuern, ist dies keine kosmetische Normalisierungslücke.
- **Schweregrad:** **wichtig**

### 11. Naive Zeitpunkte hängen von der lokalen Zeitzone des Hosts ab

- **Datei:Zeile:** `src/system_auditor/tokens.py:122`, `src/system_auditor/tokens.py:123`, `src/system_auditor/tokens.py:149`
- **Was passiert:** Für einen naiven `datetime` interpretiert `astimezone(UTC)` den Wert in der lokalen Systemzeitzone. Derselbe naive Wert `2026-01-05 00:30` wurde auf dem aktuellen Europe/Berlin-Host zu `2026-01-04T23:30Z` und damit zum Vortagstoken; ein UTC-Host würde den 5. Januar verwenden. `TimeTable.token()` hat dieselbe Eigenschaft.
- **Warum falsch:** Die öffentliche API akzeptiert eine Eingabe, bei der zwei Maschinen trotz identischer Konfiguration verschiedene Tokens ableiten können. Naive Zeitpunkte sollten abgewiesen oder ausdrücklich als UTC behandelt werden.
- **Schweregrad:** **wichtig**

### 12. Sehr große, formal gültige Perioden scheitern erst beim Token-Abruf

- **Datei:Zeile:** `src/system_auditor/tokens.py:95`, `src/system_auditor/tokens.py:126`, `src/system_auditor/tokens.py:128`
- **Was passiert:** `999999999d` lässt sich als `timedelta` konstruieren, aber `window()` berechnet immer auch `start + length`; das überschreitet den `datetime`-Wertebereich und löst `OverflowError` aus. Die Konfiguration wird nicht beim Erzeugen des Grids abgelehnt.
- **Warum falsch:** Ein akzeptierter Konfigurationswert kann jeden späteren Auditlauf abbrechen. Das ist kein Cross-Host-Split, aber eine fehlende Konfigurationsvalidierung.
- **Schweregrad:** **klein**

**Sauber gelöst:** Bei zeitzonenbewussten Zeitpunkten wird vor der Rasterberechnung nach UTC konvertiert; dadurch sind Sommerzeitwechsel kein Sonderfall. Negative Indizes vor dem Anchor werden durch Floor-Division korrekt berechnet. Python kann Schaltsekunden nicht darstellen und weist `second=60` auf allen Hosts konsistent mit `ValueError` ab.

## Testlücken

- **Klassifikation:** `tests/test_compare.py:39` prüft nur zwei gewöhnliche Windows-Home-Pfade; `tests/test_compare.py:92` prüft eine klar fremde Coverage-Wurzel. Segmentpräfixe, UNC, Linux-Großschreibung und Cross-Domain-Abwesenheit fehlen. `tests/test_timeseries.py:49` bis `tests/test_timeseries.py:69` deckt echte neueste Abwesenheit und echte neueste Nichtabdeckung ab, aber keine unbekannte Zwischenperiode und keine unsortierbaren Tokens.
- **Lock:** `tests/test_audit_lock.py:58` bis `tests/test_audit_lock.py:106` verwendet aktive Locks in einem bereits gemeinsamen Verzeichnis und kanonische `compares`-Strings. Verzögerte Sichtbarkeit, die CLI-Quarantäne, ein abgelaufener eigener Lock und äquivalente Mengen in anderer Reihenfolge fehlen.
- **Dateinamen und Parser:** `tests/test_report.py:121` beweist nur Stabilität für denselben einfachen Key; `tests/test_report.py:189` prüft nur einen fremden Dateinamen. Injektivität, Unicode-Roundtrip, leere Token, fehlender Abschlussdelimiter und ungültige Feldtypen fehlen.
- **Zeit:** `tests/test_tokens.py:29` prüft denselben bewussten UTC-Zeitpunkt und `tests/test_tokens.py:88` nur einen naiven Anchor. Naive `moment`-Werte, Sommerzeitgrenzen, negative Indizes, Schaltsekunden und große Perioden fehlen.

### Die drei wertvollsten fehlenden Tests

1. **Zweiseitiger Claim-Zustandsautomat:** zwei Hosts mit verzögerter Sicht, vertauschter `compares`-Reihenfolge und einem abgelaufenen eigenen Lock; Invariante nach dem Recheck: exakt ein `won=True`, und vor Ablauf der Quarantäne erhält niemand Schreibfreigabe.
2. **Klassifikationsmatrix für Abdeckung und Zeit:** Pfadsegmentgrenze (`foo` gegen `foobar`), unbekannte Zwischenperiode und unbekannte neueste Periode; `host_specific`, `resolved` und `persistent` dürfen nur mit der jeweils erforderlichen Evidenz entstehen.
3. **Artefakt-Invarianten als Property-Test:** verschiedene Fixed-Keys müssen verschiedene Dateinamen ergeben, `write_report()`/`read_report()` muss Unicode und leere optionale Felder roundtrip-stabil behandeln, und ein Korpus fehlerhafter Nachbarberichte darf `list_reports()` nie abbrechen.

## Was ich anders bauen würde

1. **Claims entweder ehrlich „best effort“ nennen oder transaktional koordinieren.** Gegenseitiger Ausschluss lässt sich auf einem eventuell konsistenten Sync-Ordner nicht garantieren. Bleibt „ohne Server“ zwingend, sollte ein doppeltes Meta-Ergebnis konfliktfrei und inhaltsadressiert zusammengeführt werden; bleibt Exklusivität zwingend, braucht es eine gemeinsame atomare Compare-and-Set-Instanz.
2. **Fixed-Keys kanonisch kodieren statt sluggen.** Eine kanonische JSON-Darstellung mit Dimensionsnamen und ein kurzer BLAKE2-Hash im Dateinamen erhält einen lesbaren Präfix, verhindert aber Kollisionen und Positionsmehrdeutigkeit. Pflicht-Tokens sollten vor dem Schreiben validiert werden.
3. **Locatoren strukturiert statt als global kleingeschriebene Strings modellieren.** Mindestens Pfadart, Root, Segmente und Case-Sensitivität gehören in die Vergleichsidentität; Symlinks und relative Pfade müssen am erzeugenden Host zu einem kanonischen Locator aufgelöst oder ausdrücklich als nicht vergleichbar markiert werden.
4. **Reports mit einem kleinen typisierten Schema lesen.** Der Zero-Dependency-Ansatz kann bleiben: Feldtypen, Pflichtfelder und Abschlussdelimiter lassen sich mit Standardbibliothek validieren. `read_report()` sollte ein Ergebnis mit Header oder Diagnose liefern, während `list_reports()` fehlerhafte Einträge isoliert überspringt.
5. **Zeitreihen nach expliziter Fensterordnung aufbauen.** Neben dem Token sollte der Report `window_start_utc` oder den ganzzahligen Grid-Index tragen; `time_token` bleibt Anzeige und Identität, bestimmt aber nicht die Chronologie.

## Gesamturteil

Die Kernidee, Unterschiede zwischen berechtigten Host-Sichten als Produkt zu behandeln, ist tragfähig, und die nominale Aggregationslogik sowie der UTC-Weg für bewusste Zeitpunkte sind klar umgesetzt. Für v0.3.0 sind jedoch Claim-Exklusivität, Dateinamen-Eindeutigkeit, Parser-Isolation und mehrere Evidenzgrenzen der Klassifikation noch nicht zuverlässig genug; zwei der reproduzierten Lock-Fälle erlauben ausdrücklich zwei Gewinner. Vor einer produktiven Nutzung über synchronisierte Hosts würde ich mindestens die beiden kritischen Claim-Fehler sowie die Abdeckungs-, Dateinamen- und Parserfehler beheben und mit den drei genannten Invariantentests absichern.
