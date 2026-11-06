"""actions/context-exposure/gate.sh against a stub ai-rulez, and against the real one when it is installed."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parents[1] / "actions" / "context-exposure" / "gate.sh"
DOMAINS = '[domain.billing]\nterms = ["invoice"]\n\n[repos.app]\ndomains = []\n'

STUB = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    if args == ["--version"]:
        print("ai-rulez version " + os.environ.get("STUB_VERSION", "5.11.0"))
        sys.exit(0)
    with open(os.environ["STUB_LOG"], "a") as log:
        log.write(" ".join(args) + "\\n")
    harness = "codex" if "--harness" in args and args[args.index("--harness") + 1] == "codex" else "claude"
    if "leakage" in args:
        print("violations: 1" if os.environ.get("STUB_LEAK") else "violations: 0")
        sys.exit(2 if os.environ.get("STUB_LEAK") else 0)
    if "inventory" in args:
        description = "d" * int(os.environ.get("STUB_DESCRIPTION", "40"))
        skill = {"kind": "skill", "phase": "on_demand", "path": ".claude/skills/a/SKILL.md"}
        manual = {"kind": "skill", "phase": "manual", "path": ".claude/skills/m/SKILL.md"}
        skill["listing_text"] = "a: " + description
        manual["listing_text"] = "m: " + "d" * 400
        print(json.dumps({"artifacts": [skill, manual]}))
        sys.exit(0)
    if os.environ.get(f"STUB_{harness.upper()}_BROKEN"):
        sys.exit(1)
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


def harness_dir(root: Path) -> Path:
    domains = root / "harness"
    domains.mkdir()
    shutil.copy(HERE / "areas.py", domains / "areas.py")
    (domains / "domains.toml").write_text(DOMAINS, encoding="utf-8")
    return domains


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
        self.summary = self.tmp / "summary.md"
        self.log = self.tmp / "calls.log"
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HARNESS": str(harness_dir(self.tmp)),
            "REPO_NAME": "app",
            "SUMMARY": str(self.summary),
            "WORK": str(self.tmp),
            "STUB_LOG": str(self.log),
            "STUB_CLAUDE_BUDGET": "500",
            "STUB_CODEX_BUDGET": "500",
        }

    def run_gate(self, **env: str) -> subprocess.CompletedProcess[str]:
        merged = {key: value for key, value in {**self.env, **env}.items() if value is not None}
        return subprocess.run(
            ["bash", str(GATE)], env=merged, cwd=self.tmp, capture_output=True, text=True, check=False
        )

    def test_passes_within_both_budgets_without_leaks_and_runs_every_check(self) -> None:
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 6)
        self.assertTrue(any(c.startswith("exposure leakage --areas ") for c in calls))
        self.assertIn("exposure --harness codex", calls)
        self.assertIn("exposure inventory --format json", calls)
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

    def test_fails_on_a_listed_description_over_250_characters_but_not_a_manual_one(self) -> None:
        self.assertEqual(self.run_gate(STUB_DESCRIPTION="250").returncode, 0)
        result = self.run_gate(STUB_DESCRIPTION="400")
        self.assertEqual(result.returncode, 1)
        errors = [line for line in result.stdout.splitlines() if "over 250 characters" in line]
        self.assertEqual(
            errors, ["::error::listed description over 250 characters: .claude/skills/a/SKILL.md (400 characters)"]
        )

    def test_fails_below_the_minimum_ai_rulez_version(self) -> None:
        result = self.run_gate(STUB_VERSION="5.10.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::context-exposure needs ai-rulez >= 5.11.0, found 5.10.0", result.stdout)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.run_gate(STUB_VERSION="5.12.1").returncode, 0)

    def test_fails_closed_without_a_start_budget_and_warns_without_a_codex_budget(self) -> None:
        result = self.run_gate(STUB_CLAUDE_BUDGET="0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("start_budget is not set", result.stdout)
        result = self.run_gate(STUB_CODEX_BUDGET="0")
        self.assertEqual(result.returncode, 0)
        self.assertIn("::warning::[exposure] codex_start_budget is not set", result.stdout)

    def test_tells_a_missing_report_from_a_missing_budget(self) -> None:
        result = self.run_gate(STUB_CODEX_BROKEN="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::ai-rulez exposure --harness codex --format json gave no report", result.stdout)
        self.assertNotIn("codex_start_budget is not set", result.stdout)
        result = self.run_gate(STUB_CLAUDE_BROKEN="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::ai-rulez exposure --format json gave no report", result.stdout)

    def test_runs_without_a_summary_or_work_directory(self) -> None:
        result = self.run_gate(SUMMARY=None, WORK=None)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.summary.exists())

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


def installed_ai_rulez() -> str | None:
    """The ai-rulez on PATH when it is at least 5.11.0, the first release the gate supports."""
    binary = shutil.which("ai-rulez")
    if binary is None:
        return None
    output = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", output)
    return binary if match and tuple(map(int, match.groups())) >= (5, 11, 0) else None


@unittest.skipUnless(shutil.which("bash") and installed_ai_rulez(), "needs bash and ai-rulez >= 5.11.0 on PATH")
class RealAiRulezTest(unittest.TestCase):
    """Pins the flags and JSON fields gate.sh reads from ai-rulez itself."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        files = {
            ".ai-rulez/config.toml": 'version = "5.0"\nname = "app"\npresets = ["claude", "codex"]\n\n'
            "[exposure]\nstart_budget = 100000\ncodex_start_budget = 100000\n",
            "CLAUDE.md": "@AGENTS.md\n",
            "AGENTS.md": "# app\n\nKeep changes small.\n",
            ".claude/skills/lookup/SKILL.md": "---\nname: lookup\ndescription: Look things up.\n---\nbody\n",
            ".agents/skills/lookup/SKILL.md": "---\nname: lookup\ndescription: Look things up.\n---\nbody\n",
        }
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.env = {**os.environ, "HARNESS": str(harness_dir(self.tmp)), "REPO_NAME": "app", "WORK": str(self.tmp)}

    def ai_rulez(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([installed_ai_rulez(), *args], cwd=self.repo, capture_output=True, text=True, check=False)

    def run_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(GATE)], env=self.env, cwd=self.repo, capture_output=True, text=True, check=False
        )

    def test_reports_carry_the_fields_the_gate_reads(self) -> None:
        for harness, args in (("claude", []), ("codex", ["--harness", "codex"])):
            report = json.loads(self.ai_rulez("exposure", *args, "--format", "json").stdout)
            self.assertEqual((report["harness"], report["start_budget"]), (harness, 100000))
            self.assertGreater(report["start_tokens"], 0)
        artifacts = json.loads(self.ai_rulez("exposure", "inventory", "--format", "json").stdout)["artifacts"]
        skill = next(item for item in artifacts if item["kind"] == "skill")
        self.assertEqual((skill["phase"], skill["listing_text"]), ("start", "lookup: Look things up."))

    def test_the_gate_passes_a_clean_fixture_and_fails_each_check(self) -> None:
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        long = "d" * 400
        skill = self.repo / ".claude/skills/lookup/SKILL.md"
        skill.write_text(f"---\nname: lookup\ndescription: {long}\n---\nbody\n", encoding="utf-8")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("listed description over 250 characters", result.stdout)
        skill.write_text("---\nname: lookup\ndescription: Look things up.\n---\nbody\n", encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("# app\n\nSend the invoice.\n", encoding="utf-8")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("AR9W0 billing/invoice AGENTS.md:3", result.stdout)


if __name__ == "__main__":
    unittest.main()
