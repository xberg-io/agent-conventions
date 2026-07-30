---
priority: high
---

Tracing is a first-class, user-facing product feature, not incidental logging. Every core library emits spans and events always-on (no feature gate — spans are near-zero cost without a subscriber), so traceability is uniform across the whole stack from libraries up through `xberg-enterprise`'s OTLP export.

Use the level contract consistently (hoisted from `xberg-enterprise` observability):

- `ERROR` — unrecoverable failure or data loss.
- `WARN` — degraded but continuing (recovered parse, fallback taken, truncation, skipped/unsupported input).
- `INFO` — significant state changes (keep sparse; one operation should not spam INFO).
- `DEBUG` — flow detail (pipeline-stage boundaries, counts, resolved options).
- `TRACE` — per-item detail; disabled in production.

Span names, targets, and field keys are part of the public API and are semver-relevant — choose them deliberately and keep them stable. Prefer `#[tracing::instrument]` on public entry points; `skip`/`skip_all` large or non-`Debug` args and record cheap, useful fields instead. Libraries **emit only** — they never install a global subscriber. Subscriber installation (`tracing-subscriber`, OTLP layer behind the `otel` feature) belongs to CLIs and services. See the `tracing-conventions` skill for the full contract.
