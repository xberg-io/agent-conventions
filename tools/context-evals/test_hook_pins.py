"""Consumer hooks must follow the convention repository's hook-source pin policy and lock them to commits."""

from __future__ import annotations

import fnmatch
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import hook_pins

POLICY = {
    "ai-rulez": hook_pins.Pin("ai-rulez", "v5", required=True),
    "gh-actions-updater": hook_pins.Pin("gh-actions-updater", "v0"),
    "adrlint": hook_pins.Pin("adrlint", "v0"),
}
EXACT = {**POLICY, "fixture-exact": hook_pins.Pin("fixture-exact", "v1.2.3")}
COMMIT = "8dd59ae052ee9ffbcc371dc0ee1d14e1e9a0a515"


def consumer(repo: Path, pins: dict[str, str], locked: list[str] | None = None) -> Path:
    (repo / "poly.toml").write_text(
        "".join(f'[[hooks.sources]]\nid="{source_id}"\nrevision="{rev}"\n' for source_id, rev in pins.items())
    )
    (repo / "poly-hooks.lock").write_text(
        "".join(f'[[sources]]\nid="{source_id}"\nrevision="{COMMIT}"\n' for source_id in (locked or pins))
    )
    return repo


class HookPinsTest(unittest.TestCase):
    def test_hook_pin_only_changes_trigger_both_workflow_events(self) -> None:
        workflow = Path(__file__).resolve().parents[2] / ".github/workflows/ai-rulez-validation.yml"
        config = yaml.safe_load(workflow.read_text())
        events = config.get("on", config.get(True))
        for event in ("push", "pull_request"):
            patterns = events[event]["paths"]
            for filename in ("poly.toml", "poly-hooks.lock", "tools/context-evals/hook-pins.toml"):
                with self.subTest(event=event, filename=filename):
                    self.assertTrue(any(fnmatch.fnmatchcase(filename, pattern) for pattern in patterns))
            self.assertFalse(any(fnmatch.fnmatchcase("unrelated.txt", pattern) for pattern in patterns))

    def test_ai_rulez_is_unpinned_and_the_hook_source_floats_on_a_major_tag(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertNotIn("github:Goldziher/ai-rulez", tomllib.loads((root / "mise.toml").read_text())["tools"])
        config = yaml.safe_load((root / ".github/workflows/ai-rulez-validation.yml").read_text())
        steps = config["jobs"]["validate"]["steps"]
        setup = [step for step in steps if step.get("uses") == "xberg-io/actions/setup-ai-rulez@v1"]
        self.assertEqual(len(setup), 1)
        self.assertEqual((setup[0].get("with") or {}).get("ai-rulez-version", "latest"), "latest")
        policy = hook_pins.load_policy(root / hook_pins.POLICY)
        self.assertEqual(hook_pins.source(root / "poly.toml", "hooks")["revision"], policy["ai-rulez"].revision)
        self.assertEqual(hook_pins.check(root, policy), [])

    def test_policy_floats_every_source_on_its_bare_major(self) -> None:
        policy = hook_pins.load_policy(Path(__file__).resolve().parents[2] / hook_pins.POLICY)
        self.assertEqual(
            {pin.id: (pin.revision, pin.floating, pin.required) for pin in policy.values()},
            {
                "ai-rulez": ("v5", True, True),
                "gh-actions-updater": ("v0", True, False),
                "adrlint": ("v0", True, False),
            },
        )

    def test_rejects_a_policy_with_a_sha_branch_duplicate_or_no_required_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hook-pins.toml"
            for body, message in (
                (
                    '[[sources]]\nid="a"\nrevision="8dd59ae052ee9ffbcc371dc0ee1d14e1e9a0a515"\nrequired=true\n',
                    "neither",
                ),
                ('[[sources]]\nid="a"\nrevision="main"\nrequired=true\n', "neither"),
                ('[[sources]]\nid="a"\nrevision="v1"\n[[sources]]\nid="a"\nrevision="v1"\n', "unique"),
                ('[[sources]]\nid="a"\nrevision="v1"\n', "no required"),
                ("", "no required"),
            ):
                with self.subTest(message=message, body=body):
                    path.write_text(body)
                    with self.assertRaisesRegex(ValueError, message):
                        hook_pins.load_policy(path)

    def test_rejects_old_pin_stale_lock_and_empty_hook_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5.3.0"\n')
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="v5"\n')
            errors = hook_pins.check(repo, POLICY)
            self.assertEqual(len(errors), 2)
            self.assertIn("v5.3.0", errors[0])
            self.assertIn("bare major", errors[0])
            self.assertIn("not a resolved commit", errors[1])
            (repo / "poly.toml").write_text("")
            self.assertIn("exactly one ai-rulez", hook_pins.check(repo, POLICY)[0])

    def test_each_floating_source_rejects_every_drift_shape(self) -> None:
        drift = ("v0.4.1", "v0.4", "v1", "a4fc1b972267792a7ee8fb2d84ea55d2e9c17c7b", "main")
        for source_id in POLICY:
            for revision in drift + (("v4",) if source_id == "ai-rulez" else ()):
                if revision == POLICY[source_id].revision:
                    continue
                with self.subTest(source=source_id, revision=revision), tempfile.TemporaryDirectory() as tmp:
                    repo = consumer(Path(tmp), {"ai-rulez": "v5", source_id: revision})
                    self.assertEqual(
                        hook_pins.check(repo, POLICY),
                        [
                            f"{repo / 'poly.toml'}: {source_id} revision {revision!r}, "
                            f"expected {POLICY[source_id].revision!r} (a floating source names its bare major)"
                        ],
                    )

    def test_an_exact_source_accepts_its_tag_and_rejects_the_major_and_other_tags(self) -> None:
        for revision, errors in (("v1.2.3", 0), ("v1", 1), ("v1.2.4", 1)):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as tmp:
                repo = consumer(Path(tmp), {"ai-rulez": "v5", "fixture-exact": revision})
                found = hook_pins.check(repo, EXACT)
                self.assertEqual(len(found), errors)
                if errors:
                    self.assertIn("an exact source names its full tag", found[0])

    def test_accepts_every_source_on_policy_and_skips_undeclared_optional_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = consumer(Path(tmp), {"ai-rulez": "v5", "gh-actions-updater": "v0", "adrlint": "v0"})
            self.assertEqual(hook_pins.check(repo, POLICY), [])
            self.assertEqual(len(hook_pins.in_use(POLICY, hook_pins.sources(repo / "poly.toml", "hooks"))), 3)
        with tempfile.TemporaryDirectory() as tmp:
            repo = consumer(Path(tmp), {"ai-rulez": "v5"})
            self.assertEqual(hook_pins.check(repo, POLICY), [])
            checked = hook_pins.in_use(POLICY, hook_pins.sources(repo / "poly.toml", "hooks"))
            self.assertEqual([pin.id for pin in checked], ["ai-rulez"])

    def test_an_optional_source_needs_a_resolved_lock_entry_once_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = consumer(Path(tmp), {"ai-rulez": "v5", "adrlint": "v0"}, locked=["ai-rulez"])
            self.assertEqual(
                hook_pins.check(repo, POLICY),
                [f"{repo / 'poly-hooks.lock'}: expected exactly one adrlint hook source, found 0"],
            )

    def test_accepts_the_floating_tag_resolved_to_any_release_commit(self) -> None:
        # The tag moves on every ai-rulez release, so consumers lock different commits of it.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5"\n')
            for commit in ("3109074724717b1cad38a0a4e0bd94e0e5609669", "8dd59ae052ee9ffbcc371dc0ee1d14e1e9a0a515"):
                with self.subTest(commit=commit):
                    (repo / "poly-hooks.lock").write_text(f'[[sources]]\nid="ai-rulez"\nrevision="{commit}"\n')
                    self.assertEqual(hook_pins.check(repo, POLICY), [])

    def test_skips_a_consumer_without_poly_hooks_but_not_a_lone_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.assertEqual(hook_pins.check(repo, POLICY), [])
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="v5"\n')
            errors = hook_pins.check(repo, POLICY)
            self.assertEqual(len(errors), 2)
            self.assertIn("poly.toml", errors[0])

    def test_rejects_missing_and_file_consumer_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "file"
            file.write_text("fixture")
            for consumer in (root / "missing", file):
                with self.subTest(consumer=consumer.name):
                    self.assertEqual(
                        hook_pins.check(consumer, POLICY),
                        [f"{consumer}: consumer must be an existing directory"],
                    )


if __name__ == "__main__":
    unittest.main()
