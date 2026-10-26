"""Tests for runner.py with a real throwaway git repository and a fake agent process."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import runner
import testkit

ENV = {"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "test-key", "HOME": "/home/dev", "SECRET_TOKEN": "x"}


def git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


class FakeAgent:
    """Records each call; the agent call dirties the tree so the reset is observable."""

    def __init__(self, timeout_case: str = "") -> None:
        self.calls: list[dict] = []
        self.timeout_case = timeout_case

    def __call__(self, argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        root = Path(env.get("CLAUDE_CONFIG_DIR", cwd))
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "env": dict(env),
                "timeout": timeout,
                "stray_before": any(p.name == "stray.txt" for p in cwd.rglob("stray.txt")),
                "mod_before": (cwd / "src/ocr/mod.rs").read_text() if (cwd / "src/ocr/mod.rs").exists() else "",
                "home_exists": root.is_dir(),
                "mcp": (root / "mcp.json").read_text() if (root / "mcp.json").exists() else "",
            }
        )
        if argv[0] == "ai-rulez":
            return runner.Completed(0, "", "")
        (cwd / "stray.txt").write_text("x")
        if (cwd / "src/ocr/mod.rs").exists():
            (cwd / "src/ocr/mod.rs").write_text("changed\n")
        if argv[2] == self.timeout_case:
            return runner.Completed(-1, '{"type":"system"}\n', "slow", timed_out=True)
        return runner.Completed(0, testkit.transcript_text("skill_used"), "warn\n")


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = testkit.make_checkout(base / "xberg")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self.commit = git(self.repo, "rev-parse", "HEAD")
        self.out = base / "run"
        corpus = {c.id: c for c in cases.load_corpus(testkit.CASES, testkit.domains())}
        self.cases = [corpus["xberg-ocr-dpi"], corpus["xberg-dpi-ambiguous"]]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make(self, fake: FakeAgent, generate: bool = True, environ: Mapping[str, str] = ENV) -> runner.Runner:
        config = runner.RunConfig(model="m-1", max_turns=7, timeout=30, repeats=2, generate=generate)
        return runner.Runner(self.repo, self.out, config, execute=fake, environ=environ)

    def test_sessions_are_hermetic_reset_and_cleaned_up(self) -> None:
        fake = FakeAgent()
        metas = self.make(fake).run(runner.resolve_ref(self.repo, "main"), self.cases)
        agent = [c for c in fake.calls if c["argv"][0] == "claude"]
        generate = [c for c in fake.calls if c["argv"][0] == "ai-rulez"]
        self.assertEqual((len(agent), len(generate)), (4, 5))
        self.assertEqual(generate[0]["argv"], ["ai-rulez", "generate", "--no-local"])
        self.assertEqual(set(generate[0]["env"]), {"PATH", "HOME"})
        first = agent[0]
        mcp_path = first["argv"][first["argv"].index("--mcp-config") + 1]
        self.assertEqual(
            first["argv"],
            [
                "claude", "-p", "What DPI does OCR render pages at by default?", "--output-format", "stream-json",
                "--verbose", "--model", "m-1", "--max-turns", "7", "--setting-sources", "project",
                "--strict-mcp-config", "--mcp-config", mcp_path, "--allowedTools", "Read,Glob,Grep,Skill",
            ],
        )  # fmt: skip
        self.assertEqual(json.loads(first["mcp"]), {"mcpServers": {}})
        self.assertEqual(set(first["env"]), {"PATH", "ANTHROPIC_API_KEY", "HOME", "CLAUDE_CONFIG_DIR"})
        self.assertEqual(first["env"]["HOME"], first["env"]["CLAUDE_CONFIG_DIR"])
        self.assertEqual(len({c["env"]["HOME"] for c in agent}), 4)
        self.assertFalse(any(Path(c["env"]["HOME"]).exists() for c in agent))
        self.assertEqual(first["timeout"], 30)
        self.assertEqual(first["cwd"].name, "xberg")
        self.assertEqual(first["cwd"].parent.name, "crates")
        self.assertEqual(agent[2]["cwd"], first["cwd"].parent.parent)
        self.assertEqual([c["stray_before"] for c in agent], [False, False, False, False])
        self.assertEqual([c["mod_before"] for c in agent[:2]], [testkit.FILES["crates/xberg/src/ocr/mod.rs"]] * 2)
        checkout = first["cwd"].parent.parent
        self.assertFalse(checkout.exists())
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual([(m.case_id, m.repeat, m.error, m.returncode) for m in metas], [
            ("xberg-ocr-dpi", 0, "", 0), ("xberg-ocr-dpi", 1, "", 0),
            ("xberg-dpi-ambiguous", 0, "", 0), ("xberg-dpi-ambiguous", 1, "", 0),
        ])  # fmt: skip
        self.assertEqual(metas[0].root, str(checkout))
        saved = self.out / "transcripts" / "xberg-ocr-dpi.r1.jsonl"
        self.assertEqual(saved.read_text(), testkit.transcript_text("skill_used"))
        self.assertEqual(runner.read_meta(self.out / "transcripts", "xberg-ocr-dpi", 1), metas[1])
        self.assertEqual(
            sorted(str(p.relative_to(self.out / "context")) for p in (self.out / "context").rglob("*") if p.is_file()),
            sorted(k for k in testkit.FILES if k.endswith(".md")),
        )

    def test_skip_generate_timeout_and_missing_cwd(self) -> None:
        fake = FakeAgent(timeout_case="Which DPI should I use?")
        missing = cases.Case(**{**self.cases[0].__dict__, "id": "xberg-gone", "cwd": "crates/gone"})
        metas = self.make(fake, generate=False).run(self.commit, [*self.cases, missing])
        self.assertEqual([c["argv"][0] for c in fake.calls], ["claude"] * 4)
        self.assertEqual(
            [(m.case_id, m.error) for m in metas],
            [
                ("xberg-ocr-dpi", ""),
                ("xberg-ocr-dpi", ""),
                ("xberg-dpi-ambiguous", "timeout"),
                ("xberg-dpi-ambiguous", "timeout"),
                ("xberg-gone", "cwd 'crates/gone' does not exist at this ref"),
                ("xberg-gone", "cwd 'crates/gone' does not exist at this ref"),
            ],
        )
        self.assertEqual(metas[2].stderr, "slow")
        self.assertEqual((self.out / "transcripts" / "xberg-gone.r0.jsonl").read_text(), "")

    def test_refuses_nested_session_missing_key_and_missing_model(self) -> None:
        fake = FakeAgent()
        with self.assertRaisesRegex(runner.RunnerError, "CLAUDECODE"):
            self.make(fake, environ={**ENV, "CLAUDECODE": "1"}).run(self.commit, self.cases)
        with self.assertRaisesRegex(runner.RunnerError, "ANTHROPIC_API_KEY"):
            self.make(fake, environ={"PATH": "/bin"}).run(self.commit, self.cases)
        self.assertEqual(fake.calls, [])
        with self.assertRaisesRegex(runner.RunnerError, "model is required"):
            runner.RunConfig(model="")

    def test_failed_generate_aborts_and_still_removes_the_worktree(self) -> None:
        def failing(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            return runner.Completed(2, "", "boom")

        config = runner.RunConfig(model="m")
        with self.assertRaisesRegex(runner.RunnerError, "ai-rulez generate failed: boom"):
            runner.Runner(self.repo, self.out, config, execute=failing, environ=ENV).run(self.commit, self.cases)
        self.assertEqual(len(git(self.repo, "worktree", "list").splitlines()), 1)

    def test_unknown_ref_is_an_error(self) -> None:
        with self.assertRaises(runner.RunnerError):
            runner.resolve_ref(self.repo, "no-such-ref")


if __name__ == "__main__":
    unittest.main()
