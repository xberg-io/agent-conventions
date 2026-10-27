---
type: Decision
title: Python Conventions
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
x-ai-rulez:
  kind: rule
  id: python
  metadata:
    priority: high
---

- Python 3.10+, type hints on public APIs, no `Any` where a precise type, generic or `Protocol` fits.
- Ruff for lint and format; Pyrefly (`pyrefly check`) is the only type checker. Do not add mypy, pyright or their config.
- pytest with function-based tests; `uv` with a committed `uv.lock`; `pip-audit` for dependency CVEs.
- Specific exceptions only, never a bare `except:`; `pathlib.Path` over `os.path`; dataclasses or Pydantic for known schemas.
- Async I/O with `async`/`await`; never block inside a coroutine.
