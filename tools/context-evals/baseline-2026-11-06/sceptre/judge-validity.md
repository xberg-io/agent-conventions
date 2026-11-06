# Judge validity

Prompt `judge-prompt-2` / `judge-prompt-independent-2`, rubric `rubric-2`. Models: {'primary': 'claude-opus-5-5', 'secondary': 'claude-sonnet-5-5'}.

Mutation tests: TPR 1.00 over 16 originals (min 0.9), TNR 0.85 over 47 mutants (min 0.8). Judge valid: yes.

| Mutation | TNR | Mutants |
|---|---:|---:|
| drop-fact | 0.94 | 16 |
| swap-domain | 0.80 | 5 |
| tool-deflection | 1.00 | 16 |
| wrong-path | 0.50 | 10 |

## Agreement (kappa >= 0.6, at least 4 decided items)

| Criterion | Kappa | Decided / items | Valid |
|---|---:|---:|---|
| `sceptre-adr-reverse-decision/new-adr` | 1.00 | 4 / 4 | yes |
| `sceptre-adr-reverse-decision/status` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-accelerator-fallback/reject` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-accelerator-fallback/table` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-candle-architecture/candle` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-candle-architecture/network-kind` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-direct-ort/pure-rust` | 1.00 | 4 / 4 | yes |
| `sceptre-backend-seam-direct-ort/seam` | 1.00 | 4 / 4 | yes |
| `sceptre-code-style-config-precedence/order` | 1.00 | 4 / 4 | yes |
| `sceptre-code-style-config-precedence/typo` | 1.00 | 4 / 4 | yes |
| `sceptre-code-style-stdout/denied` | 1.00 | 3 / 3 | no |
| `sceptre-code-style-stdout/tracing` | 1.00 | 3 / 3 | no |
| `sceptre-crate-layout-flag-mapping/overrides` | 1.00 | 5 / 5 | yes |
| `sceptre-mcp-add-parameter/optional` | 1.00 | 5 / 5 | yes |
| `sceptre-mcp-add-parameter/order` | 1.00 | 5 / 5 | yes |
| `sceptre-neg-ocr-accuracy/craft-knobs` | 1.00 | 3 / 3 | no |
| `sceptre-neg-release/dry-run` | 1.00 | 5 / 5 | yes |
| `sceptre-neg-release/tag` | 1.00 | 5 / 5 | yes |
| `sceptre-neg-tests-no-e2e/golden` | 1.00 | 5 / 5 | yes |
| `sceptre-nohint-mcp-subcommand/mcp` | 1.00 | 5 / 5 | yes |
| `sceptre-ocr-ctc-blank/blank` | 1.00 | 5 / 5 | yes |
| `sceptre-ocr-ctc-blank/height` | 1.00 | 5 / 5 | yes |
| `sceptre-ocr-detection-defaults/values` | 1.00 | 3 / 3 | no |
| `sceptre-ocr-model-cache/hf-cache` | 1.00 | 4 / 4 | yes |
| `sceptre-ocr-model-cache/verified` | 1.00 | 4 / 4 | yes |
| `sceptre-rust-checks-test-gate/release-gate` | 1.00 | 4 / 4 | yes |
| `sceptre-rust-checks-test-gate/upgrade` | 1.00 | 4 / 4 | yes |
