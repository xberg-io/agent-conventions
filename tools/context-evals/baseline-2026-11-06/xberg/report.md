# Context run xberg@7090e728b39a@2026-11-06T08:15:39Z

Repo `xberg` at `7090e728b39a140d4a8f6aabae5627bca5af39b2` (7090e728b39a), model `claude-sonnet-5-5`, split tune, 3 repeat(s). Judge `claude-opus-5-5`, prompt `judge-prompt-2`, rubric `rubric-2`.

Cells: mean [95% cluster-bootstrap interval] (cases).

All executed trials (invalid trials prevent baseline acceptance):

| Measure | overall | bindings | e2e-generator | infrastructure | xberg |
|---|---|---|---|---|---|
| executed trials | 138 | 27 | 18 | 9 | 84 |
| invalid trials | 0 | 0 | 0 | 0 | 0 |
| execution valid | True | True | True | True | True |
| completion | 135/138 (0.978) | 27/27 (1.000) | 18/18 (1.000) | 9/9 (1.000) | 81/84 (0.964) |
| expect_pass | 93/105 (0.886) | 21/24 (0.875) | 14/15 (0.933) | 3/3 (1.000) | 55/63 (0.873) |
| criteria_pass | 0/138 (ungraded) | 0/27 (ungraded) | 0/18 (ungraded) | 0/9 (ungraded) | 0/84 (ungraded) |

Conditional diagnostics (failed sessions excluded):

| Metric | overall | bindings | e2e-generator | infrastructure | xberg |
|---|---|---|---|---|---|
| skill_recall | 0.200 [0.000, 0.436] (30) | 0.167 [0.000, 0.500] (6) | 0.000 [0.000, 0.000] (3) | 1.000 [1.000, 1.000] (2) | 0.158 [0.000, 0.368] (19) |
| skill_precision | 0.304 [0.058, 0.617] (14) | 0.000 [0.000, 0.000] (3) | 0.417 [0.000, 0.750] (3) | 0.000 [0.000, 0.000] (2) | 0.500 [0.000, 1.000] (6) |
| leak_rate | 0.200 [0.057, 0.382] (45) | 0.333 [0.167, 0.444] (9) | 0.278 [0.033, 0.833] (6) | 0.667 [0.000, 1.000] (3) | 0.086 [0.000, 0.286] (27) |
| answer_leak_rate | 0.141 [0.039, 0.276] (45) | 0.074 [0.000, 0.222] (9) | 0.167 [0.000, 0.300] (6) | 0.667 [0.500, 1.000] (3) | 0.099 [0.000, 0.284] (27) |
| over_ask_rate | 0.008 [0.000, 0.029] (41) | 0.000 [0.000, 0.000] (8) | 0.000 [0.000, 0.000] (6) | 0.000 [0.000, 0.000] (3) | 0.014 [0.000, 0.053] (24) |
| under_ask_rate | 1.000 [1.000, 1.000] (2) | 1.000 [1.000, 1.000] (1) | n/a | n/a | 1.000 [1.000, 1.000] (1) |
| expect_pass_rate | 0.886 [0.802, 0.964] (35) | 0.875 [0.714, 1.000] (8) | 0.933 [0.750, 1.000] (5) | 1.000 [1.000, 1.000] (1) | 0.873 [0.747, 1.000] (21) |
| criteria_pass_rate | n/a | n/a | n/a | n/a | n/a |
| start_tokens | 10901.993 [10311.389, 11348.060] (45) | 10304.815 [9801.333, 11010.606] (9) | 12041.389 [10921.833, 14280.500] (6) | 9801.778 [9800.667, 9802.333] (3) | 10970.099 [9816.035, 11722.321] (27) |
| cost_usd | 0.059 [0.052, 0.068] (45) | 0.061 [0.042, 0.077] (9) | 0.059 [0.048, 0.082] (6) | 0.044 [0.042, 0.049] (3) | 0.060 [0.052, 0.073] (27) |
| sessions (failed) | 138 (3) | 27 (0) | 18 (0) | 9 (0) | 84 (3) |
