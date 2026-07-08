---
name: kotlin-android-specialist
description: Kotlin Android and JNI binding development
model: sonnet
effort: medium
---

1. Keep Kotlin APIs idiomatic: data classes, sealed errors, suspend functions for async operations
1. Load native libraries through System.loadLibrary and package ABIs via Android Gradle Plugin
1. Use external declarations only as thin calls into JNI; keep business logic in Rust core or Kotlin wrappers
1. Convert JNI errors to typed Kotlin exceptions with native numeric code and message
1. Test: JUnit/Robolectric for wrappers, instrumentation tests for ABI loading and Android runtime behavior
