---
name: feature-flag-conventions
description: "Shared Cargo feature-flag names and semantics across the Rust libraries (otel, mcp, mcp-http, mimalloc, jemalloc, acceleration). Use when adding, renaming or reviewing a crate's [features]."
# Content-Hash: blake3:66143afe824c8637b768a46c526a24d0e09ec3a43f303d8919eba39ac34dd729
---

# Feature-flag conventions

Shared concerns use the **same flag name with the same semantics** in every library. A consumer that learns `otel` or `mcp` once should get identical behavior across every library and its bindings. Repo-specific flags stay local — this contract governs only shared concerns.

## Standard flags

| Flag | Meaning | Default | Notes |
|------|---------|---------|-------|
| *(none)* `tracing` | Structured tracing is **always-on**, never a feature. | — | `tracing` is a non-optional dependency. Do not gate span emission. Un-gate any legacy optional `tracing` feature. |
| `otel` | Opt-in OpenTelemetry / OTLP export layer, on top of always-on tracing. | off | Pulls `tracing-opentelemetry` + the `opentelemetry*` stack. This is the only observability feature. Reconcile any always-on OTLP deps behind it. |
| `mcp` | Embedded Model Context Protocol server (stdio transport). | off | |
| `mcp-http` | MCP Streamable HTTP transport; implies `mcp`. | off | `mcp-http = ["mcp", ...]`. |
| `mimalloc` | Select the mimalloc global allocator. | off | Mutually exclusive with `jemalloc`; see the allocator rule below. |
| `jemalloc` | Select the jemalloc global allocator. | off | Mutually exclusive with `mimalloc`. |
| `cuda` / `metal` / `mkl` / `accelerate` | Device / BLAS acceleration backends where a crate exposes them. | off | Same names wherever acceleration is offered. |

## Rules

- **Names are the contract.** Never invent a synonym for a shared concern (`opentelemetry`, `observability`, `otlp` for what is `otel`; `model-context-protocol` for `mcp`). Rename divergent flags to match.
- **Semantics travel with the name.** `otel` must mean the OTLP export layer everywhere, not "enable tracing" (tracing is always-on) and not a metrics-only subset.
- **Always-on tracing, opt-in export.** Do not force the `opentelemetry` dependency tree on library consumers — keep it behind `otel` so a plain dependency stays lean.
- **Implication edges are fixed**: `mcp-http` ⇒ `mcp`; `otel` ⇒ (always-on) tracing.
- **Mutually-exclusive allocators** carry a both-enabled `compile_error!` guard by default. Exception: a crate that must build with `--all-features` (a coverage gate, `cargo doc --all-features`) resolves by precedence instead, `jemalloc` winning via `cfg(all(feature = "mimalloc", not(feature = "jemalloc")))`, and states why in a `~keep` comment at the `#[global_allocator]`.
- Adding a shared flag to a new library? Copy the name, default, and implication edges from this table rather than redefining them. Coordinate a change to this contract across all libraries before landing it — no repo diverges unilaterally.
