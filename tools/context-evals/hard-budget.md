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

A terminal CLI `error_max_turns` remains a failed evaluation session with its original return code, transcript
and turn limit. It alone does not stop the financial round when its exact known terminal schema and initialized
model/tool profile match, every request in the current epoch is settled, and this controller owns settled
requests. Existing stops, unknown failures, timeouts, malformed terminals, profile drift and unsettled or
uncertain billing still stop the round. This classification does not turn a failed task into a successful answer.

Reports preserve the existing success-conditional diagnostics and add `all_trials` counts and rates. A
controller-certified bounded failure contributes zero to completion, applicable expectation and criteria rates
while retaining its error and unjudged per-criterion values. Unknown, profile, billing and infrastructure failures
invalidate execution eligibility; they cannot become model misses or disappear into an apparently valid baseline.
Criteria rates remain ungraded when applicable completed trials lack validated verdicts. Reported execution
eligibility alone does not satisfy the separate complete-corpus and judge-validity gates. Old records default to
uncertified, and legacy record schemas cannot claim a valid primary baseline; the error string alone cannot
certify a failed trial.


## Immutable continuation of a reviewed collection

`continue` is a separate operation from `run --resume`. Its SHA-bound manifest enumerates every original and
remaining `(consumer, case, repeat)` tuple. Duplicate, missing, unplanned or rerun original trials are refused.
Original run metadata, case snapshots, context identity and raw/metadata pairs remain in place, hash-checked;
derived records retain their original policy, epoch, request IDs and source run. A separately hash-bound
adjudication can certify the observed maximum-turn nonanswer only after its exact transcript profile and fully
settled, serialized request slice are verified. It remains a failed trial with unjudged criterion values.

The operator prepares the manifest with `continuation.make_draft`, loading the corpus from the harness's absolute
`HERE / "cases"` path. The reviewed source commit, old/new admission policies, original round identity, immutable
financial history and identical pricing/context/output bounds must all match. The exact approved transition is
checked independently of its audit-chain hash. Model-facing command, prompt, sandbox, provider and judge ASTs
must match the original source, allowing only the declared post-execution classification and metadata changes.
Freshly generated context, CLI and generator identities must match before any model request. The only varying
command paths follow the anchored worktree and temporary empty-MCP templates; arbitrary normalization is refused.

After a separately approved same-ledger recovery, collect each consumer into a fresh directory:

```sh
mise run context:eval -- --hard-budget --budget-ledger ORIGINAL_LEDGER --budget-usd 25 continue \
  --manifest REVIEWED_MANIFEST --manifest-sha256 REVIEWED_SHA256 --repo CONSUMER --out FRESH_RUN
```

The manifest supplies the original model, turn limit, timeout, repeats and serial execution. `run --resume` cannot
drop this manifest and recollect inherited trials. Each new session records its owning epoch, policy, actor and
exact new request IDs; admitted trials require settled accounting. Judging verifies the entire derived dataset and source provenance first; cached
verdicts and validity reports must match both session provenance and the continuation manifest. Reports mask
unvalidated or stale criteria without rewriting original artifacts. `continue-report --manifest ...
--manifest-sha256 ... --run XBERG_RUN --run SCEPTRE_RUN --out NEW_REPORT` verifies the full planned cohort and reads
the financial ledger without changing it. Collection completeness and execution validity remain separate from
judge validity and criterion availability.

`all_trials` is the primary baseline metric namespace. The existing `metrics` namespace and paired comparison
helpers retain their success-conditional diagnostic semantics. Primary criterion rates stay ungraded until every
applicable answered criterion is validated; certified bounded nonanswers contribute zero. No continuation,
financial migration, new round or paid request follows automatically from producing a manifest or report.
