<img src="assets/banner.png" width="100%" alt="system-auditor banner">

# system-auditor

[![tests](https://img.shields.io/badge/pytest-136%20bestanden-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/lizenz-MIT-green)](LICENSE)
[![dependencies](https://img.shields.io/badge/abh%C3%A4ngigkeiten-keine-lightgrey)](pyproject.toml)

**Belegbasierte Systemaudits über mehrere Maschinen — mit Meta-Bündelung.**

*[English version: `README.md`](README.md)*

---

## Wozu

Der Auditor prüft ein komponiertes System in **drei Richtungen**: verletzt ein Zustand
eine Regel (*Regeltreue*), **arbeiten die Module so zusammen, wie es gedacht ist**
(*Integration* — deklarierte Zusammenarbeit aus Manifesten, Bundles und Bindings gegen
die Wirklichkeit, Prüfklassen I1–I7), und **sind Steuerdateien, Policies und bisherige
Entscheidungen untereinander konsistent** (*Steuerungs-Konsistenz*, Prüfklassen K1–K4).
Das Ziel ist Konvergenz: Jeder Fund endet mit einer Richtung — Realität an die Regel
anpassen (Maßnahme) oder Regel an die Realität (Entscheidungsvorlage).

Zwei Maschinen, die dieselbe Domäne auditieren, kommen **nicht** zum selben Ergebnis. Das
ist kein Mangel — es ist das Nützlichste daran, das Audit zweimal laufen zu lassen.

Ein gemessenes Beispiel:

> **Befund:** *„Gardener-Governance hartkodiert den Laptop-Home-Pfad"* —
> `AGENTS.md` verweist auf `C:\Users\alice\…`.
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

Einige Token festhalten, den Rest variieren lassen. **Eine Ursache darf eine Aggregation nur
dann zuschreiben, wenn genau eine Dimension variiert** — sonst ist ein Unterschied nicht
identifizierbar. Diese Regel wird im Konstruktor erzwungen, nicht bloß dokumentiert.

| Aggregation | fest | variiert | was sie zeigt |
|---|---|---|---|
| `interrater` | time+domain+system | **auditor** | sind sich zwei Modelle einig? |
| `cross-system-rater` | time+domain+auditor | **system** | ein *sauberer* Host-Effekt |
| `cross-system` | time+domain | **system** | Maschinen, Modell unkontrolliert — praktisch, aber kein Beleg |
| `cross-domain` | time+system+auditor | **domain** | bricht dieselbe Regel über Domänen? |
| `timeseries` | system+domain | **time** | wie hat sich die Domäne entwickelt? |
| `timeseries-rater` | system+domain+auditor | **time** | Entwicklung aus Sicht *eines* Modells |
| `full-system` | time+system | domain **+** auditor | **nur deskriptiv** — Bestand, keine Klassen |

`full-system` ist die Stufe, in der zwei Dimensionen zugleich variieren. Das ergibt ein
nützliches Bild einer Maschine, aber ein Unterschied zwischen zwei Zellen lässt sich weder
der Domäne noch dem Modell noch ihrem Zusammenspiel zuordnen — deshalb liefert sie eine
**Bestandsaufnahme** (`build_inventory`), kein Urteil. `build_meta` darauf wirft.

`cross-domain` vergleicht über die **Regel allein**: Zwischen Domänen gibt es keinen
gemeinsamen Ort. Die Kehrseite: *Abwesenheit* ist dort nicht beobachtbar — wer eine Regel
nicht meldet, hätte den fremden Ort nie abdecken können — solche Fälle bleiben
`unverifiable` und sagen warum.

`interrater` liefert **positive Einstimmigkeit** plus paarweisen Jaccard. Bewusst nicht
„Agreement" genannt: In den Nenner gehen nur Schlüssel ein, die jemand gemeldet hat;
gemeinsames Schweigen über saubere Stellen zählt nie mit. Ein zufallskorrigiertes Maß
(Cohens Kappa) ist ohne gemeinsame Item-Menge gar nicht berechenbar.

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

## Kein Lock — und warum keiner nötig ist

Parallele Audits einer Domäne sind die *Voraussetzung* eines Meta-Audits, keine Kollision.
Es gibt nichts auszuschließen, deshalb hält dieses Modul überhaupt keine Locks.

Das ist keine überdeckte Lücke — brauchte aber eine Korrektur:

- **Das Audit selbst ist read-only.** In der geprüften Domäne kann nichts kollidieren.
- **Die Klassifikation ist deterministisch** — gleiche Eingaben, gleiche Ausgabe, Byte für
  Byte (die Läufe werden vorher kanonisch geordnet).
- **Doppelarbeit verhindert die Planung weitgehend.** `plan_metas` liefert `skip`, sobald
  das Artefakt eines Schlüssels auf denselben Eingaben ruht.
- **Determinismus ist aber keine Erlaubnis, blind zu schreiben.** Ein früher geplanter Lauf
  kann ein neueres Artefakt überschreiben, das eine andere Maschine inzwischen
  veröffentlicht hat — ein Review hat genau das reproduziert. `write_meta` liest deshalb
  vor dem Schreiben erneut und verweigert, wenn die Datei auf der Platte bereits auf einer
  Obermenge der geplanten Eingaben ruht. Das ist eine *Schreibsicherung*, kein Lock: Sie
  kostet einen Lesevorgang, blockiert niemanden und braucht keine Abstimmung.

Eine frühere Fassung trug ein vollständiges Claim-Protokoll (Quarantäne, deterministische
Verlierer-Regel). Es schützte, wie sich zeigte, Rechenzeit und eine mögliche Konfliktkopie
— nicht die Korrektheit — und ist deshalb **nach `lock-master` verlegt**
(`pure-locking/contested.py`), wo Ausschluss der Zweck ist statt ein Ärgernis. Die
Entwurfsgeschichte steht im Git-Log dieses Repositoriums.

---

## Installation und Nutzung

```bash
python -m pip install -e .

# In welchem Audit-Fenster sind wir gerade?
system-auditor config          # was wurde gelesen?
system-auditor time-token

# Welche Domäne ist in meiner eigenen Rotation als nächste dran?
system-auditor next-domain --domains "bundles,skills,mcp" --reports ./reports --system $HOSTNAME

# Wo liegen die Regeln dieser Domäne — auf welchem System auch immer?
system-auditor discover --domain-path /pfad/zur/domaene

# Welche Meta-Audits sind im aktuellen Fenster fällig?
system-auditor meta-plan --reports ./reports --aggregation cross-system
system-auditor meta-plan --reports ./reports --aggregation interrater

# Welche meiner Audits gehören zu einem früheren Fenster?
system-auditor stale --reports ./reports --system $HOSTNAME
```

## Konfiguration

```bash
cp config/system-auditor.config.example.json system-auditor.config.json
system-auditor config          # zeigt, was tatsächlich gelesen wurde
```

Gefunden über `--config`, `SYSTEM_AUDITOR_CONFIG`, dann `./`, `./config/`,
`~/.system-auditor/`. Das Kommando `config` gibt es, weil eine vorhandene, aber nicht
benutzte Konfiguration der Fehler ist, den man am längsten übersieht — bis 0.6.0 wurde die
mitgelieferte Beispieldatei von **nichts** gelesen, und jede dort dokumentierte Einstellung
war wirkungslos.

**`reports_dir` ist der Treffpunkt.** Er muss in einem cloud-synchronisierten Ordner
liegen, den alle teilnehmenden Maschinen teilen — in einem host-lokalen Verzeichnis kann
strukturell nie ein Meta-Audit entstehen, weil dort kein Fremdbericht ankommt. Die
Beispieldatei zeigt auf den geteilten Modulordner; `config` warnt, wenn der Pfad
host-lokal aussieht.

**Der Meta-Bericht ist modellmanuell.** Der Auditor schreibt seinen Bericht nach
[`templates/AUDIT-BERICHT.de.md`](templates/AUDIT-BERICHT.de.md); entdeckt er Fremdberichte
derselben Domäne im selben Fenster, schreibt er den Meta-Bericht direkt mit — seine
Interpretation, nach [`templates/META-BERICHT.de.md`](templates/META-BERICHT.de.md).
`meta-plan` entscheidet *ob* (`create`/`update`/`skip`), die Bibliothek (`build_meta`)
dient der Kontrolle. Beide Template-Köpfe sprechen exakt das Format des Parsers.

Der Rollen-Prompt für Agenten: [`prompts/AUDITOR.de.md`](prompts/AUDITOR.de.md).

---

## Entwurfsentscheidungen

* **Keine Abhängigkeiten.** Nur Standardbibliothek; der Berichtskopf wird von einem
  bewusst minimalen Leser geparst — so kann das Format nicht mehr versprechen, als der
  Parser annimmt.
* **Kein zweites System.** Kein neues Dateiformat, keine Status-Registry, keine Datenbank.
  Ein früherer Versuch mit einer parallelen „in Arbeit"-Registry musste in diesem
  Ökosystem zurückgebaut werden; die Lehre steht in der Spec.
* **Abdeckung wird deklariert, nicht unterstellt.** Ein Lauf sagt, was er angesehen und was
  er als in Ordnung bestätigt hat. Alles andere bleibt `unverifiable`.

## Entwicklung

```bash
python -m pytest -q     # 136 Tests
ruff check src tests
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
