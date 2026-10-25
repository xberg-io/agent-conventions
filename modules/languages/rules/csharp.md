---
type: Decision
title: C# Conventions
paths:
  - "**/*.cs"
  - "**/*.csproj"
  - "packages/csharp/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: csharp
  metadata:
    priority: high
---

- .NET 8+, C# 12, file-scoped namespaces, `<Nullable>enable</Nullable>`, `TreatWarningsAsErrors`.
- `dotnet format` and Roslyn analyzers; xUnit with `[Theory]`; `dotnet list package --vulnerable` for CVEs; commit `packages.lock.json`.
- `async`/`await` throughout, never `.Result` or `.Wait()`.
- Native interop: `LibraryImport` with source-generated marshalling; `IntPtr` only at the raw layer, `SafeHandle` subclasses for cleanup; explicit UTF-8 marshalling with matching native free; map error codes to typed exceptions. Ship natives in the NuGet `runtimes/{rid}/native` layout.
