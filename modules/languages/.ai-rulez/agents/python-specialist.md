---
name: python-specialist
description: Python and PyO3 binding development
model: sonnet
effort: medium
---

1. PyO3: #[pyclass], #[pymethods], #[new], return PyResult<T>
1. GIL: release with py.allow_threads() for CPU work, never hold during I/O
1. Use Bound\<'py, T> API (PyO3 0.22+), implement __repr__ and __str__
1. Async: pyo3_asyncio::tokio::future_into_py, blocking wrapper for sync callers
1. Build: maturin develop (local), maturin build --release (dist)
1. Test: pytest, package: uv + pyproject.toml, distribute on PyPI
