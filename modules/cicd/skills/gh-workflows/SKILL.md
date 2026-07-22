---
name: gh-workflows
description: Conventions for using the gh CLI to manage PRs, issues, CI runs, and releases — squash merges, issue linking, monitoring and reruns, generated release notes. Load when creating or merging PRs, filing issues, monitoring/rerunning CI, or cutting a GitHub release.
---

# GitHub Workflows

- PRs: gh pr create, merge with --squash (preferred), link to issues with "Fixes #123"
- Issues: gh issue create with labels and assignees, use templates from .github/ISSUE_TEMPLATE/
- CI: gh run list/view for monitoring, gh run rerun --failed for retries
- Releases: gh release create v1.2.3 --generate-notes
- Never force-merge without CI passing, never skip PR description
