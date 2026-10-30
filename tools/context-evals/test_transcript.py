"""Tests for transcript.py against the recorded-style fixtures in testdata/transcripts."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import testkit
import transcript
from records import Loaded, Usage

CWD = "crates/xberg"
START = [
    Loaded("instructions", "CLAUDE.md", 0, 4),
    Loaded("instructions", "AGENTS.md", 0, 18),
    Loaded("rule", ".claude/rules/general.md", 0, 11),
    Loaded("instructions", "crates/xberg/CLAUDE.md", 0, 5),
]


class ParseTest(unittest.TestCase):
    def test_skill_session_init_calls_usage_and_turns(self) -> None:
        t = transcript.parse(testkit.transcript_text("skill_used"))
        self.assertEqual(t.cwd, "/work/xberg/crates/xberg")
        self.assertEqual(t.tools, ["Read", "Glob", "Grep", "Skill"])
        self.assertEqual(
            (t.listed_skills, t.listed_agents, t.mcp_servers),
            (["ocr-pipeline-and-quality", "crawl-tuning"], ["reviewer"], []),
        )
        self.assertEqual(t.skills_used(), [("ocr-pipeline-and-quality", 1)])
        self.assertEqual(t.assistant_turns, 2)
        self.assertEqual(t.first_usage, Usage(12, 3000, 9000, 40))
        self.assertEqual(t.usage, Usage(30, 3500, 21000, 220))
        self.assertEqual((t.cost_usd, t.turns, t.error), (0.0421, 3, ""))
        self.assertEqual(t.answer, "The default OCR DPI is 300; xberg renders pages with Tesseract at that resolution.")

    def test_reads_keep_order_turn_and_returned_size(self) -> None:
        t = transcript.parse(testkit.transcript_text("nested_claude_md"))
        self.assertEqual(t.reads(), [("/work/xberg/crates/xberg/src/ocr/mod.rs", 1, 392), ("src/ocr/mod.rs", 2, 33)])

    def test_error_result_is_reported(self) -> None:
        t = transcript.parse(testkit.transcript_text("error"))
        self.assertEqual((t.error, t.answer, t.turns), ("error_max_turns", "", 2))

    def test_missing_result_event_is_an_error_and_keeps_last_text(self) -> None:
        text = "\n".join(testkit.transcript_text("skill_used").splitlines()[:-1])
        t = transcript.parse(text)
        self.assertEqual(t.error, "no result event")
        self.assertEqual(t.answer, "The default OCR DPI is 300; xberg renders pages with Tesseract at that resolution.")

    def test_skill_name_is_read_from_command_or_name_too(self) -> None:
        line = '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"a","name":"Skill","input":%s}]}}'
        text = "\n".join([line % '{"command": "/one"}', line % '{"name": "two"}', line % "{}"])
        self.assertEqual(transcript.parse(text).skills_used(), [("one", 1), ("two", 2)])


class AskedTest(unittest.TestCase):
    def test_clarifying_question_is_an_ask(self) -> None:
        t = transcript.parse(testkit.transcript_text("asking"))
        self.assertTrue(transcript.asked(t.answer))

    def test_answers_offers_and_rhetoric_are_not_asks(self) -> None:
        self.assertFalse(transcript.asked("The DPI is 300."))
        self.assertFalse(transcript.asked("The DPI is 300.\n\nWould you like me to change it for the PDF path?"))
        self.assertFalse(transcript.asked("Why is it 300? Because Tesseract prefers it."))
        self.assertFalse(transcript.asked("Is 300 the right value?"))
        self.assertTrue(transcript.asked("Could you clarify which crate you mean?"))
        self.assertTrue(transcript.asked("Which repository are you asking about?**"))
        self.assertFalse(transcript.asked(""))


class PathTest(unittest.TestCase):
    def test_repo_relative_normalises_and_keeps_outside_paths_absolute(self) -> None:
        cwd, root = "/work/xberg/crates/xberg", "/work/xberg"
        self.assertEqual(
            transcript.repo_relative("./src/web/../web/fetch.rs", cwd, root), "crates/xberg/src/web/fetch.rs"
        )
        self.assertEqual(transcript.repo_relative("/work/xberg/AGENTS.md", cwd, root), "AGENTS.md")
        self.assertEqual(transcript.repo_relative("/etc/hosts", cwd, root), "/etc/hosts")
        self.assertEqual(transcript.repo_relative("../../../other/x", cwd, root), "/work/other/x")

    def test_session_root_strips_the_case_cwd(self) -> None:
        t = transcript.parse(testkit.transcript_text("skill_used"))
        self.assertEqual(transcript.session_root(t, CWD), "/work/xberg")
        self.assertEqual(transcript.session_root(t, "."), "/work/xberg/crates/xberg")
        self.assertEqual(transcript.session_root(t, "elsewhere"), "/work/xberg/crates/xberg")

    def test_glob_regex(self) -> None:
        self.assertTrue(transcript.glob_regex("crates/**").match("crates/a/b.rs"))
        self.assertTrue(transcript.glob_regex("**/*.rs").match("lib.rs"))
        self.assertTrue(transcript.glob_regex("src/*.{rs,toml}").match("src/Cargo.toml"))
        self.assertFalse(transcript.glob_regex("src/*.rs").match("src/a/b.rs"))
        self.assertFalse(transcript.glob_regex("src/?.rs").match("src/ab.rs"))

    def test_contamination_flags_harness_and_run_dir_paths(self) -> None:
        t = transcript.parse(testkit.transcript_text("contamination"))
        self.assertEqual(
            transcript.contaminated(t, "/work/xberg", "/runs/r1"),
            ["tools/context-evals/cases/xberg/xberg.yaml", "/runs/r1/transcripts"],
        )
        clean = transcript.parse(testkit.transcript_text("nested_claude_md"))
        self.assertEqual(transcript.contaminated(clean, "/work/xberg", "/runs/r1"), [])


class InventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = testkit.make_checkout(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def inventory(self, name: str, cwd: str = CWD) -> list[Loaded]:
        return transcript.inventory(transcript.parse(testkit.transcript_text(name)), self.repo, cwd)

    def test_skill_enters_on_invocation(self) -> None:
        self.assertEqual(self.inventory("skill_used"), [*START, Loaded("skill", "ocr-pipeline-and-quality", 1, 38)])

    def test_read_triggers_scoped_rule_and_nested_claude_md_once(self) -> None:
        self.assertEqual(
            self.inventory("nested_claude_md"),
            [
                *START,
                Loaded("file", "crates/xberg/src/ocr/mod.rs", 1, 147),
                Loaded("rule", ".claude/rules/ocr-scoped.md", 1, 28),
                Loaded("instructions", "crates/xberg/src/ocr/CLAUDE.md", 1, 7),
                Loaded("file", "crates/xberg/src/ocr/mod.rs", 2, 12),
            ],
        )

    def test_string_paths_scope_and_relative_reads(self) -> None:
        self.assertEqual(
            self.inventory("scoped_rule"),
            [
                *START,
                Loaded("file", "crates/xberg/src/web/fetch.rs", 2, 29),
                Loaded("rule", ".claude/rules/web-scoped.md", 2, 26),
            ],
        )

    def test_root_start_has_no_nested_instructions(self) -> None:
        self.assertEqual(self.inventory("asking", "."), START[:3])


if __name__ == "__main__":
    unittest.main()
