# Audit-Host-Lock — Protokoll v1

**Status:** stabil · **Eigentümer:** `system-auditor` · **Konsumenten:** `system-auditor`
(Erzeuger), `lock-master` (Erkenner)

Ein Koordinationsprotokoll für Auditoren, die auf mehreren Systemen dieselbe Domäne
prüfen. Es ist **selbsttragend**: Wer nur diese Datei gelesen hat, kann das Protokoll von
Hand ausführen. Es braucht keine Bibliothek, keinen Daemon und keinen lock-master.

---

## 1. Wozu — und wozu ausdrücklich nicht

Zwei Systeme, die dieselbe Domäne auditieren, kommen **nicht** zum selben Ergebnis. Sie
schauen auf verschiedene Maschinen; was auf der einen ein Mangel ist, ist auf der anderen
korrekt. Belegtes Beispiel (2026-08-15): Der Befund „Gardener-Governance hartkodiert
`C:\Users\User\…`" ist auf WORKSTATION-LG real — dort existiert der Pfad nicht — und auf
dem Laptop ein Nicht-Befund, weil der Pfad dort stimmt.

**Doppelte Einzelaudits sind deshalb erwünscht, nicht redundant.** Sie sind der Rohstoff
des Meta-Audits. Ein Ausschluss-Lock wäre hier schädlich.

Was das Protokoll trotzdem leistet:

| Zweck | Modus |
|---|---|
| **Anwesenheit sichtbar machen** — „auf System X läuft gerade ein Audit dieser Domäne" | `presence` |
| **Reservieren, wo Redundanz wertlos ist** — das Meta-Audit über dieselbe Eingabemenge | `claim` |

Ein Meta-Audit zweimal über dieselben Einzelaudits zu rechnen erzeugt zwei identische
Aussagen. Nur dafür gibt es eine Reservierung.

---

## 2. Dateiname (autoritativ)

```
LOCK.audit.<domaene>.<host>.txt
```

Beispiel: `LOCK.audit.ai-bundles.ASUS-GEI.txt`

Das passt **ohne Codeänderung** in die ökosystemweite Lock-Grammatik
`^LOCK(\.[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*)?\.txt$`. Bestehende Scanner, Watcher und
GUIs sehen die Datei sofort. Der Dateiname ist für Domäne und Host **autoritativ**; die
gleichnamigen Felder im Inhalt sind informativ (gleiche Regel wie im Basis-Lock-System).

`<domaene>` und `<host>` sind dateinamens-sichere Slugs (`[A-Za-z0-9_-]+`). `<host>` ist
der volle Rechnername, nicht ein Sync-Slotname.

---

## 3. Ablageort

Der Lock liegt **nicht** im geprüften Bereich, sondern im Register des Auditors:

```
<audit_home>/_locks/LOCK.audit.<domaene>.<host>.txt
```

Zwei Gründe:

1. **Read-only bleibt read-only.** Ein Lock im Zielbereich wäre ein Schreibzugriff in
   fremdes Gebiet und würde die Garantie brechen, dass ein Audit nichts verändert.
2. **Vergleichbarkeit.** Alle Audit-Locks an einem Ort sind in einem einzigen
   Verzeichnis-Listing auswertbar — genau das braucht die Claim-Auflösung in §6.

> **Pflicht bei Einführung:** `<audit_home>/_locks` gehört in die Scan-Roots des
> Lock-Systems (`lock_roots.json`). Sonst wiederholt sich der Lehrfall vom 2026-07-25:
> Locks außerhalb der Roots sind unsichtbar, und *„aus unsichtbaren Locks entstehen
> Parallelsysteme"*.

---

## 4. Inhalt

Basisformat `key: value`, eine Einstellung pro Zeile, `#` = Kommentar.

