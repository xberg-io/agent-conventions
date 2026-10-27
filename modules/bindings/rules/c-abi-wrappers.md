---
type: Decision
title: C ABI and Wrapper Conventions
description: "The C ABI crate and the wrappers built on it (Go cgo, C# P/Invoke, Zig): opaque handles, extern C exports, null and panic safety, allocate/free pairs, cbindgen headers. Use when editing an FFI crate, a C header or a Go, C# or Zig binding."
paths:
  - "crates/*-ffi/**"
  - "**/*.h"
  - "**/cbindgen.toml"
  - "packages/go/**"
  - "packages/csharp/**"
  - "packages/zig/**"
x-ai-rulez:
  kind: rule
  id: c-abi-wrappers
  metadata:
    priority: high
---

The `crates/*-ffi` C ABI is the stable native contract for the Go, C#, Zig and Java (Panama) wrappers. Version its headers semantically and freeze struct layouts across compatible releases.

- Expose only opaque handles, primitive scalars, `#[repr(C)]` structs, byte slices and explicit result structs; no `Vec`, `String` or `HashMap` across the boundary.
- Every export is `extern "C"` and `#[no_mangle]`, null-checks its pointers, catches panics, and returns an error code or result struct that keeps message, numeric code and cause.
- Pair every caller-owned allocation with a free function and document ownership in the header. Generate headers with cbindgen; the committed header must match the Rust ABI.
- Test with C smoke tests plus the wrapper suites that exercise the same ABI.
- Go (cgo): headers directly above `import "C"`, `#cgo LDFLAGS`, `defer C.free` right after every `C.CString`, `runtime.Pinner` for Go memory passed to C, a `Close` method on every handle.
- C#: `LibraryImport` with source-generated marshalling, `SafeHandle` subclasses for cleanup, explicit UTF-8 marshalling with the matching native free, natives in the NuGet `runtimes/{rid}/native` layout.
- Zig: `@cImport` the generated header, raw `extern` declarations kept apart from the idiomatic wrapper, nullable handles checked before each call, C error codes mapped to Zig error sets, `build.zig` with explicit target triples.
