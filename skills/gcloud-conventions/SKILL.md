---
name: gcloud-conventions
description: "Google Cloud conventions: project and region, service set, resource naming, workload identity federation, least-privilege IAM, gcloud-only operations. Use when provisioning GCP resources or setting up auth."
# Content-Hash: blake3:f2e9fd6957316ff2ef19d1bf3c0737a96eed2002d28e9554837b2f2d082cd4c7
---

# GCloud Conventions

- GCP project: xberg-io, region: europe-west1
- Services: Cloud Run (compute), Cloud Storage (artifacts), Cloud SQL/AlloyDB (Postgres), Pub/Sub (messaging), Artifact Registry (images), Secret Manager (credentials)
- Naming: xberg-{service}-{environment}, buckets: xberg-io-{purpose}-{environment}
- Auth: workload identity federation — never service account keys
- IAM: least privilege, no owner-level for service accounts
- Use gcloud CLI for all operations — no manual console changes
