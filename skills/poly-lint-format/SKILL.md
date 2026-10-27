---
name: poly-lint-format
description: "poly, the multi-language linter and formatter: engines, lint and fmt commands, poly.toml, severity, the uncomment pass, CI workflow. Use when linting, formatting or configuring poly.toml."
# Content-Hash: blake3:4857a9aa51d3c5e9ab8b06ba38eb9c8f176468d8822a96d21ea47ec63d4b4262
---

# Poly

Poly is a single-binary multi-language linter and formatter, configured per repo in `poly.toml`.

## Engines

- Bundled: ruff (Python), oxc (JS/TS/JSON), taplo (TOML), rumdl (Markdown), sqruff (SQL), mago (PHP), YAML,
  CSS/SCSS, GraphQL, HCL, Dockerfile, rubyfmt (Ruby format only), markup_fmt (HTML/Vue/Svelte format only).
- Automatic when on `PATH`: rustfmt, gofmt, shellcheck. Opt-in: shfmt and the first-party formatters of Zig,
  Java, Kotlin, R, Swift, Dart, Gleam.
- Whole-project phase: cargo clippy and the other configured workspace tools.
- Git hooks: `poly hooks install` wires lint, format and Conventional-Commit message checks.
- Everything else (pyrefly, golangci-lint, checkstyle, credo, clang-format, actionlint) is a repo-configured
  `[tools.<name>]` or `[hooks.pre-commit.commands.<name>]` entry: read the repo's `poly.toml`.

## Commands

- Lint: `poly lint <paths>`
- Check formatting (dry-run): `poly fmt --check <paths>`
- Apply formatting: `poly fmt --fix <paths>`
- Apply lint autofixes: `poly lint --fix <paths>`

A bare `poly lint` or `poly lint .` also runs the whole-project phase: cargo clippy and the other configured
workspace tools, which compile. Naming paths runs only the per-file tier; `--no-workspace` (or `[lint]
workspace = false`) skips the phase on a whole-repo run, and `--workspace` forces it for named paths.

## Configuration

Per-repo `poly.toml` defines linting and formatting rules:

- `[discovery]` — exclude globs
- `[lint.<lang>.<tool>]` — select/ignore rules, settings like `pydocstyle_convention`, `line_length`
- `[per-file-ignores]` — file-specific exemptions
- `[fmt.<lang>.<tool>]` — formatter options
- `[hooks.builtin]` — git hook configuration
- `[tools.<name>]` — an external tool poly runs
- `[hooks.pre-commit.commands.<name>]` — an extra pre-commit command

The cache lives outside the repo (`poly cache stats`).

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

Only error-severity findings fail a run; warnings are reported. Exit 0 is clean, 1 error findings, 2 the run
verified less than it claims (skipped or errored files): gate on `summary.checked` in `--format json`, not on
empty results.

## CI

Run linting and formatting validation in CI via the shared reusable workflow:

```yaml
uses: xberg-io/actions/.github/workflows/reusable-validate.yml@v1
```

This workflow runs `poly fmt --check .` then `poly lint .` with optional inputs `setup-rust` and `setup-python`.

After making changes, run `poly fmt --check` and `poly lint` on the changed paths.
