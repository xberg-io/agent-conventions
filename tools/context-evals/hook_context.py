"""Bind an isolated Poly hook to an explicitly exported consumer Git directory."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

GIT_CONTEXT = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class HookContext:
    consumer: Path
    execution_root: Path
    git_dir: Path
    index_file: Path | None


def child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    result = {key: value for key, value in environment.items() if key not in GIT_CONTEXT}
    result["GIT_OPTIONAL_LOCKS"] = "0"
    return result


def git_binary(root: Path, environment: Mapping[str, str]) -> str:
    path = environment.get("PATH")
    if path is None:
        raise ValueError("consumer identity requires an explicit PATH")
    lookup = os.pathsep.join(str((root / entry).resolve()) for entry in path.split(os.pathsep))
    executable = shutil.which("git", path=lookup)
    if executable is None:
        raise ValueError("consumer identity requires an eligible Git executable")
    return executable


def query(executable: str, arguments: list[str], root: Path, environment: dict[str, str]) -> bytes:
    try:
        result = subprocess.run(
            [executable, *arguments],
            cwd=root,
            env=environment,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("consumer Git identity query could not execute") from error
    if result.returncode != 0:
        raise ValueError("consumer Git identity query failed")
    return result.stdout


def registered_roots(output: bytes) -> list[Path]:
    roots = []
    for block in output.split(b"\0\0"):
        if not block:
            continue
        fields = block.split(b"\0")
        paths = [field.removeprefix(b"worktree ") for field in fields if field.startswith(b"worktree ")]
        if len(paths) != 1:
            raise ValueError("invalid registered-worktree metadata")
        if b"bare" not in fields:
            candidate = Path(os.fsdecode(paths[0]))
            if not candidate.is_absolute() or "\n" in str(candidate) or "\r" in str(candidate):
                raise ValueError("unsupported registered-worktree path")
            roots.append(candidate)
    return roots


def candidate_git_dir(executable: str, candidate: Path, environment: dict[str, str]) -> Path | None:
    if not candidate.is_dir():
        return None
    try:
        output = query(
            executable,
            ["-C", str(candidate), "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--absolute-git-dir"],
            candidate,
            environment,
        ).splitlines()
    except ValueError:
        # A stale or non-worktree registration cannot establish a live consumer's identity.
        return None
    if len(output) != 3 or output[0] != b"true":
        return None
    top, git_dir = (Path(os.fsdecode(path)) for path in output[1:])
    if not top.is_absolute() or not git_dir.is_absolute() or top.resolve() != candidate.resolve():
        return None
    return git_dir.resolve()


def bind(execution_root: Path, environment: Mapping[str, str] | None = None) -> HookContext:
    environment = os.environ if environment is None else environment
    root = execution_root.resolve()
    exported = environment.get("GIT_DIR")
    if not exported or not Path(exported).is_absolute() or not Path(exported).is_dir():
        raise ValueError("consumer identity requires an exported absolute GIT_DIR directory")
    git_dir = Path(exported).resolve()
    index = environment.get("GIT_INDEX_FILE")
    if index and not Path(index).is_absolute():
        raise ValueError("exported GIT_INDEX_FILE must be absolute")
    executable = git_binary(root, environment)
    clean = child_environment(environment)
    output = query(executable, ["--git-dir", str(git_dir), "worktree", "list", "--porcelain", "-z"], root, clean)
    matches = [
        candidate.resolve()
        for candidate in registered_roots(output)
        if candidate_git_dir(executable, candidate, clean) == git_dir
    ]
    if len(matches) != 1:
        raise ValueError(f"consumer identity requires exactly one registered worktree, found {len(matches)}")
    return HookContext(matches[0], root, git_dir, Path(index) if index else None)
