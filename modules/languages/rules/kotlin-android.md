---
type: Decision
title: Kotlin and Android Conventions
paths:
  - "**/*.kt"
  - "**/*.kts"
  - "packages/kotlin-android/**"
x-ai-rulez:
  kind: rule
  id: kotlin-android
  metadata:
    priority: high
---

- Idiomatic Kotlin API: data classes, sealed error hierarchies, `suspend` functions for async work.
- `external` declarations are thin calls into JNI; logic stays in the Rust core or the Kotlin wrapper.
- Load native libraries with `System.loadLibrary` and package ABIs through the Android Gradle Plugin.
- Convert native errors to typed Kotlin exceptions with code and message. Test wrappers with JUnit/Robolectric and ABI loading with instrumentation tests.
