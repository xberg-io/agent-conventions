---
type: Playbook
title: Quick Start
description: Developer quick-start for xberg-io repos — prerequisites, initial setup, and the core build/test/lint workflow. Load when onboarding to a repo or setting up a local dev environment for the first time.
x-ai-rulez:
  kind: skill
  id: quick-start
  metadata:
    name: quick-start
---

# Developer Quick Start

## Prerequisites

- Rust 1.75+ (stable or nightly for WASM)
- Python 3.10+ with uv package manager
- Node.js 18+ with pnpm ≥10.17
- Ruby 3.2+ with rbenv
- PHP 8.2+ with Composer
- Go 1.25+ (optional, for Go binding)
- Java JDK 22+ (optional, for Java binding)
- .NET 8.0+ SDK (optional, for C# binding)
- Task (task runner)
- Poly (multi-language linter and formatter)

## Quick Setup

```bash
# Clone the project repository and cd into it

# Install all dependencies
task setup

```

## Running Tests

```bash
# Core tests
task test

# All binding languages (alef drives the per-language suites)
task test:bindings

# Everything: Rust core + bindings
task test:all

# The languages that expose their own test task
task rust:test
task swift:test
task dart:test
task zig:test

# Coverage
task cov:rust
task cov:all
```

## Development Workflow

```bash
# Build core only
task build

# Build bindings or everything explicitly
task build:bindings
task build:all

# Regenerate Alef-managed files
task alef:generate

# Format repo code (poly handles all formatting)
task format

# Lint everything
task lint

# Generated e2e suites
task e2e:generate
task e2e:build
task e2e:test
task e2e:all

# Run benchmarks (name varies by repo — check task --list; e.g. benchmark:run, bench:run, rust:bench)
task benchmark:run

# Update dependencies
task update
```

## Editing & Committing

1. Edit source files (Rust, Python, TypeScript, Ruby, PHP, etc.)
1. Run `poly fmt --fix .` and `poly lint .` to format and lint code
1. If hooks reject, fix issues and retry git commit
1. Never use --no-verify; enforce code quality
