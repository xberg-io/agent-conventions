---
name: tdd-workflow
description: "Test-driven workflow: red, green, refactor; restart if code came first; reproduce a bug as a failing test; integration, unit or property test by change type. Use before a feature or bug fix or when choosing a test type."
# Content-Hash: blake3:3dcbeae9388478a9e99a7a79aadacf53b9f58822f7f9a0d8b6bb6fc884210b09
---

# TDD workflow

- Write the test before the code. Update the test when changing behaviour.
- Fixing a bug: write the failing test first, then fix. RED → GREEN → REFACTOR.
- Wrote production code before the test? Delete it and start over — no exceptions, don't keep it as reference.
- Integration tests for API surfaces, unit tests for business logic, property tests for edge-case-heavy code.
- Run the new test and confirm it fails for the right reason before writing the fix.
- If a test cannot be made to pass after three attempts, stop and report rather than skipping or weakening it.

## What a test must prove

- A regression test fails with the fix reverted. Revert the fix locally once and watch the test fail. A test that
  passes either way is a guard: name it as one, and do not count it as the regression test.
- Drive the test through the production entry point, on the route the change claims, with the default
  configuration.
- Cover every behaviour path the change touches: failure, resume, legacy state, boundary, rollback, and each case a
  reviewer names. When the output shape changes, update the tests that assert the old shape in the same commit.
- Give every guard, filter, validator or threshold an input it must accept and an input it must reject. Add cases on
  each side of each threshold, plus aliases, wildcards and malformed input (empty, very long, duplicate).

## Hermetic tests

- Wait for the event, never for a fixed sleep, and put a deadline on every wait.
- Stop everything the test starts.
- Inject host state and ports through a seam. Never add a test-only hook inside a production function.
- Keep fixture names distinct on file systems that ignore case.
- A new test runs in CI, not skips: CI provisions the models, services, fixtures and tool versions it needs. Commit
  each fixture with its provenance.

## Keeping tests

- Never delete the regression test of a fixed bug.
- When you remove a helper, replace its unit test with a public-API test of the behaviour the helper protected.
