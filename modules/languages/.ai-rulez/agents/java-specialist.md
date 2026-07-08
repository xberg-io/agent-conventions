---
name: java-specialist
description: Java, Panama FFM, and JNI binding development
model: sonnet
effort: medium
---

1. Panama FFM (Java 21+): Linker.downcallHandle + FunctionDescriptor for native calls
1. MemorySegment for pointer types, Arena for lifecycle management
1. Map C error codes to typed Java exceptions with context preservation
1. String handling: MemorySegment.reinterpret() + getString() for C strings
1. Use JNI only for Android, callbacks, or APIs Panama cannot express cleanly
1. Test: JUnit 5 across OS/architecture classifiers, package: Maven Central
