# CODEX-Review 2: Logikmodell von system-auditor v0.4.0

**Datum:** 2026-08-15  
**Scope:** ausschließlich Achsenmodell, Schlussregeln, Zeitreihen, Agreement, Idempotenz, Historie und Baupolitik; keine erneute Prüfung von Parsern, Pfaden oder allgemeiner Robustheit.  
**Verifikation:** `python -m pytest -q` → 109 bestanden; `ruff check src tests` → sauber. Die unten genannten Grenzfälle wurden zusätzlich mit isolierten Python-Sonden reproduziert.

## 1. Achsen-Systematik

### Fund 1 — Eine notwendige kontrollierte Systemachse fehlt

- **Datei:Zeile:** `src/system_auditor/tokens.py:270-282`, `src/system_auditor/tokens.py:311-316`, `src/system_auditor/tokens.py:333-339`
- **Logischer Fehler:** Das Modell hat nicht nur `fixed` und `varying`, sondern zusätzlich `uncontrolled`; damit beschreibt es nicht die behaupteten 16 binären Kombinationen, sondern einen dreizuständigen Raum. Ausgerechnet `cross-system` lässt den Auditor unkontrolliert, während für Zeitreihen mit `timeseries-rater` eine kontrollierte Gegenstufe existiert. Es fehlt die sinnvolle Aggregation **`cross-system-rater`** mit `time+domain+auditor` fest und `system` variierend.
- **Warum:** Wenn H1 von Opus und H2 von Sonnet auditiert wurde, ist ein Unterschied nicht als Host-Effekt identifiziert. Ein Vorbehalt benennt die Konfundierung, macht den Schluss „systemweit oder host-spezifisch“ aber nicht gültig.
- **Schweregrad:** **wichtig**

### Fund 2 — `full-system` ist als Inferenzaggregation nicht identifizierbar

- **Datei:Zeile:** `src/system_auditor/tokens.py:288-290`, `src/system_auditor/tokens.py:318-323`, `src/system_auditor/tokens.py:395-405`
- **Logischer Fehler:** `full-system` behandelt jedes Paar `domain / auditor` als einen Teilnehmer. Schon eine Domäne mit zwei Auditoren oder zwei nur diagonal besetzte Paare (`D1/A1`, `D2/A2`) bilden daher ein Meta-Audit; weder müssen beide Dimensionen tatsächlich variieren noch muss das Domäne×Auditor-Raster vollständig sein.
- **Warum:** Bei einem Unterschied kann das Modell nicht entscheiden, ob Domäne, Auditor oder deren Interaktion die Ursache ist. Als deskriptive Bestandsmatrix ist `full-system` sinnvoll; die fünf Snapshot-Klassen sind darauf nicht interpretierbar.
- **Schweregrad:** **kritisch**

**Was trägt:** `interrater`, `cross-domain` und `timeseries-rater` halten alle Nicht-Zielachsen fest und sind als Einachsenfragen widerspruchsfrei definiert.

## 2. Klassifikation

### Fund 3 — Die Klassen sind vollständig, aber nicht disjunkt

- **Datei:Zeile:** `src/system_auditor/compare.py:302-364`
- **Logischer Fehler:** Die tatsächliche Entscheidungspriorität lautet `divergent` → `inverse` → `systemwide` → `host_specific` → `unverifiable`; `CLASS_ORDER` in Zeile 51 ist nur die Sortierreihenfolge. Bei vier Teilnehmern kann derselbe Schlüssel gleichzeitig auf einem Teilnehmer mit anderer Regel `divergent`, auf einem ausdrücklich sauberen `inverse` und auf einem abgedeckten Teilnehmer ohne Befund `host_specific` sein; reproduziert wurde die Ausgabe ausschließlich als `divergent`.
- **Warum:** Die Kategorien sind damit keine logisch disjunkten Klassen, sondern eine Prioritätsprojektion mehrerer Evidenzzustände. Die Wahl „divergent schlägt inverse“ ist nicht aus dem Modell ableitbar und die Hauptklasse verschweigt im Begründungssatz die gleichzeitig vorliegende stärkere Negativbestätigung.
- **Schweregrad:** **wichtig**

