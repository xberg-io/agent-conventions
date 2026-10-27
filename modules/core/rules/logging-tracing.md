---
type: Decision
title: Logging and Tracing
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
x-ai-rulez:
  kind: rule
  id: logging-tracing
  metadata:
    priority: high
---

- `tracing` is the only logging surface. `println!`, `eprintln!`, `print!`, `eprint!` and `dbg!` are denied in production code (clippy `print_stdout`, `print_stderr`, `dbg_macro` set to `deny` in `[workspace.lints.clippy]`, and every member crate opts in with `[lints] workspace = true`).
- Exempt: a CLI's machine-readable result on stdout or an interactive prompt (`#[expect(clippy::print_stdout, reason = "...")]`), and `cargo:` directives in `build.rs`. Test files that print carry a file-level `#![allow(...)]`.
- Libraries emit and never install a subscriber; level semantics, span naming and the instrumentation checklist are in the `tracing-conventions` skill.
