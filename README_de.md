# system-auditor

[![tests](https://img.shields.io/badge/pytest-62%20bestanden-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/lizenz-MIT-green)](LICENSE)
[![dependencies](https://img.shields.io/badge/abh%C3%A4ngigkeiten-keine-lightgrey)](pyproject.toml)

**Belegbasierte Systemaudits über mehrere Maschinen — mit Meta-Bündelung.**

*[English version: `README.md`](README.md)*

---

## Wozu

Zwei Maschinen, die dieselbe Domäne auditieren, kommen **nicht** zum selben Ergebnis. Das
ist kein Mangel — es ist das Nützlichste daran, das Audit zweimal laufen zu lassen.

Ein gemessenes Beispiel:

> **Befund:** *„Gardener-Governance hartkodiert den Laptop-Home-Pfad"* —
> `AGENTS.md` verweist auf `C:\Users\User\…`.
>
> Auf **WORKSTATION-LG** ist das real: Der Pfad existiert dort nicht.
> Auf dem **Laptop** ist dieselbe Zeile korrekt und ergibt gar keinen Befund.

Eine einzelne Maschine sieht davon immer nur die Hälfte. Der Vergleich der gültigen Audits
aller beteiligten Systeme liefert eine Einordnung, die ein Einzellauf strukturell nicht
erzeugen kann:

| Klasse | Bedeutung |
|---|---|
| `systemwide` | alle Teilnehmer fanden es → echte Systeminkonsistenz |
| `host_specific` | manche fanden es, andere haben geprüft und nichts gefunden → Drift |
| `inverse` | hier ein Mangel, dort ausdrücklich in Ordnung → Host-Abhängigkeit, meist hartkodierter Pfad |
| `divergent` | gleicher Ort, *verschiedene* Regeln verletzt → Stand oder Auslegung differiert |
| `unverifiable` | jemand hat dort nie geprüft → keine Aussage möglich, und wir sagen das |

`unverifiable` ist die ehrliche Klasse. Ohne sie würde jede Lücke in der Abdeckung eines
Teilnehmers stillschweigend als echter Unterschied zwischen Systemen erscheinen.

---

## Die drei Stufen

    Karte     Was ist da?              ->  system-explorer   (optional)
    Urteil    Was ist daran falsch?    ->  system-auditor    (dieses Modul)
    Maßnahme  Was tun wir?             ->  Ticketsystem      (optional)

Eine Karte ist wertfrei, ein Ticket ist eine Handlung. Dazwischen liegt das Urteil: *welche
Regel ist verletzt, was empfehlen wir, und ist die Regel selbst noch richtig?*

**Kein Nachbar ist Voraussetzung.** Erkannt werden sie genutzt, fehlen sie, liest der
Auditor direkt und schreibt Dateien. In jede Richtung dasselbe Prinzip: *kennt sie, braucht
sie nicht.*

---

## Meta-Audits

    System A auditiert `bundles`                          ->  Einzelaudit
    System B auditiert `bundles`, sieht das von A         ->  meta-2
    System C auditiert `bundles`, sieht meta-2 + 3 Einzel ->  meta-3, meta-2 archiviert

Zwei Eigenschaften halten das ehrlich:

* **Gültigkeit ist ausdrücklich.** Ein Audit ist eine Aussage über einen Zeitpunkt. Die
  Aussage vom letzten Monat mit der von heute zu bündeln würde einen „Unterschied zwischen
  Systemen" erfinden, der in Wahrheit ein Unterschied in der Zeit ist. Veraltete Audits
  werden ausgeschlossen — und der Ausschluss wird **benannt**, nie stillschweigend.
* **Erneuern darf nur der Träger.** Ein veraltetes Audit erneuert die Maschine, die es
  erzeugt hat. Kein System darf eine Aussage über eine Maschine zurückziehen, die es nicht
  sehen kann. Ersetztes wird archiviert, nie gelöscht.

---

## Der Lock ist ein Präsenzsignal, keine Schranke

Weil parallele Einzelaudits *erwünscht* sind, schließt der Audit-Lock niemanden aus:

| Modus | Bedeutung |
|---|---|
| `presence` | „Auf System X läuft ein Selbstaudit dieser Domäne" — informativ; **nie** ein Grund, eine Domäne zu überspringen, und nie ein Grund für andere, die Arbeit einzustellen |
| `claim` | „Ich baue das Meta-Audit über genau diese Eingaben" — hier ist Redundanz wertlos, deshalb schließen sich Claims gegenseitig aus |

Ein Lock allein überlebt einen synchronisierten Ordner nicht: Bei 30 s – 5 min Latenz
schauen beide Maschinen, sehen nichts und sperren beide. Claims tragen deshalb eine
deterministische Auflösung — Quarantäne, erneutes Lesen, frühestes `created` gewinnt,
Host-Ordnung bricht exakte Gleichstände. Beide Seiten kommen bei gleicher Datenlage zum
selben Urteil, ohne Server.

Die Dateien nutzen die vorhandene Lock-Grammatik des Ökosystems
(`LOCK.audit.<domäne>.<host>.txt`), bestehende Scanner sehen sie ohne Codeänderung. Volles
Protokoll: [`protocols/audit-host-lock/SPEC.md`](protocols/audit-host-lock/SPEC.md) —
selbsttragend, von Hand ausführbar, ohne Bibliothek.

---

## Installation und Nutzung

```bash
python -m pip install -e .

# Welche Domäne ist in meiner eigenen Rotation als nächste dran?
system-auditor next-area --areas "bundles,skills,mcp" --reports ./reports --host $HOSTNAME

# Anwesenheit melden (schließt niemanden aus)
system-auditor claim --locks ./_locks --area bundles --host $HOSTNAME --mode presence

# Wo liegen die Regeln dieser Domäne — auf welchem System auch immer?
system-auditor discover --area-path /pfad/zur/domaene

# Ist ein Meta-Audit fällig?
system-auditor meta-plan --reports ./reports --area bundles --validity 14d

system-auditor release --locks ./_locks --area bundles --host $HOSTNAME
```

Der Rollen-Prompt für Agenten: [`prompts/AUDITOR.de.md`](prompts/AUDITOR.de.md).
Konfiguration: `config/system-auditor.config.example.json` kopieren.

---

## Entwurfsentscheidungen

* **Keine Abhängigkeiten.** Nur Standardbibliothek; das Lock-Format ist Klartext, der
  Berichtskopf wird von einem bewusst minimalen Leser geparst — so kann die Spezifikation
  nicht mehr versprechen, als der Parser annimmt.
* **Kein zweites System.** Kein neues Dateiformat, keine Status-Registry, keine Datenbank.
  Ein früherer Versuch mit einer parallelen „in Arbeit"-Registry musste in diesem
  Ökosystem zurückgebaut werden; die Lehre steht in der Spec.
* **Abdeckung wird deklariert, nicht unterstellt.** Ein Lauf sagt, was er angesehen und was
  er als in Ordnung bestätigt hat. Alles andere bleibt `unverifiable`.

## Entwicklung

```bash
python -m pytest -q     # 62 Tests
ruff check src tests
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