**Was trägt:** Für jeden überhaupt beobachteten Schlüssel ist die Fallunterscheidung erschöpfend; `inverse` ist als eigene Evidenzstufe sinnvoll, weil „ausdrücklich sauber“ stärker ist als bloß „abgedeckt, aber nicht gemeldet“. Sie sollte jedoch als orthogonales Evidenzmerkmal oder klarer Spezialfall, nicht als angeblich disjunkte Klasse modelliert werden.

## 3. Gruppierung nach Regel statt Ort

### Fund 4 — Regelmatching kann positive Cross-Domain-Koinzidenz zeigen, aber keine Abwesenheit

- **Datei:Zeile:** `src/system_auditor/tokens.py:279-282`, `src/system_auditor/compare.py:311-331`
- **Logischer Fehler:** Nach dem Match über `rule` prüft `_classify()` die Abwesenheit trotzdem über den **repräsentativen Locator einer anderen Domäne**. In der Sonde meldete D1 die Regel unter `/d1/x`, D2 hatte `/d2` vollständig abgedeckt und keinen Befund; D2 wurde dennoch `unknown`, das Ergebnis `unverifiable` statt „nur in D1“.
- **Warum:** Eine domänenspezifische Abdeckung kann den fremden Ort grundsätzlich nicht abdecken. Damit erkennt `cross-domain` „alle melden dieselbe Regel“, kann aber „manche Domänen melden sie trotz Prüfung nicht“ mit dem vorhandenen Evidenzschema nicht belegen.
- **Schweregrad:** **wichtig**

### Fund 5 — `group_by=rule` macht bei `full-system` falsche Rater-Übereinstimmung

- **Datei:Zeile:** `src/system_auditor/tokens.py:279-282`, `src/system_auditor/compare.py:314-347`, `src/system_auditor/compare.py:426-428`
- **Logischer Fehler:** Weil bei `full-system` die Domäne variiert, wird immer nach Regel gruppiert, auch wenn die konkret vorhandenen Teilnehmer nur verschiedene Auditoren derselben Domäne sind. Zwei Auditoren, die dieselbe Regel an `/d/x` beziehungsweise `/d/y` melden, wurden in der Sonde als `systemwide` gewertet.
- **Warum:** Für den Domänenvergleich ist die Regel der richtige positive Schlüssel; für Rater-Agreement muss dagegen derselbe Ort **und** dieselbe Regel verglichen werden. Eine einzige `group_by`-Entscheidung kann die zwei vermengten Fragen von `full-system` nicht beantworten.
- **Schweregrad:** **kritisch**

**Was trägt:** Reines Cross-Domain-Regelmatching ist für die positive Aussage „dieselbe Regel wurde in mehreren Domänen beanstandet“ korrekt.

## 4. Zeitreihenklassen und `net_change`

### Fund 6 — `new` und `persistent` behaupten mehr als beobachtet wurde

- **Datei:Zeile:** `src/system_auditor/timeseries.py:194-231`, `src/system_auditor/timeseries.py:235-240`
- **Logischer Fehler:** Ein Befund, der im neuesten Fenster erstmals **beobachtet** wird, heißt auch dann `new`, wenn alle früheren Fenster den Ort nicht abdeckten; reproduziert: W1 unbekannt, W2 vorhanden → `new`. Ebenso bleibt W1 vorhanden, W2 unbekannt, W3 vorhanden in der Klasse `persistent`; `continuity_verified=False` korrigiert zwar die Detailbegründung, aber Überschrift und Bilanz zählen weiterhin „seit dem ersten Auftreten durchgehend“.
- **Warum:** „Neu“ und „durchgehend“ sind Aussagen über frühere Abwesenheit beziehungsweise lückenlose Anwesenheit. Ohne Beobachtung ist nur „neu beobachtet“ beziehungsweise „wiederholt beobachtet, Kontinuität unbekannt“ belegt.
- **Schweregrad:** **wichtig**

### Fund 7 — `net_change` ist keine Veränderungsbilanz

