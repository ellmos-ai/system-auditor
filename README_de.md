# system-auditor

[![tests](https://img.shields.io/badge/pytest-86%20bestanden-brightgreen)](tests/)
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

## Vier Token

Jedes Audit beantwortet vier Fragen, und jede Antwort ist ein Token:

| Token | Frage |
|---|---|
| `time` | *wann* — zu welchem Zeitfenster gehört diese Aussage |
| `domain` | *was* — welche Domäne wurde auditiert |
| `system` | *wo* — auf welche Maschine wurde geschaut |
| `auditor` | *wer* — welches Modell hat geschaut |

**Warum diskrete Fenster statt eines gleitenden Gültigkeitsspanne.** Ein gleitendes Fenster
(„gilt 14 Tage ab dem Lauf") macht Überlappung zur Gradfrage — jede Maschine müsste Paare
vergleichen, um es herauszufinden. Ein aus der Config abgeleitetes **Raster** macht daraus
eine Abfrage: Uhr fragen, Token bekommen. Zwei Maschinen, die nie miteinander sprechen,
leiten für denselben Moment denselben Token ab; „gleicher Zeitraum" wird damit zum
Stringvergleich statt zum Abstimmungsproblem.

Der Preis ist die Grenze: Zwei Läufe wenige Minuten auseinander können in verschiedenen
Fenstern landen. Das ist bewusst so — Determinismus zwischen Maschinen wiegt schwerer als
Glätte am Rand, und längere Fenster machen den Rand seltener.

## Die Aggregationsleiter

Einige Token festhalten, genau einen variieren lassen:

| Aggregation | fest | variiert | was sie zeigt |
|---|---|---|---|
| `interrater` | time+domain+system | **auditor** | sind sich zwei Modelle einig? |
| `cross-system` | time+domain | **system** | liegt es am System oder an der Maschine? |
| `cross-domain` | time | **domain** | wird dieselbe Regel überall verletzt? |

Die letzte Stufe vergleicht über die **Regel allein**. Zwischen Maschinen vergleicht man
denselben *Ort*; zwischen Domänen gibt es keinen gemeinsamen Ort — Bedeutung trägt dort, ob
dieselbe Regel in unverbundenen Ecken verletzt wird. Das macht es zu einem Problem der
Regel statt eines einzelnen Ortes.

`interrater` liefert zusätzlich eine **Übereinstimmungsquote**. Ein niedriger Wert ist dort
kein Systemmangel, sondern ein Zuverlässigkeitsproblem der Auditoren selbst.

## Eine gültige Antwort je Zeitfenster

    System A auditiert `bundles`                     ->  Einzelaudit
    System B auditiert `bundles`                     ->  meta-2  (angelegt)
    System C auditiert `bundles`                     ->  meta-3  (dieselbe Datei, neu geschrieben)

Innerhalb eines Fensters wird das Meta-Audit **überschrieben, nicht archiviert**: „Was
wissen wir über diese Domäne in diesem Fenster" hat eine gültige Antwort, und meta-2 neben
meta-3 stehen zu lassen hieße, zwei Antworten auf eine Frage zu haben.

**Die Historie ergibt sich von selbst.** Das letzte Fenster hat einen anderen Token, also
eine andere Datei, und bleibt unberührt — es muss nichts verschoben werden, damit der Beleg
existiert. Ein *Einzelaudit* wird nur durch eine Wiederholung mit denselben vier Token
überschrieben; das ist eine Korrektur, und sie erzwingt den Neubau des Meta-Audits.

**Erneuern darf nur der Träger.** Nur die Maschine, die ein Audit erzeugt hat, darf es neu
aussprechen. Kein System zieht eine Aussage über eine Maschine zurück, die es nicht sehen
kann.

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

# In welchem Audit-Fenster sind wir gerade?
system-auditor time-token --period 7d

# Welche Domäne ist in meiner eigenen Rotation als nächste dran?
system-auditor next-domain --domains "bundles,skills,mcp" --reports ./reports --system $HOSTNAME

# Anwesenheit melden (schließt niemanden aus)
system-auditor claim --locks ./_locks --domain bundles --system $HOSTNAME --mode presence

# Wo liegen die Regeln dieser Domäne — auf welchem System auch immer?
system-auditor discover --domain-path /pfad/zur/domaene

# Welche Meta-Audits sind im aktuellen Fenster fällig?
system-auditor meta-plan --reports ./reports --aggregation cross-system
system-auditor meta-plan --reports ./reports --aggregation interrater

# Welche meiner Audits gehören zu einem früheren Fenster?
system-auditor stale --reports ./reports --system $HOSTNAME

system-auditor release --locks ./_locks --domain bundles --system $HOSTNAME
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
python -m pytest -q     # 86 Tests
ruff check src tests
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
