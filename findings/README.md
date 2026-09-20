# Findings and current readback

Ein Finding ist eine Beobachtung, keine bestätigte Maßnahme. Eine offene
Maßnahme darf beim Dedup nur dann als dasselbe Problem behandelt werden, wenn
ihre aktuelle Wirksamkeit durch einen **datierten Readback** belegt ist:

`YYYY-MM-DD | actor@host | observed state — measurement / receipt`

Ein alter Plan, ein Commit, ein Push, ein Ticketstatus oder ein früherer
Laufbericht ist kein aktueller Readback. Fehlt der Readback, bleibt der Befund
`needs_readback` bzw. eine Beobachtung; er wird nicht still als erledigt oder
dupliziert verworfen. Der Readback muss den geprüften Ort, den aktuellen Wert
und — soweit relevant — den Lock-/Ownership-Zustand erkennen lassen.

Historical findings remain at their original location. A changed conclusion is
recorded as a dated `NACHTRAG`/`SUPERSEDED` block with actor, ticket or measure
reference, and evidence.

## Current-readback rule (English)

Deduplication may match a new finding to an existing measure only when the
existing measure has a current, dated readback by `actor@host` that identifies
the inspected location, observed value, and relevant lock or ownership state.
A plan, commit, push, ticket status, or stale report is not a readback. Without
that receipt, keep the result as `needs_readback`/an observation and do not
silently close or suppress it.
