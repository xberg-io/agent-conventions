---
type: Decision
title: Java and JVM Conventions
paths:
  - "**/*.java"
  - "**/pom.xml"
  - "**/build.gradle*"
x-ai-rulez:
  kind: rule
  id: java
  metadata:
    priority: high
---

- Java 17+: records, sealed types, pattern matching, `final` fields, `Optional` only as a return type.
- google-java-format, Error Prone and SpotBugs; JUnit 5 with AssertJ; Maven or Gradle through the committed wrapper.
- Specific exceptions only; try-with-resources for `AutoCloseable`.
