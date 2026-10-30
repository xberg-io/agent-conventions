---
status: accepted
date: 2026-10-30
decision-makers: ["Na'aman Hirschfeld"]
---

# Record architecture decisions

## Context and Problem Statement

Org-wide decisions (the toolchain baseline, the lint gate, action pinning, runner labels and others) exist only as
rules in the agent-conventions modules, task sets in xberg-io/toolchains and actions in xberg-io/actions. A rule says
what to do, not why or what was rejected, and nothing marks when a decision changed. Only sceptre and
xberg-enterprise keep decision records, in two different formats.

## Considered Options

* An org log of MADR records in `agent-conventions/adrs/`, checked by adrlint
* Keep the decisions as rules only
* Per-repository logs only

## Decision Outcome

Chosen option: "An org log of MADR records in `agent-conventions/adrs/`, checked by adrlint", because this
repository is public, already holds the org policies as rules that can cite an ADR, and consumers include it by
version.

Records follow MADR 4 as adrlint generates it (`adrlint new`), numbered from 0000. An accepted record is not edited:
a change is a new record that supersedes or amends it. A repository keeps its own log for its own decisions and for
deviations from an org record, which it cites rather than restates. The index lives in `docs/adr-index.md`, outside
the log.

### Consequences

* Good, because an org rule can name the record that justifies it, and a repository log does not restate it.
* Good, because adrlint checks the shape, the numbering and, once locked, the immutability of every record.
* Bad, because a decision now has two homes, the rule that applies it and the record that explains it, and they
  can drift.

### Confirmation

`.adrlint.toml` sets `dir = "adrs"` and `start = 0`; `adrlint lint` and `adrlint format --check` exit 0 on `adrs/`.
The `adr-discipline` rule in `modules/core/rules/adr-discipline.md` applies the convention in every consumer.

## More Information

* [MADR](https://adr.github.io/madr/)
* [adrlint](https://github.com/Goldziher/adrlint)
