---
type: Playbook
title: Containerization Docker
description: "Dockerfile conventions: multi-stage builds, layer caching, non-root, image scanning, no baked secrets, signals and healthchecks, tagging. Use when writing Dockerfiles or container build pipelines."
paths:
  - "**/Dockerfile*"
  - "**/*.dockerfile"
  - "**/docker-compose*.yml"
  - "**/docker-compose*.yaml"
  - "**/.dockerignore"
x-ai-rulez:
  kind: skill
  id: containerization-docker
  metadata:
    name: containerization-docker
---

# Containerization / Docker

- Multi-stage builds: full toolchain builder → minimal runtime (Alpine/Distroless/Scratch)
- Layer caching: copy Cargo.toml/Cargo.lock first, then source; use BuildKit mount caches
- Security: non-root user, Trivy/Grype scanning (fail on HIGH/CRITICAL), no secrets in image
- Signal handling: tini/dumb-init as PID 1, HEALTHCHECK for orchestrator detection
- Tagging: semantic version + commit SHA, never reuse tags
