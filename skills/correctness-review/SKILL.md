---
name: correctness-review
description: "Invariants a code review keeps finding: every site, fail closed, no silent loss, bounds, safe writes, reuse, compatible API changes. Use when writing or reviewing a code change."
# Content-Hash: blake3:35efe746017a1d70de6394fea7b23baa32567d10d2443f5eefbe44dc1f906227
---

# Correctness review

The correctness rule (core) points here. Check each invariant the diff can reach. The sections run from the most
frequent finding to the least.

## Every site

- List the sites before you edit: routes, backends, bindings, success and failure paths, public views, inventories,
  and the paths that rebuild the configuration. Change each one in the same change.
- Derive a mirrored list (an allowlist, a registry, a dispatch table) from its source. A copy drifts.
- Update every comment, doc, ADR and index that describes the old behaviour, in the same change.

## Structure, not text

- Match and classify by parsed structure, position and whole-token boundaries. Never use a substring, raw-byte or
  prefix scan, a word set or a count over the whole input.
- Test real input of each legitimate shape, including scripts without spaces between words.
- On malformed input, consume up to the closing delimiter.
- Never panic on input. Index, slice and compare by character boundary, replace a bad encoding instead of failing the
  item, and contain a failure to the item that caused it.

## Specifications

Implement a standard, protocol or external API as its specification or the real service defines it. Test against a
reference implementation or a recorded real reply, not against your reading of the spec.

## Fail closed

- An unknown, unparsable or failed value is the worst case: deny, keep the full reservation, or return an error.
- Keep it distinct from every valid value. A zero or empty sentinel reads as a valid result.
- Never report success for work that did not happen.
- Before you decide an item is absent, read every page of the list, and page on the key the filter uses.

## Preflight

Run every known refusal over the whole plan before the first paid or destructive step. Reuse the real step's
validation to do it.

## State

- Advance or persist state only after the step it records is complete and verified.
- Make the guard check and the transition one atomic step.
- Keep safety state across retries and resumes.
- Make an invariant structural (a type, one API form, a lint, a check in release builds), not a comment, a debug
  assertion or an order the caller must keep.

## Retries and idempotence

- Key each handler, task and external create that can run twice by a stable identity of the work, so a second run
  does nothing new.
- Give each job and retry loop a terminal state: bound the attempts, back off, retry at one layer only, and mark a
  failure that repeats as permanent. Renew a lease while the work runs.

## Parity

- Moving, replacing or removing code keeps every effect it had and every input it handled. Change only the output
  the fix targets.
- Before you delete a workaround, prove the replacement covers each input the workaround covered.

## No silent loss

- Never drop, suppress or replace output unless the replacement provably holds the same content.
- Gate a retry or recovery before it replaces a good result.
- Derive counts from the source range. Leave a warning or a marker where data is lost.

## Authoritative allowlists

- Build a validator or allowlist from the registry of what is supported, not from a derived list such as file
  extensions.
- Accept every form that works today. Normalise case and aliases on both sides, as the spec says. Reject only what
  upstream rejects.

## Boundary validation

Validate supplied input before you transform or drop it: clamp it to the documented bound, reject a zero
denominator, reject fields the chosen variant does not use, and log a count when you repair input. Wire each accepted
option and setting through to the code that applies it, or reject it. A setting that does nothing is a defect.

## Safe writes

- Before a write, overwrite or delete, prove the target is inside a root you own: resolve symlinks, fold case, reject
  absolute and `..` paths.
- Prove this run created the target, and that no two outputs collide. Derive names from the full identity of the
  input.
- Check every path, including the empty and absent ones.

## Bounded work

- Bound every loop, search, allocation and buffer that input size or untrusted input drives: no rescan of a container
  per item, no unbounded pairwise search, limits from the memory budget, and a timeout on every public async
  operation.
- Add a scaling test with an adversarial outlier.

## Secrets

- Ambient credentials never reach an endpoint that the caller supplies.
- Assert that a secret is absent from the whole rendered error, and that the error still names the problem.
- Validate an outbound address after you decode every embedded form, again on each redirect and resolved address, and
  connect to the address you validated.

## Reuse and placement

- Before you write a helper, parser, validator, filter or estimator, search for the existing one and use it. A
  fallback or recovery path uses the strict path's function. Reusing what exists is not a premature extraction, so
  the rule of three in `code-quality-standards` does not apply to it.
- Put a fix or a new implementation in the module that owns the behaviour and holds its siblings, not in a caller. If
  a dependency owns it, fix it upstream.
- Give each name one meaning. Rename or split a parameter that gains a second meaning. Do not reuse the name of a
  removed symbol that comments still name.

## Compatible changes

- Change a public API additively. Never add a field to a public struct or a required field to a public type, because
  callers that build it literally break: use an internal option or a new entry point.
- Keep internal pipeline hints out of user-facing options. Deprecate for one minor release before you remove.
- Make each schema and wire change safe while old and new versions run together: create the invariant in one locked
  upgrade step, fence or drain old writers, and make a new wire field optional for old readers.
- Do not add compatibility code for versions the project does not support.

## Less frequent invariants

[references/more-invariants.md](references/more-invariants.md) holds resources, cache and identity keys, result
independence, serialization, units, defaults, and errors and logs. Read it when the diff touches one of them.


## Resources

This skill bundles supporting files. Read them on demand when the task calls for them — don't bulk-load.

### References

- [`references/more-invariants.md`](references/more-invariants.md) — More correctness invariants
