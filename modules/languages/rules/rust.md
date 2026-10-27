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
- `cargo deny` (`deny.toml`) gates dependencies; commit `Cargo.lock`.
- `tracing` is the only logging surface. `println!`, `eprintln!`, `print!`, `eprint!` and `dbg!` are denied in production code: clippy `print_stdout`, `print_stderr` and `dbg_macro` set to `deny` in `[workspace.lints.clippy]` with `[lints] workspace = true` in every member crate (`[lints.clippy]` in a single-crate repo).
- Exempt: a CLI's machine-readable result on stdout or an interactive prompt (`#[expect(clippy::print_stdout, reason = "...")]`), and `cargo:` directives in `build.rs`. Test files that print carry a file-level `#![allow(...)]`.
- Libraries emit and never install a subscriber; level semantics, span naming and the instrumentation checklist are in the `tracing-conventions` skill.
