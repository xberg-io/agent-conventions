---
status: accepted
date: 2025-12-29
decision-makers: ["Na'aman Hirschfeld"]
---

# ai-rulez with shared agent-conventions modules

## Context and Problem Statement

Every repository is worked on by several coding agents (Claude Code, Codex, OpenCode), each reading its own
instruction files. Hand-maintained `CLAUDE.md` and `AGENTS.md` files per repository repeat the same conventions,
drift apart, and differ between agents in the same repository.

## Considered Options

* ai-rulez sources in each repository, generating every agent's files, with the shared conventions in
  agent-conventions modules
* Hand-written instruction files per agent and repository

## Decision Outcome

Chosen option: "ai-rulez sources in each repository, generating every agent's files, with the shared conventions in
agent-conventions modules", because one source renders every agent's files, and a shared convention is written once.

A repository's `.ai-rulez/` holds its own rules, context and skills, and includes agent-conventions modules from the
GitHub remote by version range (`version = "^1"`); its lock records the exact tag and commit. Generated files are
never edited by hand. A module holds only what is true in every repository that includes it.

### Consequences

* Good, because a shared rule changes once and reaches every consumer with a release and a pin update.
* Good, because every agent in a repository sees the same rules.
* Bad, because a careless module change weakens a rule in every repository at once, so module changes need review.

### Confirmation

The `modules/` tree and README of this repository; consumers' `.ai-rulez/config.toml` includes and
`.ai-rulez/ai-rulez.lock`; `ai-rulez generate --check` (`mise run governance:check`) fails on hand-edited output, and
`ai-rulez validate --strict` runs in `.github/workflows/ai-rulez-validation.yml`. The shared repository began in
`xberg-io/agent-conventions@3e5ace3`; version-range includes followed with `v1.0.0`.
