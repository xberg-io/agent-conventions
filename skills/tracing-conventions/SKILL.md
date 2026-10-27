---
name: tracing-conventions
description: "Rust tracing contract: level semantics, span and field naming, emit-vs-install, instrumentation checklist. Use when adding spans or events, wiring a subscriber, or reviewing instrumentation."
# Content-Hash: blake3:7641780e65a52346e09059002576989e1317a0f56e6452d9757f36325f928c36
---

# Tracing conventions

`tracing` is the single logging surface and a **user-facing product feature**. Libraries emit spans and events always-on; consumers (CLIs, services) install the subscriber and export. This skill is the full contract behind the Rust logging rule.

## Level semantics (authoritative)

| Level | Meaning |
|-------|---------|
| `ERROR` | Unrecoverable failure or data loss. |
| `WARN`  | Degraded but continuing — recovered parse, fallback taken, truncation, skipped/unsupported input. |
| `INFO`  | Significant state changes. Keep sparse: a single operation must not spam INFO. |
| `DEBUG` | Flow detail — pipeline-stage boundaries, counts, resolved options. |
| `TRACE` | Per-item / per-node detail. Disabled in production. |

`RUST_LOG` (env-filter) always takes precedence over a caller-supplied default level.

## Emit vs. install

- **Libraries emit only.** Never call `tracing_subscriber::*` or install a global subscriber in a library — that steals the choice from the consumer and breaks composition. Add `tracing` as a **non-optional** dependency; spans compile to near-zero cost when no subscriber is attached.
- **CLIs and services install.** Initialize `tracing-subscriber` (env-filtered, stderr) once in `main`. The OTLP/OpenTelemetry export layer lives behind the `otel` feature (see the `feature-flag-conventions` skill), on top of the always-on `tracing`.
- A service's telemetry init wires the fmt layer, OTLP tracer and metrics providers (when `OTEL_EXPORTER_OTLP_ENDPOINT` is set), context propagation, and a panic hook that logs through `tracing::error!`. Library spans surface through it once the library emits them.

## Span and field naming (semver-relevant)

Span names, `target`s, and field keys are part of the public observability API. Changing them can break dashboards, alerts, and log queries — treat them like any other public symbol and keep them stable.

- **Span names**: `crate_name::operation` (e.g. `my_crate::convert`). Set an explicit `level` and stable `name`.
- **`#[tracing::instrument]`** on public entry points. `skip`/`skip_all` large or non-`Debug` arguments (input buffers, big option structs); record cheap, useful fields instead — `input_len`, resolved option booleans, selected strategy.
- **Field keys**: prefer stable, lowercase, snake_case keys. Reuse conventional keys across crates (`input_len`, `output_len`, `node_count`, `error`, `reason`, `elapsed_ms`). Avoid the reserved `message` field name for structured data — it collides with the event body; use a descriptive key like `detail`.
- **Events at stage boundaries**: `debug!` with small structured fields at parse/walk/render (or equivalent) boundaries; `warn!` at every silent-recovery / fallback / skip site; `error!` before returning a hard failure.

## Instrumentation checklist

1. `tracing` is a non-optional dependency of the library.
2. Top-level public operations carry an `#[instrument]` span with recorded fields, not raw args.
3. Every place the code already recovers or silently drops something emits a `WARN`.
4. No per-token/per-node `INFO`/`DEBUG` spam — that detail is `TRACE`.
5. No subscriber installed in library code.
6. Raw `println!`/`eprintln!`/`dbg!` are gone (see `logging-tracing`); the only stdout writes left are a CLI's result output behind `#[expect(clippy::print_stdout)]`.
