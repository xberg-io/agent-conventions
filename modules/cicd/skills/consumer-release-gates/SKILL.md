---
type: Playbook
title: Consumer Release Gates
description: Reproduce an alef-generated repo's release gate locally and verify published package names against the real manifests. Use before tagging a release or when auditing a registry publish.
x-ai-rulez:
  kind: skill
  id: consumer-release-gates
  metadata:
    license: MIT
    name: consumer-release-gates
---

# Consumer Release Gates

A consumer repo's release workflow runs a gate before it will publish anything. Reproduce it
locally — it answers in under a second and is the same check the release workflow runs.

## Reproduce the gate before tagging

```bash
cd <consumer-repo> && alef validate versions --json | jq '{ok, bad:[.checks[]|select(.ok==false)]}'
```

`ok: false` means the release will publish **nothing** — the gate failing skips the primary
registry publish job, and every downstream language-package build then fails with a version
resolution error against a registry version that was never pushed. Those failures look like many
unrelated bugs; they are one cascade from a single failed gate.

A `blocked_on_publish` entry in a check is expected and tolerated by design — `all_ok()` ignores
it, because a lockfile holding a dependency on the not-yet-published version genuinely cannot
resolve before publish. Only entries with `blocked_on_publish: null` are real failures. Fix a real
failure with `cargo update --offline -w` run in the lockfile's own directory — it relocks offline
in one shot.

**Run the gate after the version bump, never before.** The bump re-runs alef's version sync, which
rewrites manifest versions and leaves lockfiles stale again — checking before the bump validates a
state the bump is about to invalidate.

## Verify a published package by its real manifest name, not a guessed one

Different registries use different casing/separator conventions for the same package
(underscores vs. hyphens, a shortened vs. a full name, a group ID that doesn't match the repo
name). Guessing the coordinate manufactures phantom "never published" findings. Before querying
any registry:

1. Read the actual name out of the manifest the registry publishes from — `*.gemspec`,
   `pubspec.yaml`, `pom.xml`, `composer.json`, `package.json`, `Cargo.toml` — never infer it from
   the repo name.
2. Query the authoritative endpoint, not a search UI that can false-negative: e.g. prefer
   `repo1.maven.org/maven2/<group-path>/<artifact>/maven-metadata.xml` over a Maven search page.
3. `crates.io`'s API requires a `User-Agent` header — an unauthenticated request without one
   returns not-found regardless of whether the crate exists.
4. A per-language config block being absent from `alef.toml` (e.g. no `[crates.php]` override)
   means that language uses its defaults, not that publishing is disabled for it. Absence of an
   override is not evidence of "not published" — query the registry before reporting a gap.
5. Watch for name collisions with unrelated third-party packages already occupying the "obvious"
   name on a given registry — confirm you're looking at the right owner/coordinate, not just a
   package that exists.

A fabricated gap is worse than a missed real one: it sends real effort at a non-problem, and once
one reported "gap" turns out to be noise, a genuine gap in the same report becomes easy to dismiss
too.
