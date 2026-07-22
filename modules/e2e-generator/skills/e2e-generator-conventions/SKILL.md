---
name: e2e-generator-conventions
description: How Alef-based e2e generation works — the alef.toml [e2e] config, JSON fixtures under fixtures/, per-language output layout, fixture id/loading/sorting rules, and the regenerate/verify task commands. Load when configuring e2e generation, adding fixtures, or regenerating/running generated e2e suites.
---

# E2E Generator Conventions

- Alef CLI (`alef e2e generate`) reads JSON fixtures → generates runnable test suites per language
- E2E generation is configured in `alef.toml` `[e2e]` section with call configurations and language overrides
- Output: e2e/{language}/ directories, each a self-contained test project
- Fixtures: JSON under fixtures/ by category (smoke, chat, streaming, error-handling, etc.)
- Each fixture has unique snake_case id, loaded recursively, sorted by (category, id)
- Run `task e2e:generate:all` to regenerate, `task e2e:test:all` to verify
- Never hand-edit generated files — modify fixtures or `alef.toml` instead
