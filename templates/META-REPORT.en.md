---
run_id: <SYSTEM>-<AUDITOR>-<YYYYMMDD-HHMMSS>
audit_mode: meta
aggregation: <cross-system-rater | interrater | cross-system | cross-domain | timeseries | timeseries-rater | full-system>
meta_level: <NUMBER of inputs -- grows when a participant joins>
time_token: <shared time window of the inputs; empty only for time series>
domain: <shared domain; empty for cross-domain>
system: <shared system; empty when the system axis varies>
auditor: <shared auditor; empty when the auditor axis varies>
finished_utc: <YYYY-MM-DDTHH:MM:SSZ>
participants: [<varying values, e.g. HOST-A, HOST-B>]
inputs: [<run_id-1>, <run_id-2>]
scope: [<values of the fixed dimensions, in file-name order>]
findings: 0
measures: []
evidence_level: 1
coverage: []
clean: []
---

# Meta audit <aggregation> — window <time_token>

> **File name:** `META-<aggregation>--<fixed-keys>.md` — **no host token** and no
> participant count: per (window, scope, aggregation) there is exactly one current
> answer; a new participant **overwrites the same file** (meta-2 → meta-3). Read
> before overwriting: if a **superset** of your inputs is already there (meta_level ≥
> yours, your inputs contained), do NOT write — your state is outdated.
> **The ground rule:** only an aggregation that lets exactly ONE dimension vary may
> attribute a cause. `full-system` therefore only describes.
> Delete these blockquote hints in the finished report.

## Inputs

| run_id | system | auditor | findings | coverage (short form) |
|---|---|---|---|---|
| <run_id-1> | <HOST-A> | <model> | <n> | <prefixes> |
| <run_id-2> | <HOST-B> | <model> | <n> | <prefixes> |

**Per identity the newest audit counts** (same four tokens = same statement,
corrected). Name excluded older states here.

## Classification

> Model-manual: you read the input reports and sort every finding yourself.
> Normalise locators before comparing (path separators, case, host parts). The
> partners' `coverage[]`/`clean[]` decide whether absence is proven — **not your
> guess**.

### <systemwide | for interrater: unanimous>

<Findings that ALL participants report → genuine system inconsistency. Per finding:
locator, rule, who reports it.>

### <host_specific | model_specific>

<Some report it, others checked the place (coverage!) and found nothing → drift.>

### inverse

<Defect here, explicitly in `clean[]` there → host dependency, classically a
hardcoded path. Strongest class — needs the explicit clean evidence.>

### divergent

<Same location, different violated rules → state or interpretation differs.>

### unverifiable

<One participant never checked there → no statement. The honest class — do not fill
it with guesses.>

## Agreement

<For interrater: unanimity rate and pairwise agreement (Jaccard). A low value is a
reliability problem of the auditors, NOT a system defect. For time series instead:
new/persistent/resolved/recurring per finding, with
first_absence_verified/continuity_verified — "every window found it" means
persistent, not systemwide.>

## Interpretation and recommendations

<Your reading: what follows from the classes? Which findings deserve a measure at
which level (one host / all hosts / the rule itself)? Name caveats — for
cross-system a difference is NOT a proven host effect.>
