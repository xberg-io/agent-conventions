"""Tests for judge.py with rule-based fake graders."""

from __future__ import annotations

import json
import re
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cases
import judge
import runner
import testkit
from records import Loaded, SessionRecord

RULES = {
    "names-dpi-default": r"OCR DPI is 300",
    "names-engine": r"(?i)tesseract",
    "names-file": r"crates/xberg/src/ocr/mod\.rs",
}
ANSWER = re.compile(r"<answer>\n(.*)\n</answer>|<<<\n(.*)\n>>>", re.DOTALL)


class RuleGrader:
    """Decides each criterion by a regex over the answer it finds in either prompt layout."""

    def __init__(self, rules: dict[str, str | None], wrap: str = "{}") -> None:
        self.rules, self.wrap, self.prompts = rules, wrap, []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        match = ANSWER.search(prompt)
        answer = next(g for g in match.groups() if g is not None) if match else ""
        verdicts = {cid: None if rule is None else bool(re.search(rule, answer)) for cid, rule in self.rules.items()}
        return self.wrap.format(json.dumps({"verdicts": verdicts}))


def record(case_id: str, repeat: int, answer: str, domain: str = "xberg", error: str = "") -> SessionRecord:
    return SessionRecord(
        run_id="r",
        case_id=case_id,
        domain=domain,
        cluster=domain,
        repeat=repeat,
        split="tune",
        behaviour="answer",
        asked=False,
        criteria={c.id: None for c in CORPUS[case_id].criteria} if case_id in CORPUS else {},
        answer=answer,
        error=error,
        skills_used=["ocr-pipeline-and-quality"],
        loaded=[Loaded("file", "crates/xberg/src/ocr/mod.rs", 1)],
        turns=3,
    )


CORPUS = {c.id: c for c in cases.load_corpus(testkit.CASES, testkit.domains())}
DPI = CORPUS["xberg-ocr-dpi"]
MODULE = CORPUS["xberg-ocr-module"]


class ParseTest(unittest.TestCase):
    def test_strict_verdict_parsing(self) -> None:
        ids = ["a", "b", "c"]
        fenced = '```json\n{"verdicts": {"a": true, "b": false, "c": null, "d": true}}\n```'
        self.assertEqual(judge.parse_verdicts(fenced, ids), {"a": True, "b": False, "c": None})
        self.assertEqual(
            judge.parse_verdicts('{"verdicts": {"a": "yes", "b": 1}}', ids), {"a": None, "b": None, "c": None}
        )
        self.assertEqual(judge.parse_verdicts('{"a": true}', ids), {"a": None, "b": None, "c": None})
        self.assertEqual(judge.parse_verdicts("I think yes", ids), {"a": None, "b": None, "c": None})
        self.assertEqual(judge.parse_verdicts("{not json}", ids), {"a": None, "b": None, "c": None})


class PromptTest(unittest.TestCase):
    def test_prompts_carry_case_reference_answer_and_differ(self) -> None:
        primary = judge.primary_prompt(DPI, "It is 300.", "skills used: x")
        independent = judge.independent_prompt(DPI, "It is 300.", "")
        for text in (primary, independent):
            self.assertIn("- names-dpi-default: The answer states that the default OCR DPI is 300.", text)
            self.assertIn("- The default OCR DPI is 300.", text)
            self.assertIn("Sources: crates/xberg/src/ocr/mod.rs", text)
            self.assertIn("Grade the result the answer gives.", text)
        self.assertIn("<answer>\nIt is 300.\n</answer>", primary)
        self.assertIn("<<<\nIt is 300.\n>>>", independent)
        self.assertNotEqual(primary, independent)
        procedure = judge.primary_prompt(CORPUS["xberg-dpi-ambiguous"], "a", "")
        self.assertIn("grade the procedure, not the data", procedure)

    def test_summary_lists_skills_files_and_turns(self) -> None:
        self.assertEqual(
            judge.summary(record("xberg-ocr-dpi", 0, "a")),
            "skills used: ocr-pipeline-and-quality\nfiles read: crates/xberg/src/ocr/mod.rs\nturns: 3",
        )


