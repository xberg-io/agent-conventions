---
type: Decision
title: Targeted Verification
x-ai-rulez:
  kind: rule
  id: targeted-verification
  metadata:
    priority: critical
---

Verify assumptions before acting by checking the current branch, working directory, and relevant files. Write or
update focused tests when behavior changes, especially for bug fixes and public APIs, and keep regression coverage
close to the changed behavior with meaningful assertions. Use targeted verification appropriate to the change; do not
treat `cargo check`, `cargo test`, or a full test suite as mandatory before every commit unless the user or release
procedure requires it.
