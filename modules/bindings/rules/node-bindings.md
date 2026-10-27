---
type: Decision
title: Node Binding Conventions
paths:
  - "crates/*-node/**"
  - "packages/node/**"
  - "packages/typescript/**"
x-ai-rulez:
  kind: rule
  id: node-bindings
  metadata:
    priority: high
---

- napi-rs (`crates/*-node`): `#[napi]`/`#[napi(constructor)]`, `async fn` returns a Promise, `AsyncTask` for CPU work, generated `.d.ts` kept in sync, explicit `BigInt`/`Date`/`Buffer` mappings, no blocking the event loop.