class MutationTest(unittest.TestCase):
    def test_mutants_of_the_reference_answers(self) -> None:
        domains = testkit.domains()
        self.assertEqual(judge.reference_answer(DPI), "The default OCR DPI is 300. OCR uses Tesseract.")
        self.assertEqual(
            judge.mutants(judge.reference_answer(DPI), DPI, domains),
            {
                "drop-fact": "OCR uses Tesseract.",
                "swap-domain": "The default crawlberg DPI is 300. crawlberg uses Tesseract.",
                "tool-deflection": "Use tool X to find this out.",
            },
        )
        self.assertEqual(
            judge.mutants(judge.reference_answer(MODULE), MODULE, domains),
            {
                "drop-fact": "",
                "swap-domain": "DEFAULT_DPI is defined in crates/crawlberg/src/crawlberg/mod.rs.",
                "tool-deflection": "Use tool X to find this out.",
                "wrong-path": "DEFAULT_DPI is defined in src/nonexistent/wrong_module.rs.",
            },
        )

    def test_mutations_that_do_not_apply_are_skipped(self) -> None:
        self.assertIsNone(judge.drop_fact("Nothing relevant here.", ("The DPI is 300.",)))
        self.assertIsNone(judge.drop_fact("x", ()))
        self.assertIsNone(judge.wrong_path("no path at all"))
        self.assertIsNone(judge.swap_domain("no domain words", DPI, testkit.domains()))


class ValidateTest(unittest.TestCase):
    def sessions(self) -> list[SessionRecord]:
        return [
            record("xberg-ocr-dpi", 0, "The default OCR DPI is 300, rendered by Tesseract."),
            record("xberg-ocr-dpi", 1, "It renders at 72 DPI."),
            record("xberg-ocr-dpi", 2, "boom", error="timeout"),
            record("xberg-ocr-module", 0, "See crates/xberg/src/ocr/mod.rs."),
        ]

    def test_agreeing_graders_validate_criteria_and_pass_mutation_tests(self) -> None:
        primary, secondary = RuleGrader(RULES), RuleGrader(RULES, wrap="Sure.\n{}")
        report = judge.validate(self.sessions(), CORPUS, primary, secondary, testkit.domains())
        self.assertEqual(
            report["criteria"],
            {
                "xberg-ocr-dpi/names-dpi-default": {"kappa": 1.0, "items": 6, "decided": 6, "valid": True},
                "xberg-ocr-dpi/names-engine": {"kappa": 1.0, "items": 6, "decided": 6, "valid": True},
                "xberg-ocr-module/names-file": {"kappa": 1.0, "items": 6, "decided": 6, "valid": True},
            },
        )
        self.assertEqual(report["mutation"]["tpr"], 1.0)
        self.assertEqual((report["mutation"]["tnr"], report["mutation"]["mutants"]), (1.0, 7))
        self.assertEqual(report["mutation"]["by_kind"]["drop-fact"], {"tnr": 1.0, "mutants": 2})
        self.assertEqual(report["mutation"]["by_kind"]["swap-domain"], {"tnr": 1.0, "mutants": 2})
        self.assertTrue(report["judge_valid"])
        # 3 sessions that ran + 2 reference answers + 7 mutants, each graded once by each grader
        self.assertEqual((len(primary.prompts), len(secondary.prompts)), (12, 12))
        self.assertIn("Statements:", secondary.prompts[0])

    def test_disagreement_and_abstention_invalidate_criteria(self) -> None:
        contrary = {**RULES, "names-engine": r"(?i)^(?!.*tesseract)", "names-file": None}
        report = judge.validate(self.sessions(), CORPUS, RuleGrader(RULES), RuleGrader(contrary), testkit.domains())
        self.assertEqual(report["valid_criteria"], ["xberg-ocr-dpi/names-dpi-default"])
        engine = report["criteria"]["xberg-ocr-dpi/names-engine"]
        # primary T F T T T F, secondary the opposite: po 0, pe 16/36 -> kappa -0.8
        self.assertAlmostEqual(engine["kappa"], -0.8)
        self.assertEqual((engine["decided"], engine["valid"]), (6, False))
        self.assertEqual(report["criteria"]["xberg-ocr-module/names-file"],
                         {"kappa": None, "items": 6, "decided": 0, "valid": False})  # fmt: skip

    def test_lenient_judge_fails_mutation_tests(self) -> None:
        always = {k: r"" for k in RULES}
        report = judge.validate(self.sessions(), CORPUS, RuleGrader(always), RuleGrader(always), testkit.domains())
        self.assertEqual(
            (report["mutation"]["tpr"], report["mutation"]["tnr"], report["judge_valid"]), (1.0, 0.0, False)
        )
        self.assertIn("Judge valid: no.", judge.validity_markdown(report))
        self.assertIn("| tool-deflection | 0.00 | 2 |", judge.validity_markdown(report))

    def test_stratified_sample_caps_each_domain_and_prefers_first_repeats(self) -> None:
        records = [record(f"c{i}", k, "a", domain=d) for d in ("x", "y") for i in range(3) for k in range(2)]
        sample = judge.stratified_sample(records, 3, seed=1)
        self.assertEqual([(r.domain, r.repeat) for r in sample], [("x", 0)] * 3 + [("y", 0)] * 3)
        self.assertEqual(sorted(r.case_id for r in sample[:3]), ["c0", "c1", "c2"])
        self.assertEqual(judge.stratified_sample(records, 3, seed=1), sample)


