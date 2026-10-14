---
type: Reference
title: Kotlin Android Specialist
description: Kotlin Android and JNI binding development
x-ai-rulez:
  kind: agent
  id: kotlin-android-specialist
  metadata:
    effort: medium
    model: sonnet
    name: kotlin-android-specialist
---

1. Keep Kotlin APIs idiomatic: data classes, sealed errors, suspend functions for async operations
1. Load native libraries through System.loadLibrary and package ABIs via Android Gradle Plugin
1. Use external declarations only as thin calls into JNI; keep business logic in Rust core or Kotlin wrappers
1. Convert JNI errors to typed Kotlin exceptions with native numeric code and message
1. Test: JUnit/Robolectric for wrappers, instrumentation tests for ABI loading and Android runtime behavior
