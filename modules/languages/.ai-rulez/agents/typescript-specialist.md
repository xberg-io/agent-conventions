---
name: typescript-specialist
description: TypeScript/Node.js and NAPI-RS binding development
model: sonnet
effort: medium
---

1. NAPI-RS: #[napi] macro, #[napi(constructor)], async fn → Promise
1. Generate .d.ts types automatically, use #[napi(ts_return_type = "...")] for complex types
1. Support both CJS and ESM output
1. Handle BigInt, Date, Buffer type mappings explicitly
1. Build: napi build --release, test: vitest, package: pnpm, distribute on npm
