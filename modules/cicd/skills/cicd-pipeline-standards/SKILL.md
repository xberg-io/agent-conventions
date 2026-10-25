---
type: Playbook
title: Cicd Pipeline Standards
description: "CI/CD pipeline shape: per-domain GitHub Actions workflows, OS matrix, quality gates and coverage thresholds, task-only steps. Use when adding or editing CI workflows or quality gates."
paths:
  - ".github/workflows/**"
  - ".github/actions/**"
x-ai-rulez:
  kind: skill
  id: cicd-pipeline-standards
  metadata:
    name: cicd-pipeline-standards
---

# CI/CD Pipeline Standards

- GitHub Actions split by domain: ci-rust, ci-python, ci-node, ci-ruby, ci-php, ci-go, ci-java, ci-elixir, ci-wasm, ci-validate
- Linting: ruff, clippy, rubocop, oxlint, phpstan, golangci-lint
- OS matrix: Linux (amd64, arm64), macOS, Windows
- Quality gates: zero warnings, tests pass, coverage thresholds (Rust 95%, bindings 80%)
- Workflows use task commands exclusively, BUILD_PROFILE=ci
- Stages: Validate → Build → Test → Deploy
- Tag-based releases trigger multi-platform builds