- **Datei:Zeile:** `src/system_auditor/timeseries.py:81-85`, `src/system_auditor/timeseries.py:201-217`, `src/system_auditor/timeseries.py:265-270`
- **Logischer Fehler:** `resolved` bleibt auch zehn Fenster nach der tatsächlichen Auflösung `resolved`, und `recurring` bleibt nach irgendeiner früheren Lücke dauerhaft `recurring`. Deshalb ergab W1 vorhanden, W2 abwesend, W3 abwesend weiterhin netto −1, obwohl sich von W2 auf W3 nichts änderte; W1 vorhanden, W2 abwesend, W3 vorhanden, W4 vorhanden ergab weiterhin netto +1.
- **Warum:** Die Formel zählt Lebenslaufklassen, nicht Übergänge vom vorletzten zum letzten Fenster. Die Ausgabe „Richtung“ suggeriert daher eine aktuelle Bilanz, die nicht berechnet wird.
- **Schweregrad:** **wichtig**

**Was trägt:** `resolved` verlangt zu Recht Abdeckung im neuesten Fenster, `recurring` verlangt mindestens eine bestätigte Abwesenheit, und die fünf Rückgabeklassen sind technisch erschöpfend.

## 5. Interrater-Agreement

### Fund 8 — Die Kennzahl ist positive Einstimmigkeit, nicht allgemeine Übereinstimmung

- **Datei:Zeile:** `src/system_auditor/compare.py:213-228`, `src/system_auditor/compare.py:290-299`
- **Logischer Fehler:** Der Nenner enthält nur Schlüssel, die mindestens ein Auditor als Befund eingebracht hat und die anschließend entscheidbar waren. Gemeinsame Negativurteile über geprüfte, saubere Regeln kommen mangels vorab definierter Item-Menge gar nicht vor; bei mehr als zwei Auditoren zählt nur Einstimmigkeit aller als Treffer.
- **Warum:** Die Zahl ist eine nützliche, Jaccard-ähnliche **positive Unanimity-Quote**, aber kein allgemeines Interrater-Agreement. `inverse` und `divergent` gehören im jetzigen Maß korrekt in den Nenner, weil sie echte Nichtübereinstimmung darstellen; Cohen-Kappa wäre ohne gemeinsames Universum bewerteter Items nicht berechenbar. Für zwei Auditoren wäre ein explizit benannter Jaccard-Wert, für mehrere ein paarweiser Jaccard-Mittelwert oder die klar benannte Unanimity-Quote ehrlicher.
- **Schweregrad:** **wichtig**

## 6. Idempotenz und Lockfreiheit

### Fund 9 — Ein Check-then-write-Race kann ein neueres Meta-Audit zerstören

- **Datei:Zeile:** `src/system_auditor/__init__.py:17-22`, `src/system_auditor/meta.py:239-254`, `src/system_auditor/report.py:418-428`
- **Logischer Fehler:** `plan_metas()` prüft den vorhandenen Stand nur während der Planung; `write_report()` schreibt später ohne erneuten Vergleich direkt auf denselben Zielpfad. Reproduzierte Interleaving-Sonde: Lauf A plante Meta-3 aus `r1,r2,r3`; Lauf B sah zusätzlich `r4`, plante und schrieb Meta-4; anschließend schrieb A sein altes Meta-3 über dieselbe Datei. Der Endstand enthielt nur `r1,r2,r3`; erst ein weiterer Planungslauf bemerkte wieder `update` auf Stufe 4.
- **Warum:** `ACTION_SKIP` verhindert nur einen später startenden Lauf bei bereits sichtbarem Endartefakt. Es schützt weder zwei gleichzeitig geplante Läufe noch vor einem veralteten Schreiber; damit ist der Entfall **jedes** Locks beziehungsweise einer atomaren Compare-and-Swap-Schreibregel nicht durch Idempotenz begründet.
- **Schweregrad:** **kritisch**

### Fund 10 — Selbst bei gleicher Eingabemenge ist das Artefakt nicht kanonisch

- **Datei:Zeile:** `src/system_auditor/compare.py:290-299`, `src/system_auditor/compare.py:314-318`, `src/system_auditor/compare.py:386-395`
- **Logischer Fehler:** `build_meta()` sortiert die übergebenen Läufe nicht. Bei derselben Menge zweier Runs in umgekehrter Reihenfolge wechselten in der Sonde der repräsentative Titel (`Titel A`/`Titel B`) und die Reihenfolge von `present_on` (`A,B`/`B,A`).
- **Warum:** Die Klassenbezeichnung bleibt in diesem einfachen Fall gleich, der erzeugte Inhalt aber nicht bitgleich. Die öffentliche Kernfunktion erzwingt die für den Idempotenzclaim nötige kanonische Eingabeordnung nicht.
- **Schweregrad:** **wichtig**

