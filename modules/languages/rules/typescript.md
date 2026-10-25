---
type: Decision
title: TypeScript and Node Conventions
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.mts"
  - "**/package.json"
  - "crates/*-node/**"
  - "packages/node/**"
  - "packages/typescript/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: typescript
  metadata:
    priority: high
---

- `strict: true` and `noUncheckedIndexedAccess`; no `any` (use `unknown` and narrow), no non-null `!`, no `@ts-ignore`.
- ESM only, `import type` for type-only imports, unions instead of `enum`, `node:` prefix for core modules.
- pnpm with a committed lockfile; Vitest for tests; `pnpm audit` for CVEs.
- napi-rs bindings (`crates/*-node`): `#[napi]`/`#[napi(constructor)]`, `async fn` returns a Promise, `AsyncTask` for CPU work, generated `.d.ts` kept in sync, explicit `BigInt`/`Date`/`Buffer` mappings, no blocking the event loop.
