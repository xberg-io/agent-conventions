---
status: accepted
date: 2026-10-27
decision-makers: ["Na'aman Hirschfeld"]
---

# Pin actions to major tags

## Context and Problem Statement

Workflows referenced actions by full commit SHA, by minor tag and by major tag, mixed within one repository.
SHA and minor pins of the org's own xberg-io/actions do not receive fixes until someone bumps every caller, and the
mix makes it unclear which form a new workflow should use.

## Considered Options

* The action's shortest major tag (`@v4`, `@v1`)
* Full commit SHAs
* Minor or patch tags

## Decision Outcome

Chosen option: "The action's shortest major tag (`@v4`, `@v1`)", because callers get fixes within a major version
without a bump in every workflow, and one form is easy to review.

Every `uses:` reference names the shortest major tag, or the full version tag when the action publishes no major tag.
SHA pins are converted when a workflow is touched. xberg-io/actions keeps its callers on `@v1` working: its
`reusable-*.yml` paths are a public interface that is never renamed or removed, and new behaviour arrives as inputs.

### Consequences

* Good, because a fix to a shared action reaches every caller at once.
* Bad, because a major tag can move to code the caller has not reviewed; supply-chain trust rests on the action's
  publisher.

### Confirmation

The `github-workflow-conventions` skill (`modules/cicd/skills/github-workflow-conventions/SKILL.md`) states the rule;
added in `xberg-io/agent-conventions@2ddcd1f`. xberg-io/actions' `workflow-deltas` rule
(`.ai-rulez/rules/workflow-deltas.md`) keeps the reusable workflow paths stable.
