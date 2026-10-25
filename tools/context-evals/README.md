# context-evals

The static layer of the context harness from
[issue #3](https://github.com/xberg-io/agent-conventions/issues/3): what a session in a consumer repository sees at
start, and which product terms leak into another product's start context. It reads the files `ai-rulez generate`
wrote; it runs no model.

```sh
# in each consumer checkout first
npx -y ai-rulez@latest generate

python3 tools/context-evals/exposure.py ../xberg ../sceptre ../liter-llm --markdown report.md --json report.json
```

Per repository and preset (`claude`, `codex`) it reports:

- start tokens: the root instruction files Claude or Codex actually reads (a `CLAUDE.md` without `@AGENTS.md`
  replaces `AGENTS.md`), always-on rules, and the name and description of every skill and agent that is listed at
  start. Skills with `paths:` and user-only skills (`disable-model-invocation: true`) are counted but cost nothing at
  start. Tokens are bytes / 3.9; calibrate against a real session before quoting absolute numbers.
- inlined and glob-scoped rules, the largest always-loaded rules, descriptions over 250 characters.
- leaks: a term of a domain the repository does not own (`domains.toml`) found in its always-visible text.

`domains.toml` is the taxonomy: `[domain.<name>]` with owner, owning paths and terms; `[repos.<name>].domains` lists the
domains a repository owns; `[[accept]]` records an exception with a written `reason`. `--fail-on-leak` exits 1 when a
leak remains, for CI.

Tests: `python3 -m unittest discover tools/context-evals`.

## Probing a real session

`probe.py` calibrates the static numbers against Claude Code itself (issue #3, section 4.1). It copies a consumer
checkout to a temporary directory, plants a sentinel in the root `CLAUDE.md`, an unscoped and a glob-scoped rule, a
skill description and a nested `CLAUDE.md`, then runs `claude -p` with a fresh config directory and only project
settings: once with a trivial prompt (what loads at start, and its token cost) and once after reading a file in the
scoped directory (what loads on demand). Run it on your own machine with `ANTHROPIC_API_KEY` set, never inside
another agent session:

```sh
python3 tools/context-evals/probe.py ../xberg --scoped-file crates/xberg/src/lib.rs --repeats 3 --json probe.json
```

Record the results with the Claude Code version in `docs/load-mechanics.md`.

## Baseline

[`baseline-2026-10-25.md`](baseline-2026-10-25.md): every consumer at agent-conventions `2011d3d` (sceptre `adb0caa`),
generated with `npx -y ai-rulez@latest generate` (5.6.3).

[`after-2026-10-25.md`](after-2026-10-25.md): the same consumers after the module restructure and the per-repo pass.
