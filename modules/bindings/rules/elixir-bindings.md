---
type: Decision
title: Elixir Binding Conventions
paths:
  - "packages/elixir/**"
x-ai-rulez:
  kind: rule
  id: elixir-bindings
  metadata:
    priority: high
---

- Rustler NIFs: `#[rustler::nif]`, `schedule = "DirtyCpu"` for anything over ~1 ms, never panic or block a scheduler, `ResourceArc<T>` for shared state. Distribute precompiled NIFs with rustler_precompiled.