class JudgeSessionsTest(unittest.TestCase):
    def test_rows_carry_versions_and_apply_masks_unvalidated_criteria(self) -> None:
        sessions = ValidateTest().sessions()
        rows = judge.judge_sessions(sessions, CORPUS, RuleGrader(RULES), "judge-m")
        self.assertEqual([(r["case_id"], r["repeat"]) for r in rows], [
            ("xberg-ocr-dpi", 0), ("xberg-ocr-dpi", 1), ("xberg-ocr-module", 0)])  # fmt: skip
        self.assertEqual(rows[0]["verdicts"], {"names-dpi-default": True, "names-engine": True})
        self.assertEqual(
            {k: rows[0][k] for k in ("judge_model", "judge_prompt_version", "rubric_version")},
            {"judge_model": "judge-m", "judge_prompt_version": "judge-prompt-1", "rubric_version": "rubric-1"},
        )
        judge.apply(sessions, rows, {"xberg-ocr-dpi/names-engine", "xberg-ocr-module/names-file"})
        self.assertEqual([s.criteria for s in sessions], [
            {"names-dpi-default": None, "names-engine": True},
            {"names-dpi-default": None, "names-engine": False},
            {"names-dpi-default": None, "names-engine": None},
            {"names-file": True},
        ])  # fmt: skip


class ClaudeGraderTest(unittest.TestCase):
    def test_hermetic_invocation_and_result_extraction(self) -> None:
        seen = {}

        def fake(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
            seen.update(argv=argv, cwd=cwd, env=dict(env))
            return runner.Completed(0, json.dumps({"type": "result", "result": '{"verdicts": {}}'}), "")

        env = {"PATH": "/bin", "ANTHROPIC_API_KEY": "k", "HOME": "/home/dev"}
        grader = judge.ClaudeGrader("judge-m", execute=fake, environ=env)
        self.assertEqual(grader("hello"), '{"verdicts": {}}')
        mcp = seen["argv"][seen["argv"].index("--mcp-config") + 1]
        self.assertEqual(seen["argv"], [
            "claude", "-p", "hello", "--output-format", "json", "--model", "judge-m", "--max-turns", "1",
            "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", mcp,
        ])  # fmt: skip
        self.assertEqual(seen["env"]["HOME"], str(seen["cwd"]))
        self.assertEqual(set(seen["env"]), {"PATH", "ANTHROPIC_API_KEY", "HOME", "CLAUDE_CONFIG_DIR"})
        broken = judge.ClaudeGrader("m", execute=lambda *a: runner.Completed(1, "oops", ""), environ=env)
        self.assertEqual(broken("x"), "")
        with self.assertRaises(runner.RunnerError):
            judge.ClaudeGrader("m", execute=fake, environ={**env, "CLAUDECODE": "1"})
        with self.assertRaises(runner.RunnerError):
            judge.ClaudeGrader("", execute=fake, environ=env)


if __name__ == "__main__":
    unittest.main()
