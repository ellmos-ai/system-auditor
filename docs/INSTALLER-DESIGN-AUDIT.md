# Begrenzte native Prüfung eines Installationsdesigns

`system-auditor --json installer-design` führt den vorhandenen
`OpenOceanAdapter.plan_design` im exakt gepinnten Installer-Checkout aus. Dieser
verwendet dieselbe Ocean-Kompositionsprüfung wie die spätere Installation und
übergibt niemals `--apply`. Es gibt keine zweite Installationsengine.

Erforderlich sind das Design, `--installer-src`, `--installer-commit`,
`--ocean-cli`, `--ocean-commit` und `--producer-commit` des tatsächlichen
Auditor-Checkouts. Alle drei Checkouts müssen sauber sein und zur deklarierten
kanonischen Repositoryidentität gehören. Kein Download, kein Modellaufruf,
keine Provideraktivierung und keine Netzwerkprüfung werden ausgeführt.

`--ocean-cli` zeigt genau auf `<open-ocean>/tools/ocean_dev.py`, den vorhandenen
kanonischen Einstieg für die Kompositionsflags. `ocean.py` bietet die separate
Produktoberfläche und akzeptiert diesen Flagvertrag nicht.

Der Export ist auf explizite Module eines GUI-Add-ons begrenzt. Alle sechs
Dateieingaben werden einmal aufgenommen; die nativen Validatoren lesen private,
unveränderte Momentaufnahmen dieser Bytes. Der Katalog dient dabei zur
Identitätsauflösung; lokale relative Providerpfade werden nicht als installierte
Provider bestätigt. Exakte Bindings und Sourcepins bleiben erforderlich.
Die native Policy-Discovery liest nur das Verzeichnis der tatsächlich geprüften
Bundlemanifeste. Nach Prozessabschluss werden Design, Eingaben, Producerpins
und Metadaten der ausgewählten technischen Modulplätze erneut geprüft.

Die Receipt enthält den vollständigen Designhash, seinen Dateibytehash,
Eingangshashes, Producercommits, Policyquellen, den echten nativen Report und
acht verpflichtende Prüfergebnisse. Fehlende Ergebnisse, Fehler, Drift und
Timeout ergeben keinen PASS. Bei Timeout wird der eigene Prozessbaum beendet.
Es wird kein bereitgestellter fremder PASS-Report importiert.

`status=pass` bezeichnet ausschließlich diese mechanische Installationsplanung.
`runtime_verified`, `governance_verified` und `authorization` bleiben false.
Die Metadatenprüfung liest keine Dateiinhalte im Ziel und prüft keine Datenbank.
Ein fremder Hostpfad braucht eine eigene Prüfung auf diesem Host. Die Receipt
ist kein signierter Vertrauensanker, keine Ownerfreigabe und kein Capabilitygrant.
Der Installer bindet sie an die exakten Designbytes; seine bestehenden externen
Autorisierungsgrenzen bleiben erforderlich.
