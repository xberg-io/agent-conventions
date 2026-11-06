"""actions/context-exposure/gate.sh against a stub ai-rulez that answers as the configured repository would."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parents[1] / "actions" / "context-exposure" / "gate.sh"

STUB = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["STUB_LOG"], "a") as log:
        log.write(" ".join(args) + "\\n")
    harness = "codex" if "--harness" in args and args[args.index("--harness") + 1] == "codex" else "claude"
    if "leakage" in args:
        print("violations: 1" if os.environ.get("STUB_LEAK") else "violations: 0")
        sys.exit(2 if os.environ.get("STUB_LEAK") else 0)
    budget = int(os.environ.get(f"STUB_{harness.upper()}_BUDGET", "0"))
    tokens = int(os.environ.get(f"STUB_{harness.upper()}_TOKENS", "100"))
    over = budget and tokens > budget
    if "--format" in args:
        print(json.dumps({"harness": harness, "start_budget": budget, "start_tokens": tokens}))
    else:
        print(f"start of session: ~{tokens} tokens")
    sys.exit(2 if over else 0)
    """
)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "ai-rulez"
        stub.write_text(STUB)
        stub.chmod(0o755)
        domains = self.tmp / "harness"
        domains.mkdir()
        shutil.copy(HERE / "areas.py", domains / "areas.py")
        (domains / "domains.toml").write_text(
            '[domain.billing]\nterms = ["invoice"]\n\n[repos.app]\ndomains = []\n', encoding="utf-8"
        )
        self.summary = self.tmp / "summary.md"
        self.log = self.tmp / "calls.log"
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HARNESS": str(domains),
            "REPO_NAME": "app",
            "SUMMARY": str(self.summary),
            "WORK": str(self.tmp),
            "STUB_LOG": str(self.log),
            "STUB_CLAUDE_BUDGET": "500",
            "STUB_CODEX_BUDGET": "500",
        }

    def run_gate(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(GATE)], env={**self.env, **env}, cwd=self.tmp, capture_output=True, text=True, check=False
        )

    def test_passes_within_both_budgets_without_leaks_and_runs_every_check(self) -> None:
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 5)
        self.assertTrue(any(c.startswith("exposure leakage --areas ") for c in calls))
        self.assertTrue(any(c == "exposure --harness codex" for c in calls))
        areas = Path(calls[0].split("--areas ")[1].split()[0])
        self.assertIn('terms = ["invoice"]', areas.read_text())
        self.assertEqual(self.summary.read_text().count("## "), 3)

    def test_fails_on_a_leak(self) -> None:
        result = self.run_gate(STUB_LEAK="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Leakage at session start", result.stdout)

    def test_fails_over_either_budget(self) -> None:
        self.assertEqual(self.run_gate(STUB_CLAUDE_TOKENS="501").returncode, 1)
        result = self.run_gate(STUB_CODEX_TOKENS="501")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Codex start context", result.stdout)

    def test_fails_closed_without_a_start_budget_and_warns_without_a_codex_budget(self) -> None:
        result = self.run_gate(STUB_CLAUDE_BUDGET="0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("start_budget is not set", result.stdout)
        result = self.run_gate(STUB_CODEX_BUDGET="0")
        self.assertEqual(result.returncode, 0)
        self.assertIn("::warning::[exposure] codex_start_budget is not set", result.stdout)

    def test_deprecated_inputs_warn_and_change_nothing(self) -> None:
        result = self.run_gate(BUDGETS="claude=10\ncodex=10", MEASURE_MCP="other")
        self.assertEqual(result.returncode, 0)
        self.assertIn("budgets input is ignored", result.stdout)
        self.assertIn("measure-mcp input is ignored", result.stdout)
        self.assertNotIn("ignored", self.run_gate(BUDGETS="", MEASURE_MCP="ai-rulez").stdout)

    def test_fails_for_a_repository_missing_from_domains_toml(self) -> None:
        result = self.run_gate(REPO_NAME="ghost")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot render the area map of ghost", result.stdout)
        self.assertFalse(self.log.exists())

    def test_fails_when_ai_rulez_gives_no_report(self) -> None:
        stub = self.tmp / "bin" / "ai-rulez"
        stub.write_text("#!/bin/sh\nexit 1\n")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("gave no report", result.stdout)


if __name__ == "__main__":
    unittest.main()
