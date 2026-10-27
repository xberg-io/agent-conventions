---
name: basemind-tools
description: "Which basemind plugin skill to load for code search, history, documents or agent coordination, plus the graph modes and gotchas they omit. Use when navigating code or history in a repo where basemind is available."
# Content-Hash: blake3:272b48c56ee2bc6a976a57b077179a98e0d1a20de9df2eec9dbf2567944e8779
---

# basemind tools

The basemind-usage rule says when to use basemind; the basemind plugin's own skills hold the
per-mode detail. Load the one that matches the question:

| Question | Plugin skill |
|---|---|
| Where is X defined, what calls it, the shape of a file | `basemind:basemind-code-search` |
| What changed, who touched it, a symbol's history | `basemind:basemind-git-history` |
| Markdown, config, PDFs, web pages | `basemind:basemind-documents` |
| Other agents in the repo, threads, inbox | `basemind:basemind-comms` (several identities: `basemind:basemind-multi-agent-room`) |
| CLI or scripting use | `basemind:basemind-cli` |
| "no index", missing tools, a dead server | `basemind:basemind-doctor`, then `basemind:basemind-scan` |

What those skills leave out:

- `graph` mode `neighbors` gives the blast radius of a symbol before a change, and `path` shows how
  two symbols connect.
- A parameter that belongs to another mode is rejected, not ignored: drop it rather than retrying
  with more parameters.
