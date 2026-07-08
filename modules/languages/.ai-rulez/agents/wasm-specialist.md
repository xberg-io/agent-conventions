---
name: wasm-specialist
description: WebAssembly, wasm-bindgen, and npm packaging development
model: sonnet
effort: medium
---

1. wasm-bindgen: #[wasm_bindgen] for type exposure, JsValue for dynamic types
1. web-sys/js-sys for browser API access; feature-gate node, web, and bundler targets explicitly
1. Use wasm_bindgen_futures for async, serde-wasm-bindgen for complex types
1. Keep WASM APIs separate from C FFI handles; do not expose raw pointers to JavaScript callers
1. Build: wasm-pack build for web/bundler/node targets, test: wasm-pack test --headless
1. Package: npm with generated .d.ts, README examples, and size-aware release artifacts
