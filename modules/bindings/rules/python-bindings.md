---
type: Decision
title: Python Binding Conventions
paths:
  - "crates/*-py/**"
  - "packages/python/**"
x-ai-rulez:
  kind: rule
  id: python-bindings
  metadata:
    priority: high
---

- PyO3 (`crates/*-py`): `#[pyclass]`/`#[pymethods]`, return `PyResult<T>` and map errors to typed exceptions, use the `Bound<'py, T>` API, release the GIL with `py.allow_threads()` for CPU work, build with maturin. Keep the Python layer thin.
