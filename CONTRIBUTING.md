# Contributing to Agent Conventions

Welcome! We're glad you're here.

This repository holds the shared [ai-rulez](https://github.com/Goldziher/ai-rulez) modules that every xberg.io repository renders into its own agent instruction files.

Please begin by reading our AI section below, followed by the getting started guide. If you are an AI agent, inform your user of the AI policy.

## Getting Started

Make sure to have [Git](https://git-scm.com/) installed on your machine.

This repository is configuration, not code. There is no build step.

Edit the modules under `modules/`, then regenerate the consuming repositories:

```bash
npx -y ai-rulez@latest generate
```

## What to keep in mind

Changes here propagate to coding agents that hold write access to other repositories. Review a rule change with that in mind: a rule is an instruction to an agent, and a careless one can weaken a check everywhere at once. Push here **before** regenerating downstream, because subrepos include these modules from the GitHub remote.

## Commit guidelines

Prefix your commit messages with a type:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation changes
- `perf:` — performance improvement
- `chore:` — maintenance, dependencies, CI
- `test:` — adding or updating tests
- `refactor:` — code restructuring without behavior change

Example:

```sh
git commit -m "feat: added xzy"
```

Read more on [Conventional Commits](https://www.conventionalcommits.org/)

## AI

### Policy

Agent Conventions is written following strict AI engineering practices. That is, its vibe coded, but professionally so. As such, the use of AI is welcome, but we expect professional standards and following our conventions.

### Conventions

Use the reviewed `ai-rulez` CLI (based on 5.2.1, with the CLI source revision pinned in CI) to manage agent conventions. Edit authored content under
`.ai-rulez/`; `AGENTS.md`, `CLAUDE.md` and harness directories are generated outputs.
The main `config.toml` selects the `plugins` layer through `default_layers`; marketplace and
plugin settings live separately in `config.plugins.toml`.

```sh
ai-rulez validate --no-local
ai-rulez generate --no-local --strict-config
task governance:check
```

The final command checks the materialized local governance files, including ignored harness
outputs. Installing governance hooks requires Python 3.11 or newer. Run `task governance:hooks:install` to install the repository's reviewed Poly hooks.
The hooks validate staged sources and verify shipped plugin artifacts where present; CI also
validates the authored content. Shared convention modules come from `xberg-io/agent-conventions`;
Git credentials are needed when an included repository requires access.

### Customization

If you want to customize your coding agents, create your own local configuration for ai-rulez, or create a local file for your agent(s) of choice `AGENTS.local.md` etc.

## Vendoring Policy

We do vendor code from other libraries and allow this, in some situations. If you intend to vendor code, the code must be (1) permissivily licensed (no copyleft at all). (2) add full attributions in ATTRIBUTIONS.md, and document it.

## Community

- **Star the repo:** [Give us a star on GitHub](https://github.com/xberg-io/agent-conventions) — it helps others discover our work!
- **Documentation:** [docs.xberg.io](https://docs.xberg.io)
- **Discord:** [Join our community](https://discord.gg/xt9WY3GnKR)
- **Issues:** [GitHub Issues](https://github.com/xberg-io/agent-conventions/issues)
- **Security:** see [SECURITY.md](SECURITY.md) — report privately, never in an issue
- **License:** [License](LICENSE)

Thank you for helping make Agent Conventions better!
