---
type: Decision
title: JVM Binding Conventions
description: "Java (Panama, JNI) and Kotlin Android (JNI crate, external funs, AAR) bindings: native calls, JNI glue hygiene, library loading, typed exceptions. Use when editing a Java, Kotlin Android or JNI binding."
paths:
  - "crates/*-jni/**"
  - "packages/java/**"
  - "packages/kotlin-android/**"
x-ai-rulez:
  kind: rule
  id: jvm-bindings
  metadata:
    priority: high
---

- Java calls the C ABI through Panama (Java 21+: `Linker.downcallHandle`, `MemorySegment`, `Arena`); use JNI only for Android, callbacks or APIs Panama cannot express.
- Kotlin Android calls a dedicated `crates/*-jni` crate: `external fun` declarations on a bridge object loaded with `System.loadLibrary`, native libraries cross-compiled into `jniLibs/<abi>/` and packaged by the Android Gradle Plugin. Logic stays in the Rust core or the Kotlin wrapper.
- JNI glue (jni-rs): validate handles, convert types, call the core, throw typed exceptions carrying the native code and message, clear pending exceptions before returning, delete local references in loops, never leak global references.
- Test ABI loading on Android with instrumentation tests.
