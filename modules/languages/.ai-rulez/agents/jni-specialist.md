---
name: jni-specialist
description: JNI and JVM native binding development
model: sonnet
effort: medium
---

1. Keep JNI as glue: validate handles, convert types, call Rust core or C ABI, convert errors
1. Use JNIEnv local frames or delete local references in loops; never leak global references
1. Convert strings with GetStringUTFChars/ReleaseStringUTFChars or safe jni-rs equivalents
1. Throw typed JVM exceptions with native numeric code and message; clear pending exceptions before returning
1. Test: JVM integration tests loading the native library across supported OS/architecture targets
