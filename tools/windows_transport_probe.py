"""Compare stock Python and the fixture PE forwarder across native and Poly transports."""

from __future__ import annotations

import argparse
import ensurepip
import hashlib
import io
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import traceback
import zipfile
from pathlib import Path

ARGUMENTS = ("validate", "--no-local", "two words", 'quote"inside', "trailing\\")
CAPTURE = (
    "import json,os,sys; from pathlib import Path; "
    "Path(os.environ['TRANSPORT_CAPTURE']).write_text("
    "json.dumps({'argv':sys.argv[1:],'cwd':os.getcwd()}),encoding='utf-8')"
)
TIMEOUT_SECONDS = 30


def assert_capture(record: dict, cwd: Path) -> None:
    assert record == {"argv": list(ARGUMENTS), "cwd": str(cwd)}, record


def negative_controls(record: dict, cwd: Path) -> int:
    corruptions = [dict(record, argv=['"validate"', *ARGUMENTS[1:]]), dict(record, cwd=str(cwd / "wrong"))]
    rejected = 0
    for corrupted in corruptions:
        try:
            assert_capture(corrupted, cwd)
        except AssertionError:
            rejected += 1
    assert rejected == 2, f"capture oracle rejected {rejected}/2 deliberate corruptions"
    return rejected


def error_details(error: BaseException) -> dict:
    details = {
        "type": type(error).__name__,
        "message": str(error),
        "traceback": "".join(traceback.format_exception(error)),
    }
    for key in ("stdout", "stderr"):
        value = getattr(error, key, None)
        if value is not None:
            details[key] = repr(value)
    return details


