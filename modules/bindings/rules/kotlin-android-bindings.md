---
type: Decision
title: Kotlin Android Binding Conventions
paths:
  - "packages/kotlin-android/**"
x-ai-rulez:
  kind: rule
  id: kotlin-android-bindings
  metadata:
    priority: high
---

- `external` declarations are thin calls into JNI; logic stays in the Rust core or the Kotlin wrapper.
- Load native libraries with `System.loadLibrary` and package ABIs through the Android Gradle Plugin.
- Convert native errors to typed Kotlin exceptions with code and message. Test ABI loading with instrumentation tests.
