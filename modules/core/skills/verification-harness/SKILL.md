---
type: Playbook
title: Verification Harness
description: "Zero-work passes seen in practice and how to guard a harness against them: xargs limits, empty path variables, wrong-reason negative controls, job-count assertions. Use when writing or trusting a sweep, gate or check script."
x-ai-rulez:
  kind: skill
  id: verification-harness
  metadata:
    name: verification-harness
---

# Verification harness

The `prove-the-check-fired` rule states the principle. These are the forms it has taken; each
exited `0` and rendered identically to success.

## Observed zero-work passes

- `xargs -a`: not supported by BSD/macOS `xargs`. Wrote a header row, ran nothing.
- An `xargs` command line over the length limit: `command line cannot be assembled, too long`,
  zero rows, `DONE` printed.
- An empty shell variable from a drifted working directory: the tool was handed no path and
  "succeeded" in 0.02 s.
- A negative control that passed for the wrong reason: a planted typo was rejected by a
  `duplicate key` error rather than by the unknown-field check it was meant to exercise.
- A source-only grep that was clean while the rendered or fetched result still carried the bug, and
  an uncommitted scratch file that reported clean regardless of content.

## Guards

- Assert the expected job count up front and compare it with the row count produced; report both.
- Guard interpolated paths (`[ -n "$x" ] || exit 1`) so a drifted variable aborts instead of
  silently examining nothing.
- Prefer absolute paths in any harness whose working directory is not guaranteed.
- Smoke-test a new harness against an input whose answer is already known.
- Make the assertion fail once on purpose, and check that it failed for the reason it exists.
