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
- MCP servers each preset's config declares (`.mcp.json`, `.codex/config.toml`). A server costs nothing in the
  report until `--measure-mcp NAME` starts it over stdio and counts its tool schemas and instructions; unmeasured
  servers are listed. The full `ai-rulez mcp` server lists 67 tools (about 38k tokens); restricted to `find_skill`
  and `load_skill` (`[mcp] tools`), about 1.1k.
- inlined and glob-scoped rules, the largest always-loaded rules, descriptions over 250 characters.
- leaks: a term of a domain the repository does not own (`domains.toml`) found in its always-visible text.

`domains.toml` is the taxonomy: `[domain.<name>]` with owner, owning paths and terms; `[repos.<name>].domains` lists the
domains a repository owns; `[[accept]]` records an exception with a written `reason`. `--fail-on-leak` exits 1 when a
leak remains; `--fail-on-long-descriptions` when a listed skill or agent description is over 250 characters;
`--budget claude=N` (repeatable, per preset) when the estimated start tokens exceed `N`. `--repo-name` sets the name the
repository is looked up by in `domains.toml`, and a name missing from `[repos]` is an error under `--fail-on-leak`.

## CI gate

Consumers run the checks after `validate-ai-rulez` has generated the outputs, with budgets about 10% above the last
measurement, pinned to an agent-conventions commit:

```yaml
- uses: xberg-io/agent-conventions/actions/context-exposure@<sha>
  with:
    budgets: |
      claude=4650
      codex=7250
```

The action measures the `ai-rulez` server by default (`measure-mcp`), so it needs `ai-rulez` on `PATH`. Raising a
budget is a reviewed change to the consumer's workflow; the job summary carries the full report.

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

[`after-5.7.0-2026-10-26.md`](after-5.7.0-2026-10-26.md): the same consumers on ai-rulez 5.7.0 with
`scoped_fallback = "skill"`, which gives Codex the glob-scoped rules as path-gated skills.
