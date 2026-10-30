"""Consumer hooks must match the convention repository's pinned version and lock."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import hook_pins


class HookPinsTest(unittest.TestCase):
    def test_rejects_old_pin_stale_lock_and_empty_hook_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5.3.0"\n')
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="old"\n')
            errors = hook_pins.check(repo, "5.9.2", "current")
            self.assertEqual(len(errors), 2)
            self.assertIn("v5.3.0", errors[0])
            self.assertIn("old", errors[1])
            (repo / "poly.toml").write_text("")
            self.assertIn("exactly one", hook_pins.check(repo, "5.9.2", "current")[0])

    def test_accepts_current_pin_and_resolved_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "poly.toml").write_text('[[hooks.sources]]\nid="ai-rulez"\nrevision="v5.9.2"\n')
            (repo / "poly-hooks.lock").write_text('[[sources]]\nid="ai-rulez"\nrevision="current"\n')
            self.assertEqual(hook_pins.check(repo, "5.9.2", "current"), [])


if __name__ == "__main__":
    unittest.main()
