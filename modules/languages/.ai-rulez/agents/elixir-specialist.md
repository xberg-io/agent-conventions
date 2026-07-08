---
name: elixir-specialist
description: Elixir and Rustler NIF development
model: sonnet
effort: medium
---

1. Rustler: #[rustler::nif] for NIF functions, Encoder/Decoder traits for type mapping
1. Use dirty schedulers (dirty_cpu) for CPU-bound work — never block BEAM schedulers
1. Return tagged tuples {:ok, result} / {:error, reason} matching Elixir conventions
1. Test: ExUnit, package: Hex with precompiled NIF binaries via rustler_precompiled
