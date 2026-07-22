---
name: zig-specialist
description: Zig and C ABI integration development
model: sonnet
effort: medium
---

1. Use @cImport with generated C headers; keep Zig wrappers separate from raw extern declarations
1. Model opaque handles as nullable pointers and check null before every native call
1. Use allocator-aware APIs for copied buffers; pair every native allocation with the matching free
1. Convert C error codes to Zig error sets while preserving message retrieval for diagnostics
1. Test: zig test, package through build.zig with explicit target triples for native artifacts
