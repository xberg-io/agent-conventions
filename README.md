# agent-conventions

Shared agent-conventions modules for xberg.io polyglot projects. Include modules by `path`; consumer
repos generate local AGENTS.md from these sources.

## Available Modules

### `modules/core` — All repos need this

- **Agents** (7): code-reviewer, polyglot-architect, rust-core-engineer, ffi-engineer, docs-writer,
  security-auditor, performance-engineer
- **Rules** (8): atomic-commits, branch-hygiene, commit-messages, commit-procedure, safe-git-operations,
  tdd-workflow, test-alongside-code, verify-before-acting
- **Context** (1): polyrepo-structure
- **Skills** (8): common-task-commands, quick-start, alef-workflow, basemind-tools, binding-architecture,
  poly-lint-format, taskfile-structure, xberg-brand-and-docs

### `modules/languages` — Repos with language bindings

- **Agents** (16): python, typescript, ruby, go, java, csharp, php, elixir, wasm, dart, swift,
  kotlin-android, zig, r, c-ffi, jni specialists

### `modules/cicd` — Most repos need this

- **Agents** (2): release-engineer, devops-engineer
- **Skills** (2): cicd-pipeline-standards, gh-workflows

### `modules/e2e-generator` — Repos with `tools/e2e-generator/`

- **Agents** (1): e2e-generator-engineer
- **Rules** (1): generated-code-policy
- **Skills** (4): create-e2e-fixture, add-language-generator, e2e-generator-conventions, fixture-schema-design

### `modules/infrastructure` — Deployed services only

- **Skills** (3): containerization-docker, gcloud-conventions, monitoring-observability

## Usage

```yaml
includes:
  - name: xberg-core
    source: https://github.com/xberg-io/agent-conventions.git
    path: modules/core
    merge_strategy: local-override
  - name: xberg-languages
    source: https://github.com/xberg-io/agent-conventions.git
    path: modules/languages
    merge_strategy: local-override
  - name: xberg-cicd
    source: https://github.com/xberg-io/agent-conventions.git
    path: modules/cicd
    merge_strategy: local-override
```

Run `ai-rulez generate` from each consumer repo after updating include pins or local rule sources.

## Consumer Configurations

| Repo | Modules |
|------|---------|
| xberg | core, languages, cicd, infrastructure, e2e-generator |
| html-to-markdown | core, languages, cicd, infrastructure, e2e-generator |
| liter-llm | core, languages, cicd, e2e-generator |
| crawlberg | core, languages, cicd, e2e-generator |
| tree-sitter-language-pack | core, languages, cicd, e2e-generator |
| xberg-enterprise | cicd, infrastructure |
| infra | cicd, infrastructure |
| actions | cicd |

## License

See the LICENSE file for licensing information.
