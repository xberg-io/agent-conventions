---
status: accepted
date: 2026-07-30
decision-makers: ["Na'aman Hirschfeld"]
---

# Shared Cargo feature flag names

## Context and Problem Statement

The Rust libraries expose the same optional concerns (OpenTelemetry export, an MCP server, allocators, hardware
acceleration) under different flag names and meanings. A consumer who learns a flag in one library cannot rely on it
in another, and the bindings inherit the inconsistency.

## Considered Options

* One flag name and meaning per shared concern, used by every library
* Flag names chosen per library

## Decision Outcome

Chosen option: "One flag name and meaning per shared concern, used by every library", because a consumer then gets the
same behaviour from the same flag everywhere.

The shared flags are `otel` (opt-in OTLP export; tracing itself is always on and never a feature), `mcp`, `mcp-http`
(implies `mcp`), the mutually exclusive `mimalloc` and `jemalloc`, and `cuda`, `metal`, `mkl` and `accelerate` where a
crate offers acceleration. Flags for repository-specific concerns stay local. A change to the shared set is
coordinated across all libraries.

### Consequences

* Good, because the flags behave the same in every library and binding.
* Bad, because renaming a divergent flag is a breaking change for that library's users.

### Confirmation

The `feature-flag-conventions` skill (`modules/languages/skills/feature-flag-conventions/SKILL.md`), loaded on every
`Cargo.toml`, holds the table. Added in `xberg-io/agent-conventions@f234ec1`; the allocator precedence exception for
`--all-features` builds followed in `xberg-io/agent-conventions@b6c8280`.
