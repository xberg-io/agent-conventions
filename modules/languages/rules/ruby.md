---
type: Decision
title: Ruby Conventions
paths:
  - "**/*.rb"
  - "**/Gemfile"
  - "**/*.gemspec"
  - "**/*.rbs"
x-ai-rulez:
  kind: rule
  id: ruby
  metadata:
    priority: high
---

- Ruby 3.2+, `# frozen_string_literal: true`, RuboCop clean, RBS signatures checked with steep.
- RSpec; bundler with a committed `Gemfile.lock` and `~>` constraints; `bundler-audit` for CVEs.
- Exceptions inherit `StandardError`; no bare `rescue`, no monkey patching.
