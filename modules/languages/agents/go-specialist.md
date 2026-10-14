---
type: Reference
title: Go Specialist
description: Go and cgo FFI development
x-ai-rulez:
  kind: agent
  id: go-specialist
  metadata:
    effort: medium
    model: sonnet
    name: go-specialist
---

1. cgo: #include "lib.h", link via #cgo LDFLAGS
1. C.CString with defer C.free for string passing, C.GoString for returns
1. unsafe.Pointer for opaque handles, defer handle_free() pattern
1. Error handling via out-params or error codes — wrap in idiomatic Go errors
1. Test: go test, package: Go module with replace directive for local dev
