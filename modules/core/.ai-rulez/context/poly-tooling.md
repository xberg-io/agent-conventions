---
priority: medium
---

# Poly Tooling

Poly provides linting and formatting across languages via bundled engines and native tool delegates. Configure via per-repo `poly.toml`.

| Scope | Engine(s) |
|-------|-----------|
| **Python** | ruff (lint + format), pyrefly (type check) |
| **JS/TS/JSON/CSS** | oxc (lint + format) |
| **TOML** | taplo (lint + format) |
| **Markdown** | rumdl (format) |
| **Rust** | cargo fmt + cargo clippy (via cargo hook) |
| **Go** | golangci-lint |
| **Java** | checkstyle, maven verify |
| **Ruby** | rubocop (format + lint) |
| **C#** | dotnet format |
| **PHP** | php-cs-fixer, phpstan |
| **Elixir** | mix format, mix credo |
| **R** | styler, lintr |
| **C/C++** | clang-format, cppcheck |
| **Shell** | shfmt, shellcheck |
| **Git** | gitfluff (commit message linting), ai-rulez-generate |
| **GH Actions** | actionlint |
| **Helm/K8s** | helm-lint, kubeconform |
