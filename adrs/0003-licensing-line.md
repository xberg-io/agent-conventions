---
status: accepted
date: 2026-06-27
decision-makers: ["Na'aman Hirschfeld"]
---

# Licensing line

## Context and Problem Statement

The organization publishes open-source libraries and sells a commercial platform built on them. Each repository needs
an unambiguous license, and the line between the open and the commercial products has to be the same everywhere.

## Considered Options

* MIT for the libraries and tools, proprietary for xberg-enterprise, private infrastructure
* BUSL-1.1 for xberg-enterprise, converting to Elastic License 2.0 in 2030
* Elastic License 2.0 for xberg-enterprise

## Decision Outcome

Chosen option: "MIT for the libraries and tools, proprietary for xberg-enterprise, private infrastructure", because
it keeps the libraries free to adopt while the platform's commercial value stays proprietary with no conversion date.

The libraries and the org's published tooling (alef, sdks, toolchains, agent-conventions, docs-theme, assets) are
MIT. xberg-enterprise is proprietary under a commercial license, as its
ADR-0065 decides (it replaces the BUSL-1.1 model of its ADR-0062). The infrastructure repository is private and
unlicensed.

### Consequences

* Good, because a library user needs no agreement, and the commercial tiers can change without an open-source
  conversion to coordinate.
* Bad, because code moving from xberg-enterprise into a library needs a deliberate relicensing decision.

### Confirmation

The `LICENSE` files of xberg, crawlberg, html-to-markdown, liter-llm, tree-sitter-language-pack, alef, sdks, assets,
docs-theme, toolchains and agent-conventions carry the MIT text. xberg-enterprise's `LICENSE` is the proprietary
commercial license, and its `adrs/0065-proprietary-commercial-licensing.md` records the choice, dated 2026-06-27.