```
# Audit-Host-Lock -- protocols/audit-host-lock/SPEC.md
# ADVISORY: this lock does not block work in the audited area.

owner: system-auditor
host: ASUS-GEI
created: 2026-08-15T16:20:39Z
expires_after: 2h
mode: soft
advisory_for: system-auditor

audit_mode: presence
area: ai-bundles
area_path: <HOME>/OneDrive/.TOPICS/.AI/.BUNDLES
run_id: ASUS-GEI-20260815T162039Z
phase: sweep
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `owner` | ja | Immer `system-auditor` |
| `host` | ja | Rechnername (informativ; Dateiname entscheidet) |
| `created` | ja | **UTC, sekundengenau** — siehe §5 |
| `expires_after` | ja | Default `2h`. Ein Sweep dauert keine 24 h, und ein vergessener Lock soll die Rotation nicht einen Tag blockieren |
| `mode` | ja | Immer `soft` — Basisfeld, sagt fremden Agenten: keine harte Sperre |
| `advisory_for` | ja | `system-auditor` — *für wen* der Lock überhaupt Bedeutung hat |
| `audit_mode` | ja | `presence` \| `claim` |
| `area` | ja | Domänen-Slug |
| `area_path` | nein | Realer Ort der Domäne auf diesem Host |
| `run_id` | ja | Korreliert Lock, Laufbericht und erzeugte Maßnahmen |
| `phase` | nein | `claim` \| `sweep` \| `writeback` |
| `compares` | nur `claim` | Die Eingabemenge des Meta-Audits (§6) |
| `purpose` | nein | Freitext |

### Verbindliche Lesart für fremde Agenten

> Ein Lock mit `advisory_for: system-auditor` ist **niemals** ein Grund, im betroffenen
> Bereich nicht zu arbeiten. Er sagt nur: dort läuft gerade eine Prüfung, die nichts
> verändert.

Und für Auditoren:

> Ein `presence`-Lock ist **niemals** ein Grund, eine Domäne zu überspringen. Er ist ein
> Hinweis, dass hinterher ein Meta-Audit möglich wird.

---

## 5. Zeitauflösung — dokumentierte Abweichung

Das Basis-Lock-Format schreibt `created` minutengenau (`YYYY-MM-DDTHH:MM`). Der
Audit-Lock schreibt **sekundengenau** (`YYYY-MM-DDTHH:MM:SSZ`, UTC).

Begründung: Bei Minutengenauigkeit landen zwei Claims derselben Minute regelmäßig im
Host-Tiebreak — und dort verliert derselbe Host **strukturell immer**. Das Präfix bleibt
identisch, minutengenaue Parser lesen die Zeile unverändert. Implementierungen müssen
beide Formen lesen können.

---

## 6. Claim-Verfahren (nur `audit_mode: claim`)

Ein Lock allein genügt über einen synchronisierten Ordner **nicht**: Bei 30 s – 5 min
Latenz schauen beide Systeme, sehen nichts und sperren beide. Deshalb gehört ein
Auflösungsverfahren dazu.

```
1. CLAIM       Lock schreiben: audit_mode: claim, phase: claim,
               compares: <sortierte Eingabemenge>, created = jetzt (UTC, sek.)
2. QUARANTAENE Warten (Default 300 s, konfigurierbar)
3. RECHECK     _locks/ erneut lesen: alle LOCK.audit.<domaene>.*.txt
4. ENTSCHEID   Teilnehmer sind NUR Locks mit audit_mode: claim UND gleichem
               `compares`. Gewinner = frühestes `created`.
               Gleichstand -> lexikografisch kleinerer <host>.
5. VERLIERER   eigenen Lock löschen, kein Meta-Audit rechnen; der Gewinner
               veröffentlicht es. Maximal 3 Versuche, dann melden.
