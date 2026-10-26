---
name: error-handling
description: "Error handling by language: wrap with context, never swallow, Result in Rust, %w wrapping in Go, typed exceptions in Python and Java, fail fast. Use when writing or reviewing an error path or custom error type."
# Content-Hash: blake3:d58ff2ae357b5c0e76057fb079d28ea34d45bc95d9de079299822112b529c8b2
---

- Always wrap errors with context describing what operation failed.
- Never swallow errors silently — either handle, propagate, or log them.
- Use language-idiomatic patterns: `Result<T, E>` in Rust, `if err != nil` with `fmt.Errorf("doing X: %w", err)` in Go, typed exceptions in Python/Java.
- Fail fast on unrecoverable errors.
