---
type: Decision
title: C FFI Conventions
paths:
  - "crates/*-ffi/**"
  - "**/*.h"
  - "**/cbindgen.toml"
x-ai-rulez:
  kind: rule
  id: c-ffi
  metadata:
    priority: high
---

- Expose only opaque handles, primitive scalars, `#[repr(C)]` structs, byte slices and explicit result structs. No `Vec`, `String` or `HashMap` across the boundary.
- Every export is `extern "C"`, `#[no_mangle]`, null-checks its pointers, catches panics, and returns an error code or result struct.
- Pair every caller-owned allocation with a free function and document ownership in the header.
- Generate headers with cbindgen; the committed header must match the Rust ABI.
- Test with C smoke tests plus the downstream binding suites that exercise the same ABI.
