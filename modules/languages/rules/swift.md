---
type: Decision
title: Swift Conventions
paths:
  - "**/*.swift"
  - "**/Package.swift"
  - "packages/swift/**"
x-ai-rulez:
  kind: rule
  id: swift
  metadata:
    priority: high
---

- Import generated C headers through a module map or a SwiftPM system library target.
- Wrap opaque pointers in `final class`es with `deinit` cleanup and an explicit `close()`.
- Convert C strings with `String(cString:)` and document ownership of every returned buffer.
- Map native error codes to Swift `Error` types carrying code, message and operation. Test with XCTest; ship binary artifacts through SwiftPM.
