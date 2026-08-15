---
run_id: <SYSTEM>-<AUDITOR>-<YYYYMMDD-HHMMSS>
audit_mode: self
time_token: <AUS system-auditor time-token>
domain: <DOMAENE>
system: <VOLLER-RECHNERNAME>
auditor: <MODELL-ODER-AGENT>
started_utc: <YYYY-MM-DDTHH:MM:SSZ>
finished_utc: <YYYY-MM-DDTHH:MM:SSZ>
window_start_utc: <Fensterbeginn aus system-auditor time-token -- traegt die Chronologie, NICHT der Token-Text>
next_domain: <naechste Domaene der Rotation>
findings: 0
measures: []
evidence_level: 1
coverage: [<pfad-praefix-1>, <pfad-praefix-2>]
clean: [<ort-ausdruecklich-in-ordnung>]
findings_detail:
- <locator> | <verletzte-regel> | <kurztitel>
---

# Audit <DOMAENE> — <SYSTEM> — Fenster <time_token>

> **Dateiname:** `AUDIT-<time>--<domain>.<system>.<auditor>.md` — doppelter
> Bindestrich zwischen Zeit und Domäne, sonst kollidieren Namen.
> **Kopf zuerst, Prosa danach.** Der Kopf ist das, was Maschinen und spätere
> Meta-Audits lesen; alles unterhalb dieser Linie ist deine Interpretation.
> Diese Blockquote-Hinweise im fertigen Bericht löschen.

## Auftrag und Abdeckung

- **Zuteilungsweg:** <explizit | selektor | rotation> — <Beleg, z. B. letzter Bericht>
- **Geprüft wurde:** <was coverage[] konkret bedeutet — welche Ebene, welche Tiefe>
- **Nicht geprüft:** <bewusst ausgelassene Teile, mit Grund>
- **Regelquellen:** <Stufe der Kaskade: konfiguriert / Modul-Probe / Konvention / nichts>

## Funde

> Je Fund ein Block. Ohne B und C ist es keine Maßnahme, sondern eine
> Beobachtung (unten). `findings:` im Kopf zählt nur die Blöcke hier.

### Fund 1 — <Kurztitel>

- **A — Problem und Ort:** <konkreter Pfad, ggf. Zeile; beobachteter Ist-Zustand;
  Bedingung des Auftretens>
- **B — verletzte Regel:** <Policy mit Fundort>
- **C — Grundlage der Empfehlung:** <Entscheidung/Policy mit Fundort>
- **EMPFEHLUNG:** <was zu tun wäre — du änderst nichts>
- **GEGENREDE:** <gäbe es ohne die bisherigen Entscheidungen eine bessere Lösung?
  Ist die Regel selbst überholt?>
- **DRIFT-FAZIT:** <unerwünschter Drift | erwünschter Drift (→ Regelanpassung als
  Entscheidungsvorlage) | kein Drift>

## Beobachtungen ohne Beleg

<Kandidaten, denen B oder C fehlt — hier festhalten, nicht als Maßnahme ausgeben.>

## Maßnahmen-Ausgabe

<Wohin die Funde gingen: Senke (Referenz) oder Datei-Fallback (Pfad). Leer bei
Null-Befund.>

## Meta-Schritt (Pflichtprüfung am Ende)

<Ergebnis von `system-auditor meta-plan`: Lagen Fremdberichte gleicher Domäne im
gleichen Fenster vor? Wenn ja: Meta-Bericht nach templates/META-BERICHT.de.md
gleich mit erstellt — hier die Datei nennen. Wenn nein: „kein Partner in diesem
Fenster" ist das normale Ergebnis.>