**Was trägt:** Bei identisch geordneten, unveränderten Runs ist die reine Klassenentscheidung deterministisch; das genügt jedoch nicht für kollisionsfreies Schreiben.

## 7. Überschreiben statt Archivieren

### Fund 11 — Die Historienbehauptung gilt nur für Fensterwechsel von Snapshot-Aggregationen

- **Datei:Zeile:** `src/system_auditor/meta.py:7-15`, `src/system_auditor/report.py:240-255`, `src/system_auditor/report.py:418-428`
- **Logischer Fehler:** Für die vier Snapshot-Aggregationen erzeugt ein neues Zeitfenster tatsächlich eine neue Datei. `timeseries` und `timeseries-rater` tragen den Zeittoken absichtlich nicht im Namen und überschreiben jede frühere „as of“-Auswertung; auch meta-2 → meta-3 und Korrekturen innerhalb desselben Fensters verlieren den früher veröffentlichten Ableitungsstand.
- **Warum:** Beim bloßen Teilnehmerzuwachs bleiben die Einzelaudits erhalten und die alte Teilmenge wäre rechnerisch rekonstruierbar, aber nicht, **welcher Stand wann als gültiges Meta-Audit vorlag**. Überschreibt zusätzlich ein Träger sein Einzelaudit mit denselben vier Token, ist auch die frühere Grundlage weg. Für ein reines Current-State-Dashboard ist das akzeptabel; für ein Audit-Trail ist „Historie steckt im Zeittoken“ falsch, besonders bei den beiden Zeitreihen.
- **Schweregrad:** **wichtig**

## 8. Baupolitik

### Fund 12 — Die einzige `always`-Stufe ist zugleich die am stärksten konfundierte

- **Datei:Zeile:** `src/system_auditor/meta.py:101-110`, `src/system_auditor/tokens.py:311-316`, `src/system_auditor/compare.py:275-285`
- **Logischer Fehler:** `cross-system` ist als einzige Aggregation `always`, obwohl gerade dort der Auditor unkontrolliert bleiben darf. Das System erzeugt damit standardmäßig eine als Host-/Systemschluss beschriftete Auswertung, bevor Rater-Zuverlässigkeit (`interrater`) oder ein auditor-kontrollierter Systemvergleich gesichert sind.
- **Warum:** Als Produktentscheidung „Fleet-Alarm zuerst“ ist die Auswahl nachvollziehbar, als Evidenzhierarchie nicht. Solange `cross-system-rater` fehlt, sollte der Default nur eine deskriptive Teilnehmerdifferenz mit sichtbarer Konfundierung behaupten; nach Ergänzung wäre die kontrollierte Stufe der logisch richtige `always`-Kandidat.
- **Schweregrad:** **wichtig**

**Was trägt:** Die Trennung `always`/`on_demand`/`off`, eigene Mindestteilnehmerzahlen und genau ein stehender Bericht sind als Anti-Rausch-Politik schlüssig; nicht schlüssig ist die Beweiskraft der gewählten Default-Stufe.

## Gesamturteil zur Logik

Das Vier-Token-Modell trägt für sauber kontrollierte Einachsenvergleiche und erzwingt an mehreren Stellen zu Recht `unverifiable` statt eines unbelegten Schlusses. Die Implementierung überschreitet diese Beweiskraft jedoch bei der zweiachsigen `full-system`-Aggregation, bei Zeitreihenbezeichnungen und bei der als allgemeines Agreement beziehungsweise aktuelle Bilanz beschrifteten Kennzahl. Am schwersten wiegt, dass die zentrale Begründung für vollständige Lockfreiheit durch einen reproduzierbaren veralteten Schreiber widerlegt ist.

**Wirksamste Änderung:** Erlaube inferenzielle Klassen nur bei **genau einer variierenden und allen übrigen festgehaltenen Dimensionen**; ergänze insbesondere `cross-system-rater`, und führe `full-system` nur noch als deskriptive Domäne×Auditor-Matrix ohne die fünf Snapshot-Klassen.
