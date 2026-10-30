---
status: accepted
date: 2026-08-07
decision-makers: ["Na'aman Hirschfeld"]
---

# Shared assets and distribution channels

## Context and Problem Statement

Brand assets, model weights, test corpora, CLI binaries and coding-agent plugins were copied into or built separately
by each product. Copies drift, and binary corpora in git (or Git LFS) make every clone and CI checkout heavy.

## Considered Options

* One shared home and channel per kind of artifact
* Each product keeps and ships its own copies

## Decision Outcome

Chosen option: "One shared home and channel per kind of artifact", because each artifact then has one source and one
way to reach users.

* Brand assets live in xberg-io/assets and are served through jsDelivr by tag; docs sites and READMEs reference them
  instead of local copies. The one exception: every docs site commits `docs-site/src/assets/hero-logo.svg` and
  `hero-logo-light.svg`, byte-identical to the assets repository, because the Starlight hero frontmatter imports a
  local file.
* Model weights the org converts or hosts itself (layout, PaddleOCR ONNX) are published under the `xberg-io` Hugging
  Face organization. Models used as published upstream are pulled from their own organizations.
* Test documents live in xberg-io/test_documents; binaries are content-addressed by sha256 in a public bucket and
  pinned by `corpus.lock.json`, not committed or kept in Git LFS.
* The CLIs of xberg, crawlberg, liter-llm, html-to-markdown and tree-sitter-language-pack each ship an npm and PyPI
  proxy package, `@xberg-io/<tool>-cli` (`cli-proxy/`), that downloads the checksummed release binary, so `npx` and
  `uvx` work.
* Each product's coding-agent plugin lives in its repository under `plugin/`.

These were settled between June 20 and August 7, 2026; this record is dated to the last, the corpus move.

### Consequences

* Good, because each artifact is updated once and every product picks it up.
* Bad, because products depend on external hosts (jsDelivr, Hugging Face, the corpus bucket) at build or run time.

### Confirmation

The `xberg-brand-and-docs` skill (`modules/docs-sites/skills/xberg-brand-and-docs/SKILL.md`, jsDelivr assets) and the
`document-corpus-handling` skill (`modules/document-corpora/`). Commits: `xberg-io/assets@b5069fb` (assets),
`xberg-io/xberg@bac2a10fdc` (Hugging Face models moved to `xberg-io`), `xberg-io/test_documents@b1bc47e` (corpus
without Git LFS), `xberg-io/xberg@55fd5b92c1` and the matching `cli-proxy/` commits in the other libraries (CLI
proxies), and `xberg-io/crawlberg@050b719bf7` with its siblings (plugins moved into the product repositories).
