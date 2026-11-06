# More correctness invariants

Review findings rarer than those in `SKILL.md`, most frequent first.

## Resources

Release each handle, thread, runtime and child process you start on every exit path, cancellation and signals
included, with a bounded wait. Leave process-global state as you found it.

## Cache and identity keys

- Every input that changes a result is part of the key.
- Key identity and dedup sets by the canonical form of the identity (the final address, the normalised spelling).
  Fold only what the standard calls equivalent.
- Initialise a cache once. Release cached state by what the run selected.
- Test the cache at the handler level, not only the cache type.

## Result independence

A result does not change with output options, traversal order, API mode or entry point, unless the change says that
it should.

## Serialization

Every field and its provenance cross each serialization boundary. Escape or quote each value for the target syntax,
and bind query values. Test the round trip: the reader parses back the structure and the values of the source.

## Units

Compute each limit, metric and routing decision on the quantity, unit and basis that its name states. Record it
once, where the event is decided, and use one basis for related numbers.

## Defaults

- Size each default (volume, buffer, limit) against the data it must hold.
- Latch only a decision that must stay stable, never a value that changes during the life of the process.
- Never overwrite or silently disable a value the caller set. An update changes only the fields it names, and a merge
  keeps explicit values over defaults.

## Errors and logs

- Write each error and warning in the caller's terms: the problem, the real values and the setting that fixes it.
  State only what was verified, and keep internal identifiers out.
- Log a recoverable condition once, at warning level or lower. Keep error level for real failures, and rate-limit a
  line that can flood.
