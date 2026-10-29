#!/usr/bin/env bash
#MISE description="Fail unless the ai-rulez on PATH is at least the version this checkout requires"
#MISE hide=true
#MISE quiet=true
set -euo pipefail

# mise.toml pins ai-rulez; this floor still catches a mise.local.toml or MISE_*_VERSION override
# that resolves an older release. ~keep
AI_RULEZ_MIN_VERSION="5.9.2"
installed_version="$(ai-rulez --version)"
found="${installed_version#ai-rulez version }"
lowest="$(printf '%s\n%s\n' "$AI_RULEZ_MIN_VERSION" "$found" | sort -V | head -n 1)"
if [ "$found" = "$installed_version" ] || [ "$lowest" != "$AI_RULEZ_MIN_VERSION" ]; then
  echo "This checkout requires ai-rulez $AI_RULEZ_MIN_VERSION or newer; found $installed_version" >&2
  exit 1
fi
