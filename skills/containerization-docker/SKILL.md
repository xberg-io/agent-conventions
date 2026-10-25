---
name: containerization-docker
description: "Dockerfile conventions: multi-stage builds, layer caching, non-root, image scanning, no baked secrets, signals and healthchecks, tagging. Use when writing Dockerfiles or container build pipelines."
# Content-Hash: blake3:c0e0710fc69f004c55ff1a4ca553a83d9f24e337dfa2ea5de904e93111617eb4
---

# Containerization / Docker

- Multi-stage builds: full toolchain builder → minimal runtime (Alpine/Distroless/Scratch)
- Layer caching: copy Cargo.toml/Cargo.lock first, then source; use BuildKit mount caches
- Security: non-root user, Trivy/Grype scanning (fail on HIGH/CRITICAL), no secrets in image
- Signal handling: tini/dumb-init as PID 1, HEALTHCHECK for orchestrator detection
- Tagging: semantic version + commit SHA, never reuse tags
