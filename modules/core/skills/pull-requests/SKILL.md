---
type: Playbook
title: Pull Requests
description: "Pull request scope and text: claims as wide as the head commit, Closes only for a full fix, one change per PR, acceptance items, follow-up issues. Use when opening, writing or readying a PR."
x-ai-rulez:
  kind: skill
  id: pull-requests
  metadata:
    name: pull-requests
---

# Pull requests

## Claims

- Make every claim in the title, body, commits, changelog and comments exactly as wide as the head commit.
- Take each number from one measured run. Name the exact stage where a behaviour happens. Check a third-party fact
  at its source.
- Read the title and body again after every push, and correct each claim the push changed.

## Issue links

Write `Closes #n` only for an issue the change fully fixes. Otherwise write `Refs #n`.

## Scope

- Keep one logical change per pull request. Split separable changes, such as unrelated fixes or unrelated golden
  files.
- Land two halves that are unsafe alone as one unit.

## Before it leaves draft

Deliver every acceptance item that the issue names: each site, the tests, and each comparison or measurement it asks
for. If an item remains, list it in the body.

## Before merge

Open an issue for every gap or sibling site that the pull request discloses and does not fix, including an upstream
gap that it works around.
