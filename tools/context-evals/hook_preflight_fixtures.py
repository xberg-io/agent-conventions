"""Disposable real-Poly producers; only transport and external CLI boundaries are controlled."""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess

import test_hook_context as context_fixtures
import test_hook_runtime_poly as poly_fixtures

MODULES = Path(__file__).parent
REPORTS = MODULES.resolve().parents[2] / "reports/conventions-preflight-2026-10-31"
LATEST = "5.9.8"
OLD = "5.9.2"
VALID_CONFIG = 'version="5.0"\nname="fixture"\npresets=["claude"]\nbuiltins=[]\n'

ADAPTER = """import io, json, os, sys, urllib.request
from pathlib import Path
from urllib.error import URLError
if Path(sys.argv[0]).name == "hook_preflight.py":
    record = {"actor": "preflight", "cwd": str(Path.cwd()),
              "source_root": os.environ.get("POLY_HOOK_SOURCE_ROOT"),
              "git_dir": os.environ.get("GIT_DIR"), "index": os.environ.get("GIT_INDEX_FILE"),
              "snapshot_config": Path("poly.toml").read_text(),
              "probe": Path("probe.txt").read_text()}
    with open(os.environ["PREFLIGHT_TRACE"], "a") as trace:
        trace.write(json.dumps(record) + "\\n")
    def reference(url, timeout):
        if url == os.environ["CATALOGUE_URL"]:
            return io.BytesIO(Path(os.environ["CATALOGUE_FILE"]).read_bytes())
        if url == "https://registry.npmjs.org/ai-rulez/latest":
            return io.BytesIO(b'{"name":"ai-rulez","version":"5.9.8"}')
        raise URLError("unexpected fixture reference: " + str(url))
    urllib.request.urlopen = reference
"""

PROVIDER = """import json, os, subprocess, sys, tomllib
from pathlib import Path
provider = Path(sys.argv[0]).name
args = sys.argv[1:]
if provider == "npx":
    if args[:2] != ["-y", "ai-rulez@latest"]:
        sys.exit(91)
    args = args[2:]
version_probe = args == ["--version"]
record = {"actor": "provider", "provider": provider, "args": args, "cwd": str(Path.cwd())}
native = os.environ.get("NATIVE_AI_" + ("NPM" if provider == "npx" else "SYSTEM"))
if version_probe and os.environ.get("FAIL_VERSION") == "1":
    status = 17
elif native:
    status = subprocess.run([native, *args], check=False).returncode
elif version_probe:
    print("ai-rulez version " + os.environ["AI_VERSION_" + provider])
    status = 0
else:
    try:
        data = tomllib.loads(Path(".ai-rulez/config.toml").read_text())
        status = 0 if data.get("name") == "fixture" else 1
    except (ValueError, OSError):
        status = 1
record["status"] = status
record["native"] = bool(native)
with open(os.environ["PREFLIGHT_TRACE"], "a") as trace:
    trace.write(json.dumps(record) + "\\n")
sys.exit(status)
"""


def fixture_parent() -> Path:
    parent = REPORTS / "fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def git(root: Path, environment: dict[str, str], *arguments: str) -> str:
    return context_fixtures.git(root, environment, *arguments)


def producer_commit(root: Path, producer: Path, environment: dict[str, str]) -> str:
    for args in (
        ["init", "-q"],
        ["add", "poly-hooks.toml", "tools"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "test: define preflight producer",
        ],
    ):
        git(root, environment, "-C", str(producer), *args)
    return git(root, environment, "-C", str(producer), "rev-parse", "HEAD")


def gate_producer(root: Path, environment: dict[str, str]) -> tuple[Path, str]:
    producer = root / "gauv producer"
    modules = producer / "tools/context-evals"
    modules.mkdir(parents=True)
    for name in ("hook_context.py", "hook_runtime.py", "hook_preflight.py"):
        shutil.copyfile(MODULES / name, modules / name)
    shutil.copyfile(MODULES / "runtime-gate-producer.toml", producer / "poly-hooks.toml")
    return producer, producer_commit(root, producer, environment)


