---
name: incremental-approach
description: "Build in verified increments rather than one speculative block: smallest viable change first, verify, then extend; prototype the risky part before committing to a design; batch edits to one file into a single operation. Load when planning a large or multi-file change, when uncertain which of several approaches will work, or when tempted to generate a whole subsystem before running anything."
# Content-Hash: blake3:95041fb2a28e78eb25d36daa919c6057ee47a0c1b0f42ece17a87379b26bb938
---

- Start with the smallest viable change, verify it works, then extend. Implement one piece, test, move on.
- Avoid generating large blocks of speculative code.
- When uncertain about an approach, prototype the critical part before committing to the full implementation.
- Batch multiple edits to the same file into one operation, and prefer multi-file search over reading files one by one when exploring.
