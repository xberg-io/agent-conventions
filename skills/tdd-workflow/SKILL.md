---
name: tdd-workflow
description: "Test-driven workflow: red, green, refactor; restart if code came first; reproduce a bug as a failing test; integration, unit or property test by change type. Use before a feature or bug fix or when choosing a test type."
# Content-Hash: blake3:d4ab5a05e311e3fda34ff94a10347e8d62e445d0bc50fe01e57eea0aaf5bd5d6
---

# TDD workflow

- Write the test before the code. Update the test when changing behaviour.
- Fixing a bug: write the failing test first, then fix. RED → GREEN → REFACTOR.
- Wrote production code before the test? Delete it and start over — no exceptions, don't keep it as reference.
- Integration tests for API surfaces, unit tests for business logic, property tests for edge-case-heavy code.
- Run the new test and confirm it fails for the right reason before writing the fix.
- If a test cannot be made to pass after three attempts, stop and report rather than skipping or weakening it.
