---
name: poly-lint-format
description: "poly, the multi-language linter and formatter: engines, lint and fmt commands, poly.toml, severity, the uncomment pass, CI workflow. Use when linting, formatting or configuring poly.toml."
# Content-Hash: blake3:833a94ac5f6c51f8e4447c5b244887a5096571d605e7d0ef4dd992a0986e21c4
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
- Opt-in engines: `[engines.<id>] enabled = true` (typos, harper, skif, tsrs and others).
- Everything else (pyrefly, golangci-lint, checkstyle, credo, clang-format, actionlint) is a repo-configured
  `[tools.<name>]` or `[hooks.pre-commit.commands.<name>]` entry: read the repo's `poly.toml`.

## Commands

- Lint: `poly lint <paths>`
- Check formatting (dry run): `poly fmt <paths>`; `--check` is rejected with exit 2.
- Apply formatting: `poly fmt --fix <paths>`
- Apply lint autofixes: `poly lint --fix <paths>`
- Pin hook sources, remote `extends` bases and downloaded tools: `poly lock`, which writes `poly.lock` (it
  replaced `poly hooks update`, `poly config update`, `poly-hooks.lock` and `poly-config.lock`).

The repo's `mise.toml` pins the poly version. A bare `poly lint` or `poly lint .` also runs the whole-project
phase: cargo clippy and the other configured workspace tools, which compile. Naming paths runs only the per-file
tier; `--workspace never` (or `[workspace] run = "never"`) skips the phase on a whole-repo run, and
`--workspace always` forces it for named paths.

## Trust

Config keys that run programs (`[tools]` overrides, `[hooks]` whole-project jobs, `[cache] dir` and others) are
ignored, and `poly hooks run` and the git hooks refuse to run, until the repository is trusted. Run `poly trust`
once per clone (`poly hooks install` also records it) and again after a change to those keys; `poly trust --show`
lists them. CI sets `POLY_TRUST=1`.

## Configuration

Per-repo `poly.toml` defines linting and formatting rules:

- `[discovery]` — exclude globs
- `[engines.<id>]` — select/ignore rules and settings like `line_length`, narrowed by `[engines.<id>.lint]`,
  `[engines.<id>.format]` and `[engines.<id>.lang.<language>]`; `[engines.<id>.rules.<code>] level` remaps one rule
- `[per_file_ignores]` — file-specific exemptions
- `[hooks.builtin]` — git hook configuration
- `[tools.<name>]` — an external tool poly runs
- `[hooks.pre-commit.commands.<name>]` — an extra pre-commit command

The cache lives outside the repo (`poly cache stats`).

## Uncomment pass

`[engines.uncomment]` in `poly.toml` reports removable comments; `poly lint --fix` deletes them.

- `code_only = true` (the default) flags only comment blocks that read as commented-out code; prose
  comments are kept with or without a marker. `code_only = false` flags every comment that is not preserved.
- Preserved: `~keep` anywhere in the comment; the defaults `TODO`, `FIXME`, `HACK`, `XXX`, `NOTE`, `WARNING`,
  `COPYRIGHT`/`LICENSE`, the file header, shebangs and linter directives (`noqa`, `eslint-disable`, `@ts-ignore`,
  ...); and the repo's `preserve_patterns` (`SAFETY`, `SPDX`, ...). `SAFETY` is not a default.
- Doc comments are kept unless `remove_docs = true`; `remove_todos` / `remove_fixme = true` drop those markers.
- Test a change to these settings against staged or committed content: an uncommitted scratch file
  reports clean whatever it contains.
- Generated sources are exempted with `[per_file_ignores]` set to `["comment", "doc-comment"]` (the codes the
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

This workflow pins poly through its `poly-version` input (default `v0.36.1`), sets `POLY_TRUST=1` and runs
`poly fmt .` then `poly lint .` with optional inputs `setup-rust` and `setup-python`.

After making changes, run the formatting dry run and `poly lint` on the changed paths.
