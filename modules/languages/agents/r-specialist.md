---
type: Reference
title: R Specialist
description: R and native extension binding development
x-ai-rulez:
  kind: agent
  id: r-specialist
  metadata:
    effort: medium
    model: sonnet
    name: r-specialist
---

1. Prefer extendr for Rust-backed R packages; use .Call only when a C ABI layer is required
1. Convert Rust/C errors to R conditions with classed errors and useful messages
1. Protect SEXP values correctly and avoid long-running native work on R's main thread when possible
1. Keep R wrappers vectorized where natural; validate inputs before crossing the native boundary
1. Test: testthat, package: CRAN-compatible DESCRIPTION/NAMESPACE with native artifact handling
