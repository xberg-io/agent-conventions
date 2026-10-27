---
type: Decision
title: C# Conventions
paths:
  - "**/*.cs"
  - "**/*.csproj"
x-ai-rulez:
  kind: rule
  id: csharp
  metadata:
    priority: high
---

- .NET 8+, C# 12, file-scoped namespaces, `<Nullable>enable</Nullable>`, `TreatWarningsAsErrors`.
- `dotnet format` and Roslyn analyzers; xUnit with `[Theory]`; `dotnet list package --vulnerable` for CVEs; commit `packages.lock.json`.
- `async`/`await` throughout, never `.Result` or `.Wait()`.
