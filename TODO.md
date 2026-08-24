# TODO — system-auditor

## STATUS

| Category | Status |
|---|---|
| Tests / Lint | 158 passed, ruff sauber, keine Abhängigkeiten |
| Sprachstufe (P-006) | Core erfüllt: README + Rollen-Prompt + Templates je DE und EN |
| Release-Gate | Lauf siehe RELEASE_GATE.md |
| Bewusste Entscheidung | Kern-Doku zweisprachig DE/EN (CHANGELOG/TODO deutsch — internes Arbeitsjournal, absichtlich); `_review/`-Berichte bleiben lokal (gitignored): interne Systemdetails, kein Release-Inhalt |


Stand: 2026-08-24 · Version 0.9.1 · 158 Tests grün, ruff sauber, keine Abhängigkeiten

Drei externe Reviews sind eingearbeitet und liegen unter `_review/`:
Codex 1 (Robustheit, 12 Funde), Codex 2 (Logik, 12 Funde), Fable (Benutzbarkeit).

## Geklärt durch Nutzerentscheidung (2026-08-16)

Die zwei großen offenen Fragen des Fable-Reviews sind beantwortet:

- **Meta-Audits sind modellmanuell — by design, keine Lücke.** Auditoren
  schreiben ihre Berichte selbst; entdecken sie Fremdberichte derselben Domäne
  im selben Fenster, schreiben sie den Meta-Bericht direkt mit — als ihre
  Interpretation. Das Werkzeug liefert die Entscheidung (`meta-plan`), die
  Klassen und die Kontrolle (`build_meta`); die Einordnung macht das Modell.
  Dafür gibt es jetzt **`templates/AUDIT-BERICHT.de.md`** und
  **`templates/META-BERICHT.de.md`** — beide sprechen exakt das Format von
  `parse_front_matter` (testgesichert). Die „Torso"-Einordnung des Fable-Reviews
  ist damit gegenstandslos: Die fehlende Maschinen-Extraktion war nie der Plan.
- **Die Berichte treffen sich im cloud-geteilten Modulordner.** Vorausgesetzt
  ist ein Cloud-Ordner, den alle teilnehmenden Maschinen synchronisieren (auf
  diesem System: OneDrive, `.TOPICS/.AI/.MODULES/.CONTROL/system-auditor/`).
  Die Beispiel-Config zeigt dorthin; `config` warnt, wenn `reports_dir`
  host-lokal aussieht. Sync-Latenz ist einkalkuliert: Ein verspäteter
  Fremdbericht macht das nächste `meta-plan` zum `update`.

## Offen — Betrieb

- [ ] **Ausgefallene Fenster sind unsichtbar.** Wurde eine Woche gar nicht
      auditiert, bleibt ein Befund `persistent` mit `continuity_verified=True` —
      die Lücke existiert in den Daten nicht, weil kein Bericht sie meldet. Ein
      erwartetes Fensterraster müsste gegen die vorhandenen Berichte geprüft werden.
- [ ] **`stale` wächst unbegrenzt.** Alte Fenster werden gelistet, nie geräumt.

## Veröffentlichung (erledigt 2026-08-16)

- [x] `prompts/AUDITOR.en.md` + `templates/*.en.md` — Sprachstufe Core (P-006).
- [x] Freigabe zur Veröffentlichung vom User erteilt (2026-08-16).
- [x] Final Gate Check 10/10 PASS → `RELEASE_GATE.md` (UNLOCKED).
- [x] Remote: `ellmos-ai/system-auditor`.

## Offen — Ausbau

- [ ] **Maschinelle Findings-Extraktion als Kontrollpfad** (optional, nicht der
      Regelweg): `findings_detail:` im Berichtskopf ist jetzt Template-Standard
      (`locator | regel | titel` je Zeile) — ein späteres `meta-build`-Kommando
      könnte daraus `Finding`-Objekte bauen und die modellmanuelle Einordnung
      gegen `build_meta` prüfen.
- [ ] **Explorer-Adapter** (Beleg-A-Stufe 2/3): Coverage-/Kartenausgabe als
      Einstieg, Receipts als Beleg. Additiv hinter `enabled_probe`.
- [ ] Klassennamen sind achsenabhängig lesbar (`systemwide` heißt bei
      `interrater` „alle Modelle einig"). Die Überschriften passen sich an, die
      **Feldnamen nicht** — wer die Rohdaten liest, kann das missverstehen.
      Kandidat: neutrale Namen (`universal`/`partial`) mit achsenabhängiger Anzeige.
- [ ] JSON-Schema für den Berichtskopf.

## Erledigt (Auswahl)

- [x] Statusangaben nach Release 0.9.1 auf die verifizierten 158 Tests
      aktualisiert (2026-08-24).
- [x] Vier Token, Zeitraster, Aggregationsleiter mit erzwungener
      Identifizierbarkeit (0.5.0)
- [x] Zeitreihen mit eigenen Klassen und Beobachtungs-Flags
- [x] Bau-Politik `always`/`on_demand`/`off` je Aggregation
- [x] Schreibsicherung gegen veraltete Schreiber (0.4.1)
- [x] Lock-Protokoll verlegt nach `lock-master` (0.4.0)
- [x] Konfiguration wird tatsächlich gelesen; CLI-Anker repariert (0.6.0)
- [x] **Cloud-Treffpunkt + modellmanuelle Templates** (0.7.0) — Beispiel-Config
      zeigt auf den geteilten OneDrive-Modulordner, `config` warnt bei
      host-lokalem `reports_dir`; Berichts- und Meta-Templates mit
      parser-kompatiblem Kopf inkl. `window_start_utc` und `findings_detail`.

## Bewusst nicht gebaut

- **Automatische Findings-Extraktion als Regelweg** — der Meta-Bericht ist die
  Interpretation des Auditors, kein Maschinenprodukt (Nutzerentscheidung
  2026-08-16). Die Bibliothek bleibt Kontrollinstanz.
- **Gleitendes Gültigkeitsfenster** — ersetzt durch diskrete Zeitraster.
- **Archivierung im Normalfluss** — der Fixed-Key im Dateinamen trägt die
  Historie (für Snapshots über Fenstergrenzen; *nicht* für Zeitreihen).
- **Zentrales Cursor-Register** — der Bericht *ist* der Rotationsanker.
- **Ticket-IDs, Kategorien, Routing** — Hoheit des Ticketsystems.
- **Eigene Kartenerzeugung** — Hoheit des Explorers.
