---
type: Decision
title: Elixir Conventions
paths:
  - "**/*.ex"
  - "**/*.exs"
  - "packages/elixir/**"
targets:
  - ".claude/rules/"
  - ".github/instructions/"
x-ai-rulez:
  kind: rule
  id: elixir
  metadata:
    priority: high
---

- Elixir 1.14+/OTP 25+; `mix format`, Credo `--strict`, Dialyzer; `mix_audit` for CVEs; commit `mix.lock`.
- `{:ok, value}` / `{:error, reason}` for expected failures; `with` for multi-step operations; ExUnit and doctests.
- Rustler NIFs: `#[rustler::nif]`, `schedule = "DirtyCpu"` for anything over ~1 ms, never panic or block a scheduler, `ResourceArc<T>` for shared state. Distribute precompiled NIFs with rustler_precompiled.
