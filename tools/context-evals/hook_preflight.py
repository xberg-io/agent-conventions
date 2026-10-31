"""Candidate producer entry point for an independent AI runtime freshness hook."""

import subprocess
import sys
from pathlib import Path

import hook_context
import hook_runtime


def main() -> int:
    try:
        context = hook_context.bind(Path.cwd())
        runtimes = hook_runtime.verify(context.consumer, context.execution_root)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.stderr.write(f"AI runtime preflight: {error}\n")
        return 1
    for runtime in runtimes:
        sys.stdout.write(f"{runtime.hook}: {runtime.channel} ai-rulez {runtime.version} matches npm latest\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
