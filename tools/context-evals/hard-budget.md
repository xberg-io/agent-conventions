# Bounded evaluation egress

Harness 5 adds `--hard-budget` for `run`, `judge` and `judge-validate`. It reserves the worst-case documented
standard API charge in one SQLite ledger **before** forwarding each Messages request. This protocol caps each
request at 4,096 output tokens; it is a new study protocol, not a comparable continuation of older runs.
The historical soft-budget attempt stays invalid.

A real-provider attempt stopped with uncertain accounting; it did not establish a valid baseline. The transport
now derives documented beta headers from validated request fields and records only bounded HTTP status,
provider request ID, error type and redacted SSE/usage-presence metadata. It never logs credentials, request
prompts, response text or provider error messages. Offline mocked usage remains synthetic: a passing local
contract proves routing and accounting, not provider acceptance or model quality. Fresh review precedes paid use.

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

The same sandbox denies writes globally, allowing only the isolated session home (including its private
TMPDIR/config/cache) and `/dev/null`. The case worktree, controller source and budget ledger remain read-only.
Direct and symlink writes are denied; new hardlinks are denied and preexisting writable-home hardlinks are
refused before launch. Generic Mach/AppleEvent brokers and privileged task-port access are also denied so
project hooks cannot delegate protected-file access to another process. Process information is restricted to
the sandboxed process itself: an actual `sysctl(KERN_PROCARGS2)` fixture proves a sibling's dummy API key cannot
be recovered from its environment, while self inspection remains available.

The sandbox denies reads from the original home directory, with narrow exceptions for the session
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
  --split tune --repeats 3 --jobs 1 --out ../reports/fresh-round/xberg
```

Use the **same** ledger for Sceptre, primary judging and independent judge validation. `--hard-budget` and
`--allow-soft-budget` are mutually exclusive. The legacy `probe.py` interface is outside this hard-budget
execution path; do not charge probes to this round through its soft-budget interface.

`run.json` records harness 5, the price/output policy, and a digest of the gateway implementation. A separate
`budget_round` records the ledger's immutable UUID, total ceiling and canonical path. Both repositories share
that identity; resume and paid judging reject any attempt to switch to a new ledger. Verdicts and validity
reports must match the same round. Different independently approved rounds can still be compared when their
execution protocols match. Use one paid worker for this round: overlapping conservative reservations can
otherwise stop admission before earlier calls settle.

Resume,
comparison and paid judging reject a different execution policy. An old report cannot validate a new round. Record the committed source SHA, CLI version, models,
rubric/taxonomy versions and final ledger snapshot alongside the round. Recheck the official pricing before
using this dated policy; it assumes those documented prices, not undisclosed or future account-specific charges.


## Reviewed recovery within the same ceiling

A controller-policy change is refused by normal ledger construction. `gateway.recover_round` is a separate,
explicit operator action; it is never called by a run, an HTTP request, a retry or constructor. The caller must
supply the exact original round identity, previous policy manifest and approval binding the old/new policy
hashes and exact prior admission epoch/audit hash to a reviewed Git commit. A legacy import uses an explicit
`previous_admission: null`; subsequent recoveries bind the observed epoch and audit hash inside the transaction.
Every controller file must byte-match that immutable commit. This is a trusted operator workflow: the audit hash chain records approval; it does not grant authorization by itself.

Recovery preserves the original UUID, canonical ledger path, $25 ceiling, every request/charge and the legacy
stop/policy fields. An uncertain $6.14096 reservation remains fully charged against admission. Pricing, context
and output bounds must be canonically identical. Pending requests block the transaction. An append-only epoch
records the old and new manifests, approval and hash chain before the active admission cursor advances.

Database triggers make the round identity and retained nonempty legacy stop immutable, including to old
controllers. Legacy controllers remain fenced by that permanently retained stop. New controllers recheck their
captured epoch and policy atomically at every reservation and sum charges across all epochs. Immutable request
bindings include epoch and controller actor; settlement can reduce only that actor's own pending ticket.
Historical uncertain rows cannot be rewritten. Stops preserve their first cause; later refusals increment a
separate counter. A crash or failed check rolls back the complete transition.

After an independently reviewed transition, any permitted continuation uses fresh output directories with the
same original repository refs and case corpus. Old runs, transcripts and provenance remain unchanged. No
transition or paid continuation is implied by these offline tests; both require the reviewed operator action.
