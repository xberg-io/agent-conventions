---
type: Decision
title: Java Binding Conventions
paths:
  - "crates/*-jni/**"
  - "packages/java/**"
x-ai-rulez:
  kind: rule
  id: java-bindings
  metadata:
    priority: high
---

- Native calls: prefer Panama (Java 21+: `Linker.downcallHandle`, `MemorySegment`, `Arena`); use JNI only for Android, callbacks or APIs Panama cannot express.
- JNI glue (`crates/*-jni`, jni-rs): validate handles, convert types, call the core, throw typed exceptions with the native code and message, clear pending exceptions before returning, delete local references in loops, never leak global references.
