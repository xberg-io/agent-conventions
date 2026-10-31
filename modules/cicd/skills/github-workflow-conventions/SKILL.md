---
type: Playbook
title: Github Workflow Conventions
description: "Organize GitHub Actions workflows, name CI/release/deployment files, pin actions, and audit workflow references and stage boundaries. Use when creating, renaming, splitting, or reviewing workflows."
paths:
  - ".github/workflows/**"
  - ".github/actions/**"
x-ai-rulez:
  kind: skill
  id: github-workflow-conventions
  metadata:
    name: github-workflow-conventions
---

# GitHub workflow conventions

Name new workflows in lowercase kebab-case with the `.yaml` extension. Classify by the workflow's outcome,
not its trigger: a manually dispatched test is CI; a scheduled image publisher is a release.

A workflow path that other repos call or that rulesets name is a public interface and keeps its
name and extension: xberg-io/actions' `reusable-*.yml` workflows are called by path from every repo,
each repo's governance workflow (`ai-rulez-validation.yml` or `ci-ai-rulez.yaml`) is the shared
governance check, and an existing `publish.yaml` is named by the registries' OIDC trusted-publisher
entries (PyPI, npm, crates.io, RubyGems), so renaming it breaks publishing. Never rename those, or
their `publish-<artifact>.yaml` siblings, to fit the table; the `release-` row is for new workflows.

| Purpose | Filename | Display name |
| --- | --- | --- |
| Validation, build, or test without publication | `ci-<domain>.yaml` | `<Domain> CI` |
| Independently scheduled or expensive test suite | `ci-<domain>-<suite>.yaml` | `<Domain> <Suite> CI` |
| Publish versioned packages or images | `release-<artifact>.yaml` | `<Artifact> Release` |
| Apply configuration or deploy an environment | `deploy-<target>.yaml` | `<Target> Deploy` |
| Notifications or repository housekeeping | `maintenance-<purpose>.yaml` | `<Purpose> Maintenance` |
| Only invoked through `workflow_call` | `reusable-<purpose>.yaml` | `<Purpose> (Reusable)` |

Keep one domain's normal CI in one primary workflow. Split suites for different schedules, permissions,
or resource needs, not merely because they have separate jobs. Publication and deployment belong in
their own entrypoints; reuse validation through tasks or a reusable workflow rather than copying it.
A release may call a deployment workflow after its publication and verification gates pass.

## Job structure

- Use explicit Validate → Build → Test → Publish/Deploy dependencies where those stages apply.
  Do not add empty stages or serialize independent checks just to fit the sequence.
- Keep job IDs and check names stable during filename-only refactors. Changing a required check name
  requires checking branch rules and coordinating the change, not assuming the rule is absent.
- Invoke the repo's tasks (`mise run <task>`) for project checks/builds/tests. Actions install tooling,
  authenticate, cache, and transfer artifacts; avoid duplicating application scripts in YAML.
- Declare least-privilege permissions. Scope secrets and write permissions to jobs that use them.
- Include the workflow itself and its actual script/task/config inputs in path filters. A negative
  test must prove the gate rejects the intended fault, and inventory checks must reject zero matches.
- Cancel superseded validation runs when safe. Do not cancel publication or deployment midway through
  irreversible work, or a workflow one of them calls. Preserve existing trigger semantics when
  renaming; review behavior changes separately.
- Pin every `uses:` reference to the action's latest bare major tag (`@v4`); the full version tag
  only where the upstream publishes no major; never a SHA or branch (org ADR-0008). gau
  (gh-actions-updater) owns the updates: the `gh-actions-updater-lint-pins` poly hook gates them and
  xberg-io/actions `reusable-actions-bump.yml` moves them. Renovate and Dependabot never manage
  github-actions (org ADR-0019).
<!-- ~keep org ADR-0015 runs ai-rulez at latest on purpose. -->
<!-- ai-rulez-lint-ignore: AR021 ~keep -->
- Tasks run `npx -y ai-rulez@latest`: ai-rulez is never pinned (org ADR-0015). Workflows use
  `xberg-io/actions/setup-ai-rulez@v1`, which installs latest whatever `ai-rulez-version` says. The
  ai-rulez hook source in `poly.toml` uses the floating `revision = "v5"`; its hooks run on poly's
  `npm` channel, npx at the npm `latest` tag (org ADR-0017).

## Rename and release audit

Inventory filenames, display names, triggers, job dependencies, permissions, and all callers before editing.
Update local workflow calls, `workflow_run.workflows`, CLI commands, path filters, tasks, tests, documentation,
badges, and fixture copies together. Check external callers and identity-provider restrictions that may name
a workflow path; report inaccessible branch rules as unverified, not absent. Do not expand cloud IAM or bypass
required checks merely to make a rename work.

Validate parsed YAML and local call targets, run action-reference/workflow checks and the affected task suites,
and search active sources for obsolete paths. Keep archival references that genuinely describe history.
Review the final diff for accidental trigger, permission, secret, concurrency, or deployment changes.
Commit renames and their references as a coherent change; keep functional fixes independently reviewable.
