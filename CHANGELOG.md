# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `actions/context-exposure` gates with ai-rulez's native exposure checks instead of `exposure.py`: it renders the
  repository's area map from `tools/context-evals/domains.toml` and runs `ai-rulez exposure` for Claude Code and
  Codex and `ai-rulez exposure leakage`. Budgets come from the consumer's `[exposure] start_budget` (required) and
  `codex_start_budget` (warns when unset); the `budgets` and `measure-mcp` inputs are ignored with a warning. Needs
  ai-rulez 5.11.0. See `docs/native-exposure-migration.md` for the consumer steps
  ([#4](https://github.com/xberg-io/agent-conventions/issues/4)).
- `areas.py` renders `domains.toml`'s `names` and compound terms as each area's `exclude`, and the acceptances that
  hold in a repository and harness as `[[accept]]`; `--harness` selects the harness. An `[[accept]]` gains
  `harnesses`, and paddle-to-onnx's stale `OCR` acceptance is removed.

### Removed

- `tools/context-evals/exposure.py` and its tests. The eval harness's static start model and term matching moved to
  `start_context.py`.
