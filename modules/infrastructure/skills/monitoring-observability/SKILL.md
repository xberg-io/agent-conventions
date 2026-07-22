---
name: monitoring-observability
description: Observability conventions for xberg-io services — structured JSON logging, tracing spans and context fields, log-level semantics, Prometheus metric types and cardinality rules, and health endpoints wired to K8s probes. Load when adding logging, tracing, metrics, or health checks to a service.
---

# Monitoring / Observability

- Logging: tracing crate (Rust) / structlog (Python), JSON output, key=value — never f-strings
- Spans: #[instrument] macro, context fields (user_id, request_id)
- Levels: ERROR (unrecoverable), WARN (degraded), INFO (state changes), DEBUG (flow), TRACE (off in prod)
- Metrics: Prometheus — counter (requests), gauge (connections), histogram (latency), no high-cardinality labels
- Health: /health endpoint with component status, wired to K8s liveness/readiness probes
