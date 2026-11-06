#!/usr/bin/env bash
# Gate a consumer's start context with ai-rulez's native exposure checks, from the repository root.
# Env: HARNESS (tools/context-evals), REPO_NAME, optional BUDGETS and MEASURE_MCP (deprecated inputs),
# SUMMARY (a Markdown file to append the reports to) and WORK (a scratch directory).
set -uo pipefail

MIN_VERSION=5.11.0
DESCRIPTION_LIMIT=250
SUMMARY=${SUMMARY:-/dev/null}
if [ -z "${WORK:-}" ]; then
  WORK=$(mktemp -d)
  trap 'rm -rf "$WORK"' EXIT
fi

[ -n "${REPO_NAME:-}" ] || {
  echo "::error::repo-name is empty"
  exit 1
}
command -v ai-rulez >/dev/null || {
  echo "::error::ai-rulez is not on PATH; run xberg-io/actions/setup-ai-rulez first"
  exit 1
}
version=$(ai-rulez --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
if [ -z "$version" ] || [ "$(printf '%s\n%s\n' "$MIN_VERSION" "$version" | sort -V | head -n 1)" != "$MIN_VERSION" ]; then
  echo "::error::context-exposure needs ai-rulez >= $MIN_VERSION, found ${version:-no version}"
  exit 1
fi
BUDGETS=${BUDGETS:-}
if [ -n "${BUDGETS//[[:space:]]/}" ]; then
  echo "::warning::the budgets input is ignored: set [exposure] start_budget (and codex_start_budget) in .ai-rulez/config.toml"
fi
if [ -n "${MEASURE_MCP:-}" ] && [ "${MEASURE_MCP//[[:space:]]/}" != "ai-rulez" ]; then
  echo "::warning::the measure-mcp input is ignored: set [exposure] mcp_server_tokens in .ai-rulez/config.toml"
fi

areas="$WORK/context-exposure-areas.toml"
python3 "$HARNESS/areas.py" --repo "$REPO_NAME" --domains "$HARNESS/domains.toml" --out "$areas" ||
  {
    echo "::error::cannot render the area map of $REPO_NAME from domains.toml"
    exit 1
  }

budget() {
  python3 -c 'import json, sys; print(int(json.load(sys.stdin)["start_budget"] or 0))' <"$1" 2>/dev/null
}

failed=0
report() {
  local title=$1
  shift
  local rc=0
  local out
  out=$(ai-rulez exposure "$@" 2>&1) || rc=$?
  printf '%s\n' "$out"
  printf '## %s\n\n```text\n%s\n```\n\n' "$title" "$out" >>"$SUMMARY"
  if [ "$rc" -ne 0 ]; then
    echo "::error::ai-rulez exposure $* exited $rc ($title)"
    failed=1
  fi
}

ai-rulez exposure --areas "$areas" --format json >"$WORK/claude.json" || true
ai-rulez exposure --harness codex --format json >"$WORK/codex.json" || true
claude_budget=$(budget "$WORK/claude.json") || {
  echo "::error::ai-rulez exposure --format json gave no report"
  exit 1
}
codex_budget=$(budget "$WORK/codex.json") || {
  echo "::error::ai-rulez exposure --harness codex --format json gave no report"
  exit 1
}

if [ "$claude_budget" -eq 0 ]; then
  echo "::error::[exposure] start_budget is not set in .ai-rulez/config.toml; the start context has no budget"
  failed=1
fi
report "Claude Code start context" --areas "$areas"
if [ "$codex_budget" -eq 0 ]; then
  echo "::warning::[exposure] codex_start_budget is not set; the Codex start context is reported, not gated"
fi
report "Codex start context" --harness codex
report "Leakage at session start" leakage --areas "$areas"

# Skill and agent listings a model can invoke: at start for Claude Code, path-gated ones too for Codex, which lists
# them all. The bound is the gate's own, so a consumer's [lint.description] cannot loosen it.
ai-rulez exposure inventory --format json >"$WORK/inventory.json" || true
if ! long=$(
  python3 - "$WORK/inventory.json" "$DESCRIPTION_LIMIT" <<'EOF'
import json
import sys

artifacts = json.load(open(sys.argv[1]))["artifacts"]
for item in artifacts:
    if item["kind"] in ("skill", "agent") and item["phase"] != "manual":
        description = item["listing_text"].partition(": ")[2]
        if item.get("truncated") or len(description) > int(sys.argv[2]):
            print(f"{item['path']} ({len(description)} characters)")
EOF
); then
  echo "::error::ai-rulez exposure inventory --format json gave no usable report"
  failed=1
elif [ -n "$long" ]; then
  while read -r line; do
    echo "::error::listed description over $DESCRIPTION_LIMIT characters: $line"
  done <<<"$long"
  printf '## Descriptions over %s characters\n\n```text\n%s\n```\n\n' "$DESCRIPTION_LIMIT" "$long" >>"$SUMMARY"
  failed=1
fi
exit "$failed"
