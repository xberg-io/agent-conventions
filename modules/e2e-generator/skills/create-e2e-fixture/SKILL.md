---
type: Playbook
title: Create E2e Fixture
description: How to author a new e2e test fixture for cross-language test generation — fixture fields, assertion types, and id conventions. Load when adding or editing e2e fixtures consumed by the generator.
paths:
  - "fixtures/**"
  - "e2e/**"
x-ai-rulez:
  kind: skill
  id: create-e2e-fixture
  metadata:
    name: create-e2e-fixture
---

# Create E2E Fixture

## Steps

1. **Identify the test case**: What behavior needs testing across language bindings?
1. **Choose category**: smoke, basic, parsing, edge-case, error-handling, or platform-specific.
1. **Write fixture JSON**:

   ```json
   {
     "id": "descriptive_snake_case_name",
     "category": "basic",
     "description": "Tests that X produces Y",
     "source_code": "input data or code",
     "assertions": {
       "tree_not_null": true,
       "expect_error": false
     },
     "tags": ["regression"]
   }
   ```

1. **Add to fixtures directory**: Place in appropriate category file or subdirectory.
1. **Regenerate**: Run `task e2e:generate`.
1. **Verify**: Run `task e2e:test` to confirm all languages pass.
1. **Commit**: Include fixture + regenerated test files in same commit.

## Guidelines

- IDs must be unique across all fixture files
- Include both positive and negative test cases
- Add skip conditions for platform-specific behavior
- Keep source_code minimal — test one thing per fixture
