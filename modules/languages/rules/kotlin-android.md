---
type: Decision
title: Kotlin and Android Conventions
paths:
  - "**/*.kt"
  - "**/*.kts"
x-ai-rulez:
  kind: rule
  id: kotlin-android
  metadata:
    priority: high
---

- Idiomatic Kotlin API: data classes, sealed error hierarchies, `suspend` functions for async work.
- Test with JUnit, and Robolectric for Android framework code.
