---
name: binding-architecture
description: "Org layout for polyglot bindings: crate and package naming, distribution paths, what the generator decides vs the architect, binding review checklist, per-language doc formats. Use when designing, adding or reviewing a binding."
# Content-Hash: blake3:9ce747e3f0dc98f887942db4ca729e3203e5a0996543ff22bcccf31fb2736349
---

# Binding Architecture

General binding and FFI principles (minimal glue, core then ABI then language surface, ownership,
error and async boundaries) are in the ai-rulez `polyglot-bindings` builtin and the `c-ffi` rule.
This skill holds the org layout on top of them.

## Layout

- Crates: `{lib}-py` (PyO3), `{lib}-node` (napi-rs), `{lib}-php` (ext-php-rs), `{lib}-wasm`
  (wasm-bindgen), `{lib}-ffi` (C ABI), `{lib}-jni` (JNI). The Ruby extension (Magnus) lives in
  `packages/ruby`.
- Packages: `packages/python/` (PyPI), `node/` or `typescript/` (npm), `ruby/` (RubyGems),
  `php/` (Composer), `go/` (Go module), `java/` (Maven), `csharp/` (NuGet), `dart/` (pub.dev),
  `swift/` (SwiftPM), `kotlin-android/` (Maven/Gradle), `r/` (CRAN/GitHub), `zig/`, `elixir/` (Hex).
- Generated e2e suites live under `e2e/{language}/` and are never hand-edited.
- All packages share the version in `Cargo.toml`.

## Generator vs architect

With an `alef.toml`, API extraction, binding code generation and scaffolding are automated. The
decisions left to a person: which types are opaque handles and which are transparent DTOs, the DTO
style per language, and adapter patterns for APIs that do not translate. Review generated bindings
for correctness and idiomatic quality; fix the generator input, not the output.

## Review checklist for binding changes

1. No business logic in a binding: it calls the core, converts types and converts errors.
2. Every `unsafe` block at the FFI boundary has a `SAFETY` comment; pointers are validated and
   ownership is documented.
3. A cross-language change keeps feature parity across the bindings, with idiomatic naming.
4. The committed C header and generated files match a fresh regeneration.

## Docs per language

Examples ship in every supported language. Inline formats: rustdoc, docstrings with type hints
(Python), JSDoc (TypeScript), YARD (Ruby), Javadoc (Java), XML docs (C#), PHPDoc, ExDoc (Elixir),
roxygen2 (R), GoDoc.
