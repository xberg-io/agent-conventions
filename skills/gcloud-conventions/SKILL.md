---
name: gcloud-conventions
description: "Google Cloud conventions: workload identity federation, least-privilege IAM, CLI or IaC over console changes, project and naming facts kept in the infra repo. Use when provisioning GCP resources or setting up auth."
# Content-Hash: blake3:7454768593eda747442cac4f914529b93760d3c6a605de9e0025d4aa1637e962
---

# GCloud Conventions

- Auth: workload identity federation for CI and workloads; never create or commit service account keys.
- IAM: least privilege; no owner-level roles for service accounts; grant at the narrowest resource.
- Change resources through `gcloud` or infrastructure-as-code, never by hand in the console, so every change is reviewable and reproducible.
- Project ids, regions and the resource naming scheme are facts of the infra repo; read them there instead of assuming them.
