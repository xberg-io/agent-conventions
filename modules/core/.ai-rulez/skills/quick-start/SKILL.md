---
description: Developer quick start guide with prerequisites, setup, and workflow commands
priority: medium
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

# Specific languages
task test:rust
task test:python
task test:ruby
task test:node
task test:ts
task test:js
task test:php
task test:go

# Coverage
task cov:rust
task cov:python
task cov:all
```

## Development Workflow

```bash
# Build core only
task build

# Build bindings or everything explicitly
task build:bindings
task build:all

# Regenerate Alef-managed files without formatting
task alef:generate

# Run Alef formatting explicitly when needed
task alef:format

# Format repo code; excludes Alef formatting
task format

# Lint everything
task lint

# Generated e2e suites
task e2e:generate
task e2e:build
task e2e:test
task e2e:all

# Run benchmarks
task bench

# Update dependencies
task update
```

## Editing & Committing

1. Edit source files (Rust, Python, TypeScript, Ruby, PHP, etc.)
1. Run `poly fmt --fix .` and `poly lint .` to format and lint code
1. If hooks reject, fix issues and retry git commit
1. Never use --no-verify; enforce code quality
