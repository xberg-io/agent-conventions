# Round-zero attempt: 2026-11-06

**Stopped.** This attempt is not a recorded baseline, and no round-zero ledger entry was appended. Protocol choices are in
[study.toml](study.toml) (`rounds.round-zero-2026-11-06`) and
[ADR-0021](../../adrs/0021-judge-context-evaluations-with-opus-5-5-under-a-55-dollar-round-ceiling.md); counts and
costs are in [baseline-attempt-2026-11-06.json](baseline-attempt-2026-11-06.json).

| Consumer | Ref | Tune sessions | Collected | Failed | Judged (Opus 5.5) |
|---|---|---:|---:|---:|---:|
| Sceptre | `4828941` | 48 | 48 | 0 | 48 |
| Xberg | `7090e72` | 138 | 124 | 14 | 0 |

Subject `claude-sonnet-5-5`, three repeats, eight turns, 180-second timeout, one worker, hard-budget gateway
(protocol `hard-gateway-5`, policy `anthropic-standard-sonnet-opus-2026-11-06-1`, $55 ceiling), controller `b801c2e`
(source sha256 `056afc17`; it ran as `84a6bc3` before the rebase onto main), Claude Code 2.1.318, ai-rulez 5.10.0.
Judge prompt `judge-prompt-2`, rubric `rubric-2`, taxonomy 1, harness 6.

## Spend

The gateway ledger settled 613 requests for $10.7949498: 565 Sonnet 5.5 agent requests ($9.928) and 48 Opus 5.5
judge requests ($0.867). No request is uncertain or pending; the stop holds no reservation. Agent sessions averaged
$0.056 and Opus judge calls $0.018.

## Stop

In `xberg-neg-unit-test-not-benchmark` repeat 1 the model called `Edit`, which the session does not offer; the CLI
rejected it locally with its native unavailable-tool error, as designed. The gateway should have certified that as a
bounded `tool_unavailable` failure. It instead refused the follow-up request as a tool-profile mismatch and stopped the
round, so the remaining 13 Xberg sessions were refused before reaching the provider.

Cause: the live API now returns every model tool call with `caller: {"type": "direct"}`. The certification evidence
accepted only the older block keys, and the offline provider fixture omitted the field, so the real-CLI controls passed.
`57d32d8` accepts exactly the direct caller (any other caller still refuses), emits the field in the fixture, and the
real-CLI controls fail without the fix. The fixed controller certifies the stopped session's raw transcript.

## Not done

Judge validation, Xberg judging and the round-zero ledger entry need the remaining Xberg slots and validation in
the same round. The fix changes the controller policy hash, so continuing this ledger requires the reviewed
recovery and continuation procedure in [hard-budget.md](hard-budget.md); $44.21 of the $55 ceiling remains.
The failed Xberg sessions are the stopping session and 13 refused after it.

That procedure cannot serve this round yet. Recovery and the continuation header refused any ceiling above $25
(fixed in `86e9db1`), and the continuation compatibility proof (`continuation_compat.proof`) accepts only the
2026-10-30 controller transition: for `b801c2e` to `57d32d8` it fails with "unreviewed CLI classification tail".
No recovery was applied; the ledger is unchanged.

Raw transcripts, the ledger and per-run reports stay in the ignored polyrepo `reports/context-evals-round0-2026-11-06/`.
