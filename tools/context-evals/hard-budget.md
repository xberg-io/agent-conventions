# Bounded evaluation egress

Harness 5 adds `--hard-budget` for `run`, `judge` and `judge-validate`. It reserves the worst-case documented
standard API charge in one SQLite ledger **before** forwarding each Messages request. This protocol caps each
request at 4,096 output tokens; it is a new study protocol, not a comparable continuation of older runs.
The historical soft-budget attempt stays invalid.

No real-provider traffic has been used to verify this implementation. The real installed Claude CLI is tested
against a local mocked provider; its usage and costs in those tests are synthetic. A successful offline contract
proves routing and accounting, not provider acceptance or model quality. A fresh review must precede paid use.

## Price bound

The 2026-10-30 policy supports only `claude-sonnet-5-5` and `claude-sonnet-5`: one million context tokens,
$2 per million uncached input tokens, $10 output, $2.50 five-minute cache writes and $4 one-hour cache writes.
Cache reads cost $0.10 and $0.20 respectively. These are documented standard, global-inference prices;
fast mode, priority tiers, US-only routing, server tools, images, documents and unknown features are refused.
See [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview),
[Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/overview) and
[API pricing](https://platform.claude.com/docs/en/about-claude/pricing).

The [token-count endpoint](https://platform.claude.com/docs/en/build-with-claude/token-counting) is an estimate,
so it cannot establish a strict input bound. Instead each reservation independently charges the full context
ceiling for uncached input, cache creation at the one-hour rate, and cache reads, plus the clamped output maximum.
The [Messages API](https://platform.claude.com/docs/en/api/messages/create) defines `max_tokens` as an absolute
output maximum, including thinking. The resulting reservations are $6.14096 and $6.24096 per request. This
intentionally overcounts input categories; it can stop a round far below its $25 cash ceiling.

Every charge uses integer nanodollars. Valid terminal provider usage replaces a reservation with its actual
standard usage charge. Missing, decreasing, negative, noninteger, overflowing or unknown usage, incomplete
streams, transport failures and uncertain responses retain the entire reservation and stop the shared round.
A pending request whose owner process has disappeared also stops the round. No automatic provider retries,
redirects, budget increases or uncertain-reservation releases are permitted. Two processes share the same
atomic ledger, including agent and judge requests. A historical soft-budget ledger cannot be reused.

## Process boundary

Only the gateway retains the provider key. Each CLI receives a random local credential, fresh HOME and
`CLAUDE_CONFIG_DIR`, strict empty MCP configuration and the exact agent or judge tool profile. Initialization
must advertise the expected tools and model before a request can be forwarded. API tool schemas must also
match: agent `Read`, `Glob`, `Grep`, `Skill`; judge none. Tool search is disabled to remove the CLI's otherwise
advertised-on-the-wire deferred placeholder. Nonessential traffic is disabled and fallback models are pinned.

On macOS, `sandbox-exec` denies network access except TCP to the gateway's exact IPv4 loopback port. A live
positive connection and three denied connections establish the boundary: another IPv4 loopback port,
IPv6 loopback on the same port, and an external address. A denial must be EPERM/EACCES, not a timeout or
connection refusal. Other platforms currently refuse hard execution.

The same sandbox denies reads from the original home directory, with narrow exceptions for the session
worktree, its temporary home and exact CLI/Python runtime directories. Environment files and common private-key
extensions remain denied inside the worktree. Offline fixture tests prove credential-file reads, secret-path
glob lookup and symlink traversal fail while AGENTS.md remains readable. Directory entry names are not secret
contents: a wildcard can enumerate a readable worktree, but cannot read a denied target. The disposable Git
worktree also excludes the original checkout's untracked `.env`. No real credential file is inspected in these tests.

Requests are bounded to 4 MiB and provider responses/CLI output to 16 MiB with finite timeouts. The upstream is
fixed to TLS `api.anthropic.com:443/v1/messages`, independent of proxy environment variables. Only explicit
known protocol beta headers are supplied; inbound CLI headers are never forwarded. Request bodies, credentials
and answers are not logged by the gateway. Sensitive transcripts remain in ignored reports.

## Execution and provenance

Use a fresh ledger and fresh output directories for the approved round. For example, after review:

```sh
mise run context:eval -- --hard-budget --budget-ledger ../reports/fresh-round/round.sqlite3 \
  --budget-usd 25 run --repo ../xberg --ref main --model claude-sonnet-5-5 \
  --split tune --repeats 3 --jobs 2 --out ../reports/fresh-round/xberg
```

Use the **same** ledger for Sceptre, primary judging and independent judge validation. `--hard-budget` and
`--allow-soft-budget` are mutually exclusive. The legacy `probe.py` interface is outside this hard-budget
execution path; do not charge probes to this round through its soft-budget interface.

`run.json` records harness 5, the price/output policy, and a digest of the gateway implementation. Resume,
comparison and paid judging reject a different execution policy. Verdicts and validity reports carry that same
policy, so an old report cannot validate a new round. Record the committed source SHA, CLI version, models,
rubric/taxonomy versions and final ledger snapshot alongside the round. Recheck the official pricing before
using this dated policy; it assumes those documented prices, not undisclosed or future account-specific charges.
