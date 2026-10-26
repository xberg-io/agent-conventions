---
type: Decision
title: WebAssembly Conventions
paths:
  - "crates/*-wasm/**"
  - "packages/wasm/**"
x-ai-rulez:
  kind: rule
  id: wasm
  metadata:
    priority: high
---

- wasm-bindgen for JS interop, wasm-pack for build and packaging; feature-gate `web`, `node` and `bundler` targets explicitly.
- `Result<T, JsValue>` with descriptive errors; no panics, no `std::thread`, no synchronous I/O.
- `wasm-bindgen-futures` for async and `serde-wasm-bindgen` for complex types.
- Keep WASM APIs separate from C FFI handles; never expose raw pointers to JavaScript.
- Release profile for size: `opt-level = "z"`, `lto = true`, `codegen-units = 1`. Test with `wasm-pack test --headless`.
