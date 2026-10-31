"""Run only hook controls, refusing empty, incomplete or skipped qualification."""

import sys
import unittest
from pathlib import Path

PATTERN = "test_hook*.py"
MINIMUM_TESTS = 73


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern=PATTERN)
    count = suite.countTestCases()
    if count < MINIMUM_TESTS:
        sys.stderr.write(f"Hook qualification collected {count} tests; at least {MINIMUM_TESTS} are required\n")
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.testsRun != count:
        sys.stderr.write(f"Hook qualification ran {result.testsRun} of {count} collected tests\n")
        return 2
    if result.skipped:
        sys.stderr.write(f"Hook qualification skipped {len(result.skipped)} tests; every control is required\n")
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
