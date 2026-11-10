# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Removed

- `tools/context-evals/exposure.py` and its tests. The eval harness's static start model and term matching moved to
  `start_context.py`.

### Fixed

- The commit-procedure and agent-workflow rules and the poly-lint-format and release-workflow skills no longer
  prescribe `poly fmt --check`, which poly 0.33 rejects with exit 2 now that the dry run is the default. They name the
  dry run on each side of that change, since a bare `poly fmt` on 0.32 and older rewrites files.
