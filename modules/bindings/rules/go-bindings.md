---
type: Decision
title: Go Binding Conventions
paths:
  - "packages/go/**"
x-ai-rulez:
  kind: rule
  id: go-bindings
  metadata:
    priority: high
---

- cgo: declare headers directly above `import "C"`, link with `#cgo LDFLAGS`, `defer C.free` right after every `C.CString`, pin Go memory passed to C with `runtime.Pinner`, wrap opaque handles with a `Close`/free pattern and convert C error codes to Go errors.
