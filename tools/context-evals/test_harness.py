"""End-to-end tests for harness.py: a real throwaway repository, a fake agent and fake graders."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import harness
import records
import runner
import testkit
from test_judge import RULES, RuleGrader
from test_runner import ENV, git

BASE = {
    "Where is DEFAULT_DPI defined in this crate?": "nested_claude_md",
    "Where is fetch() implemented?": "scoped_rule",
    "Which DPI should I use?": "asking",
    "What DPI does OCR render pages at by default?": "skill_used",
}
ARM = {**BASE, "Where is DEFAULT_DPI defined in this crate?": "skill_used"}


def agent(script: dict[str, str]) -> runner.Execute:
    """Replays a fixture per prompt, rewritten to the worktree the session really ran in."""

    def execute(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float) -> runner.Completed:
        root = next(p for p in [cwd, *cwd.parents] if (p / ".git").exists())
        text = testkit.transcript_text(script[argv[2]]).replace(testkit.RUN_ROOT, str(root))
        return runner.Completed(0, text, "")

    return execute


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = testkit.make_checkout(self.base / "xberg")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def main(self, *argv: str, script: dict[str, str] = BASE, environ: Mapping[str, str] = ENV) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = harness.main(
                ["--cases-dir", str(testkit.CASES), *argv],
                execute=agent(script),
                environ=environ,
                grader_factory=lambda model: RuleGrader(RULES),
            )
        return code, out.getvalue(), err.getvalue()

    def run_harness(self, name: str, script: dict[str, str] = BASE, *extra: str) -> Path:
        out = self.base / name
        code, _, err = self.main(
            "run", "--repo", str(self.repo), "--ref", "main", "--model", "m-1", "--repeats", "2",
            "--skip-generate", "--out", str(out), *extra, script=script,
        )  # fmt: skip
        self.assertEqual((code, err), (0, ""))
        return out

    def test_paid_cli_requires_explicit_prospective_budget_consent(self) -> None:
        def forbidden_execute(*_args):
            raise AssertionError("paid executor must not run")

        with patch.object(runner, "subprocess_execute", forbidden_execute):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = harness.main(
                    [
                        "run",
                        "--repo",
                        str(self.repo),
                        "--ref",
                        "main",
                        "--model",
                        "m",
                        "--skip-generate",
                        "--out",
                        str(self.base / "unbounded"),
                    ],
                    execute=forbidden_execute,
                    environ=ENV,
                )
        self.assertEqual(code, 2)
        self.assertIn("hard dollar ceiling", err.getvalue())

    def test_validate_cases(self) -> None:
        self.assertEqual(self.main("validate-cases")[:2], (0, "4 cases (3 tune, 1 holdout), 0 checkout errors\n"))
        self.assertEqual(self.main("validate-cases", "--repo-root", str(self.repo))[0], 0)
        (self.repo / "crates/xberg/src/web/fetch.rs").unlink()
        code, out, err = self.main("validate-cases", "--repo-root", str(self.repo))
        self.assertEqual((code, out), (1, "4 cases (3 tune, 1 holdout), 1 checkout errors\n"))
        self.assertIn("reference source 'crates/xberg/src/web/fetch.rs' does not exist", err)
        self.assertEqual(self.main("validate-cases", "--repo-root", str(self.repo), "--repo", "crawlberg")[0], 0)
        empty = harness.main(["--cases-dir", str(self.base / "none"), "validate-cases"])
        self.assertEqual(empty, 1)

    def test_run_scores_tune_split_by_default(self) -> None:
        out = self.run_harness("run")
        meta = json.loads((out / "run.json").read_text())
        self.assertEqual(meta["cases"], ["xberg-ocr-module", "xberg-fetch-location", "xberg-dpi-ambiguous"])
        self.assertEqual(
            {
                k: meta[k]
                for k in ("repo", "ref", "model", "split", "repeats", "judge_prompt_version", "rubric_version")
            },
            {
                "repo": "xberg",
                "ref": "main",
                "model": "m-1",
                "split": "tune",
                "repeats": 2,
                "judge_prompt_version": "judge-prompt-1",
                "rubric_version": "rubric-2",
            },
        )
        self.assertEqual(meta["commit"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(len(meta["case_corpus_hash"]), 64)
        sessions = records.read_sessions(out / "sessions.jsonl")
        self.assertEqual([(s.case_id, s.repeat) for s in sessions], [
            ("xberg-ocr-module", 0), ("xberg-ocr-module", 1), ("xberg-fetch-location", 0),
            ("xberg-fetch-location", 1), ("xberg-dpi-ambiguous", 0), ("xberg-dpi-ambiguous", 1),
        ])  # fmt: skip
        module, fetch, ask = sessions[0], sessions[2], sessions[4]
        self.assertEqual(
            [(i.kind, i.name, i.turn) for i in module.loaded[4:]],
            [
                ("file", "crates/xberg/src/ocr/mod.rs", 1),
                ("rule", ".claude/rules/ocr-scoped.md", 1),
                ("instructions", "crates/xberg/src/ocr/CLAUDE.md", 1),
                ("file", "crates/xberg/src/ocr/mod.rs", 2),
            ],
        )
        self.assertEqual(
            (module.must_use_missed, module.expect_pass, module.error), (["ocr-pipeline-and-quality"], True, "")
        )
        self.assertEqual(fetch.leaked_artifacts, [".claude/rules/web-scoped.md"])
        self.assertEqual((ask.asked, ask.behaviour_ok), (True, True))

    def test_holdout_is_explicit_and_runs_refuse_reuse_and_nesting(self) -> None:
        out = self.run_harness("hold", BASE, "--split", "holdout")
        self.assertEqual(json.loads((out / "run.json").read_text())["cases"], ["xberg-ocr-dpi"])
        code, _, err = self.main(
            "run", "--repo", str(self.repo), "--ref", "main", "--model", "m", "--skip-generate", "--out", str(out)
        )
        self.assertEqual(code, 2)
        self.assertIn("is not empty", err)
        code, _, err = self.main(
            "run", "--repo", str(self.repo), "--ref", "main", "--model", "m", "--skip-generate",
            "--out", str(self.base / "nested"), environ={**ENV, "CLAUDECODE": "1"},
        )  # fmt: skip
        self.assertEqual(
            (code, err), (2, "error: refusing to run inside another Claude Code session (CLAUDECODE is set)\n")
        )
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            harness.main(["run", "--repo", str(self.repo), "--ref", "main", "--out", str(self.base / "x")])

    def test_incomplete_run_cannot_report_a_successful_score(self) -> None:
        out = self.run_harness("missing-transcript")
        transcript = next((out / "transcripts").glob("*.jsonl"))
        transcript.unlink()
        code, _, err = self.main("score", str(out))
        self.assertEqual(code, 2)
        self.assertIn("expected 6 sessions, found 5", err)

    def test_judge_masks_until_validated_then_report(self) -> None:
        out = self.run_harness("hold", BASE, "--split", "holdout")
        code, stdout, err = self.main("judge", str(out), "--model", "judge-m")
        self.assertEqual((code, stdout), (0, "graded 2 sessions\n"))
        self.assertIn("criteria stay None", err)
        sessions = records.read_sessions(out / "sessions.jsonl")
        self.assertEqual(sessions[0].criteria, {"names-dpi-default": None, "names-engine": None})
        self.assertEqual(json.loads((out / "run.json").read_text())["judge_model"], "judge-m")

        code, stdout, _ = self.main("judge-validate", str(out), "--model", "judge-m", "--second-model", "judge-n")
        self.assertEqual((code, stdout), (0, "2/2 criteria valid; judge valid: yes\n"))
        sessions = records.read_sessions(out / "sessions.jsonl")
        # The fixture answer says "OCR DPI is 300" and names Tesseract.
        self.assertEqual(sessions[0].criteria, {"names-dpi-default": True, "names-engine": True})
        self.assertTrue((out / "judge" / "validity.md").read_text().startswith("# Judge validity\n"))

        self.assertEqual(self.main("score", str(out))[0], 0)
        rescored = records.read_sessions(out / "sessions.jsonl")
        self.assertEqual(rescored[1].criteria, {"names-dpi-default": True, "names-engine": True})

        code, stdout, _ = self.main("report", str(out))
        self.assertEqual(code, 0)
        self.assertIn("| criteria_pass_rate | 1.000 [1.000, 1.000] (1) | 1.000 [1.000, 1.000] (1) |", stdout)
        self.assertIn("| sessions (failed) | 2 (0) | 2 (0) |", stdout)
        report = json.loads((out / "report.json").read_text())
        self.assertEqual(report["summary"]["overall"]["metrics"]["skill_recall"]["mean"], 1.0)
        self.assertEqual(report["judge_validity"]["models"], {"primary": "judge-m", "secondary": "judge-n"})

    def test_resume_preserves_the_model_that_graded_existing_verdicts(self) -> None:
        out = self.run_harness("resume-judge")
        self.main("judge", str(out), "--model", "judge-original")
        self.run_harness("resume-judge", BASE, "--resume")
        self.assertEqual(json.loads((out / "run.json").read_text())["judge_model"], "judge-original")
        reasons = harness.comparable(
            json.loads((out / "run.json").read_text()),
            {**json.loads((out / "run.json").read_text()), "judge_model": "judge-other"},
        )
        self.assertIn("judge_model: 'judge-original' != 'judge-other'", reasons)

    def test_mixed_stale_verdict_versions_cannot_use_current_validity(self) -> None:
        out = self.run_harness("stale-verdicts", BASE, "--split", "holdout")
        self.main("judge-validate", str(out), "--model", "judge-m", "--second-model", "judge-n")
        self.main("judge", str(out), "--model", "judge-m")
        path = out / "judge/verdicts.jsonl"
        original = [json.loads(line) for line in path.read_text().splitlines()]
        for key in ("rubric_version", "judge_prompt_version"):
            with self.subTest(version=key):
                rows = [dict(row) for row in original]
                rows[0][key] = "legacy"
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                self.assertEqual(self.main("score", str(out))[0], 0)
                self.assertEqual(
                    records.read_sessions(out / "sessions.jsonl")[0].criteria,
                    {"names-dpi-default": None, "names-engine": None},
                )

    def test_validity_for_another_judge_model_is_not_applied(self) -> None:
        out = self.run_harness("hold", BASE, "--split", "holdout")
        self.main("judge-validate", str(out), "--model", "judge-m", "--second-model", "judge-n")
        code, _, err = self.main("judge", str(out), "--model", "other-judge")
        self.assertEqual(code, 0)
        self.assertIn("validity report is for another judge", err)
        self.assertEqual(
            records.read_sessions(out / "sessions.jsonl")[0].criteria, {"names-dpi-default": None, "names-engine": None}
        )

    def test_failed_mutation_validation_keeps_criteria_unscored(self) -> None:
        out = self.run_harness("invalid-judge", BASE, "--split", "holdout")
        self.main("judge-validate", str(out), "--model", "judge-m", "--second-model", "judge-n")
        path = out / "judge/validity.json"
        validity = json.loads(path.read_text())
        path.write_text(json.dumps({**validity, "judge_valid": False}))
        self.main("judge", str(out), "--model", "judge-m")
        self.assertEqual(
            records.read_sessions(out / "sessions.jsonl")[0].criteria, {"names-dpi-default": None, "names-engine": None}
        )

    def test_paid_judging_refuses_legacy_rubric_without_migration(self) -> None:
        out = self.run_harness("legacy-rubric")
        path = out / "run.json"
        meta = json.loads(path.read_text())
        path.write_text(json.dumps({**meta, "rubric_version": "legacy"}))
        for command in ("judge", "judge-validate"):
            args = [command, str(out), "--model", "judge-m"]
            if command == "judge-validate":
                args += ["--second-model", "judge-n"]
            code, _, err = self.main(*args)
            self.assertEqual(code, 2)
            self.assertIn("rubric", err)

    def test_comparison_refuses_different_token_calibration(self) -> None:
        reasons = harness.comparable({"calibration_version": "1"}, {"calibration_version": "2"})
        self.assertEqual(reasons, ["calibration_version: '1' != '2'"])

    def test_compare_pairs_cases_and_refuses_other_judge_versions(self) -> None:
        base, arm = self.run_harness("base", BASE), self.run_harness("arm", ARM)
        result = self.base / "compare.json"
        code, stdout, _ = self.main("compare", str(base), str(arm), "--json", str(result))
        self.assertEqual(code, 0)
        rows = {(r["metric"], r["scope"]): r for r in json.loads(result.read_text())["rows"]}
        recall = rows[("skill_recall", "overall")]
        self.assertEqual((recall["diff"], recall["lo"], recall["hi"], recall["verdict"]), (1.0, 1.0, 1.0, "improved"))
        self.assertEqual((recall["cases"], recall["clusters"], recall["mde"]), (1, 1, 0.0))
        leak = rows[("leak_rate", "xberg")]
        self.assertEqual((leak["diff"], leak["verdict"]), (0.0, "inconclusive"))
        expect = rows[("expect_pass_rate", "overall")]
        # two cases have `expect`: module drops from 1 to 0 (the skill answer names no file), fetch stays 1
        self.assertEqual((expect["diff"], expect["lo"], expect["hi"]), (-0.5, -1.0, 0.0))
        self.assertEqual(expect["verdict"], "inconclusive")
        self.assertIn("| skill_recall | overall | +1.000 | [+1.000, +1.000] | 0.000 | 1 (1) | improved |", stdout)

        meta = json.loads((arm / "run.json").read_text())
        (arm / "run.json").write_text(json.dumps({**meta, "rubric_version": "rubric-0"}))
        code, _, err = self.main("compare", str(base), str(arm))
        self.assertEqual(code, 2)
        self.assertEqual(
            err, "error: refusing to compare runs graded differently: rubric_version: 'rubric-2' != 'rubric-0'\n"
        )


if __name__ == "__main__":
    unittest.main()
