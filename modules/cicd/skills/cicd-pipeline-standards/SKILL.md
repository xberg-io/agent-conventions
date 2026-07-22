---
name: cicd-pipeline-standards
description: Standard shape of the CI/CD pipeline across xberg-io repos — per-domain GitHub Actions workflows, linters, OS matrix, quality gates and coverage thresholds, task-only invocation, and the Validate→Build→Test→Deploy stages. Load when adding or editing CI workflows, setting up release builds, or defining quality gates.
---

# CI/CD Pipeline Standards

- GitHub Actions split by domain: ci-rust, ci-python, ci-node, ci-ruby, ci-php, ci-go, ci-java, ci-elixir, ci-wasm, ci-validate
- Linting: ruff, clippy, rubocop, oxlint, phpstan, golangci-lint
- OS matrix: Linux (amd64, arm64), macOS, Windows
- Quality gates: zero warnings, tests pass, coverage thresholds (Rust 95%, bindings 80%)
- Workflows use task commands exclusively, BUILD_PROFILE=ci
- Stages: Validate → Build → Test → Deploy
- Tag-based releases trigger multi-platform builds
