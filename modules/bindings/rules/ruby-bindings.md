---
type: Decision
title: Ruby Binding Conventions
paths:
  - "crates/*-rb/**"
  - "packages/ruby/**"
x-ai-rulez:
  kind: rule
  id: ruby-bindings
  metadata:
    priority: high
---

- Magnus: `define_class`, `function!`/`method!`, `TryConvert`/`IntoValue`, `TypedData` for GC-safe wrapping, release the GVL for CPU work, map errors to specific Ruby exception classes. Build with rb_sys and rake-compiler.
