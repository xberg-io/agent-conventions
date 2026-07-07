---
priority: high
---

# Poly

Poly is a single-binary multi-language linter and formatter. It bundles language engines (ruff for Python, oxc for JS/TS/JSON, taplo for TOML, rumdl for Markdown) and delegates to native tools (cargo fmt, cargo clippy, golangci-lint, actionlint, shellcheck, shfmt) when present. Most repos need no extra toolchains.

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

## Severity

`poly lint` exits non-zero only on error-severity findings. Warnings are reported but do not fail CI.

## CI

Run linting and formatting validation in CI via the shared reusable workflow:

```yaml
uses: xberg-io/actions/.github/workflows/reusable-validate.yml@v1
```

This workflow runs `poly fmt --check .` then `poly lint .` with optional inputs `setup-rust` and `setup-python`.

Always run `poly fmt --check .` and `poly lint .` after making changes to verify compliance.
