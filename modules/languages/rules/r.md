---
type: Decision
title: R Conventions
paths:
  - "**/*.R"
  - "**/DESCRIPTION"
x-ai-rulez:
  kind: rule
  id: r
  metadata:
    priority: high
---

- R 4.4+, styler and lintr, roxygen2 docs with `@examples` on exports, testthat.
- `R CMD check --as-cran` is clean.
