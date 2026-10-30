---
status: accepted
date: 2026-03-15
decision-makers: ["Na'aman Hirschfeld"]
---

# Polyrepo with a root workspace

## Context and Problem Statement

The organization ships several products (xberg, crawlberg, html-to-markdown, liter-llm, tree-sitter-language-pack,
sceptre, xberg-enterprise) and the tooling around them (alef, actions, toolchains, agent-conventions, infra). Each
product releases on its own cadence to many package registries. Work that crosses repositories still needs one
place to clone, update and branch them all.

## Considered Options

* One repository per product or tool, plus a root workspace repository that registers and orchestrates them
* A single monorepo

## Decision Outcome

Chosen option: "One repository per product or tool, plus a root workspace repository that registers and orchestrates
them", because each product keeps its own history, tags, CI and release pipeline, while the root gives cross-repo work
one checkout.

The root repository (`xberg-io/polyrepo`) tracks only orchestration files: the registry `repos.txt`, its tasks and
its governance. Every registered directory is an independent git repository. Git worktrees live under the root at
`.worktrees/<repo>/<name>`, which the root ignores.

### Consequences

* Good, because a product's tags, releases and CI are independent of every other product.
* Good, because one root checkout clones, updates and branches every repository with shared tasks.
* Bad, because a change that spans repositories lands as several commits and releases, ordered by hand.

### Confirmation

`modules/core/context/polyrepo-structure.md` states the layout in every consumer's start context. The root's
`repos.txt` lists the managed repositories and its `.gitignore` ignores `/.worktrees/`. The layout dates from
`xberg-io/polyrepo@b294003d` ("align root repo with polyrepo layout"); the `.worktrees/<repo>/<name>` namespace came
in `xberg-io/polyrepo@3c86e2c9` and `@cb04b040`, and the `repos.txt` registry in `@486cfd23`.
