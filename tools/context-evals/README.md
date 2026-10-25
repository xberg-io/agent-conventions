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

## Baseline

[`baseline-2026-10-25.md`](baseline-2026-10-25.md): every consumer at agent-conventions `2011d3d` (sceptre `adb0caa`),
generated with `npx -y ai-rulez@latest generate` (5.6.3).
