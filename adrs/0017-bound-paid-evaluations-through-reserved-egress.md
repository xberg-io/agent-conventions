---
status: proposed
date: 2026-10-30
decision-makers: ["xberg-io maintainers"]
---

# Bound paid evaluations through reserved egress

## Context and Problem Statement

The context evaluation's approved fresh round has a $25 total ceiling. Claude CLI dollar limits and prospective
per-session reservations cannot guarantee that ceiling across parallel agents, judges, retries and ambiguous
failures. A prior attempt also advertised more tools than intended, so routing must verify the actual CLI and
API profiles before paying for a request.

## Considered Options

* Retain soft CLI limits and reconcile cost after each session.
* Require an external provider account spending control.
* Reserve a conservative request maximum in an atomic ledger and restrict paid egress to that gateway.

## Decision Outcome

Chosen option: "Reserve a conservative request maximum in an atomic ledger and restrict paid egress to that
gateway", because it can enforce the approved round's documented standard-price bound locally without assuming
that estimated input-token counts or CLI dollar flags are strict limits. The protocol is opt-in and limited to
two dated Sonnet pricing profiles; unsupported platforms and unknown billing features fail closed.

### Consequences

* Good, because every request reserves its entire possible documented charge before forwarding, including
  concurrent agent and judge traffic. Uncertain requests retain their reservation and stop the round.
* Good, because exact tool initialization, API schemas, isolated credentials and operating-system network/file
  controls are verified without making hosted model calls.
* Bad, because whole-context reservations can stop the campaign below $25 and leave an honestly partial result.
* Bad, because the first implementation supports macOS confinement only and must be re-reviewed when prices,
  CLI protocol or execution policy changes. A local mock does not prove provider acceptance or answer quality.

### Confirmation

`mise run context:test` collects the existing harness tests plus the new policy, transport, sandbox, real-CLI
mock-provider and harness-routing tests in `tools/context-evals/test_gateway*.py`. Negative controls remove the
file boundary, remove the loopback permission and advertise Bash before forwarding. They must fail for those
specific reasons. `tools/context-evals/hard-budget.md` records the price bound, immutable protocol identity and
approved-round procedure. No paid use precedes fresh independent review of those checks.
