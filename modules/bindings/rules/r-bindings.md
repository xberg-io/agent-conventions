---
type: Decision
title: R Binding Conventions
paths:
  - "packages/r/**"
x-ai-rulez:
  kind: rule
  id: r-bindings
  metadata:
    priority: high
---

- extendr for Rust-backed packages (`.Call` only when a C ABI layer is required); `Result<T, extendr_api::Error>`, explicit NA handling, no R allocation from Rust threads.
- Convert native errors to classed R conditions; validate inputs before crossing the boundary. Vendor Rust dependencies for CRAN.
