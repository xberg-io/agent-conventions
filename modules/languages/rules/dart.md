---
type: Decision
title: Dart Conventions
paths:
  - "**/*.dart"
  - "**/pubspec.yaml"
  - "packages/dart/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: dart
  metadata:
    priority: high
---

- `dart:ffi` with `DynamicLibrary`; `NativeCallable` only when Dart callbacks are needed.
- Opaque `Pointer<Void>` handles with explicit `close()`/`dispose()`; finalizers are a backup only.
- UTF-8 strings via `package:ffi`; every native allocation has its matching free.
- Map native error codes to typed Dart exceptions. Test with `package:test`, and Flutter integration tests where assets or platform channels are involved.
