# system-auditor

[![tests](https://img.shields.io/badge/pytest-62%20passed-brightgreen)](tests/)
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
> `AGENTS.md` points at `C:\Users\User\…`.
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

## Meta audits

    system A audits `bundles`                            ->  single audit
    system B audits `bundles`, sees A's                  ->  meta-2
    system C audits `bundles`, sees meta-2 + 3 singles   ->  meta-3, meta-2 archived

Two properties keep this honest:

* **Validity is explicit.** An audit is a statement about a moment. Bundling last month's
  statement with today's would fabricate a "difference between systems" that is really a
  difference in time. Stale audits are excluded — and the exclusion is *named*, never
  silent.
* **Renewal belongs to the bearer.** A stale audit is refreshed by the machine that
  produced it. No other system may retire a statement about a machine it cannot see.
  Superseded artefacts are archived, never deleted.

---

## The lock is a presence signal, not a gate

Because parallel single audits are *wanted*, the audit lock does not exclude anybody:

| mode | meaning |
|---|---|
| `presence` | "a self-audit of this domain is running on host X" — informational; **never** a reason to skip a domain, and never a reason for anyone else to stop working |
| `claim` | "I am building the meta audit over exactly these inputs" — here redundancy is worthless, so claims are mutually exclusive |

A lock alone does not survive a synchronised folder: with 30 s – 5 min latency, both
machines look, see nothing and lock. So claims carry a deterministic resolution —
quarantine, recheck, earliest `created` wins, host order breaks exact ties. Both sides
reach the same verdict from the same data, without a server.

The files use the ecosystem's existing lock grammar (`LOCK.audit.<domain>.<host>.txt`), so
existing scanners see them without a code change. Full protocol:
[`protocols/audit-host-lock/SPEC.md`](protocols/audit-host-lock/SPEC.md) — self-contained,
executable by hand, no library required.

---

## Install and use

```bash
python -m pip install -e .

# which domain is next in my own rotation?
system-auditor next-area --areas "bundles,skills,mcp" --reports ./reports --host $HOSTNAME

# announce presence (does not exclude anyone)
system-auditor claim --locks ./_locks --area bundles --host $HOSTNAME --mode presence

# where are this domain's rules, on whatever system this is?
system-auditor discover --area-path /path/to/domain

# is a meta audit due?
system-auditor meta-plan --reports ./reports --area bundles --validity 14d

system-auditor release --locks ./_locks --area bundles --host $HOSTNAME
```

The role prompt an agent follows is [`prompts/AUDITOR.de.md`](prompts/AUDITOR.de.md).
Configuration: copy `config/system-auditor.config.example.json`.

---

## Design notes

* **Zero dependencies.** Standard library only; the lock format is plain text and the
  report front matter is parsed by a deliberately minimal reader, so the spec cannot
  promise more than the parser accepts.
* **No second system.** No new file format, no status registry, no database. An earlier
  attempt at a parallel "in progress" registry elsewhere in this ecosystem had to be rolled
  back; the lesson is in the spec.
* **Coverage is declared, not assumed.** A run states what it looked at and what it
  confirmed as fine. Everything else stays `unverifiable`.

## Development

```bash
python -m pytest -q     # 62 tests
ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE).
