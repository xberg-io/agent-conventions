---
name: gh-workflows
description: "gh CLI conventions for PRs, issues, CI runs and releases: squash merges, issue links, monitoring and reruns, generated release notes. Use when opening or merging PRs, filing issues or watching CI."
# Content-Hash: blake3:c4149f5792535d49a84d0dd488ef1f659d3325c19b6a1901df24c1c5bdff4889
---

# GitHub Workflows

- PRs: gh pr create, merge with --squash (preferred), link to issues with "Fixes #123"
- Issues: gh issue create with labels and assignees, use templates from .github/ISSUE_TEMPLATE/
- CI: gh run list/view for monitoring, gh run rerun --failed for retries
- Releases: gh release create v1.2.3 --generate-notes
- Never force-merge without CI passing, never skip PR description
