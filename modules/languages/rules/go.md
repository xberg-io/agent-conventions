---
type: Decision
title: Go Conventions
paths:
  - "**/*.go"
  - "**/go.mod"
x-ai-rulez:
  kind: rule
  id: go
  metadata:
    priority: high
---

- Effective Go; `gofmt`/`goimports`; golangci-lint (govet, staticcheck, errcheck, gosec); `govulncheck` in CI.
- Handle every error; wrap with `fmt.Errorf("doing x: %w", err)`; compare with `errors.Is`/`errors.As`.
- Table-driven tests with `t.Run`; `context.Context` first and never stored in a struct; no package-level state or `init()`.
