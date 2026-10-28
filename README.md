# agent-conventions

Shared ai-rulez modules for the xberg-io organization's repositories. Include modules by `path`; consumer
repos generate local AGENTS.md from these sources.

## Available Modules

Modules hold generic conventions only: content that is true in every repository that includes the module.
Product knowledge (a product's corpora, formats, benchmarks, crates) lives in that product's own `.ai-rulez/`.
Where an ai-rulez builtin already says the same thing, the module does not repeat it.

### `modules/core`: all repos

- **Rules, always on** (10): agent-workflow, basemind-usage, comment-discipline, commit-messages, commit-procedure,
  prove-the-check-fired, safe-git-operations, skill-discovery, test-alongside-code, toolchain-management
- **Context** (1): polyrepo-structure
- **Skills** (8): agent-coordination, basemind-tools, mise-toolchains, poly-lint-format, release-workflow,
  taskfile-structure, tdd-workflow, verification-harness

`test-alongside-code` and `tdd-workflow` replace the `testing` builtin's rule and skill of the same ids, which say to
run the full suite before committing, and `agent-workflow` replaces the `ai-governance` builtin's, adding the
subagent rules (no compiling in subagents, disjoint worktrees, implement-review-adjust rounds, reported deviations).
Each override works but raises `AR703 duplicate-collapsed`, which fails `ai-rulez validate --strict`; add
`"!testing/test-alongside-code"`, `"!testing/tdd-workflow"` and `"!ai-governance/agent-workflow"` to `builtins` to
keep the module items without the warning.

### `modules/languages`: all repos with code

- **Rules, glob-scoped** (12): rust, python, typescript, ruby, php, go, java, kotlin-android, csharp, elixir, r, shell
  (Bats is the only shell test framework). Plain
  language conventions plus org policy (for example Pyrefly as the only Python type checker), gated on the language's
  file types, so a rule costs nothing until a matching file is read. They replace the ai-rulez language builtins;
  drop those from `builtins` when you include this module.
- **Skills** (2), Rust paths: feature-flag-conventions (`**/Cargo.toml`), tracing-conventions
- **Agents** (1): performance-engineer

### `modules/bindings`: repos that generate polyglot bindings with alef

- **Rules, glob-scoped** (3), gated on the alef layout: rust-native-bindings (PyO3, napi-rs, Magnus,
  ext-php-rs, Rustler, extendr, wasm-bindgen, and the Dart and Swift bridge crates), c-abi-wrappers (the
  `crates/*-ffi` C ABI plus the Go, C# and Zig wrappers), jvm-bindings (Java, Kotlin Android, `crates/*-jni`)
- **Skills** (3): binding-architecture, consumer-release-gates, e2e-generation (`e2e/**`, `fixtures/**`,
  `alef.toml`)

A repo that includes this module must enable the `polyglot-bindings` builtin: it holds the general binding
and FFI principles (ownership, opaque handles, error and async boundaries, ABI stability) and the
ffi-engineer and polyglot-architect agents, which this module does not repeat. Exclude
`!polyglot-bindings/rust-polyglot-conventions`: it restates the languages module's `rust` rule. alef's own installed skill
(`[[installed_skills]] alef`) covers the generator, its tasks and the version sync.

### `modules/cicd`: most repos

- **Skills** (2): github-workflow-conventions (`.github/workflows/**`, `.github/actions/**`), scoop-distribution
  (`scripts/publish/**`)

The `cicd` builtin (`cicd/github-workflow`, `cicd/pipeline-standards`) is opt-in; no consumer enables it.

### `modules/infrastructure`: deployed services only

- **Skills** (1): gcloud-conventions (IaC, workflow and deploy paths)

Container and service-observability guidance is the `docker` and `observability` builtins.

### `modules/docs-sites`: repos with a docs site or a generated README brand block

- **Skills** (1): xberg-brand-and-docs (`docs-site/**`, `readme_templates/**`, `templates/readme/**`): brand,
  product list, the shared docs theme, docs tasks, analytics IDs, README-template policy

### `modules/document-corpora`: repos that handle partner or public-record document corpora

- **Skills** (1): document-corpus-handling (corpus, manifest and attribution paths)

## Placement

Every session should start with the smallest context that lets it do the task, and load the rest when the work
reaches it. Place each rule, skill or agent at the first level that fits:

1. True for every file and task in the repo: an always-on rule. Keep it short.
2. Tied to a file type or a directory: a rule with `paths:` globs, or a skill with `paths:`. Shared modules use the
   org's repeatable layout (`crates/<name>-<lang>/`, `packages/<lang>/`, `e2e/`, `fixtures/`, `alef.toml`) so one
   definition gates correctly in every repo. Presets without path scoping (Codex, OpenCode) get each glob-scoped
   rule as an on-demand skill in `.agents/skills` through `[rules] scoped_fallback = "skill"`, instead of having it
   inlined into the shared `AGENTS.md`, where every preset would load it at start.
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
presets = ["claude", "codex", "opencode"]
default_layers = ["plugins"]
compact = true
# The agent roster repeats the agent files in every root file; harnesses list agents natively.
builtins = [
  "!agent-delegation", "!git-workflow", "!ai-governance/agent-workflow",
  "!testing/test-alongside-code", "!testing/tdd-workflow",
  "!token-efficiency/output-awareness", "!ai-governance/explain-reasoning",
  "!security/least-privilege", "!security/input-validation",
  "default-commands",
]

# Glob-scoped rules stay out of the shared AGENTS.md (and so out of CLAUDE.md, which imports it): Claude
# loads them from .claude/rules on a matching read, presets without a rules folder as path-gated skills.
[rules]
scoped_fallback = "skill"

# The full ai-rulez server lists 67 tools (~38k tokens) at every start; skill discovery needs two (~1.1k).
# core's skill-discovery rule points the model at them.
[mcp]
self_server_command = ["ai-rulez", "mcp"]
serve_skills = true
read_only = true
discover_skills = "repo"
tools = ["find_skill", "load_skill"]

[[includes]]
name = "xberg-core"
source = "https://github.com/xberg-io/agent-conventions.git"
version = "^1"
path = "modules/core"
merge_strategy = "local-override"

[[includes]]
name = "xberg-languages"
source = "https://github.com/xberg-io/agent-conventions.git"
version = "^1"
path = "modules/languages"
merge_strategy = "local-override"

[[includes]]
name = "xberg-cicd"
source = "https://github.com/xberg-io/agent-conventions.git"
version = "^1"
path = "modules/cicd"
merge_strategy = "local-override"
```

Put the example in `.ai-rulez/config.toml`. The repository's own root context is short: an area map in
`.ai-rulez/context/area-map.md` (one line per top-level area, pointing to the scoped rules and skills that cover
it, no procedures) and only the rules that hold for every file. Everything else is a path-scoped rule, a skill
gated by `paths:`, or a nested `.ai-rulez` under the directory it serves. Put marketplace and plugin declarations in
`.ai-rulez/config.plugins.toml`, selected by the `plugins` default layer. Add only the modules
your repository uses, by version range (`version = "^1"`; the lock records the exact tag and commit). Use the latest
ai-rulez release (CI installs `latest`; minimum 5.7.0) to validate and regenerate after editing sources:

```sh
ai-rulez validate --no-local
ai-rulez generate --no-local --strict-config
task governance:check
```

## Releasing

Push a `vX.Y.Z` tag, or run the Conventions Release workflow (`release-conventions.yaml`) from the default branch
with a version: it validates, creates the tag if needed, moves the floating `vX` tag to it with a lease (never
backwards), and publishes the GitHub release. Consumers then move their pins with `ai-rulez update` (the polyrepo
root runs it everywhere with `task ai-rulez:update`); `ai-rulez lock --outdated` shows what would move.
Bump the major version only for a change that breaks consumers, such as removing or renaming a module or item.

Consumers generate local harness files from these modules. Product plugin content is maintained
separately under each product's `plugin/.ai-rulez/`; its public `skills/` export contains product
integration instructions. It does not expose this repository's internal contributor conventions.
CI gates the start context with `actions/context-exposure` (budgets, leaks, description length); see
[tools/context-evals](tools/context-evals/README.md) and [docs/load-mechanics.md](docs/load-mechanics.md).
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

Repos that include `bindings` also enable the `polyglot-bindings` builtin; infra enables the `docker` and
`observability` builtins, xberg-enterprise `docker`.

| Repo | Modules |
|------|---------|
| xberg | core, languages, cicd, infrastructure, bindings, document-corpora, docs-sites |
| crawlberg, html-to-markdown, liter-llm, tree-sitter-language-pack | core, languages, cicd, bindings, docs-sites |
| xberg-enterprise | core, languages, cicd, infrastructure, document-corpora, docs-sites |
| sceptre, sdks | core, languages, cicd, docs-sites |
| alef, actions, test-apps | core, languages, cicd |
| infra | core, languages, cicd, infrastructure |
| docs-theme | core, cicd, docs-sites |
| test_documents | core, cicd, document-corpora |
| paddle-to-onnx | core, languages |
| assets, homebrew-tap, scoop-bucket, polyrepo root | core |

## License

See the LICENSE file for licensing information.
