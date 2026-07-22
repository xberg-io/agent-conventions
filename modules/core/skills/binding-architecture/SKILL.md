---
name: binding-architecture
description: Architecture rules for the polyglot binding layer and the C FFI boundary — crate naming, distribution paths, ownership and null-safety invariants, error-context propagation, and async patterns. Load when designing or editing language bindings, the C ABI, cbindgen headers, or FFI type/error conversions.
---

# Binding Architecture

## Bindings

- Bindings are minimal glue: call Rust core, convert types, convert errors — no business logic
- Canonical surface: Rust core API first, C FFI ABI second, language bindings third;
  integrations/adapters sit outside bindings
- Crate naming: {lib}-py (PyO3), {lib}-node (NAPI-RS), {lib}-rb (Magnus), {lib}-php (ext-php-rs),
  {lib}-wasm (wasm-bindgen), {lib}-ffi (C FFI), {lib}-jni (JNI)
- Distribution paths: packages/python/ (PyPI), typescript/ (npm), ruby/ (RubyGems), php/ (Composer),
  go/ (Go module), java/ (Maven), csharp/ (NuGet), dart/ (pub.dev), swift/ (SwiftPM),
  kotlin-android/ (Maven/Gradle), r/ (CRAN/GitHub), zig/ (Zig package)
- Each binding has its own language-native test suite — 80%+ coverage
- Generated e2e code lives under e2e/{language}/ and is not hand-edited
- Error conversion must preserve context (message + numeric code) at every FFI boundary
- Async: pyo3_asyncio (Python), native #[napi] async (TS), Fiber (Ruby), block on Tokio via FFI only at
  sync host boundaries

## FFI and language interop

- Every pointer has one owner, documented with SAFETY comments
- Opaque handles only — never expose Rust types directly, use #[repr(transparent)] wrappers
- Null safety: check ALL pointers before use, return null + error code on failure
- Allocate/free pairs: every \_new() has a matching \_free(), caller owns \*mut
- Every unsafe block has a SAFETY comment: what invariant, why it holds, what breaks if violated
- Generate C headers with cbindgen — CI verifies generated headers match committed
- C ABI is the stable native contract for Go, Java/JNI, C#, Dart, Swift, Kotlin Android, Zig, and R wrappers
- Semantic versioning for C headers, struct layouts frozen at MAJOR.MINOR boundaries
- All exported functions use #[no_mangle] extern "C"
- Rust Result\<T, E> → host exceptions via dedicated conversion functions at every boundary
- Preserve error context across boundaries: message, numeric code (1000+), source location, cause chain
