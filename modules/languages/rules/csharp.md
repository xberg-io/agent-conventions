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

- .NET 10 (`net10.0`), file-scoped namespaces, `<Nullable>enable</Nullable>`, `TreatWarningsAsErrors`.
- `dotnet format` and Roslyn analyzers; xUnit with `[Theory]`.
- `async`/`await` throughout, never `.Result` or `.Wait()`.
