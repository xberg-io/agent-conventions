---
name: adr-authoring
description: "Write, supersede or seed MADR decision records with adrlint: shape, Confirmation, lock, index. Use when adding or changing an ADR or an adrs/ log."
# Content-Hash: blake3:f11d4e5928acfcc8b0d69e5b887b25f5dcdc969571c9f75438beaea7a03cbd82
---

# ADR authoring

The adr-discipline rule says when a record is needed. Org-wide decisions live in `xberg-io/agent-conventions` under
`adrs/`; a repository log holds that repository's decisions and its deviations from an org record, citing the org
record (`org ADR-NNNN`) rather than restating it.

## Create

- `adrlint new "<title>"` writes the next number from `.adrlint.toml`. A repository without a log starts one with
  `adrlint init --dir adrs --start 0`; set `[lock] statuses = ["accepted", "rejected", "superseded", "deprecated"]`.
- Files are `adrs/NNNN-kebab-title.md`, numbered consecutively from 0000. Fill the template; do not hand-copy an older
  record.

## Shape (MADR 4)

- Front matter: `status` (proposed, accepted, rejected, deprecated, superseded), `date` (YYYY-MM-DD, when the decision
  was made), `decision-makers` (a list, even of one), and `supersedes: "NNNN"`, `superseded-by: "NNNN"` or
  `amends: ["NNNN"]` where they apply. Every ADR id is a quoted four-digit string.
- Sections: `# Title`, `## Context and Problem Statement`, `## Considered Options`, `## Decision Outcome`. The outcome
  starts with `Chosen option: "<option>", because <rationale>` and holds `### Consequences` (`* Good, because …`,
  `* Bad, because …`) and `### Confirmation`.
- Confirmation says how the decision is verified and cites a file, test or CI gate that exists. adrlint 0.3.0 does not
  require it; review does.
- List markers are `*`. `adrlint format` fixes Markdown; `adrlint lint` checks the shape and numbering.

## Change a decision

An accepted record is immutable once locked (`adrlint.lock`, checked by `adrlint lock --check`).

- Supersede: write the new record with `supersedes: "<old>"`, then `adrlint unlock adrs/<old>.md --reason "<why>"`, set the old record's
  `status: superseded` and `superseded-by: "<new>"`, change nothing else in it, and `adrlint lock`.
- Amend a part: a new record with `amends: ["<old>"]`; the old record is not touched.
- Never fix an accepted record's wording in place, even a typo: the lock check fails and the history is lost.

## Seed records

A seed records a decision already in force: `status: accepted`, dated to the commit that made it, with the Context
from the situation at that time and a Confirmation citing the file or commit that shows it at origin. Never invent a
decision or an alternative the evidence does not show.

## Index and checks

- The index lives outside the log (`docs/adr-index.md` or a docs-site page), because adrlint lints every `.md` in
  `adrs/`. Add the row in the same change as the record.
- adrlint owns ADR Markdown: `poly.toml` excludes `/adrs/**` from discovery and from the hook lint and fmt.
- Before committing: `adrlint lint`, `adrlint format --check`, and `adrlint lock --check` once the log is locked.
- Keep decision rationale out of code comments; link the record.
