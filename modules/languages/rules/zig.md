---
type: Decision
title: Zig Conventions
paths:
  - "**/*.zig"
  - "**/build.zig.zon"
  - "packages/zig/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: zig
  metadata:
    priority: high
---

- `@cImport` the generated C headers; keep raw `extern` declarations apart from the idiomatic wrapper.
- Opaque handles are nullable pointers, checked before every native call.
- Allocator-aware APIs for copied buffers; pair every native allocation with its free.
- Convert C error codes to Zig error sets and keep the message retrievable. Test with `zig test`; build through `build.zig` with explicit target triples.
