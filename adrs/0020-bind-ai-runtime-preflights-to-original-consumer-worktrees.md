---
status: proposed
date: 2026-10-31
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0017"]
---

# Bind AI runtime preflights to original consumer worktrees

## Context and Problem Statement

[ADR-0015](0015-ai-rulez-runs-at-latest-through-npx.md) requires the newest stable ai-rulez.
[ADR-0017](0017-the-poly-hooks-run-ai-rulez-through-the-npm-channel.md) preserves machine-owned npm/system
preferences, including system fallback. A valid catalog lock does not prove that the selected executable is current:
an older CLI can successfully validate compatible data. Poly 0.31.2 selects hooks from the original worktree's
configuration before executing them against the staged snapshot, so probing from an unrelated directory can also
measure a different executable or configuration.

## Considered Options

* Add an independent producer preflight bound to the original consumer worktree
* Wait for a dedicated original-consumer-root export from Poly
* Guess the consumer from the snapshot path, current branch or nearest repository
* Replace the canonical ai-rulez hook with a wrapper

## Decision Outcome

Chosen option: "Add an independent producer preflight bound to the original consumer worktree", because it can
reject the overall commit without replacing the canonical AI source, changing its pin policy or rewriting machine
preferences. This is a candidate contract, not authorization to install the hook in consumers.

`tools/context-evals/runtime-gate-producer.toml` is a candidate manifest, not this repository's production
`poly-hooks.toml`. The fixtures materialize it in a real Git producer and let Poly check out its resolved commit.
The entry point finds its standard-library Python helpers beside itself through the producer's
`POLY_HOOK_SOURCE_ROOT`; that variable identifies the producer, never the consumer. A later distribution change
would promote the manifest to the conventions producer root, publish a reviewed immutable release, and explicitly
add a versioned source and resolved lock to consumers. That source identity and release pin require review before
rollout; existing canonical ai-rulez declarations remain executable and unchanged.

The bootstrap uses Poly's exported absolute `GIT_DIR` to enumerate registered worktrees. It accepts exactly one
candidate whose real top-level and Git directory match, using child-scoped sanitized Git queries. It does not infer
identity from cache paths, branches, HEAD values or proximity. The actual hook cwd is passed separately as the
execution root. Preferences and source selection come from the original consumer, while relative PATH entries and
`--version` execute in the same staged cwd as the canonical validator. The original index, including an explicitly
selected alternate index, stays in effect; staged configuration is not substituted for worktree selection policy.

The preflight measures the selected allowlisted command before asking npm for its stable latest reference. A stale,
failed or unmeasured runtime rejects the overall commit. System fallback remains available when current; owners
retain their channel preferences and global installations. The candidate offers matching system/npm bootstrap
paths and additionally requires Python 3.11 or newer. It always runs when selected, including commits where the
canonical validator's existing path filter has no work.

The preflight and canonical validator are independent hooks. No ordering or fail-fast behavior is promised: Poly
may run both even when the preflight fails. The required invariant is a failed overall commit, not suppression of
read-only validation. Validator failure must also remain fatal after a successful freshness check.

### Consequences

* Good, because compatible data cannot conceal a stale selected CLI behind a successful validator.
* Good, because original worktree preferences, linked-worktree overrides and staged execution remain distinct.
* Good, because canonical AI source pins, validation behavior and owner-managed preferences are preserved.
* Bad, because the independent preflight needs Python and public catalog/npm metadata at commit time, including
  commits where the canonical validator has no matching files; unavailable references fail closed.
* Bad, because arbitrary catalogs and cwd overrides remain unsupported rather than being interpreted approximately.
* Bad, because an unassociated separate Git directory or missing context export cannot prove consumer identity and
  is refused. A future explicit Poly context API could remove this boundary.
* Neutral, because production distribution, consumer wiring and acceptance remain separate follow-up work.

### Confirmation

`tools/context-evals/test_hook_preflight.py` runs actual normal Poly commits through two physical hooks. Its stale
control first demonstrated a successful older validator and successful commit with a no-op preflight; enabling
`hook_context.bind` and `hook_runtime.verify` rejects that commit. The controls also require current-runtime success,
independently fatal validator failures, failed version probes, linked preference overrides and main fallback,
partial staging with an alternate index, and unsupported-topology refusal. External reference transport is
controlled offline; the local proof also uses existing native CLI binaries, without installing or
changing a machine tool. Protocol-mode doubles keep the fixture suite portable.

The existing runtime and context controls in `test_hook_runtime.py`, `test_hook_runtime_poly.py` and
`test_hook_context.py` remain required. Before acceptance or rollout, review the real distributed producer bytes,
rerun these controls, and prove a normal commit in each supported consumer topology with its actual execution
root. No paid evaluations, model requests or evaluation artifacts are involved in this confirmation.
