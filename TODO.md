# TODO — system-auditor

Stand: 2026-08-15 · Version 0.1.0 · 62 Tests grün, ruff sauber

## Was v0.1.0 wirklich kann

- [x] **Audit-Host-Lock v1** — `presence` (Signal, schließt nie aus) und `claim`
      (Reservierung nur für Meta-Audits) mit deterministischer Verlierer-Regel,
      sekundengenauem `created`, Ablauf, Freigabe. Spec + Referenz-Implementierung.
- [x] **Berichte** — maschinenlesbarer Kopf, Rotation nach `finished_utc`, Rotation pro
      Host, Rückwärtskompatibilität zu `SIG-TU-*.md` ohne Kopf.
- [x] **Meta-Audit** — Klassifikation über N Systeme (`systemwide` / `host_specific` /
      `inverse` / `divergent` / `unverifiable`), Home-Pfad-Normalisierung,
      Vergleichbarkeits-Gate mit Blockern und Vorbehalten.
- [x] **Meta-Lebenszyklus** — Gültigkeitsfenster, neuestes Audit je System, `meta-N`
      ersetzt `meta-(N-1)`, Archivierung statt Löschung, Erneuerung nur durch den eigenen
      Host.
- [x] **Erkennungskaskade** — konfiguriert → Modul-Probe → Konvention → nichts
      (Beobachtungen statt Maßnahmen), tiefenbegrenzt.
- [x] **Senken** — Datei-Senke; Kommando-Senke mit automatischem Rückfall.
- [x] **CLI** — `next-area`, `claim`, `release`, `locks`, `meta-plan`, `reports`,
      `discover`.

## Offen — vor einer Veröffentlichung

- [ ] **`prompts/AUDITOR.en.md`** — Sprachstufe Core (DE+EN) ist für veröffentlichte
      Repos Pflicht (P-006). Aktuell liegt nur die deutsche Fassung vor.
- [ ] **`llms.txt`** ergänzen (Discovery-Index).
- [ ] `PRIVATE.txt`-Gate bewusst setzen oder Freigabe einholen — das Repo ist als
      `visibility: private` deklariert.

## Offen — Integration

- [ ] **`locks_dir` in die Scan-Roots** des Lock-Systems eintragen. Ohne das ist der
      Audit-Lock für Scanner und Watcher unsichtbar — genau die Lücke, aus der im
      Ökosystem am 2026-07-25 schon einmal ein Parallelsystem entstand.
- [ ] **`lock_utils.is_audit_lock()`** im Lock-System ergänzen und Audit-Locks in
      Scan/Watcher/GUI als *advisory* ausweisen, damit sie nicht als Sperre gelesen werden.
- [ ] **Rollenverlagerung** aus dem Ticketsystem: Prompt dort stilllegen, Verweis hierher,
      Architektur-Vorbehalt vom 2026-07-31 als aufgelöst markieren.
- [ ] **Bestandsberichte** (`SIG-TU-*.md`) beim ersten Lauf je Host mit Kopf nachziehen
      oder auslaufen lassen — sie werden gelesen, tragen aber weder `coverage` noch
      `clean` und können deshalb nicht in ein Meta-Audit eingehen.

## Offen — Ausbau

- [ ] **Explorer-Adapter** (Beleg-A-Stufe 2/3): Coverage-/Kartenausgabe als Einstieg,
      Receipts als Beleg. Rein additiv hinter `enabled_probe`.
- [ ] **`meta-build`-Kommando** — derzeit liefert `meta-plan` die Entscheidung, das
      Zusammenstellen der Findings übernimmt der Agent. Ein Kommando, das aus vorhandenen
      Berichten direkt das Meta-Audit schreibt, wäre der nächste sinnvolle Schritt.
      Voraussetzung: Findings müssen maschinenlesbar im Bericht liegen (heute Prosa).
- [ ] **Findings im Berichtskopf** — Ergänzung zu obigem: strukturierte Fundliste
      (`locator`, `rule`, `title`) neben der Prosa, damit Meta-Audits ohne Nachlesen des
      Fließtexts gebaut werden können.
- [ ] Protokoll `protocols/audit-host-lock/` in ein eigenes Repo heben — **erst wenn ein
      dritter Konsument existiert.** Der Schnitt ist bereits so gelegt, dass das ein
      Verschieben ist, kein Umbau.
- [ ] JSON-Schema für den Berichtskopf (`audit-report.v1.schema.json`).

## Bewusst nicht gebaut

- **Zentrales Cursor-Register.** Der Bericht *ist* der Rotationsanker; eine geteilte
  Schreibdatei wäre genau die Bauform, die dieses Ökosystem schon zweimal zurückbauen
  musste.
- **Ticket-IDs, Kategorien, Routing.** Hoheit des Ticketsystems. Der Auditor kennt nur
  „lege eine Maßnahme an".
- **Eigene Kartenerzeugung.** Hoheit des Explorers.
