---
type: Decision
title: TypeScript and Node Conventions
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.mts"
  - "**/package.json"
x-ai-rulez:
  kind: rule
  id: typescript
  metadata:
    priority: high
---

- `strict: true` and `noUncheckedIndexedAccess`; no `any` (use `unknown` and narrow), no non-null `!`, no `@ts-ignore`.
- ESM only, `import type` for type-only imports, unions instead of `enum`, `node:` prefix for core modules.
- pnpm with a committed lockfile; Vitest for tests; `pnpm audit` for CVEs.
