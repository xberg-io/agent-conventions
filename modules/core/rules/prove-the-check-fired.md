---
type: Decision
title: Prove The Check Fired
x-ai-rulez:
  kind: rule
  id: prove-the-check-fired
  metadata:
    priority: critical
---

The dominant defect shape here is a check that passes because it examined nothing. Before trusting
a green result: make it fail on purpose once, to prove it is wired to what you think it is wired
to. Read the count or the diff, not the word "ok" — a `0 files`, an empty match set, and a real
pass can render identically. Check the artifact actually in effect at runtime — generated output,
committed content, a pushed ref — not just the source you edited; a source-only grep can be clean
while the rendered or fetched result still carries the bug, and an uncommitted scratch file can
report clean regardless of content. A gate scoped to a path or a diff is blind to any change that
doesn't touch those paths — confirm the filter matches the shape it exists to catch.

Observed forms of the zero-work pass, all of which exited `0` and rendered identically to success:

- `xargs -a` — not supported by BSD/macOS `xargs`. Wrote a header row, ran nothing.
- An `xargs` command line over the length limit — `command line cannot be assembled, too long`,
  zero rows, `DONE` printed.
- An empty shell variable from a drifted working directory, so the tool was handed no path and
  "succeeded" in 0.02 s.
- A negative control that passed for the wrong reason: a planted typo was rejected by a
  `duplicate key` error rather than by the unknown-field check it was meant to exercise.

Therefore: assert the expected job count up front and compare it to the row count actually
produced, reporting both numbers. Guard interpolated paths (`[ -n "$x" ] || exit`) so a drifted
variable aborts instead of silently examining nothing. Prefer absolute paths in any harness whose
working directory is not guaranteed. Smoke-test a new harness against an input whose answer is
already known before trusting its output, and make the assertion itself fail once on purpose.
