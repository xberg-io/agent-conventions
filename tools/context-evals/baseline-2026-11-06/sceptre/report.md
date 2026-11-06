# Context run sceptre@4828941cb158@2026-11-06T08:02:00Z

Repo `sceptre` at `4828941cb15812d95251dfa57e689116ce59c859` (4828941cb158), model `claude-sonnet-5-5`, split tune, 3 repeat(s). Judge `claude-opus-5-5`, prompt `judge-prompt-2`, rubric `rubric-2`.

Cells: mean [95% cluster-bootstrap interval] (cases).

All executed trials (invalid trials prevent baseline acceptance):

| Measure | overall | sceptre |
|---|---|---|
| executed trials | 48 | 48 |
| invalid trials | 0 | 0 |
| execution valid | True | True |
| completion | 48/48 (1.000) | 48/48 (1.000) |
| expect_pass | 31/39 (0.795) | 31/39 (0.795) |
| criteria_pass | 32.5/48 (ungraded) | 32.5/48 (ungraded) |

Conditional diagnostics (failed sessions excluded):

| Metric | overall | sceptre |
|---|---|---|
| skill_recall | n/a | n/a |
| skill_precision | 1.000 [1.000, 1.000] (1) | 1.000 [1.000, 1.000] (1) |
| leak_rate | 1.000 [1.000, 1.000] (16) | 1.000 [1.000, 1.000] (16) |
| answer_leak_rate | 0.021 [0.021, 0.021] (16) | 0.021 [0.021, 0.021] (16) |
| over_ask_rate | 0.000 [0.000, 0.000] (15) | 0.000 [0.000, 0.000] (15) |
| under_ask_rate | n/a | n/a |
| expect_pass_rate | 0.795 [0.795, 0.795] (13) | 0.795 [0.795, 0.795] (13) |
| criteria_pass_rate | 0.833 [0.833, 0.833] (13) | 0.833 [0.833, 0.833] (13) |
| start_tokens | 10232.021 [10232.021, 10232.021] (16) | 10232.021 [10232.021, 10232.021] (16) |
| cost_usd | 0.056 [0.056, 0.056] (16) | 0.056 [0.056, 0.056] (16) |
| sessions (failed) | 48 (0) | 48 (0) |
