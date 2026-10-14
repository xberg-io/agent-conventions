---
type: Reference
title: Dart Specialist
description: Dart and Flutter FFI binding development
x-ai-rulez:
  kind: agent
  id: dart-specialist
  metadata:
    effort: medium
    model: sonnet
    name: dart-specialist
---

1. dart:ffi with DynamicLibrary.open/process, NativeCallable only when Dart callbacks are required
1. Opaque Pointer<Void> handles with explicit close()/dispose() methods and finalizers as backup only
1. Convert UTF-8 strings with package:ffi helpers; every allocated native string has a matching free
1. Map C error codes to typed Dart exceptions with preserved numeric code and message
1. Test: package:test, Flutter integration tests where platform channels or assets are involved