def execute(arguments: list[str], cwd: Path, environment: dict[str, str], capture: Path) -> dict:
    row = {"command": arguments, "expected": {"argv": list(ARGUMENTS), "cwd": str(cwd)}, "passed": False}
    try:
        result = subprocess.run(
            arguments, cwd=cwd, env=environment, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
        row.update(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if capture.exists():
            row["capture_text"] = capture.read_text(encoding="utf-8")
            row["capture"] = json.loads(row["capture_text"])
        assert result.returncode == 0, f"child exited {result.returncode}"
        assert capture.exists(), "child returned success without producing a capture"
        assert_capture(row["capture"], cwd)
        row["passed"] = True
    except (AssertionError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        row["error"] = error_details(error)
    return row


def pe_forwarder(path: Path) -> dict:
    assert os.name == "nt" and struct.calcsize("P") == 8, "native Windows x64 is required"
    wheels = list(Path(ensurepip.__file__).with_name("_bundled").glob("pip-*.whl"))
    assert len(wheels) == 1, wheels
    with zipfile.ZipFile(wheels[0]) as wheel:
        launcher = wheel.read("pip/_vendor/distlib/t64.exe")
    assert launcher[:2] == b"MZ", "vendored resource is not a PE executable"
    body = (
        "import subprocess,sys\n"
        f"sys.exit(subprocess.run([{json.dumps(sys.executable)},*sys.argv[1:]],check=False).returncode)\n"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("__main__.py", body)
    path.write_bytes(launcher + f'#!"{sys.executable}"\n'.encode() + archive.getvalue())
    return {
        "wheel": str(wheels[0]),
        "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
        "launcher_sha256": hashlib.sha256(launcher).hexdigest(),
        "forwarder_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "body": body,
    }


def poly_repository(root: Path, executable: Path, environment: dict[str, str]) -> str:
    producer = root / "producer"
    producer.mkdir()
    command = f'{executable.name} -c "{CAPTURE}"'
    (producer / "poly-hooks.toml").write_text(
        'version=1\n[[hooks]]\nid="capture"\nstages=["pre-commit"]\n'
        f"args={json.dumps(ARGUMENTS)}\n"
        'files=["**"]\nworkspace=true\nalways_run=true\npass_filenames=false\n'
        '[[hooks.paths]]\nchannel="system"\ncheck="command -v git"\n'
        f"run={json.dumps(command)}\n",
        encoding="utf-8",
    )
    (root / "poly.toml").write_text(
        '[hooks]\nstages=["pre-commit"]\nisolate=false\n[hooks.builtin]\nlint=false\nfmt=false\n'
        '[[hooks.sources]]\nid="transport"\npath="producer"\nhooks=["capture"]\n',
        encoding="utf-8",
    )
    (root / "poly.local.toml").write_text('[hook_preferences]\nchannels=["system"]\n', encoding="utf-8")
    (root / "probe.txt").write_text("transport probe\n", encoding="utf-8")
    for arguments in (["git", "init", "-q"], ["git", "add", "probe.txt", "poly.toml"]):
        subprocess.run(arguments, cwd=root, env=environment, check=True, capture_output=True, timeout=TIMEOUT_SECONDS)
    return command


def run_case(label: str, executable: Path, root: Path, poly: str | None) -> dict:
    root.mkdir()
    capture = root / "capture.json"
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith("GIT_"):
            environment.pop(key)
    environment.update(
        TRANSPORT_CAPTURE=str(capture),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        PATH=str(executable.parent) + os.pathsep + environment["PATH"],
    )
    configured_run = None
    try:
        if poly:
            configured_run = poly_repository(root, executable, environment)
            arguments = [poly, "hooks", "run", "--all-files", "--no-cache", "--jobs", "1"]
        else:
            arguments = [str(executable), "-c", CAPTURE, *ARGUMENTS]
        row = execute(arguments, root, environment, capture)
    except (OSError, subprocess.SubprocessError) as error:
        row = {"passed": False, "error": error_details(error)}
    return {"case": label, "native_endpoint": str(executable), "producer_run": configured_run, **row}


def provenance(stock_only: bool) -> dict:
    root = Path(__file__).resolve().parents[1]
    tools = tomllib.loads((root / "mise.toml").read_text())["tools"]
    assert platform.python_version() == tools["python"], (sys.version, tools["python"])
    result = {"platform": sys.platform, "python": sys.version, "executable": sys.executable}
    result["mise_lock_sha256"] = hashlib.sha256((root / "mise.lock").read_bytes()).hexdigest()
    if not stock_only:
        poly = shutil.which("poly")
        assert poly and shutil.which("git"), "committed Poly and Git must be available"
        version = subprocess.check_output([poly, "--version"], text=True).strip()
        assert version.split()[:2] == ["poly", tools["github:Goldziher/poly"]], version
        result.update(poly=poly, poly_version=version, poly_sha256=hashlib.sha256(Path(poly).read_bytes()).hexdigest())
    return result


def diagnose(report: Path, stock_only: bool) -> dict:
    assert stock_only or os.name == "nt", "full transport diagnosis requires native Windows"
    result = {"provenance": provenance(stock_only), "expected_cases": 1 if stock_only else 4, "cases": []}
    with tempfile.TemporaryDirectory(prefix="transport space ", dir=report) as temporary:
        root = Path(temporary).resolve()
        stock = Path(sys.executable)
        row = run_case("A-stock-direct", stock, root / "A consumer space", None)
        result["cases"].append(row)
        result["negative_controls_expected"] = 2
        result["negative_controls_rejected"] = (
            negative_controls(row["capture"], root / "A consumer space") if row["passed"] else 0
        )
        if not stock_only:
            forward = root / "transport-forward.exe"
            result["pe_forwarder"] = pe_forwarder(forward)
            for label, executable, poly in [
                ("B-PE-direct", forward, None),
                ("C-stock-Poly", stock, result["provenance"]["poly"]),
                ("D-PE-Poly", forward, result["provenance"]["poly"]),
            ]:
                result["cases"].append(run_case(label, executable, root / f"{label} consumer space", poly))
    result["executed_cases"] = len(result["cases"])
    result["passed_cases"] = sum(row["passed"] for row in result["cases"])
    assert result["executed_cases"] == result["expected_cases"], result
    (report / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument(
        "--stock-control", action="store_true", help="run only portable A and two negative oracle controls"
    )
    arguments = parser.parse_args()
    report = arguments.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=False)
    try:
        result = diagnose(report, arguments.stock_control)
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        (report / "setup-error.json").write_text(json.dumps(error_details(error), indent=2) + "\n", encoding="utf-8")
        raise
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed_cases"] == result["expected_cases"] and result["negative_controls_rejected"] == 2 else 1


if __name__ == "__main__":
    sys.exit(main())
