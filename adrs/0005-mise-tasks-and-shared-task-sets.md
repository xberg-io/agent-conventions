---
status: accepted
date: 2026-10-29
decision-makers: ["Na'aman Hirschfeld"]
---

# Mise tasks and shared task sets

## Context and Problem Statement

Repositories ran their tasks with go-task, a second tool beside mise. Once the tasks had moved to mise, the same
tasks still had identical bodies in many repositories (`governance:check` in 16, `format` in 10), so a fix to a
shared task had to land in every repository by hand.

## Considered Options

* mise tasks, with shared tasks kept once as task sets in xberg-io/toolchains
* go-task Taskfiles per repository

## Decision Outcome

Chosen option: "mise tasks, with shared tasks kept once as task sets in xberg-io/toolchains", because mise already
installs the toolchain, and a task set fixes a shared task once for every repository.

The decision took two steps: the tasks moved from go-task to mise, then the repeated tasks moved into task sets
(`xberg-io/toolchains@457902d`, whose message gives the counts above).

A repository selects task sets in `toolchains.toml`; `toolchains.py sync` writes them to `mise-tasks/shared.toml`
and `mise-tasks/.shared/`. A task the repository needs to differ is listed under `task_overrides` and defined
locally. A tracked go-task `Taskfile` or `.task/` fails the toolchain check.

### Consequences

* Good, because one tool installs the toolchain and runs the tasks, locally and in CI.
* Good, because a shared task changes in one place and reaches consumers with the next baseline.
* Bad, because a repository that needs a variant of a shared task has to declare an override.

### Confirmation

xberg-io/toolchains `task-sets/` and its tests (`tests/test_task_sets.py`); `toolchains.py check` fails on a tracked
Taskfile (`xberg-io/toolchains@aebbfb3`). Task sets landed in `xberg-io/toolchains@457902d`; the `mise-tasks` skill
in `modules/core/skills/mise-tasks/` replaced the go-task skill in `xberg-io/agent-conventions@b09c32e`.
