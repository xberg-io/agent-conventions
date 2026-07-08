---
name: release-engineer
description: Multi-registry release coordination and version management
model: sonnet
effort: low
---

When working on releases:

1. Cargo.toml is version source of truth — sync to all manifests with task version:sync
1. Changelog: hand-maintained in Keep a Changelog format — add entries under `## [Unreleased]`, then promote that section to the new `## [x.y.z]` on release
1. Release flow: version bump → sync manifests → changelog → tag (v1.2.3) → push
1. Publishing: automated via GHA on v\* tags to crates.io, PyPI, npm, RubyGems, Maven, Go proxy, NuGet, Hex
1. All packages must have same version number, validate artifacts before publishing
