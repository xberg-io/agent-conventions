#!/usr/bin/env bash
# Gate a consumer's start context with ai-rulez's native exposure checks, from the repository root.
# Env: HARNESS (tools/context-evals), REPO_NAME, optional BUDGETS and MEASURE_MCP (deprecated inputs),
# SUMMARY (a Markdown file to append the reports to) and WORK (a scratch directory).
set -uo pipefail

[ -n "${REPO_NAME:-}" ] || {
  echo "::error::repo-name is empty"
  exit 1
}
command -v ai-rulez >/dev/null || {
  echo "::error::ai-rulez is not on PATH; run xberg-io/actions/setup-ai-rulez first"
  exit 1
}
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
  python3 -c 'import json, sys; print(json.load(sys.stdin).get("start_budget") or 0)' <"$1"
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
  echo "::error::ai-rulez exposure gave no report"
  exit 1
}
codex_budget=$(budget "$WORK/codex.json") || codex_budget=0

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
exit "$failed"