6. GEWINNER    phase: writeback, Meta-Audit schreiben, danach Lock löschen.
```

**Warum `compares` mitzählt:** Zwei Meta-Audits derselben Domäne über *verschiedene*
Teilnehmermengen sind verschiedene Aussagen — sie konkurrieren nicht.

**Determinismus:** Beide Systeme kommen bei gleicher Datenlage zum selben Ergebnis, ohne
Server, ohne Datenbank, ohne Echtzeitkanal.

**Die Quarantäne ist nicht optional.** Wer Schritt 2 überspringt und sofort auflöst, stellt
genau das Rennen wieder her, das dieses Verfahren beilegen soll: Bei nicht synchronisierten
Verzeichnissichten sieht jeder nur seinen eigenen Lock, und beide gewinnen. Der Default von
300 s ist am oberen Ende der oben genannten Latenzspanne gewählt — eine kürzere Wartezeit
deckt sie nicht ab, auch wenn sie sich schneller anfühlt.

**Ein abgelaufener eigener Claim gewinnt nie.** Ein Prozess, der über den Ablauf hinaus
pausiert war, muss neu claimen: Andere Systeme haben seinen Lock längst herausgefiltert,
sodass er sich sonst als frühester Claimant sähe, während niemand sonst ihn noch sieht —
zwei Gewinner bei identischer Datenlage, ganz ohne Sync-Verzögerung.

**`compares` wird kanonisiert.** `a+b` und `b+a` bezeichnen dieselbe Menge; die
Implementierung sortiert und dedupliziert vor dem Vergleich, statt sich auf eine
Schreibkonvention zu verlassen, die die Schnittstelle nicht erzwingen kann.

**Ehrliche Grenze:** Startet ein zweites System *nach* Ablauf der Quarantäne des ersten,
aber bevor dessen Lock synchronisiert ist, greift die Regel nicht. Das Restrisiko liegt
im Sekundenbereich statt, wie ohne Verfahren, bei einem Totalausfall der Koordination.
Ein hartes Ausschlussverfahren gäbe es nur mit einer gemeinsamen transaktionalen Instanz;
das ist gemessen am Nutzen unverhältnismäßig.

---

## 7. Lebenszyklus

1. **BEACHTEN** — `_locks/` lesen. Fremde `presence`-Locks notieren (Meta-Audit wird
   möglich), nicht ausweichen.
2. **ANLEGEN** — eigenen Lock schreiben. Ein aktiver Lock **desselben** Hosts für
   dieselbe Domäne wird nie überschrieben; ein abgelaufener eigener darf ersetzt werden.
   Fremde Locks werden nie angefasst.
3. **FREIGEBEN** — nach dem Schreiben des Laufberichts eigenen Lock löschen. `expires_after`
   ist nur das Sicherheitsnetz.

Unlesbare fremde Lock-Dateien werden übersprungen, nicht als Fehler behandelt: Ein
defekter Fremd-Lock darf niemanden am Arbeiten hindern.

---

## 8. Was `lock-master` ergänzen muss (und mehr nicht)

Das Protokoll läuft ohne lock-master. Für die volle Anzeige genügt dort **eine**
Ergänzung — ein reserviertes Markersegment `audit` neben `team`/`user`/`condition`:

| Ergänzung | Wirkung |
|---|---|
| `lock_utils.is_audit_lock(path)` | Erkennung über `LOCK.audit.*` |
| Ausweisung als **advisory** in `lock_scan`, Watcher und GUI | Verhindert, dass ein Audit-Lock als Sperre missverstanden wird |
| `is_prunable()`: erst nach `expires_after` | Wie alle Zeit-Locks; kein Sonderschutz nötig |

Ausdrücklich **nicht** nötig: neues Dateiformat, neues Statusfeld, eigene Registry, eigene
Datenbank. Der Audit-Lock ist bewusst kein zweites System — genau das war die Lehre aus
dem Ersatzmechanismus, der 2026-07-25 zurückgebaut werden musste.

---

## 9. Referenz-Implementierung

`system_auditor.audit_lock` (Python 3.10+, keine Abhängigkeiten):
`write_lock`, `read_lock`, `list_locks`, `foreign_presence`, `resolve_claim`, `release`.

CLI: `system-auditor claim|release|locks`.

Beides ist Komfort, nicht Voraussetzung — das Protokoll ist von Hand ausführbar.
