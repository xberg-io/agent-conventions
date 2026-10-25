---
type: Decision
title: Go Conventions
paths:
  - "**/*.go"
  - "**/go.mod"
  - "packages/go/**"
x-ai-rulez:
  kind: rule
  id: go
  metadata:
    priority: high
---

- Effective Go; `gofmt`/`goimports`; golangci-lint (govet, staticcheck, errcheck, gosec); `govulncheck` in CI.
- Handle every error; wrap with `fmt.Errorf("doing x: %w", err)`; compare with `errors.Is`/`errors.As`.
- Table-driven tests with `t.Run`; `context.Context` first and never stored in a struct; no package-level state or `init()`.
- cgo bindings: declare headers directly above `import "C"`, link with `#cgo LDFLAGS`, `defer C.free` right after every `C.CString`, pin Go memory passed to C with `runtime.Pinner`, wrap opaque handles with a `Close`/free pattern and convert C error codes to Go errors.
