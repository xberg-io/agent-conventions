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
- Checkstyle (`packages/java/checkstyle.xml`), plus Spotless and PMD where the repo's Java lint task runs them; JUnit 5 with AssertJ; Maven as the repo's tasks invoke it.
- Specific exceptions only; try-with-resources for `AutoCloseable`.
