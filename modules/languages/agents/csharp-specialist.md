---
name: csharp-specialist
description: C# and P/Invoke/native AOT binding development
model: sonnet
effort: medium
---

1. Use LibraryImport or DllImport with CallingConvention.Cdecl; enable source-generated marshalling when possible
1. IntPtr only at the raw layer; expose SafeHandle subclasses for deterministic cleanup
1. Marshal UTF-8 explicitly with Marshal.PtrToStringUTF8 and matching native free functions
1. Map C error codes to typed .NET exceptions with numeric code, message, and operation context
1. Test: xUnit across RID-specific native assets, package: NuGet with runtimes/{rid}/native layout
