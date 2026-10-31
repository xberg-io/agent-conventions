"""Measure the AI hook command selected by Poly, without changing machine preferences.

Selection follows Poly 0.31.2's crates/poly-cli/src/hooks/sources/select.rs and
crates/poly-config/src/hook_sources.rs: first eligible preferred channel, with main-worktree preferences fallback.
Only the reviewed ai-rulez system/npm catalog paths are executable here; an unknown path fails closed.
The consumer is the worktree execution root by default; a staged-hook caller must supply its actual snapshot root.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SOURCE = "https://github.com/Goldziher/ai-rulez.git"
REGISTRY = "https://registry.npmjs.org/ai-rulez/latest"
STABLE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
VERSION = re.compile(rf"ai-rulez version ({STABLE})")
COMMIT = re.compile(r"[0-9a-f]{40}")
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 512_000
PATHS = {
    "system": ("command -v ai-rulez", "ai-rulez", ("ai-rulez",)),
    "npm": ("command -v npx", "npx -y ai-rulez@latest", ("npx", "-y", "ai-rulez@latest")),
}
HOOK_FIELDS = {"id", "stages", "args", "files", "workspace", "pass_filenames", "always_run", "paths"}
SOURCE_FIELDS = {"id", "path", "git", "revision", "hooks"}


@dataclass(frozen=True)
class Runtime:
    hook: str
    channel: str
    command: tuple[str, ...]
    version: str


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def unique_ai_source(entries: list[dict]) -> dict:
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("invalid hook source list")
    found = [entry for entry in entries if entry.get("id") == "ai-rulez"]
    if len(found) != 1:
        raise ValueError(f"expected exactly one ai-rulez hook source, found {len(found)}")
    return found[0]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("hook runtime reference exceeds the response size limit")
    return content


def locked_sources(path: Path) -> list[dict]:
    document = read_toml(path)
    if type(document.get("version")) is not int or document["version"] != 1:
        raise ValueError(f"{path}: lock version must be integer 1")
    entries = document.get("sources")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError(f"{path}: lock requires a sources list")
    for entry in entries:
        for key in ("id", "source", "revision", "path"):
            if not isinstance(entry.get(key), str):
                raise ValueError(f"{path}: lock source requires string {key}")
    return entries


def catalogue(consumer: Path) -> tuple[list[str], dict]:
    configured = unique_ai_source(read_toml(consumer / "poly.toml").get("hooks", {}).get("sources", []))
    if configured.keys() - SOURCE_FIELDS:
        raise ValueError("unknown configured hook source field")
    locked = unique_ai_source(locked_sources(consumer / "poly-hooks.lock"))
    if configured.get("git") != SOURCE or locked.get("source") != SOURCE or "path" in configured:
        raise ValueError("AI runtime probe requires the canonical Goldziher/ai-rulez Git source")
    revision = locked.get("revision", "")
    if not isinstance(revision, str) or not COMMIT.fullmatch(revision):
        raise ValueError("AI runtime probe requires a resolved catalog commit")
    selected = configured.get("hooks", [])
    if (
        not isinstance(selected, list)
        or not selected
        or any(not isinstance(hook, str) or not hook for hook in selected)
    ):
        raise ValueError("AI runtime probe requires nonempty selected hooks")
    if len(set(selected)) != len(selected):
        raise ValueError("AI runtime probe requires unique selected hooks")
    # Poly derives the checkout from source URL + revision; locked.path is descriptive, not a selector.
    url = f"https://raw.githubusercontent.com/Goldziher/ai-rulez/{revision}/poly-hooks.toml"
    return selected, tomllib.loads(fetch(url).decode())


def main_worktree(consumer: Path) -> Path | None:
    if shutil.which("git") is None:
        return None
    result = subprocess.run(
        ["git", "-C", str(consumer), "worktree", "list", "--porcelain", "-z"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode == 0 and result.stdout.startswith("worktree "):
        return Path(result.stdout.split("\0", 1)[0].removeprefix("worktree "))
    return None


def preferences(consumer: Path) -> list[str]:
    path = consumer / "poly.local.toml"
    if not path.is_file():
        main = main_worktree(consumer)
        if main is None or not (main / "poly.local.toml").is_file():
            raise ValueError("AI runtime probe requires machine hook_preferences.channels; no provider was checked")
        path = main / "poly.local.toml"
    table = read_toml(path).get("hook_preferences", {})
    if not isinstance(table, dict):
        raise ValueError("invalid hook_preferences table")
    if table.keys() - {"channels"}:
        raise ValueError("unknown hook_preferences field")
    channels = table.get("channels", [])
    if (
        not isinstance(channels, list)
        or not channels
        or any(not isinstance(channel, str) or channel not in PATHS for channel in channels)
    ):
        raise ValueError("AI runtime probe supports only nonempty system/npm channel preferences")
    if len(set(channels)) != len(channels):
        raise ValueError("AI runtime probe requires unique channel preferences")
    return channels


def paths(hook: dict) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    entries = hook.get("paths", [])
    if not isinstance(entries, list) or any(not isinstance(path, dict) for path in entries):
        raise ValueError(f"hook {hook['id']}: invalid catalog execution paths")
    for path in entries:
        channel = path.get("channel")
        if not isinstance(channel, str) or channel not in PATHS or channel in found:
            raise ValueError(f"hook {hook['id']}: unknown or duplicate execution channel {channel!r}")
        check, run, command = PATHS[channel]
        if (
            path.keys() - {"channel", "check", "run", "install"}
            or path.get("check") != check
            or path.get("run") != run
            or path.get("install") is not None
        ):
            raise ValueError(f"hook {hook['id']}: unreviewed {channel} check/run command")
        found[channel] = command
    return found


def reviewed_hook(hook: dict) -> None:
    if hook.keys() - HOOK_FIELDS:
        raise ValueError(f"hook {hook['id']}: unreviewed catalog execution metadata")
    if hook.get("stages") != ["pre-commit"]:
        raise ValueError(f"hook {hook['id']}: unreviewed catalog stages")
    for key in ("args", "files"):
        value = hook.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"hook {hook['id']}: invalid catalog {key}")
    for key in ("workspace", "always_run", "pass_filenames"):
        if key in hook and not isinstance(hook[key], bool):
            raise ValueError(f"hook {hook['id']}: invalid catalog {key}")


def search_path(execution_root: Path) -> str:
    if "PATH" not in os.environ:
        raise ValueError("PATH is unset; no AI runtime provider was checked")
    entries = os.environ["PATH"].split(os.pathsep)
    return os.pathsep.join(str((execution_root / entry).resolve()) for entry in entries)


def select(
    selected: list[str], producer: dict, channels: list[str], execution_root: Path | None = None
) -> list[tuple[str, str, tuple[str, ...]]]:
    if type(producer.get("version")) is not int or producer["version"] != 1:
        raise ValueError("AI runtime probe requires producer catalog version 1")
    if producer.keys() - {"version", "hooks"}:
        raise ValueError("AI runtime probe rejects unreviewed catalog metadata")
    hooks = producer.get("hooks", [])
    if not isinstance(hooks, list) or any(
        not isinstance(hook, dict) or not isinstance(hook.get("id"), str) or not hook["id"] for hook in hooks
    ):
        raise ValueError("AI runtime probe rejects malformed catalog hooks")
    by_id = {hook["id"]: hook for hook in hooks}
    if len(by_id) != len(hooks):
        raise ValueError("AI runtime probe rejects duplicate catalog hook IDs")
    resolved = []
    lookup = search_path((execution_root or Path.cwd()).resolve())
    for identifier in selected:
        if identifier not in by_id:
            raise ValueError(f"selected hook {identifier!r} is absent from the locked catalog")
        reviewed_hook(by_id[identifier])
        available = paths(by_id[identifier])
        eligible = next(
            (
                channel
                for channel in channels
                if channel in available and shutil.which(available[channel][0], path=lookup)
            ),
            None,
        )
        if eligible is None:
            raise ValueError(f"hook {identifier}: no eligible AI runtime provider; no provider was checked")
        command = available[eligible]
        executable = shutil.which(command[0], path=lookup)
        resolved.append((identifier, eligible, (executable, *command[1:])))
    if not resolved:
        raise ValueError("AI runtime probe selected zero hooks")
    return resolved


def measure(command: tuple[str, ...], execution_root: Path | None = None) -> str:
    try:
        result = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            cwd=execution_root,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("selected AI runtime --version timed out") from error
    if result.returncode != 0:
        raise ValueError(f"selected AI runtime --version exited {result.returncode}")
    version = VERSION.fullmatch(result.stdout.strip())
    if version is None:
        raise ValueError("selected AI runtime did not report an ai-rulez stable version")
    return version.group(1)


def latest() -> str:
    reference = json.loads(fetch(REGISTRY))
    version = reference.get("version", "")
    if reference.get("name") != "ai-rulez" or not isinstance(version, str) or not re.fullmatch(STABLE, version):
        raise ValueError("npm latest did not identify a stable ai-rulez release")
    return version


def verify(consumer: Path, execution_root: Path | None = None) -> list[Runtime]:
    consumer = consumer.resolve()
    execution_root = (execution_root or consumer).resolve()
    channels = preferences(consumer)
    selected, producer = catalogue(consumer)
    resolved = select(selected, producer, channels, execution_root)
    commands = dict.fromkeys(command for _, _, command in resolved)
    measured = {command: measure(command, execution_root) for command in commands}
    expected = latest()
    results = []
    for hook, channel, command in resolved:
        version = measured[command]
        if version != expected:
            raise ValueError(
                f"hook {hook}: selected {channel} ai-rulez {version}, npm latest is {expected}; "
                "update that runtime or choose the npm channel in your own machine preferences"
            )
        results.append(Runtime(hook, channel, command, version))
    return results
