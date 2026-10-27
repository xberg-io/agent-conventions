---
type: Playbook
title: Poly Lint Format
description: "poly, the multi-language linter and formatter: engines, lint and fmt commands, poly.toml, severity, the uncomment pass, CI workflow. Use when linting, formatting or configuring poly.toml."
x-ai-rulez:
  kind: skill
  id: poly-lint-format
  metadata:
    name: poly-lint-format
---

# Poly

Poly is a single-binary multi-language linter and formatter. It bundles language engines (ruff for Python, oxc for JS/TS/JSON, taplo for TOML, rumdl for Markdown) and delegates to native tools (cargo fmt, cargo clippy, golangci-lint, actionlint, shellcheck, shfmt) when present. Most repos need no extra toolchains. Configure via per-repo `poly.toml`.

## Engines by language

| Scope | Engine(s) |
|-------|-----------|
| **Python** | ruff (lint + format), pyrefly (type check) |
| **JS/TS/JSON/CSS** | oxc (lint + format) |
| **TOML** | taplo (lint + format) |
| **Markdown** | rumdl (format) |
| **Rust** | cargo fmt + cargo clippy (via cargo hook) |
| **Go** | golangci-lint |
| **Java** | checkstyle, maven verify |
| **Ruby** | rubocop (format + lint) |
| **C#** | dotnet format |
| **PHP** | php-cs-fixer, phpstan |
| **Elixir** | mix format, mix credo |
| **R** | styler, lintr |
| **C/C++** | clang-format, cppcheck |
| **Shell** | shfmt, shellcheck |
| **Git** | gitfluff (commit message linting), ai-rulez-generate |
| **GH Actions** | actionlint |
| **Helm/K8s** | helm-lint, kubeconform |

## Commands

- Lint: `poly lint .`
- Check formatting (dry-run): `poly fmt --check .`
- Apply formatting: `poly fmt --fix .`
- Apply lint autofixes: `poly lint --fix .`

## Configuration

Per-repo `poly.toml` defines linting and formatting rules:

- `[discovery]` — exclude globs
- `[lint.<lang>.<tool>]` — select/ignore rules, settings like `pydocstyle_convention`, `line_length`
- `[per-file-ignores]` — file-specific exemptions
- `[fmt.<lang>.<tool>]` — formatter options
- `[hooks.builtin]` — git hook configuration

Cache directory `.polylint/` is gitignored.

## Uncomment pass

`[lint.uncomment]` in `poly.toml` reports removable comments; `poly lint --fix` deletes them.

- `code_only = true` (the default) flags only comment blocks that read as commented-out code; prose
  comments are kept with or without a marker. `code_only = false` flags every comment that is not preserved.
- Preserved: `~keep` anywhere in the comment; the defaults `TODO`, `FIXME`, `HACK`, `XXX`, `NOTE`, `WARNING`,
  `COPYRIGHT`/`LICENSE`, the file header, shebangs and linter directives (`noqa`, `eslint-disable`, `@ts-ignore`,
  ...); and the repo's `preserve_patterns` (`SAFETY`, `SPDX`, ...). `SAFETY` is not a default.
- Doc comments are kept unless `remove_docs = true`; `remove_todos` / `remove_fixme = true` drop those markers.
- Test a change to these settings against staged or committed content: an uncommitted scratch file
  reports clean whatever it contains.
- Generated sources are exempted with `[per-file-ignores]` set to `["comment", "doc-comment"]` (the codes the
  uncomment pass emits), not by adding markers.

## Severity

`poly lint` exits non-zero only on error-severity findings. Warnings are reported but do not fail CI.

## CI

Run linting and formatting validation in CI via the shared reusable workflow:

```yaml
uses: xberg-io/actions/.github/workflows/reusable-validate.yml@v1
```

This workflow runs `poly fmt --check .` then `poly lint .` with optional inputs `setup-rust` and `setup-python`.

Always run `poly fmt --check .` and `poly lint .` after making changes to verify compliance.
