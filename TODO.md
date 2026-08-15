# TODO — system-auditor

Stand: 2026-08-15 · Version 0.6.0 · 136 Tests grün, ruff sauber, keine Abhängigkeiten

Drei externe Reviews sind eingearbeitet und liegen unter `_review/`:
Codex 1 (Robustheit, 12 Funde), Codex 2 (Logik, 12 Funde), Fable (Benutzbarkeit).

## Die eine offene Lücke, die alles andere blockiert

- [ ] **Findings maschinenlesbar aus Berichten gewinnen.** `meta-plan` entscheidet
      zuverlässig, *ob* ein Meta-Audit fällig ist, und `build_meta()` klassifiziert
      korrekt — aber nichts extrahiert `Finding`-Objekte aus geschriebenen
      Berichten, denn die sind Prosa. Der Agent stellt sie heute selbst zusammen.

      **Das Fable-Review nennt das Modul deshalb einen Torso mit exzellenten
      Einzelteilen — zu Recht.** Zwei Konsequenzen, die daran hängen:
      Determinismus und Schreibsicherung greifen an `Finding`-Objekten, die nur
      aus Prosa rekonstruierbar sind; und `write_meta` vergleicht Run-IDs, nicht
      Inhalte, merkt also nicht, wenn zwei Läufe dieselben Eingaben verschieden
      interpretiert haben.

      Nächster Schritt: `findings_detail: [{locator, rule, title}]` im
      Berichtskopf, dann `meta-build` als Kommando.

## Offen — Betrieb (aus dem Fable-Review)

- [ ] **Wo treffen sich die Berichte physisch?** `reports_dir` zeigt per Default
      auf ein host-lokales Verzeichnis — dort kann ein Meta-Audit strukturell nie
      entstehen, weil keine zweite Maschine hinschreibt. Ohne diese Entscheidung
      (geteilter Ordner? Sync-Latenz?) trägt die lockfreie Architektur nicht.
      **Das ist die Frage, die vor dem ersten Produktivlauf beantwortet sein muss.**
- [ ] **Ausgefallene Fenster sind unsichtbar.** Wurde eine Woche gar nicht
      auditiert, bleibt ein Befund `persistent` mit `continuity_verified=True` —
      die Lücke existiert in den Daten nicht, weil kein Bericht sie meldet. Ein
      erwartetes Fensterraster müsste gegen die vorhandenen Berichte geprüft werden.
- [ ] **`stale` wächst unbegrenzt.** Alte Fenster werden gelistet, nie geräumt.
- [ ] **`window_start_utc` wird von keinem dokumentierten Schritt befüllt** —
      das Feld existiert und trägt die Chronologie, aber der Prompt sagt nirgends,
      dass es zu setzen ist.
- [ ] Kein Kommando für Bericht-Schreiben, Maßnahmen-Ausgabe und Meta-Bau; diese
      Schritte laufen über die Bibliothek, nicht über die CLI.

## Offen — vor einer Veröffentlichung

- [ ] `prompts/AUDITOR.en.md` — Sprachstufe Core (DE+EN) ist Pflicht (P-006).
- [ ] `PRIVATE.txt`-Gate setzen oder Freigabe einholen (`visibility: private`).
- [ ] Remote anlegen und pushen (bisher nur lokal).

## Offen — Ausbau

- [ ] **Explorer-Adapter** (Beleg-A-Stufe 2/3): Coverage-/Kartenausgabe als
      Einstieg, Receipts als Beleg. Additiv hinter `enabled_probe`.
- [ ] Klassennamen sind achsenabhängig lesbar (`systemwide` heißt bei
      `interrater` „alle Modelle einig"). Die Überschriften passen sich an, die
      **Feldnamen nicht** — wer die Rohdaten liest, kann das missverstehen.
      Kandidat: neutrale Namen (`universal`/`partial`) mit achsenabhängiger Anzeige.
- [ ] JSON-Schema für den Berichtskopf.

## Erledigt (Auswahl)

- [x] Vier Token, Zeitraster, Aggregationsleiter mit erzwungener
      Identifizierbarkeit (0.5.0)
- [x] Zeitreihen mit eigenen Klassen und Beobachtungs-Flags
- [x] Bau-Politik `always`/`on_demand`/`off` je Aggregation
- [x] Schreibsicherung gegen veraltete Schreiber (0.4.1)
- [x] Lock-Protokoll verlegt nach `lock-master` (0.4.0)
- [x] **Konfiguration wird tatsächlich gelesen** (0.6.0) — bis dahin war die
      Beispieldatei reine Dokumentation: kein `json.load` im Modul, kein
      `--config`. Jede dort dokumentierte Einstellung war wirkungslos.
- [x] **CLI-Anker zerstörte das Zeitfenster** (0.6.0): Default war Mitternacht
      des Aufruftags, damit degenerierte ein 7-Tage-Fenster zu Tagesfenstern.

## Bewusst nicht gebaut

- **Gleitendes Gültigkeitsfenster** — ersetzt durch diskrete Zeitraster.
- **Archivierung im Normalfluss** — der Fixed-Key im Dateinamen trägt die
  Historie (für Snapshots über Fenstergrenzen; *nicht* für Zeitreihen).
- **Zentrales Cursor-Register** — der Bericht *ist* der Rotationsanker.
- **Ticket-IDs, Kategorien, Routing** — Hoheit des Ticketsystems.
- **Eigene Kartenerzeugung** — Hoheit des Explorers.