def configure_sources(root: Path, producer: Path, revision: str) -> None:
    (root / "poly.toml").write_text(
        '[hooks]\nstages=["pre-commit"]\n[hooks.builtin]\nlint=false\nfmt=false\n'
        '[[hooks.sources]]\nid="ai-rulez"\ngit="https://github.com/Goldziher/ai-rulez.git"\n'
        'revision="v5"\nhooks=["ai-rulez-validate"]\n'
        f'[[hooks.sources]]\nid="gauv-preflight"\ngit={json.dumps(producer.as_uri())}\n'
        f'revision="{revision}"\nhooks=["ai-runtime-freshness"]\n'
    )


def providers(root: Path, environment: dict[str, str], stale: bool) -> None:
    (root / "bin/python3").symlink_to(sys.executable)
    for name in ("ai-rulez", "npx"):
        command = root / "bin" / name
        command.write_text(f"#!{sys.executable}\n" + PROVIDER)
        command.chmod(0o755)
    environment.update({"AI_VERSION_ai-rulez": OLD if stale else LATEST, "AI_VERSION_npx": LATEST})
    system = os.environ.get("PREFLIGHT_NATIVE_OLD" if stale else "PREFLIGHT_NATIVE_CURRENT")
    npm = os.environ.get("PREFLIGHT_NATIVE_CURRENT")
    if system:
        environment["NATIVE_AI_SYSTEM"] = system
    if npm:
        environment["NATIVE_AI_NPM"] = npm


def network_adapter(root: Path, environment: dict[str, str], revision: str) -> None:
    adapter = root / "network adapter"
    adapter.mkdir()
    (adapter / "sitecustomize.py").write_text(ADAPTER)
    environment.update(
        {
            "PYTHONPATH": str(adapter),
            "PREFLIGHT_TRACE": str(root / "trace.jsonl"),
            "CATALOGUE_FILE": str(root / "producer/poly-hooks.toml"),
            "CATALOGUE_URL": f"https://raw.githubusercontent.com/Goldziher/ai-rulez/{revision}/poly-hooks.toml",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{(root / 'producer').as_uri()}.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/Goldziher/ai-rulez.git",
        }
    )


def setup(root: Path, *, stale: bool = False, separate: Path | None = None) -> dict[str, str]:
    environment = poly_fixtures.sandbox(root, ["system"], {})
    providers(root, environment, stale)
    catalogue = poly_fixtures.fixtures.CATALOGUE.replace(
        'files = ["**"]', 'files = [".ai-rulez/**", "**/.ai-rulez/**"]'
    ).replace("always_run = true\n", "")
    (root / "producer/poly-hooks.toml").write_text(catalogue)
    revision = poly_fixtures.git_producer(root, environment)
    git(root, environment, "-C", str(root / "producer"), "tag", "v5")
    producer, gate_revision = gate_producer(root, environment)
    configure_sources(root, producer, gate_revision)
    network_adapter(root, environment, revision)
    init = ["init", "-q"] + (["--separate-git-dir", str(separate)] if separate else [])
    git(root, environment, *init)
    (root / ".ai-rulez").mkdir()
    (root / ".ai-rulez/config.toml").write_text(VALID_CONFIG)
    update = poly_fixtures.run([str(root / "bin/poly"), "hooks", "update"], root, environment)
    if update.returncode != 0:
        raise AssertionError(update.stdout + update.stderr)
    git(root, environment, "add", "poly.toml", "poly-hooks.lock", "probe.txt", ".ai-rulez/config.toml")
    return environment


def commit(root: Path, environment: dict[str, str], label: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
    trace = Path(environment["PREFLIGHT_TRACE"])
    trace.unlink(missing_ok=True)
    result = poly_fixtures.execute_hook(str(root / "bin/poly"), root, environment, commit=True)
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    receipt = {
        "case": label,
        "exit": result.returncode,
        "events": events,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    (REPORTS / f"receipt-{label}-{uuid.uuid4().hex}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return result, events


def captured(events: list[dict]) -> tuple[list[dict], list[dict]]:
    gates = [event for event in events if event["actor"] == "preflight"]
    validators = [
        event for event in events if event["actor"] == "provider" and event["args"] == ["validate", "--no-local"]
    ]
    return gates, validators
