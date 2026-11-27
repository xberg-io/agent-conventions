# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.11.1] - 2026-11-27

### Changed

- `tools/context-evals/domains.toml` lists the `plugins` repository (the pinned plugin marketplace) with no owned domains.
- The repository follows the `xberg-io/toolchains` baseline v1.22.0, and the shared tasks it syncs are refreshed.

### Fixed

- The context-eval runner copies the `claude` and `ai-rulez` executables it resolves at start into a read-only bin
  directory (`--bin-dir`, default `RUN_DIR/bin`, recorded in `frozen-binaries.json`) and puts it first on every child's
  `PATH`, so a self-updating Claude Code install no longer aborts a run on the binary identity check.
- Generation runs with a run-private `HOME` (`RUN_DIR/generator-home`), so the ai-rulez include cache is private to the
  run instead of shared machine-wide; git credentials are linked from the real home and generation calls are
  serialised.
- The eval mutation generator swaps a domain term only where a criterion's check names it. It replaces only a path a
  check names in full. Fewer mutants apply, so validation tops up each case until every criterion has the graded
  answers kappa needs. Reports record `mutation-2` and the session count; true-negative rates from the earlier
  generator are not comparable.
- The judge prompts compare every concrete name (path, crate, repository, tool, command, config key, product) with the
  reference's name. A substituted name counts as a contradiction. Versions move to `judge-prompt-3`,
  `judge-prompt-independent-3` and `rubric-3`; earlier verdicts are not comparable.
- Three xberg criteria the judges split on (`which-binding`, `on-struct`, `crates-e2e`) state what is required and what
  fails ([#14](https://github.com/xberg-io/agent-conventions/issues/14)).

## [1.11.0] - 2026-11-19

The entries below sat under `[Unreleased]` when v1.11.0 was tagged; the changelog was not rolled forward then.

### Changed

- `actions/context-exposure` gates with ai-rulez's native exposure checks instead of `exposure.py`: it renders the
  repository's area map from `tools/context-evals/domains.toml` and runs `ai-rulez exposure` for Claude Code and
  Codex and `ai-rulez exposure leakage`. Budgets come from the consumer's `[exposure] start_budget` (required) and
  `codex_start_budget` (warns when unset); the `budgets` and `measure-mcp` inputs are ignored with a warning. It
  still fails on an invocable skill or agent whose listed description is over 250 characters, now read from
  `ai-rulez exposure inventory` whatever the consumer's `[lint.description]`, and refuses ai-rulez below 5.11.0.
  Budgets are in ai-rulez's native units: re-measure them, do not copy the old `budgets` values. See
  `docs/native-exposure-migration.md` for the rollout order and ADR-0022 for the decision
  ([#4](https://github.com/xberg-io/agent-conventions/issues/4)).
- `areas.py` renders `domains.toml`'s `names` and compound terms as each area's `exclude`, and the acceptances that
  hold in a repository and harness as `[[accept]]`; `--harness` selects the harness. An `[[accept]]` gains
  `harnesses`, and paddle-to-onnx's stale `OCR` acceptance is removed.
- The poly guidance follows poly 0.36 and the v2 config: the commit-procedure rule and release-workflow skill name
  only `poly fmt` as the formatting dry run, the poly-lint-format skill covers `poly lock` and `poly.lock`,
  `poly trust`, `--workspace never` and the `[engines.<id>]` and `[per_file_ignores]` tables, and the
  comment-discipline and PHP rules name `[engines.uncomment]` and `[engines.mago]`.

### Removed

- `tools/context-evals/exposure.py` and its tests. The eval harness's static start model and term matching moved to
  `start_context.py`.

### Fixed

- The AI runtime probe (`hook_pins.py --runtime`, `hook_preflight.py`) refuses a hook source that `poly.lock` locked
  for another revision (`ref`, recorded by poly 0.36), as poly does, and reports a malformed hook sources table
  as an error instead of a traceback.
- The commit-procedure and agent-workflow rules and the poly-lint-format and release-workflow skills no longer
  prescribe `poly fmt --check`, which poly 0.33 rejects with exit 2 now that the dry run is the default. They name the
  dry run on each side of that change, since a bare `poly fmt` on 0.32 and older rewrites files.
