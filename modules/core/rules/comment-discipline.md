---
priority: high
---

A comment survives only if it carries information that cannot be inferred from the code it accompanies — a non-obvious rationale, a workaround and its cause, a cross-boundary invariant, a spec or issue reference. Comments that restate what the code plainly does are noise; delete them rather than write them.

Any comment worth keeping must contain a `~keep` marker, so `poly`'s uncomment pass does not strip it. `~keep` is honored unconditionally by the `uncomment` engine (no `poly.toml` `preserve_patterns` entry is needed). Comments without `~keep` — and without one of the engine's built-in markers such as `SAFETY`, `HACK`, `TODO`, or a license header — are removed automatically. Write the keep-worthy comment, mark it `~keep`, and let everything else be pruned. See the `poly-lint-format` skill for how the uncomment pass runs.
