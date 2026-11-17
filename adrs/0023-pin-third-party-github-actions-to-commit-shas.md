---
status: proposed
date: 2026-11-16
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0008", "0019"]
---

# Pin third-party GitHub Actions to commit SHAs

## Context and Problem Statement

The [Xberg supply-chain audit](https://github.com/xberg-io/xberg/issues/3168) found mutable third-party action refs in
workflows, including release jobs that can request OIDC tokens. A publisher can move a tag after a workflow change
has been reviewed. Shared Xberg actions also use movable tags, which let the organization deliver fixes to its own
consumers within a supported major version.

## Considered Options

* Keep major tags for every action
* Pin every remote action and reusable workflow to a commit SHA
* Pin third-party refs to full commit SHAs and retain the first-party major-tag policy

## Decision Outcome

Chosen option: "Pin third-party refs to full commit SHAs and retain the first-party major-tag policy", because
changes to code owned outside the organization should appear in a consumer's review diff and the organization
still needs to deliver fixes to its shared actions and reusable workflows.

An adopting repository uses a full 40-character commit SHA for every remote third-party action or reusable
workflow in a workflow or composite action. This includes GitHub-maintained actions under `actions/`. Use an
upstream release tag in the line comment when one is available. The first-party `xberg-io/*` namespace follows
[ADR-0008](0008-pin-actions-to-major-tags.md). Repository-local action and workflow paths and `docker://` refs
are outside this rule. Poly hook source revisions remain governed by
[ADR-0019](0019-gh-actions-updater-owns-action-pin-updates.md).

Roll out to Xberg after this ADR is accepted. The adoption change pins the third-party refs, enables an
owner-aware offline check, and configures the updater to retain each ref's representation. gh-actions-updater
0.4.0 supports representation-preserving updates with `--latest`. Its offline `--lint-pins` gate requires
major tags and cannot enforce this policy, so the adopting repository needs a separate owner-aware gate until
the shared tooling supports it. The updater opens a pull request for review. Reviewing a change to a release
workflow includes checking the upstream change represented by its new SHA.

Keep the existing major-tag checker and updater mode for repositories that have yet to adopt this policy. Once
the shared enforcement and updater support the policy, update the workflow conventions and toolchain rules and
roll out to other consumers. Shared reusable workflow defaults keep their existing behavior for callers during
the rollout.

### Consequences

* Good, because an upstream tag move cannot change the action code selected by a reviewed third-party ref.
* Good, because Xberg can test an owner-aware checker and a representation-preserving updater before wider adoption.
* Bad, because third-party fixes require a new review and merge in each consumer.
* Bad, because the rollout uses parallel checks until the shared tooling supports both policies.

### Confirmation

The current shared check and update commands are in
[reusable-validate.yml](https://github.com/xberg-io/actions/blob/v1/.github/workflows/reusable-validate.yml) and
[reusable-actions-bump.yml](https://github.com/xberg-io/actions/blob/v1/.github/workflows/reusable-actions-bump.yml).
Before Xberg adopts the policy, its offline check must enumerate workflow and composite action refs and report a
nonzero checked count. Exercise a third-party full SHA and first-party major tag as positive cases, and a
third-party version tag, branch, and abbreviated SHA as negative cases. Include a reusable workflow call and
verify that the updater keeps third-party SHAs and first-party major tags in its proposed diff. The existing
hook-source check remains in `tools/context-evals/test_hook_pins.py`.
