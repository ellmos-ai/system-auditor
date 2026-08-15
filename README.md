<img src="assets/banner.png" width="100%" alt="system-auditor banner">

# system-auditor

[![tests](https://img.shields.io/badge/pytest-136%20passed-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![dependencies](https://img.shields.io/badge/dependencies-none-lightgrey)](pyproject.toml)

**Evidence-based system audits across several machines — with meta bundling.**

*[Deutsche Fassung: `README_de.md`](README_de.md)*

---

## Why this exists

Two machines auditing the same domain do **not** produce the same result. That is not a
defect — it is the most useful thing about running the audit twice.

A measured example:

> **Finding:** *"Gardener governance hardcodes the laptop home path"* —
> `AGENTS.md` points at `C:\Users\alice\…`.
>
> On **WORKSTATION-LG** this is real: the path does not exist there.
> On the **laptop** the very same line is correct and produces no finding at all.

A single machine can only ever see one half of that. Comparing the valid audits of all
participating systems yields a classification no single run can produce:

| class | meaning |
|---|---|
| `systemwide` | every participant found it → genuine system defect |
| `host_specific` | some found it, others checked and did not → drift on one machine |
| `inverse` | a defect here, explicitly fine there → host dependency, usually a hardcoded path |
| `divergent` | same location, *different* rules broken → differing sync state or reading |
| `unverifiable` | someone never looked there → no statement possible, and we say so |

`unverifiable` is the honest rung. Without it, every gap in a participant's coverage would
silently masquerade as a real difference between systems.

---

## The three stages

    map      what is there            ->  system-explorer   (optional)
    verdict  what is wrong about it   ->  system-auditor    (this)
    measure  what we do about it      ->  ticket system     (optional)

A map is value-free; a ticket is an action. In between sits the judgement: *which rule is
violated, what do we recommend, and is the rule itself still right?* That is this module.

**Nothing here requires its neighbours.** Detected, they are used; absent, the auditor
reads directly and writes files. Same pattern in every direction: *know them, don't need
them.*

---

## Four tokens

Every audit answers four questions, and each answer is a token:

| token | question |
|---|---|
| `time` | *when* — which period window does this statement belong to |
| `domain` | *what* — which domain was audited |
| `system` | *where* — which machine was looked at |
| `auditor` | *who* — which model did the looking |

**Why discrete windows instead of a sliding validity span.** A sliding window ("valid for
14 days from the run") makes overlap a matter of degree — every machine has to compare
pairs to find out. A window *grid* derived from config turns that into a lookup: ask the
clock, get a token. Two machines that never talk to each other derive the same token for
the same moment, so "same period" becomes a string comparison instead of an agreement
problem.

The price is the boundary: two runs minutes apart can land in different windows. That is
deliberate — determinism across machines is worth more than smoothness at the edge, and
longer windows make the edge rarer.

## The aggregation ladder

Hold some tokens fixed, let the rest vary. **An aggregation may only attribute a cause when
exactly one dimension varies** — otherwise a difference is not identifiable. That rule is
enforced in the constructor, not just documented.

| aggregation | fixed | varies | what it tells you |
|---|---|---|---|
| `interrater` | time+domain+system | **auditor** | do two models agree? |
| `cross-system-rater` | time+domain+auditor | **system** | a *clean* host effect |
| `cross-system` | time+domain | **system** | machines, model uncontrolled — practical, but not proof |
| `cross-domain` | time+system+auditor | **domain** | is the same rule broken across domains? |
| `timeseries` | system+domain | **time** | how did this domain develop? |
| `timeseries-rater` | system+domain+auditor | **time** | development as *one* model sees it |
| `full-system` | time+system | domain **+** auditor | **descriptive only** — inventory, no classes |

`full-system` is the one where two dimensions vary at once. That is a useful picture of a
machine, but a difference between two cells cannot be traced to domain, model, or their
interaction — so it yields an **inventory** (`build_inventory`), not a verdict. Calling
`build_meta` on it raises.

`cross-domain` matches by **rule alone**: across domains there is no shared place. The flip
side is that *absence* is not observable there — a participant that did not report a rule
could never have covered a foreign domain's locator — so those cases stay `unverifiable`
and say why.

`interrater` reports **positive unanimity** plus a pairwise Jaccard. Deliberately not called
"agreement": only keys somebody raised enter the denominator, so shared silence about clean
places never counts. A chance-corrected measure (Cohen's kappa) is not computable without a
common item universe.

## One current answer per window

    system A audits `bundles`                        ->  single audit
    system B audits `bundles`                        ->  meta-2  (created)
    system C audits `bundles`                        ->  meta-3  (same file, rewritten)

Within a window the meta audit is **overwritten, not archived**: "what do we know about
this domain in this window" has one current answer, and keeping meta-2 beside meta-3 would
leave two answers to one question.

**History keeps itself.** Last window is a different token, hence a different file, and
stays untouched — nothing has to be moved for the record to exist. The only thing that
overwrites a *single* audit is a restatement with the same four tokens; that is a
correction, and it forces the window's meta audit to be rebuilt.

**Renewal belongs to the bearer.** Only the machine that produced an audit may restate it.
No system may retire a statement about a machine it cannot see.

---

## No lock — and why none is needed

Parallel audits of one domain are the *premise* of a meta audit, not a collision. There is
nothing to exclude, so this module holds no locks at all.

That is not a gap papered over, but it needed one correction:

- **The audit itself is read-only.** Nothing in the audited domain can collide.
- **The classification is deterministic** — same inputs, same output, byte for byte
  (the runs are ordered canonically first).
- **Duplicate work is largely prevented already.** `plan_metas` returns `skip` as soon as
  the artefact for a key rests on the same inputs.
- **But determinism is not permission to write blindly.** A run that planned earlier can
  overwrite a newer artefact another machine published meanwhile — a review reproduced
  exactly that. So `write_meta` re-reads the target and refuses when the file on disk
  already rests on a superset of the planned inputs. That is a *write guard*, not a lock:
  it costs one read, blocks nobody, and needs no coordination.

An earlier version carried a full claim protocol (quarantine, deterministic loser rule).
It turned out to protect compute time and a possible conflict copy — not correctness — and
was therefore **moved to `lock-master`** (`pure-locking/contested.py`), where exclusion is
the purpose rather than a nuisance. The design history is in this repository's git log.

---

## Install and use

```bash
python -m pip install -e .

# which audit window is it right now?
system-auditor config          # what was actually read?
system-auditor time-token

# which domain is next in my own rotation?
system-auditor next-domain --domains "bundles,skills,mcp" --reports ./reports --system $HOSTNAME

# where are this domain's rules, on whatever system this is?
system-auditor discover --domain-path /path/to/domain

# which meta audits are due in the current window?
system-auditor meta-plan --reports ./reports --aggregation cross-system
system-auditor meta-plan --reports ./reports --aggregation interrater

# which of my audits belong to an earlier window?
system-auditor stale --reports ./reports --system $HOSTNAME
```

## Configuration

```bash
cp config/system-auditor.config.example.json system-auditor.config.json
system-auditor config          # shows what was actually read
```

Found via `--config`, `SYSTEM_AUDITOR_CONFIG`, then `./`, `./config/`,
`~/.system-auditor/`. `system-auditor config` exists because a config that is present but
not being used is the failure that takes longest to notice — until 0.6.0 the shipped
example was read by *nothing*, and every setting it documented was inert.

**`reports_dir` is the meeting point.** It must live in a cloud-synchronised folder that
every participating machine shares — in a host-local directory a meta audit can
structurally never happen, because no foreign report ever arrives there. The example file
points at the shared module folder; `config` warns when the path looks host-local.

**The meta report is model-manual.** The auditor writes their own report following
[`templates/AUDIT-BERICHT.de.md`](templates/AUDIT-BERICHT.de.md); on discovering foreign
reports for the same domain and window, they write the meta report right after their own —
their interpretation, following [`templates/META-BERICHT.de.md`](templates/META-BERICHT.de.md).
`meta-plan` decides *whether* (`create`/`update`/`skip`); the library (`build_meta`) serves
as a cross-check. Both template headers speak exactly the parser's format.

The role prompt an agent follows is [`prompts/AUDITOR.de.md`](prompts/AUDITOR.de.md).

---

## Design notes

* **Zero dependencies.** Standard library only; the report front matter is parsed by a
  deliberately minimal reader, so the format cannot promise more than the parser accepts.
* **No second system.** No new file format, no status registry, no database. An earlier
  attempt at a parallel "in progress" registry elsewhere in this ecosystem had to be rolled
  back; the lesson is in the spec.
* **Coverage is declared, not assumed.** A run states what it looked at and what it
  confirmed as fine. Everything else stays `unverifiable`.

## Development

```bash
python -m pytest -q     # 136 tests
ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE).
