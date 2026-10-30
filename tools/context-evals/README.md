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
  start. Tokens use the recorded Sonnet instruction-text calibration in `calibration.json`; CLI runtime overhead is separate.
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
measurement:

```yaml
- uses: xberg-io/agent-conventions/actions/context-exposure@v1
  with:
    budgets: |
      claude=4650
      codex=7250
```

The action preserves its existing budget inputs in legacy byte/3.9 units while reporting calibrated totals. It
also checks the consumer's ai-rulez hook revision and lock against this repository's pins.

The action measures the `ai-rulez` server by default (`measure-mcp`), so it needs `ai-rulez` on `PATH`. Raising a
budget is a reviewed change to the consumer's workflow; the job summary carries the full report.

Tests: `mise run context:test` (supplies PyYAML).

## Dynamic layer

Runs real headless sessions per case and scores them (issue #3, section 5.2). Never in per-commit CI: it costs model
calls and is nondeterministic. Needs `claude`, `ai-rulez`, PyYAML and `ANTHROPIC_API_KEY`; refuses to start inside
another agent session. `--model` has no default: pick one per study and keep it fixed.

- Cases: `cases/<repo>/<domain>.yaml` (schema in `cases.py`), owned by the domain's owner. Split tune/holdout by
  `sha256(id) % 5`. `harness.py validate-cases [--repo-root CHECKOUT --repo NAME]` checks the schema, and against a
  checkout that every `cwd`, source and skill exists; CI runs the schema check.
- `harness.py run --repo CHECKOUT --ref REF --model M --out RUN_DIR [--split tune|holdout|all] [--repeats 3]`: a
  throwaway worktree at REF, `ai-rulez generate`, then one `claude -p` per case and repeat with a fresh config
  directory, project settings only, a strict empty MCP config and `--tools Read,Glob,Grep,Skill` plus the same
  permission allowlist. The advertised tool set and tool calls must match that profile; mismatches fail the
  session. Hard-budget mode adds the operating-system boundary described below. The tree is reset between
  sessions. `--jobs N` gives each worker its own worktree; `--resume` reuses only saved sessions with identical
  run parameters. Immutable context/configuration fingerprints and agent/generator binary hashes must match
  before reuse; existing snapshots are never overwritten. Legacy runs without identity are refused. Writes `run.json`, `transcripts/` and `sessions.jsonl` (`records.py`).
Paid execution requires an explicit policy. `--hard-budget --budget-ledger PATH --budget-usd 25` routes
agents and judges through the reserved egress gateway, caps output at 4,096 tokens and confines CLI network and
credential-file access. See [the price bound, offline proofs and limitations](hard-budget.md) before use.
`--allow-soft-budget` remains a separate prospective-accounting opt-in and cannot guarantee a dollar ceiling.
Never mix policies or reuse the historical invalid attempt's ledger; `study.toml` records that attempt's choices.

- `harness.py judge RUN_DIR --model M` grades criteria; `judge-validate RUN_DIR --model M --second-model M2` computes
  Cohen's kappa per criterion and the mutation-test TPR/TNR. Judges use `--tools ""` and must advertise an empty
  tool set. Only validated criteria count. Harness 5 rejects older tool and execution profiles for resume and paid judging;
  comparisons, verdicts and validity reports retain protocol provenance. Both judge prompts include their
  no-tools protocol versions so prompt-digest caches cannot reuse replies from the earlier tool-enabled profile.
- `harness.py report RUN_DIR`, `harness.py compare BASE_RUN ARM_RUN`: per-domain recall, precision, leak and
  answer-leak rates, over-/under-ask, criteria pass rate, start tokens and cost, with paired cluster-bootstrap
  intervals; "inconclusive" when an interval spans zero.

## Improvement loop

`loop.py triage | decide | ledger | holdout` (issue #3, section 6). The round, its arms and the decision rule are in
the repo-local `context-improvement` skill (`/context-improvement`, user-invoked). Every decision is appended to
`ledger.jsonl`.

## Probing a real session

`probe.py` measures loading in Claude Code and Codex themselves (issue #3, section 4.1). It creates an isolated consumer
worktree under `.worktrees/<repo>/`, plants a sentinel in the root `CLAUDE.md`, an unscoped and a glob-scoped rule, a
skill description and a nested `CLAUDE.md`, then runs `claude -p` with a fresh config directory and only project
settings: once with a trivial prompt (what loads at start, and its token cost) and once after reading a file in the
scoped directory (what loads on demand). Run it on your own machine with `ANTHROPIC_API_KEY` set, never inside
another agent session:

```sh
mise exec -- python tools/context-evals/probe.py ../xberg --scoped-file crates/xberg/src/lib.rs \
  --preset claude --model claude-sonnet-5-5 --repeats 3 --budget-ledger ../reports/study/budget.sqlite3 --json probe.json
```

Record the results with the Claude Code version in `docs/load-mechanics.md`.

## Baseline

[`baseline-2026-10-25.md`](baseline-2026-10-25.md): every consumer at agent-conventions `2011d3d` (sceptre `adb0caa`),
generated with `npx -y ai-rulez@latest generate` (5.6.3).

[`after-2026-10-25.md`](after-2026-10-25.md): the same consumers after the module restructure and the per-repo pass.

[`after-5.7.0-2026-10-26.md`](after-5.7.0-2026-10-26.md): the same consumers on ai-rulez 5.7.0 with
`scoped_fallback = "skill"`, which gives Codex the glob-scoped rules as path-gated skills.

[`after-mcp-2026-10-26.md`](after-mcp-2026-10-26.md): with the ai-rulez MCP server measured, before and after
restricting it to `find_skill` and `load_skill`.
