---
type: Playbook
title: Gcloud Conventions
description: "Google Cloud conventions: workload identity federation, least-privilege IAM, changes through IaC only with gcloud for inspection, project and naming facts kept in the infra repo. Use when provisioning GCP resources or setting up auth."
paths:
  - "**/*.tf"
  - "**/*.tofu"
  - "**/*.tfvars"
  - "deploy/**"
  - "charts/**"
x-ai-rulez:
  kind: skill
  id: gcloud-conventions
  metadata:
    name: gcloud-conventions
---

# GCloud Conventions

- Auth: workload identity federation for CI and workloads; never create or commit service account keys.
- IAM: least privilege; no owner-level roles for service accounts; grant at the narrowest resource.
- Change resources only through infrastructure-as-code, reviewed and merged; use `gcloud` to inspect state and for documented one-time bootstrap, never to apply a change by hand (and never through the console).
- Project ids, regions and the resource naming scheme are facts of the infra repo; read them there instead of assuming them.
