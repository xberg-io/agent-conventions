# Judge validity

Prompt `judge-prompt-2` / `judge-prompt-independent-2`, rubric `rubric-2`. Models: {'primary': 'claude-opus-5-5', 'secondary': 'claude-sonnet-5-5'}.

Mutation tests: TPR 1.00 over 46 originals (min 0.9), TNR 0.79 over 146 mutants (min 0.8). Judge valid: no.

| Mutation | TNR | Mutants |
|---|---:|---:|
| drop-fact | 0.96 | 46 |
| swap-domain | 0.38 | 21 |
| tool-deflection | 1.00 | 46 |
| wrong-path | 0.52 | 33 |

## Agreement (kappa >= 0.6, at least 4 decided items)

| Criterion | Kappa | Decided / items | Valid |
|---|---:|---:|---|
| `xberg-api-no-extract-url-route/batch-is-async` | 1.00 | 6 / 6 | yes |
| `xberg-api-no-extract-url-route/url-is-field` | 1.00 | 6 / 6 | yes |
| `xberg-ask-fix-tests/which` | 1.00 | 5 / 5 | yes |
| `xberg-ask-stale-results/cache-or-ask` | 1.00 | 5 / 5 | yes |
| `xberg-benchmark-workflow-dispatch-only/dispatch-only` | 1.00 | 4 / 4 | yes |
| `xberg-bindings-ask-broken/which-binding` | 0.17 | 5 / 5 | no |
| `xberg-bindings-extractor-alef-skip/global-abort` | 1.00 | 6 / 6 | yes |
| `xberg-bindings-extractor-alef-skip/on-struct` | 0.57 | 6 / 6 | no |
| `xberg-bindings-ffi-trait-default/default-fallback` | 1.00 | 3 / 3 | no |
| `xberg-bindings-ffi-trait-default/json` | 1.00 | 3 / 3 | no |
| `xberg-bindings-generator-bug-owner/alef-owns` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-generator-bug-owner/order` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-handfix-generated/fix-source` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-handfix-generated/generated` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-java-panama/jni-owner` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-java-panama/panama` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-neg-release-not-enterprise/alef-sync` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-neg-release-not-enterprise/no-hand-edit` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-no-alef-format/poly` | 1.00 | 5 / 5 | yes |
| `xberg-bindings-non-exhaustive-e0639/derive-default` | 1.00 | 3 / 3 | no |
| `xberg-bindings-non-exhaustive-e0639/struct-literal` | 1.00 | 3 / 3 | no |
| `xberg-config-duplicate-tesseract-default/change-both` | 1.00 | 5 / 5 | yes |
| `xberg-config-duplicate-tesseract-default/two-structs` | 1.00 | 5 / 5 | yes |
| `xberg-crate-structure-native-pdf-log-target/constant` | 1.00 | 5 / 5 | yes |
| `xberg-crate-structure-new-member-docker/allowlist` | 1.00 | 5 / 5 | yes |
| `xberg-crate-structure-new-member-docker/verify-task` | 1.00 | 5 / 5 | yes |
| `xberg-e2e-add-fixture/fixture-json` | 1.00 | 5 / 5 | yes |
| `xberg-e2e-add-fixture/regen` | 1.00 | 5 / 5 | yes |
| `xberg-e2e-config-table/crates-e2e` | 0.50 | 4 / 4 | no |
| `xberg-e2e-config-table/languages` | 1.00 | 4 / 4 | yes |
| `xberg-e2e-edit-generated-test/generated` | 0.62 | 5 / 5 | yes |
| `xberg-e2e-no-generator-dir/not-here` | 1.00 | 5 / 5 | yes |
| `xberg-e2e-single-language/lang-task` | 1.00 | 5 / 5 | yes |
| `xberg-e2e-verify-freshness/verify-task` | 1.00 | 4 / 4 | yes |
| `xberg-either-bump-version/task` | 1.00 | 3 / 3 | no |
| `xberg-feature-parity-windows-target/add-to-windows` | 1.00 | 4 / 4 | yes |
| `xberg-feature-parity-windows-target/names-check` | 1.00 | 4 / 4 | yes |
| `xberg-feature-sevenz-opt-level/keep-opt-level-1` | 1.00 | 3 / 3 | no |
| `xberg-infra-chart-appversion-image/image-exists` | 1.00 | 5 / 5 | yes |
| `xberg-infra-chart-version-sync/script-owns` | 1.00 | 6 / 6 | yes |
| `xberg-infra-neg-chart-not-enterprise/chart-values` | 0.62 | 5 / 5 | yes |
| `xberg-neg-unit-test-not-benchmark/unit-scope` | 0.62 | 5 / 5 | yes |
| `xberg-nohint-long-extraction-route/async` | 1.00 | 4 / 4 | yes |
| `xberg-ocr-font-size-comparison/different-quantities` | 0.67 | 6 / 6 | yes |
| `xberg-ocr-font-size-comparison/font-info` | 1.00 | 6 / 6 | yes |
| `xberg-office-security-budget/alef-skip` | 1.00 | 5 / 5 | yes |
| `xberg-office-security-budget/budget` | 0.62 | 5 / 5 | yes |
| `xberg-pdfium-capability-gap/narrower` | 1.00 | 4 / 4 | yes |
| `xberg-pdfium-capability-gap/native` | 1.00 | 4 / 4 | yes |
| `xberg-pipeline-cache-docker-build-id/build-id-in-key` | 1.00 | 4 / 4 | yes |
| `xberg-pipeline-cache-docker-build-id/empty-build-id` | 1.00 | 4 / 4 | yes |
| `xberg-pipeline-fallback-parsing-error/eligible-errors` | 1.00 | 6 / 6 | yes |
| `xberg-pipeline-fallback-parsing-error/names-predicate` | 1.00 | 6 / 6 | yes |
| `xberg-pipeline-fallback-parsing-error/not-a-bug` | 1.00 | 6 / 6 | yes |
| `xberg-plugin-internal-extractor-trait/collision` | 1.00 | 5 / 5 | yes |
| `xberg-plugin-internal-extractor-trait/internal` | 1.00 | 5 / 5 | yes |
| `xberg-release-version-sync/check` | 1.00 | 4 / 4 | yes |
| `xberg-release-version-sync/integrations` | 1.00 | 4 / 4 | yes |
| `xberg-release-version-sync/sync` | 1.00 | 4 / 4 | yes |
| `xberg-rule-async-select/timeout` | 1.00 | 4 / 4 | yes |
| `xberg-rule-changelog-ci-entry/no-entry` | 1.00 | 3 / 3 | no |
| `xberg-rule-extraction-safety-max-pages/max-pages` | 1.00 | 5 / 5 | yes |
| `xberg-rule-measurement-ratio-vs-count/absolute` | 1.00 | 3 / 3 | no |
| `xberg-rule-measurement-ratio-vs-count/distribution` | 1.00 | 3 / 3 | no |
| `xberg-rule-partner-corpus-ids/names` | 1.00 | 3 / 3 | no |
| `xberg-rule-partner-corpus-ids/opaque-id` | 1.00 | 3 / 3 | no |
| `xberg-test-corpus-no-include-bytes/helper` | 1.00 | 3 / 3 | no |
| `xberg-test-corpus-no-include-bytes/no-include` | 1.00 | 3 / 3 | no |
| `xberg-test-corpus-worktree-control/fix` | 1.00 | 3 / 3 | no |
| `xberg-test-corpus-worktree-control/vacuous` | 1.00 | 3 / 3 | no |
| `xberg-ts-integration-lockfiles/own-lockfile` | 1.00 | 5 / 5 | yes |
| `xberg-wasm-html-limit/limit` | 1.00 | 5 / 5 | yes |
