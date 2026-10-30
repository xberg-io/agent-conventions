---
status: accepted
date: 2026-10-30
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0014"]
---

# Agent plugin bundles ship local brand assets

## Context and Problem Statement

ADR-0014 serves brand assets from xberg-io/assets through jsDelivr, with one local exception: the Starlight hero
logos. Each product's coding-agent plugin also carries an icon and a logo. Codex says to keep manifest paths
(`.codex-plugin/plugin.json`, including `interface.composerIcon` and `interface.logo`) relative to the plugin root,
starting with `./`, and to store visual assets under `./assets/` "when possible"
(developers.openai.com/codex/plugins/build). Cursor's optional `logo` accepts a relative path or an absolute URL, but
its submission checklist requires every manifest path to be relative (cursor.com/docs/plugins/building). The products
already ship such copies: xberg's `plugin/.ai-rulez/config.plugins.toml` sets `icon = "./assets/icon.svg"` and
`logo = "./assets/logo.png"` with `include = ["assets/**"]`, and ai-rulez renders them, byte-identical, to
`plugin/assets/`. Those copies are product placeholders, such as xberg's generic document glyph on `#1F6FEB`, not
the brand symbol.

## Considered Options

* Local icon and logo files in each plugin bundle, derived from the assets repository
* CDN URLs in the plugin manifests
* No icon or logo in the plugin manifests

## Decision Outcome

Chosen option: "Local icon and logo files in each plugin bundle, derived from the assets repository", because the
Codex `./` rule and Cursor's submission checklist call for paths inside the bundle, and deriving the files keeps one
brand source.

Agent plugin bundles are a second exception to ADR-0014's CDN rule. The source copies live in
`plugin/.ai-rulez/assets/` and must derive from the assets repository's `logo/symbol-*` files; ai-rulez copies them
into `plugin/assets/`, which the manifests reference. Today's placeholder copies are to be replaced with derived ones.
Nothing else in a plugin vendors brand assets.

### Consequences

* Good, because the plugin icons render in every agent that reads the bundle, offline and from a marketplace.
* Bad, because each product holds a copy that must be refreshed by hand when the symbol files change.

### Confirmation

The `xberg-brand-and-docs` skill (`modules/docs-sites/skills/xberg-brand-and-docs/SKILL.md`) states the exception.
xberg-io/xberg `plugin/.ai-rulez/config.plugins.toml` and `plugin/.codex-plugin/plugin.json` show the local paths,
and `ai-rulez verify --plugin` (`mise run plugin:verify`) fails when `plugin/assets/` drifts from
`plugin/.ai-rulez/assets/`. No gate compares the source copies with the assets repository; review does.
