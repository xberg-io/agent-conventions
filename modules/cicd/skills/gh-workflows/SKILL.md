---
type: Playbook
title: Gh Workflows
description: "gh CLI conventions for PRs, issues, CI runs and releases: squash merges, issue links, monitoring and reruns, generated release notes. Use when opening or merging PRs, filing issues or watching CI."
x-ai-rulez:
  kind: skill
  id: gh-workflows
  metadata:
    name: gh-workflows
---

# GitHub Workflows

- PRs: gh pr create, merge with --squash (preferred), link to issues with "Fixes #123"
- Issues: gh issue create with labels and assignees, use templates from .github/ISSUE_TEMPLATE/
- CI: gh run list/view for monitoring, gh run rerun --failed for retries
- Releases: gh release create v1.2.3 --generate-notes
- Never force-merge without CI passing, never skip PR description
