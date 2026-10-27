---
type: Decision
title: C# Binding Conventions
paths:
  - "packages/csharp/**"
x-ai-rulez:
  kind: rule
  id: csharp-bindings
  metadata:
    priority: high
---

- `LibraryImport` with source-generated marshalling; `IntPtr` only at the raw layer, `SafeHandle` subclasses for cleanup; explicit UTF-8 marshalling with matching native free; map error codes to typed exceptions. Ship natives in the NuGet `runtimes/{rid}/native` layout.
