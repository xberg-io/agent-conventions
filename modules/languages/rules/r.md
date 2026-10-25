---
type: Decision
title: R Conventions
paths:
  - "**/*.R"
  - "**/DESCRIPTION"
  - "packages/r/**"
x-ai-rulez:
  kind: rule
  id: r
  metadata:
    priority: high
---

- R 4.1+, styler and lintr, roxygen2 docs with `@examples` on exports, testthat.
- extendr for Rust-backed packages (`.Call` only when a C ABI layer is required); `Result<T, extendr_api::Error>`, explicit NA handling, no R allocation from Rust threads.
- Convert native errors to classed R conditions; validate inputs before crossing the boundary.
- `R CMD check --as-cran` is clean; vendor Rust dependencies for CRAN.
