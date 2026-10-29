---
name: mise-tasks
description: "Run and write tasks with mise: mise run, ns:verb names, mise.toml vs mise-tasks/ file tasks, usage args, depends, root-task guard, CI, go-task conversion. Use before a raw build, test, lint or format command, or when adding a task."
# Content-Hash: blake3:b55470a7392fa6e40ac82e42e39df89a0f2ee50066d0399fbb1b9a1e68f5f980
---

# Mise tasks

Prefer `mise run <task>` over the raw tool: the task carries the flags and env the raw command omits.
Task sets differ per repo, so list them (`mise tasks`, `--hidden` for hidden ones, `mise tasks info <task>`)
rather than assume a `<lang>:<verb>` task exists. Repos still on go-task (a `Taskfile.yml`, no mise tasks):
run `task <name>` there, and convert with the mapping below.

## Where tasks live

- One-liners: `[tasks."ns:verb"]` in `mise.toml` with `description` and `run` (a string, or an array run in
  order; `{ task = "x" }` in the array runs a task at that point).
- Anything longer: a file task `mise-tasks/<ns>/<verb>.sh` is `ns:verb` (mise strips the extension). Make it
  executable, `#!/usr/bin/env bash`, `set -euo pipefail`, `#MISE description="…"`, and other keys as
  `#MISE depends=["x"]` or `#MISE hide=true`. Put sourced helpers in a dot directory such as `.lib` inside the task directory.
- Names are `ns:verb` and stay unchanged in a conversion. Common: `setup`, `build`, `test`, `lint`, `format`,
  `format:check`, `docs:build`/`docs:serve`, `update`, `clean`, `version:sync`/`version:check`, `cov:all` and a
  repo-specific benchmark task where present. Where a repo defines `BUILD_PROFILE` (most alef binding repos) it
  selects `dev`, `release` or `ci`.
- Tools come from the same `mise.toml` (procedures: the `mise-toolchains` skill); tasks run with them on PATH.

## Task features

- Arguments: `#USAGE arg "<repo>" help="…"` and `#USAGE flag "--base <ref>"` (toml: `usage = '…'`) become
  `$usage_repo` and `$usage_base`. A task without a usage spec appends `mise run t -- a b` to its last command.
- `depends = ["a", "b"]` run first, in parallel; `depends_post` after; `wait_for` only orders tasks that run anyway.
- `sources` and `outputs` globs skip the task while outputs are newer (`mise run -f` forces it).
- `run_windows` replaces `run` on Windows; inside a script, branch on `uname` or `$OSTYPE`.
- `dir` (default: the config root; `{{cwd}}` is the caller's directory), `env = { K = "v" }`,
  `[env] _.file = ".env"`, `hide = true`, `quiet = true`, `shell = "bash -euo pipefail -c"` (the default
  `sh` has no pipefail).
- `mise tasks validate` checks cycles, missing dependencies, usage specs and file tasks; exit 1 on error.

## Polyrepo root tasks

Every subrepo inherits the polyrepo root `mise.toml` as a parent config, its tasks included, but those tasks
refuse to run from a subrepo. Each repo defines its own `setup`, `lint` and the rest; a repo task of the same
name overrides the root's.

## CI

`uses: xberg-io/actions/setup-mise@v1`, then `run: mise run <task>`; do not copy the task's commands into YAML.
To install only some tools, pass `install-args` and set `MISE_TASK_RUN_AUTO_INSTALL: "false"`.

## Converting from go-task

| go-task | mise |
| --- | --- |
| `cmds:` | `run` (array) |
| `deps:` | `depends` |
| `- task: x` in cmds | `{ task = "x" }` in `run`, or `mise run x` in a script |
| `vars:` (static, `sh:`) | `[vars]` / `{{vars.x}}`; `sh:` becomes shell in the script |
| `platforms:` | `run_windows`, or an OS branch in the script |
| `ignore_error: true` | `cmd \|\| true` |
| `status:` / `sources:` | `sources` + `outputs`, or a guard in the script |
| `defer:` | `trap … EXIT` in a file task |
| `for:` | a shell loop |
| `requires:`, `{{.CLI_ARGS}}` | `#USAGE` args, or appended `--` args |
| `set: [pipefail]` | a file task, or `shell = "bash -euo pipefail -c"` |
| `internal: true` | `hide = true` |
| `includes:` (`.task/x.yml`) | `mise-tasks/<ns>/` file tasks |

Prove parity before deleting the Taskfile: every name from `task --list-all --json | jq -r '.tasks[].name'`
must appear in `mise tasks --json`. Then delete `Taskfile.yml` and `.task/`, drop `task` from `mise.toml`,
relock, and switch CI to `mise run`.
