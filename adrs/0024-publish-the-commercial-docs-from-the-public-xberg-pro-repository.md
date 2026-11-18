---
status: accepted
date: 2026-11-18
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0010"]
---

# Publish the commercial docs from the public xberg-pro repository

## Context and Problem Statement

ADR-0010 serves the Xberg Pro and Enterprise documentation from the `xberg-enterprise` repository at
`enterprise.xberg.io`. That repository is private, so GitHub Pages never published the site, and customers and
evaluators had no public documentation for the commercial products.

## Decision Drivers

* Prospects and customers must read the Pro and Enterprise docs without repository access.
* The product source, internal design notes and customer material must stay private.
* The site keeps the shared theme and deployment of every other docs site.

## Considered Options

* A public, code-free `xberg-io/xberg-pro` repository that holds a commercial README and the docs site at
  `pro.xberg.io`
* Make `xberg-enterprise` public
* Host the docs from the private repository on a paid plan with public Pages

## Decision Outcome

Chosen option: "A public, code-free `xberg-io/xberg-pro` repository", because it publishes the docs on the same
theme and reusable deploy workflow as the open-source sites while keeping the product private.

The commercial docs site is served at `pro.xberg.io`, replacing `enterprise.xberg.io` in ADR-0010. Customer-facing
guides move out of `xberg-enterprise`; its engineering notes stay there. Content is licensed CC BY 4.0, and a CI
gate in `xberg-pro` rejects links to the private repository, internal source paths, internal hostnames and
customer names.

### Consequences

* Good, because the docs are public and indexed, and the README gives the commercial offer a public front page.
* Good, because the gate keeps private references out of a repository whose history cannot be retracted.
* Bad, because a documentation change and the product change it describes land in two repositories.

### Confirmation

The `xberg-brand-and-docs` skill names `pro.xberg.io` as the commercial docs domain, and `xberg-pro` runs
`scripts/check-public-content.sh` in its docs CI.
