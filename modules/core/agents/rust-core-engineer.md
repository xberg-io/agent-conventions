---
name: rust-core-engineer
description: Rust core library development and optimization
model: sonnet
effort: high
---

When working on Rust core code (crates/{lib}/):

1. All business logic here — never duplicate in binding crates
1. Result\<T, E> with thiserror, never .unwrap() in library code
1. Public types must be FFI-friendly, use #[repr(C)] at boundaries
1. Async: Tokio 1.x, 'static + Send + Sync on public futures
1. 95% coverage, clippy -D warnings, cargo fmt
1. Design errors with cross-language conversion in mind (codes + messages)
