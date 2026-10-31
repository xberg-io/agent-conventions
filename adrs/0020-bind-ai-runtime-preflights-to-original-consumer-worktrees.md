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

The root `poly-hooks.toml` distributes two optional hooks. Declaring this catalog does not enable either hook in
consumers. The fixtures copy the exact shipping manifest and standard-library Python helpers into a real Git
producer, and let Poly check out its resolved commit. The entry point finds those helpers beside itself through
`POLY_HOOK_SOURCE_ROOT`; that variable identifies the producer, never the consumer. Release and consumer wiring
remain separate: publish a reviewed immutable release, then explicitly add a versioned source and resolved lock
to each eligible consumer. That source identity and release pin require review before rollout; existing canonical
ai-rulez declarations remain executable and unchanged.

The default snapshot bootstrap uses Poly's exported absolute `GIT_DIR` to enumerate registered worktrees. It accepts exactly one
candidate whose real top-level and Git directory match, using child-scoped sanitized Git queries. It does not infer
identity from cache paths, branches, HEAD values or proximity. The actual hook cwd is passed separately as the
execution root. Preferences and source selection come from the original consumer, while relative PATH entries and
`--version` execute in the same staged cwd as the canonical validator. The original index, including an explicitly
selected alternate index, stays in effect; staged configuration is not substituted for worktree selection policy.

An intentionally nonisolated consumer instead selects `ai-runtime-freshness-worktree`, which passes the explicit
`--worktree` flag. Independent sanitized Git queries must prove that the actual cwd is exactly a registered
consumer top-level; a nested directory or staged snapshot cannot infer its parent repository. Conflicting
`GIT_DIR`, `GIT_WORK_TREE` and `GIT_COMMON_DIR` exports are refused. Both the worktree `poly.toml` and the selected
active-index `poly.toml` must explicitly declare `hooks.isolate=false`. HEAD is not the policy authority: the initial
adoption commit may introduce that setting. Relative active-index paths are resolved only against the verified
execution root, and the selected index is deliberately retained for the policy read after identity queries sanitize
Git context. No parent environment or cwd changes. Default snapshot mode still refuses missing exports rather than
automatically falling back to this mode.

The preflight measures the selected allowlisted command before asking npm for its official stable latest reference.
The selected version must equal that reference: an older, different newer or unpublished local version cannot
replace it. A failed or unmeasured runtime also rejects the overall commit. System fallback remains available when current; owners
retain their channel preferences and global installations. The optional producer offers matching system/npm bootstrap
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
* Bad, because an unassociated separate Git directory or a missing default-mode context export cannot prove consumer identity and
  is refused. A future explicit Poly context API could remove this boundary.
* Neutral, because catalog availability is optional; release, consumer wiring and acceptance remain follow-up work.

### Confirmation

`tools/context-evals/test_hook_preflight.py` runs actual normal Poly commits through two physical hooks. Its stale
control first demonstrated a successful older validator and successful commit with a no-op preflight; enabling
`hook_context.bind` and `hook_runtime.verify` rejects that commit. The controls also require current-runtime success,
independently fatal validator failures, failed version probes, linked preference overrides and main fallback,
partial staging with an alternate index, and unsupported-topology refusal.
Explicit nonisolated controls also cover an initial index without HEAD, conflicting exports, exact-root and
registration ambiguity, literal policy values, and opposing normal/alternate-index policies. Default-mode controls
remain collected and unchanged. External reference transport is
controlled offline; the local proof also uses existing native CLI binaries, without installing or
changing a machine tool. Protocol-mode doubles keep the fixture suite portable.

The existing runtime and context controls in `test_hook_runtime.py`, `test_hook_runtime_poly.py` and
`test_hook_context.py` remain required. Before acceptance or rollout, review the real distributed producer bytes,
rerun these controls, and prove a normal commit in each supported consumer topology with its actual execution
root. No paid evaluations, model requests or evaluation artifacts are involved in this confirmation.

The shipping-byte regression and focused `context:hooks` task qualify this catalog without discovering evaluation
tests. CI requires separate Linux, macOS and Windows baseline legs; adding those jobs is not proof that they pass.
ADR acceptance remains pending actual supported-platform evidence and the reviewed immutable producer release.
