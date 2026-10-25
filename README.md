# agent-conventions

Shared agent-conventions modules for xberg.io polyglot projects. Include modules by `path`; consumer
repos generate local AGENTS.md from these sources.

## Available Modules

Modules hold generic conventions only: content that is true in every repository that includes the module.
Product knowledge (a product's corpora, formats, benchmarks, crates) lives in that product's own `.ai-rulez/`.

### `modules/core`: all repos

- **Rules, always on** (6): comment-discipline, commit-messages, commit-procedure, prove-the-check-fired,
  safe-git-operations, targeted-verification
- **Rules, glob-scoped** (1): logging-tracing (`**/*.rs`, `**/Cargo.toml`)
- **Agents** (7): code-reviewer, polyglot-architect, rust-core-engineer, ffi-engineer, docs-writer,
  security-auditor, performance-engineer
- **Context** (1): polyrepo-structure
- **Skills** (10): agent-coordination, alef-workflow, basemind-tools, binding-architecture,
  feature-flag-conventions, poly-lint-format, release-workflow, taskfile-structure, tracing-conventions,
  xberg-brand-and-docs

### `modules/languages`: all repos with code

- **Rules, glob-scoped** (17): rust, c-ffi, python, typescript, wasm, ruby, php, go, java, kotlin-android, csharp,
  elixir, swift, dart, zig, r. Each holds the language conventions, its binding framework (PyO3, napi-rs, Magnus,
  ext-php-rs, jni-rs, cgo, Rustler, extendr, wasm-bindgen) and org policy (for example Pyrefly as the only Python type
  checker). Globs cover the file types plus the shared alef layout (`crates/*-py/**`, `packages/python/**`, ...), so a
  rule costs nothing until a matching file is read. They replace the ai-rulez language and binding builtins; drop
  those from `builtins` when you include this module.

### `modules/cicd`: most repos

- **Agents** (2): release-engineer, devops-engineer
- **Skills** (4): cicd-pipeline-standards, consumer-release-gates, gh-workflows, scoop-distribution

### `modules/e2e-generator`: repos with alef e2e suites

- **Agents** (1): e2e-generator-engineer
- **Rules, glob-scoped** (1): generated-code-policy (`e2e/**`, `fixtures/**`)
- **Skills** (4): create-e2e-fixture, add-language-generator, e2e-generator-conventions, fixture-schema-design

### `modules/infrastructure`: deployed services only

- **Skills** (3): containerization-docker, gcloud-conventions, monitoring-observability

## Placement

Every session should start with the smallest context that lets it do the task, and load the rest when the work
reaches it. Place each rule, skill or agent at the first level that fits:

1. True for every file and task in the repo: an always-on rule. Keep it short.
2. Tied to a file type or a directory: a rule with `paths:` globs, or a skill with `paths:`. Shared modules use the
   org's repeatable layout (`crates/<name>-<lang>/`, `packages/<lang>/`, `e2e/`, `fixtures/`, `alef.toml`) so one
   definition gates correctly in every repo. Shared glob-scoped rules set `targets` to the rules folders
   (`.claude/rules/`, `.github/instructions/`): presets without path scoping (Codex, OpenCode, Pi) would inline them
   into `AGENTS.md`, where they cost every session and push the file past Codex's 32 KiB read limit.
3. An area with its own skills, agents and toolchain that people work in directly (an integration package, a docs
   site, a tool): a nested `.ai-rulez/` in that directory, generated with `ai-rulez generate --recursive`. It writes a
   nested `CLAUDE.md`/`AGENTS.md` and nested skills that load only inside that tree. Set `builtins = false` there so the
   root's builtins are not repeated.
4. A procedure used for some tasks: a skill whose description (250 characters or less) says what it is for and the
   words a user would say.
5. Needs isolation or restricted tools: an agent. Otherwise not an agent.
6. Shared across repos: a module here, only if it is true in every repo that includes the module.

`tools/context-evals/exposure.py` reports what each consumer loads at start and flags product terms that leak into
another product's start context; see [tools/context-evals](tools/context-evals/README.md).

## Usage

```toml
version = "5.0"
name = "your-project"
presets = ["claude", "codex", "opencode", "pi"]
default_layers = ["plugins"]
compact = true
# Claude reads a CLAUDE.md without the glob-scoped rules (they go to .claude/rules/ with `paths:`).
# With the default `agents_md = true`, CLAUDE.md imports AGENTS.md, which inlines them for Codex.
agents_md = false
# The agent roster repeats the agent files in every root file; harnesses list agents natively.
builtins = ["!agent-delegation", "!git-workflow"]

[[includes]]
name = "xberg-core"
source = "https://github.com/xberg-io/agent-conventions.git"
path = "modules/core"
merge_strategy = "local-override"

[[includes]]
name = "xberg-languages"
source = "https://github.com/xberg-io/agent-conventions.git"
path = "modules/languages"
merge_strategy = "local-override"

[[includes]]
name = "xberg-cicd"
source = "https://github.com/xberg-io/agent-conventions.git"
path = "modules/cicd"
merge_strategy = "local-override"
```

Put the example in `.ai-rulez/config.toml`. Put marketplace and plugin declarations in
`.ai-rulez/config.plugins.toml`, selected by the `plugins` default layer. Add only the modules
your repository uses, pinned by `ref`. Use ai-rulez 5.6.3 or later (CI pins the release) to
validate and regenerate after editing sources:

```sh
ai-rulez validate --no-local
ai-rulez generate --no-local --strict-config
task governance:check
```

Consumers generate local harness files from these modules. Product plugin content is maintained
separately under each product's `plugin/.ai-rulez/`; its public `skills/` export contains product
integration instructions. It does not expose this repository's internal contributor conventions.
Reviewed Poly hooks validate staged source configuration; `task governance:check` checks the
materialized local output. See [CONTRIBUTING.md](CONTRIBUTING.md) for editing and hook setup.

## Installable skills

The public [`skills/`](skills/) directory contains the Agent Skills maintained in these modules
plus the ai-rulez built-in governance skills. A native ai-rulez provider projects their consumer frontmatter
and supporting resources; edit the source modules and run `task skills:generate`, then
`task skills:check`. The generated export is committed and checked in CI.

```sh
npx skills add xberg-io/agent-conventions --skill release-workflow
```

For Codex, a skill can also be copied into your project’s `.agents/skills/` or your user skills
directory. These skills describe repository development and release conventions; product SDK
skills live in each product repository.

## Consumer Configurations

| Repo | Modules |
|------|---------|
| xberg | core, languages, cicd, infrastructure, e2e-generator |
| html-to-markdown | core, languages, cicd, infrastructure, e2e-generator |
| liter-llm | core, languages, cicd, e2e-generator |
| crawlberg | core, languages, cicd, e2e-generator |
| tree-sitter-language-pack | core, languages, cicd, e2e-generator |
| alef | core, languages, cicd |
| sceptre | core, languages, cicd |
| xberg-enterprise | core, languages, cicd, infrastructure |
| actions | core, languages, cicd |
| infra | cicd, infrastructure |

## License

See the LICENSE file for licensing information.
