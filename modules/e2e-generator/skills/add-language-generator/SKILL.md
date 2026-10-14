---
type: Playbook
title: Add Language Generator
description: How to add a new target language to Alef-based e2e test generation — generator wiring, output layout, and registration. Load when extending e2e generation to a new language binding.
x-ai-rulez:
  kind: skill
  id: add-language-generator
  metadata:
    name: add-language-generator
---

# Add Language Generator

E2E test generation is handled by [Alef](https://github.com/xberg-io/alef). To add a new language:

## Steps

1. **Add language to `alef.toml`**: Configure the new language under `[e2e.languages.<lang>]` with appropriate test framework, file extensions, and assertion patterns.
1. **Add call overrides**: If the language needs special call syntax, add `[e2e.call.<call_name>.languages.<lang>]` overrides.
1. **Generate and test**: Run `task e2e:generate` then `task e2e:test` to verify the generated tests compile and pass.
1. **Update CI matrix**: Add the new language to the e2e test CI workflow.

## Checklist

- [ ] Language configured in `alef.toml` `[e2e]` section
- [ ] Generated tests use language-idiomatic assertion patterns
- [ ] Skip conditions translate to language-native skip annotations
- [ ] CI runs generated tests on all supported platforms
