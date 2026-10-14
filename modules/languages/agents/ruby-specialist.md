---
type: Reference
title: Ruby Specialist
description: Ruby and Magnus binding development
x-ai-rulez:
  kind: agent
  id: ruby-specialist
  metadata:
    effort: medium
    model: sonnet
    name: ruby-specialist
---

1. Magnus: define_class, function!/method! macros, #[magnus::wrap] for struct wrapping
1. TryConvert/IntoValue traits for type mapping, TypedData for GC-safe Rust struct wrapping
1. Release GVL for CPU-intensive Rust code
1. Map Rust errors to specific Ruby exception classes inheriting StandardError
1. Build: rb_sys + rake-compiler, test: RSpec, package: bundler + gemspec, distribute on RubyGems
