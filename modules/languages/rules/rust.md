---
type: Decision
title: Rust Conventions
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
x-ai-rulez:
  kind: rule
  id: rust
  metadata:
    priority: high
---

- Rust 2024 edition; `cargo fmt` and `clippy -D warnings` are clean.
- Library errors: a derive-based error type (thiserror); applications: a context-adding one (anyhow). Propagate with `?`; no `.unwrap()` or panics in library code.
- Every `unsafe` block carries a `// SAFETY:` comment stating the invariant.
- `&str` over `String` in parameters, `Cow<'_, str>` for conditional ownership. `pub(crate)` for internal items; workspace dependency inheritance in multi-crate repos.
- Follow the Rust API Guidelines: `as_`/`to_`/`into_` conversions, `field()` getters, common traits derived eagerly, newtypes or enums instead of `bool` parameters, private struct fields.
- Unit tests in `#[cfg(test)]`, integration tests in `tests/`; benchmarks with criterion.
- `cargo audit` and `cargo deny` gate dependencies; commit `Cargo.lock`.
