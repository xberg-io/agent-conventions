---
type: Decision
title: Java and JVM Conventions
paths:
  - "**/*.java"
  - "**/pom.xml"
  - "**/build.gradle*"
  - "crates/*-jni/**"
  - "packages/java/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: java
  metadata:
    priority: high
---

- Java 17+ (Panama FFM needs 21+): records, sealed types, pattern matching, `final` fields, `Optional` only as a return type.
- google-java-format, Error Prone and SpotBugs; JUnit 5 with AssertJ; Maven or Gradle through the committed wrapper.
- Specific exceptions only; try-with-resources for `AutoCloseable`.
- Native calls: prefer Panama (`Linker.downcallHandle`, `MemorySegment`, `Arena`); use JNI only for Android, callbacks or APIs Panama cannot express.
- JNI glue (`crates/*-jni`, jni-rs): validate handles, convert types, call the core, throw typed exceptions with the native code and message, clear pending exceptions before returning, delete local references in loops, never leak global references.
