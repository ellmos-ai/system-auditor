---
run_id: <SYSTEM>-<AUDITOR>-<YYYYMMDD-HHMMSS>
audit_mode: self
time_token: <FROM system-auditor time-token>
domain: <DOMAIN>
system: <FULL-HOSTNAME>
auditor: <MODEL-OR-AGENT>
started_utc: <YYYY-MM-DDTHH:MM:SSZ>
finished_utc: <YYYY-MM-DDTHH:MM:SSZ>
window_start_utc: <window start from system-auditor time-token -- carries the chronology, NOT the token text>
next_domain: <next domain in the rotation>
findings: 0
measures: []
evidence_level: 1
coverage: [<path-prefix-1>, <path-prefix-2>]
clean: [<place-explicitly-fine>]
findings_detail:
- <locator> | <violated-rule> | <short-title>
---

# Audit <DOMAIN> — <SYSTEM> — window <time_token>

> **File name:** `AUDIT-<time>--<domain>.<system>.<auditor>.md` — double hyphen
> between time and domain, or names collide.
> **Header first, prose after.** The header is what machines and later meta audits
> read; everything below this line is your interpretation.
> Delete these blockquote hints in the finished report.

## Assignment and coverage

- **Assignment path:** <explicit | selector | rotation> — <evidence, e.g. last report>
- **What was checked:** <what coverage[] concretely means — which level, which depth>
- **Not checked:** <parts deliberately left out, with reason>
- **Rule sources:** <tier of the cascade: configured / module probe / convention / nothing>

## Findings

> One block per finding. Without B and C it is not a measure but an observation
> (below). `findings:` in the header counts only the blocks here.

### Finding 1 — <short title>

- **A — problem and location:** <concrete path (line if applicable); observed actual
  state; condition of occurrence>
- **B — violated rule:** <policy with its location>
- **C — basis of the recommendation:** <decision/policy with location>
- **RECOMMENDATION:** <what should be done — you change nothing>
- **COUNTER-ARGUMENT:** <absent the past decisions, would there be a better solution?
  Is the rule itself outdated?>
- **DRIFT VERDICT:** <unwanted drift | wanted drift (→ rule adaptation as a decision
  proposal) | no drift>

## Observations without evidence

<Candidates missing B or C — record here, do not emit as measures.>

## Measure output

<Where the findings went: sink (reference) or file fallback (path). Empty on zero
findings.>

## Meta step (mandatory check at the end)

<Result of `system-auditor meta-plan`: were there foreign reports for the same domain
in the same window? If yes: meta report written right away following
templates/META-REPORT.en.md — name the file here. If no: "no partner in this window"
is the normal result.>
