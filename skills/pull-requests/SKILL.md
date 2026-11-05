---
name: pull-requests
description: "Pull request scope and text: title and description, claims as wide as the head commit, Closes only for a full fix, one change per PR, acceptance items, follow-up issues. Use when opening, writing or readying a PR."
# Content-Hash: blake3:d34447f7722544d217f17d16f0219a10849c4e04343735bf315336c1124c9de4
---

# Pull requests

## Claims

- Make every claim in the title, body, commits, changelog and comments exactly as wide as the head commit.
- Take each number from one measured run. Name the exact stage where a behaviour happens. Check a third-party fact
  at its source.
- Read the title and body again after every push, and correct each claim the push changed.

## Title and description

- The title follows the commit-messages rule: a conventional-commit type and scope, under 72 characters, imperative
  mood. It describes the whole change, not the last commit.
- The description says what changed and why, links the issue, and lists what the change does not cover.
- Describe the change in prose. Do not walk through the diff file by file, and do not list internal symbol names
  where a sentence says the same.

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
