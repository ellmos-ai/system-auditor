---
run_id: <SYSTEM>-<AUDITOR>-<YYYYMMDD-HHMMSS>
audit_mode: meta
aggregation: <cross-system-rater | interrater | cross-system | cross-domain | timeseries | timeseries-rater | full-system>
meta_level: <ANZAHL der Eingaben -- steigt, wenn ein Teilnehmer hinzukommt>
time_token: <gemeinsames Zeitfenster der Eingaben; leer nur bei Zeitreihen>
domain: <gemeinsame Domaene; leer bei cross-domain>
system: <gemeinsames System; leer, wenn die Systemachse variiert>
auditor: <gemeinsamer Auditor; leer, wenn die Auditorachse variiert>
finished_utc: <YYYY-MM-DDTHH:MM:SSZ>
participants: [<variierende-werte, z. B. HOST-A, HOST-B>]
inputs: [<run_id-1>, <run_id-2>]
scope: [<werte der festgehaltenen Dimensionen, in der Reihenfolge des Dateinamens>]
findings: 0
measures: []
evidence_level: 1
coverage: []
clean: []
---

# Meta-Audit <aggregation> — Fenster <time_token>

> **Dateiname:** `META-<aggregation>--<fixe-schluessel>.md` — **ohne Host-Token**
> und ohne Teilnehmerzahl: je (Fenster, Scope, Aggregation) gibt es genau eine
> gültige Antwort, ein neuer Teilnehmer **überschreibt dieselbe Datei**
> (meta-2 → meta-3). Vor dem Überschreiben lesen: Liegt dort schon eine
> **Obermenge** deiner Eingaben (meta_level ≥ deiner Zahl, deine inputs
> enthalten), dann NICHT schreiben — dein Stand ist veraltet.
> **Die Grundregel:** Eine Ursache darf nur zuschreiben, wer genau EINE
> Dimension variieren lässt. `full-system` beschreibt deshalb nur.
> Diese Blockquote-Hinweise im fertigen Bericht löschen.

## Eingaben

| run_id | System | Auditor | findings | coverage (Kurzform) |
|---|---|---|---|---|
| <run_id-1> | <HOST-A> | <modell> | <n> | <praefixe> |
| <run_id-2> | <HOST-B> | <modell> | <n> | <praefixe> |

**Je Identität zählt das neueste Audit** (gleiche vier Token = dieselbe Aussage,
korrigiert). Ausgeschlossene ältere Stände hier nennen.

## Klassifikation

> Modellmanuell: Du liest die Eingabeberichte und ordnest jeden Fund selbst ein.
> Locators vor dem Vergleich normalisieren (Pfadtrenner, Groß-/Kleinschreibung,
> Host-Anteile). `coverage[]`/`clean[]` der Partner entscheiden, ob Abwesenheit
> belegt ist — **nicht deine Vermutung**.

### <systemwide | bei interrater: einstimmig>

<Funde, die ALLE Teilnehmer melden → echte Systeminkonsistenz. Je Fund: Locator,
Regel, wer ihn meldet.>

### <host_specific | modell_spezifisch>

<Manche melden, andere haben den Ort geprüft (coverage!) und nichts gefunden → Drift.>

### inverse

<Hier Mangel, dort ausdrücklich in `clean[]` → Host-Abhängigkeit, klassisch
hartkodierter Pfad. Stärkste Klasse — braucht expliziten clean-Beleg.>

### divergent

<Gleicher Ort, verschiedene verletzte Regeln → Stand oder Auslegung differiert.>

### unverifiable

<Ein Teilnehmer hat dort nie geprüft → keine Aussage. Die ehrliche Klasse —
nicht mit Vermutungen füllen.>

## Übereinstimmung

<Bei interrater: Einstimmigkeitsquote und paarweise Übereinstimmung (Jaccard).
Niedriger Wert = Zuverlässigkeitsproblem der Auditoren, KEIN Systemmangel.
Bei Zeitreihen stattdessen: new/persistent/resolved/recurring je Fund, mit
first_absence_verified/continuity_verified — „alle Fenster fanden es" heißt
anhaltend, nicht systemweit.>

## Interpretation und Empfehlungen

<Deine Lesart: Was folgt aus den Klassen? Welche Funde verdienen eine Maßnahme
auf welcher Ebene (ein Host / alle Hosts / die Regel selbst)? Vorbehalte nennen —
bei cross-system ist ein Unterschied KEIN belegter Host-Effekt.>
