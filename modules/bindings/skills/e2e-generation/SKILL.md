---
type: Playbook
title: E2E Generation
description: "Fixture-driven cross-language e2e suites: the [e2e] generator config, fixture files and ids, per-language output, adding a language, regenerate and verify. Use when adding or editing fixtures or configuring e2e generation."
paths:
  - "alef.toml"
  - "fixtures/**"
  - "e2e/**"
x-ai-rulez:
  kind: skill
  id: e2e-generation
  metadata:
    name: e2e-generation
---

# E2E Generation

`alef e2e generate` reads JSON fixtures and writes one self-contained test project per language
under `e2e/{language}/`. Fixtures are the single source of truth: test logic comes from them, never
from hand-written tests in `e2e/`.

## Fixtures

- The fixture schema (fields, call names, assertion keys, categories) is the repo's own: read the
  `[e2e]` section of `alef.toml` and two or three existing fixtures before writing one. Do not copy
  a schema from another repo.
- Every fixture has a unique snake_case `id` across all fixture files; it becomes the test function
  name. Fixtures load recursively and sort by (category, id).
- One behavior per fixture; include negative cases. Platform- or language-specific behavior goes in
  the fixture's skip conditions, which the generators turn into native skip annotations.

## Generator config

`alef.toml` `[e2e]` holds call configurations, per-language overrides
(`[e2e.call.<call>.languages.<lang>]`) and fixture paths.

## Adding a language

1. Configure it under `[e2e.languages.<lang>]`: test framework, file layout, assertion patterns.
2. Add call overrides where the language needs different call syntax.
3. `task e2e:generate`, then `task e2e:test`; the generated tests must compile and pass.
4. Add the language to the e2e CI matrix.

## Loop

Edit fixtures or `alef.toml`, run `task e2e:generate` then `task e2e:test`, and commit fixtures and
regenerated output in one commit.
