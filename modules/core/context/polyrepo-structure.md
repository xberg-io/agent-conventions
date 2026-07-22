---
priority: high
---

# Polyrepo Structure

This repo is part of the `xberg-io` polyrepo. From any subrepo, `../` is the polyrepo root.

- Shared AI governance config: `../agent-conventions/` (shared ai-rulez modules)
- Polyrepo-level orchestration: `../Taskfile.yml`, `../poly.toml`
- Each subrepo is an independent git repo with its own `.ai-rulez/config.toml`
- Navigate between repos via `../` relative paths
