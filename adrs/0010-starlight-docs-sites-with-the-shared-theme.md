---
status: accepted
date: 2026-07-07
decision-makers: ["Na'aman Hirschfeld"]
---

# Starlight docs sites with the shared theme

## Context and Problem Statement

Each open-source product has a documentation site. Copying brand CSS, fonts, logos and analytics tags into every
site's configuration let them drift, and a brand change had to be made in each repository.

## Considered Options

* Astro Starlight sites that consume the shared `@xberg-io/docs-theme` package, served at `docs.<product>.xberg.io`
* Per-site brand configuration in every repository

## Decision Outcome

Chosen option: "Astro Starlight sites that consume the shared `@xberg-io/docs-theme` package, served at
`docs.<product>.xberg.io`", because the theme carries the brand, assets and analytics once for every site.

Each docs site is an Astro Starlight project under `docs-site/` that wraps `xbergStarlightConfig()` from
`@xberg-io/docs-theme`. Sites do not add their own brand CSS or analytics. A product's site is served at
`docs.<repo>.xberg.io`; the core extraction library uses `docs.xberg.io`.

### Consequences

* Good, because a brand or analytics change ships in one theme release.
* Bad, because every site depends on the theme's release, and a theme defect reaches all of them.

### Confirmation

The `xberg-brand-and-docs` skill (`modules/docs-sites/skills/xberg-brand-and-docs/SKILL.md`) states the theme and
the domain pattern. The theme began in `xberg-io/docs-theme@653b281`.
