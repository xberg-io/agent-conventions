---
type: Decision
title: Elixir Conventions
paths:
  - "**/*.ex"
  - "**/*.exs"
x-ai-rulez:
  kind: rule
  id: elixir
  metadata:
    priority: high
---

- Elixir 1.14+/OTP 25+; `mix format` and Credo `--strict`; commit `mix.lock`.
- `{:ok, value}` / `{:error, reason}` for expected failures; `with` for multi-step operations; ExUnit and doctests.
