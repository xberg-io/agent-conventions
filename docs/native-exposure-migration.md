# Native exposure migration

Rechecked on 2026-10-30 against published ai-rulez 5.9.6 (SHA256
`9c9c64d87207f6de6be2c03f9faab1386a75fc31810db9b32acd661737db609e`). Local evidence is retained under the
polyrepo's ignored `reports/native-exposure-5.9.6-2026-10-30/`, including the independent import-budget control.

[Issue 522](https://github.com/Goldziher/ai-rulez/issues/522) is closed. The ignored-instruction regression is fixed:
the tracked and Git-ignored fixtures both report 22 start tokens, and a one-token budget rejects the ignored
fixture with exit 2. The earlier 5.9.2 ignored-file failure is historical, not a current migration blocker.

Keep `tools/context-evals/exposure.py` and the existing two-preset consumer gate until these remaining gaps are resolved:

- `ai-rulez exposure --harness codex` still fails with `unknown --harness "codex" (only claude)`.
- Native `--areas` rejects the existing taxonomy's `names`, `domain`, `repos` and `accept` schema. A reviewed
  translation and same-checkout parity proof are needed before replacing the current classifier.
- `CLAUDE.md` imports are omitted from start-budget enforcement. With budget 50, the fixture importing AGENTS.md
  reports 14 tokens and exits 0; the same instruction text inlined into CLAUDE.md reports 883 and exits 2.
  [Issue 532](https://github.com/Goldziher/ai-rulez/issues/532) tracks this remaining false-green path.

The validation workflow runs the latest ai-rulez release (org ADR-0015). Do not remove the existing classifier or
move its budgets into native `[exposure]` until both presets, imported instructions and taxonomy semantics are
covered. Re-run tracked/ignored positive fixtures, import-versus-inline budget controls and the same-checkout
comparison before switching the consumer gate. Historical totals from different generated artifacts cannot
establish current parity.
