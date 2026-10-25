---
name: e2e-generator-conventions
description: "Alef e2e generation: the alef.toml [e2e] section, JSON fixtures, per-language output layout, regenerate and verify tasks. Use when configuring e2e generation or regenerating e2e suites."
# Content-Hash: blake3:5810284ec0d1d63653fbf05adcf6e95c21da7e70c159ce2980d36f8460b8e471
---

# E2E Generator Conventions

- Alef CLI (`alef e2e generate`) reads JSON fixtures → generates runnable test suites per language
- E2E generation is configured in `alef.toml` `[e2e]` section with call configurations and language overrides
- Output: e2e/{language}/ directories, each a self-contained test project
- Fixtures: JSON under fixtures/ by category (smoke, chat, streaming, error-handling, etc.)
- Each fixture has unique snake_case id, loaded recursively, sorted by (category, id)
- Run `task e2e:generate` to regenerate, `task e2e:test` to verify
- Never hand-edit generated files — modify fixtures or `alef.toml` instead
