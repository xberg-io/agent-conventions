---
status: accepted
date: 2026-11-06
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0018"]
---

# Judge context evaluations with Opus 5.5 under a 55 dollar round ceiling

## Context and Problem Statement

Issue #3 (section 9) leaves open which models run the dynamic evaluation and what one round may spend; issue #6 needs
both fixed before the first baseline. [ADR-0018](0018-bound-paid-evaluations-through-reserved-egress.md) priced only
the two Sonnet models and capped a round at $25. Every request reserves its worst case (the whole 1M-token context
plus 4,096 output tokens) before it is forwarded: $6.14 for Sonnet 5.5 and $12.28 for Opus 5.5. A full tune-split
round (186 agent sessions, judging and judge validation) was estimated at about $29 to $38, which neither fits $25
nor leaves room for the reservation of the next request.

## Decision Drivers

* The judge decides the primary quality metric, so it should be the strongest model the round can afford.
* The subject model must stay fixed across rounds so comparisons stay valid.
* The gateway's dollar guarantee from ADR-0018 must hold unchanged; only the priced models and the ceiling move.

## Considered Options

* Opus 5.5 judge, Sonnet 5.5 subject, $55 round ceiling.
* Sonnet 5.5 judge and subject within the $25 ceiling.
* Keep $25 per round but split agent runs and judging into separate ledgers.
* Lower the per-request reservation below the full context window.

## Decision Outcome

Chosen option: "Opus 5.5 judge, Sonnet 5.5 subject, $55 round ceiling", because it gives the strongest judge without
weakening the reservation protocol, and $55 covers the estimated spend plus one Opus reservation of headroom.

* Subject (agent) model: `claude-sonnet-5-5`, kept fixed across rounds.
* Primary judge: `claude-opus-5-5`; the independent second judge for `judge-validate` is `claude-sonnet-5-5`.
* Round ceiling: $55 (`gateway.MAX_BUDGET_USD`). Opus 5.5 is priced at its documented standard rates (checked
  2026-11-06): $4 input, $20 output, $5 five-minute and $8 one-hour cache writes, $0.20 cache reads per million
  tokens. The policy version is `anthropic-standard-sonnet-opus-2026-11-06-1`.

### Consequences

* Good, because judge verdicts come from the strongest current Opus while agent sessions stay comparable to the
  earlier Sonnet attempts.
* Good, because every ADR-0018 guarantee (atomic whole-request reservations, fail-closed stops, sandboxed egress)
  is unchanged.
* Bad, because an Opus request is admitted only while at most $42.72 has been spent, so a round that overruns its
  estimate stops before judging finishes.
* Bad, because the new policy hash makes earlier ledgers and rounds incomparable under resume and continuation.

### Confirmation

`tools/context-evals/test_gateway.py` checks the Opus reservation and settlement amounts, that unpriced models are
still refused, and that a $55 ledger admits requests only within the ceiling. `test_gateway_transport.py` runs the real
Claude CLI judge profile on `claude-opus-5-5` against a mocked provider through the gateway. `study.toml` records the
models and ceiling of each round.

## More Information

* Issues [#3](https://github.com/xberg-io/agent-conventions/issues/3) and
  [#6](https://github.com/xberg-io/agent-conventions/issues/6).
* [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).
