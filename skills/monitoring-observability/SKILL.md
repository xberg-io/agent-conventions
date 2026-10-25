---
name: monitoring-observability
description: "Service observability: structured JSON logs, tracing context, Prometheus metric types and cardinality, health endpoints wired to probes. Use when adding logs, metrics or health checks to a service."
# Content-Hash: blake3:e682c3527ca48b342d6b440afab14fefd55b98d54e05c1b78fffcf563ef6c023
---

# Monitoring / Observability

- Logging: tracing crate (Rust) / structlog (Python), JSON output, key=value — never f-strings
- Spans: #[instrument] macro, context fields (user_id, request_id)
- Levels: ERROR (unrecoverable), WARN (degraded), INFO (state changes), DEBUG (flow), TRACE (off in prod)
- Metrics: Prometheus — counter (requests), gauge (connections), histogram (latency), no high-cardinality labels
- Health: /health endpoint with component status, wired to K8s liveness/readiness probes
