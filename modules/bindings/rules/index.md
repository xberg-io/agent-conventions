# Concepts

* [C ABI and Wrapper Conventions](c-abi-wrappers.md) - The C ABI crate and the wrappers built on it (Go cgo, C# P/Invoke, Zig): opaque handles, extern C exports, null and panic safety, allocate/free pairs, cbindgen headers. Use when editing an FFI crate, a C header or a Go, C# or Zig binding.
* [JVM Binding Conventions](jvm-bindings.md) - Java (Panama, JNI) and Kotlin Android (JNI crate, external funs, AAR) bindings: native calls, JNI glue hygiene, library loading, typed exceptions. Use when editing a Java, Kotlin Android or JNI binding.
* [Rust-Native Binding Conventions](rust-native-bindings.md) - Bindings built as Rust extensions or bridge crates: PyO3, napi-rs, Magnus, ext-php-rs, Rustler, extendr, wasm-bindgen, flutter_rust_bridge, swift-bridge. Use when editing a Python, Node, Ruby, PHP, Elixir, R, WASM, Dart or Swift binding.
