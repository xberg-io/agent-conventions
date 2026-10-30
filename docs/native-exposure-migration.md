# Native exposure migration

Checked on 2026-10-30 against the published ai-rulez 5.9.2 binary installed by mise (SHA256
`a65b63841e909acac4391f05043867b0ed2c8db88c8bc01fb7ab6f3fbe81e768`).

Keep `tools/context-evals/exposure.py` and the existing two-preset consumer gate until these gaps are resolved:

- `ai-rulez exposure --harness codex` fails with `unknown --harness "codex" (only claude)`.
- Native exposure omits Git-ignored instruction files. A standalone Git fixture with a `CLAUDE.md` and one
  unscoped `.claude/rules/*.md` reports 22 start tokens. Adding those same paths to `.gitignore` changes the
  report to zero without removing either file. The upstream reproduction is
  [ai-rulez issue 522](https://github.com/Goldziher/ai-rulez/issues/522).
- Against the current Xberg checkout, native exposure reports zero start tokens and only settings plus a deferred
  MCP server. The existing classifier, measuring the ai-rulez MCP schemas, reports 5,565 Claude and 6,040 Codex
  estimated tokens with the previous 3.9-byte estimator. These are current-checkout measurements; the historical
  2026-10-26 totals came from different generated artifacts and cannot establish parity today.

The validation workflow runs the latest ai-rulez release (org ADR-0015). Do not delete the existing classifier or move its
budgets into native `[exposure]` until both presets and ignored files are covered. Re-run the positive fixture,
its ignored-file negative control, and the same-checkout comparison before switching the consumer gate.
