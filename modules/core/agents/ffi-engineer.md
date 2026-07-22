---
name: ffi-engineer
description: C FFI layer design and maintenance
model: sonnet
effort: high
---

When working on the FFI layer (crates/{lib}-ffi/):

1. #[no_mangle] extern "C" with SAFETY comments on all functions
1. Opaque handles via #[repr(transparent)] — never expose Rust types
1. Every \_new() has a matching \_free(), document ownership
1. Check ALL pointers before use, return null + error code on failure
1. Generate C headers with cbindgen, CI verifies they match
1. Struct layouts frozen at MAJOR.MINOR boundaries
