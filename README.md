# agent-conventions

Shared agent-conventions modules for xberg.io polyglot projects. Include modules by `path`; consumer
repos generate local AGENTS.md from these sources.

## Available Modules

### `modules/core` — All repos need this

- **Agents** (7): code-reviewer, polyglot-architect, rust-core-engineer, ffi-engineer, docs-writer,
  security-auditor, performance-engineer
- **Rules** (13): atomic-commits, branch-hygiene, comment-discipline, commit-messages, commit-procedure,
  extraction-measurement-hygiene, logging-tracing, measurement-discipline, partner-corpus-handling,
  prove-the-check-fired, safe-git-operations, targeted-verification, tracing-product-surface
- **Context** (1): polyrepo-structure
- **Skills** (12): agent-coordination, alef-workflow, basemind-tools, binding-architecture,
  common-task-commands, feature-flag-conventions, poly-lint-format, quick-start, release-workflow,
  taskfile-structure, tracing-conventions, xberg-brand-and-docs

### `modules/languages` — Repos with language bindings

- **Agents** (16): python, typescript, ruby, go, java, csharp, php, elixir, wasm, dart, swift,
  kotlin-android, zig, r, c-ffi, jni specialists

### `modules/cicd` — Most repos need this

- **Agents** (2): release-engineer, devops-engineer
- **Skills** (4): cicd-pipeline-standards, consumer-release-gates, gh-workflows, scoop-distribution

### `modules/e2e-generator` — Repos with `tools/e2e-generator/`

- **Agents** (1): e2e-generator-engineer
- **Rules** (1): generated-code-policy
- **Skills** (4): create-e2e-fixture, add-language-generator, e2e-generator-conventions, fixture-schema-design

### `modules/infrastructure` — Deployed services only

- **Skills** (3): containerization-docker, gcloud-conventions, monitoring-observability

## Usage

```toml
version = "5.0"
name = "your-project"
presets = ["claude", "codex", "opencode", "pi"]
default_layers = ["plugins"]

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
your repository uses. Use the reviewed ai-rulez CLI, based on 5.2.1 and pinned by source revision in `poly.toml`,
to validate and regenerate after editing sources:

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

The public [`skills/`](skills/) directory contains 29 Agent Skills: 23 maintained in these modules
and six built-in governance skills. A native ai-rulez provider projects their consumer frontmatter
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
| sceptre | core, cicd |
| xberg-enterprise | cicd, infrastructure |
| infra | cicd, infrastructure |
| actions | cicd |

## License

See the LICENSE file for licensing information.
