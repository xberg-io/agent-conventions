---
type: Decision
title: Test Alongside Code
x-ai-rulez:
  kind: rule
  id: test-alongside-code
  metadata:
    priority: high
---

Tests ship with the behavior change, in the same commit; reproduce a bug with a failing test before fixing it (bug fixes and public APIs first). Run the checks that exercise the change, not the whole suite by default: a full build or test run is not a commit step unless the user or a release procedure asks for it.
