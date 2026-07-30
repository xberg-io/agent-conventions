---
priority: high
---

`tracing` is the only logging surface. Raw `println!`, `eprintln!`, `print!`, `eprint!`, and `dbg!` are forbidden in production Rust — use `tracing::{error,warn,info,debug,trace}!` instead. They are allowed only in tests and in temporary, documented debugging that is removed before commit.

Two exemptions are not debugging and opt back in locally, each with a one-line justification:

- A CLI's actual machine-readable **result** output to stdout: keep the write and add `#[expect(clippy::print_stdout)]` (or `print_stderr`) at the call or module, with a `reason`. An interactive prompt a user must see without a subscriber installed is likewise legitimate output, not a diagnostic.
- Build-script `cargo:` directives (`println!` in `build.rs`) are exempt natively.

Enforcement is per-repo clippy config: `[workspace.lints.clippy]` (or `[lints.clippy]` for single-crate repos) sets `print_stdout`, `print_stderr`, and `dbg_macro` to `deny`. Each member crate must opt in via `[lints]\nworkspace = true`, or the deny is inert. Test and integration-test files that print carry a top-of-file `#![allow(clippy::print_stdout, clippy::print_stderr, clippy::dbg_macro)]` (integration tests are separate crates and do not inherit a library's crate-root allow).
