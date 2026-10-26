# Start context with ai-rulez 5.7.0 scoped_fallback, 2026-10-26

Each consumer at the head of `claude/elegant-archimedes-jbbr15`, agent-conventions `757ee40`, ai-rulez 5.7.0 with `agents_md = true` and `[rules] scoped_fallback = "skill"`. Columns: [baseline](baseline-2026-10-25.md) → [5.6.3 pass](after-2026-10-25.md) (`agents_md = false`, glob rules withheld from Codex) → now. Codex now lists every glob-scoped rule as a skill (Codex does not gate skills by path), which is the content it previously lacked. Tokens are bytes / 3.9, uncalibrated.

| Repo | Claude: baseline → 5.6.3 pass → 5.7.0 | Codex: baseline → 5.6.3 pass → 5.7.0 | Glob rules for Codex | Leaks |
|---|---:|---:|---:|---:|
| xberg | 13,305 → 4,646 → 4,208 | 13,228 → 7,006 → 6,569 | 0 → 25 | 0 |
| xberg-enterprise | 13,355 → 5,319 → 4,924 | 13,297 → 5,272 → 6,314 | 0 → 22 | 0 |
| crawlberg | 11,987 → 4,387 → 3,949 | 11,834 → 5,316 → 5,116 | 0 → 18 | 0 |
| html-to-markdown | 11,585 → 4,514 → 4,075 | 11,507 → 4,447 → 5,376 | 0 → 19 | 0 |
| liter-llm | 9,276 → 4,312 → 3,874 | 9,197 → 4,245 → 5,068 | 0 → 20 | 0 |
| tree-sitter-language-pack | 11,728 → 4,352 → 3,914 | 11,645 → 4,280 → 5,182 | 0 → 21 | 0 |
| sceptre | 11,917 → 4,427 → 4,033 | 11,843 → 4,366 → 5,317 | 0 → 25 | 0 |
| alef | 12,026 → 3,456 → 3,188 | 11,948 → 4,647 → 4,518 | 0 → 23 | 0 |
| actions | 9,395 → 3,887 → 3,569 | 9,317 → 4,064 → 4,639 | 0 → 18 | 0 |
| **total** | 104,574 → 39,300 → 35,734 (-66%) | 103,816 → 43,643 → 48,099 (-54%) | | |

## Full report

| Repo | Preset | Start tokens | Root file | Inlined rules | Rules always/gated | Skills (gated, user-only) | Agents | Descr. > 250 | Leaks |
|---|---|---:|---:|---:|---|---|---:|---:|---:|
| xberg | claude | 4,208 | 8.8 KB | 22 | 0/25 | 52 (23, 0) | 11 | 0 | 0 |
| xberg | codex | 6,569 | 8.8 KB | 22 | 0/0 | 77 (0, 2) | 11 | 0 | 0 |
| xberg-enterprise | claude | 4,924 | 11.1 KB | 22 | 0/22 | 41 (10, 1) | 10 | 0 | 0 |
| xberg-enterprise | codex | 6,314 | 11.1 KB | 22 | 0/0 | 63 (0, 3) | 10 | 0 | 0 |
| crawlberg | claude | 3,949 | 8.8 KB | 22 | 0/18 | 41 (9, 5) | 11 | 0 | 0 |
| crawlberg | codex | 5,116 | 8.8 KB | 22 | 0/0 | 59 (0, 7) | 11 | 0 | 0 |
| html-to-markdown | claude | 4,075 | 8.8 KB | 22 | 0/19 | 39 (10, 0) | 11 | 0 | 0 |
| html-to-markdown | codex | 5,376 | 8.8 KB | 22 | 0/0 | 58 (0, 2) | 11 | 0 | 0 |
| liter-llm | claude | 3,874 | 8.7 KB | 22 | 0/20 | 34 (8, 0) | 11 | 0 | 0 |
| liter-llm | codex | 5,068 | 8.7 KB | 22 | 0/0 | 54 (0, 2) | 11 | 0 | 0 |
| tree-sitter-language-pack | claude | 3,914 | 8.8 KB | 22 | 0/21 | 34 (8, 0) | 11 | 0 | 0 |
| tree-sitter-language-pack | codex | 5,182 | 8.8 KB | 22 | 0/0 | 55 (0, 2) | 11 | 0 | 0 |
| sceptre | claude | 4,033 | 10.0 KB | 26 | 0/25 | 28 (6, 0) | 10 | 0 | 0 |
| sceptre | codex | 5,317 | 10.0 KB | 26 | 0/0 | 53 (0, 3) | 10 | 0 | 0 |
| alef | claude | 3,188 | 7.8 KB | 13 | 0/23 | 27 (8, 2) | 9 | 0 | 0 |
| alef | codex | 4,518 | 7.8 KB | 13 | 0/0 | 50 (0, 4) | 9 | 0 | 0 |
| actions | claude | 3,569 | 8.7 KB | 22 | 0/18 | 26 (7, 0) | 10 | 0 | 0 |
| actions | codex | 4,639 | 8.7 KB | 22 | 0/0 | 44 (0, 2) | 10 | 0 | 0 |

## xberg: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## xberg-enterprise: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## crawlberg: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## html-to-markdown: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## liter-llm: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## tree-sitter-language-pack: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

## sceptre: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `adr-immutability` 0.5 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB

## alef: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `repo-commits` 0.6 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `customer-data-boundary` 0.3 KB
- `commit-messages` 0.3 KB
- `secrets-handling` 0.3 KB

## actions: largest always-loaded rules

- `prove-the-check-fired` 1.8 KB
- `safe-git-operations` 0.8 KB
- `agent-workflow` 0.7 KB
- `verification-before-completion` 0.4 KB
- `commit-procedure` 0.4 KB
- `comment-discipline` 0.4 KB
- `communication-style` 0.3 KB
- `customer-data-boundary` 0.3 KB

