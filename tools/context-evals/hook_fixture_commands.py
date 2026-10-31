"""Real fixture commands: native Windows console launchers and unchanged Unix scripts."""

import ensurepip
import hashlib
import io
import json
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path


def command_path(path: Path) -> Path:
    return path.with_name(path.name + ".exe") if os.name == "nt" and path.suffix.lower() != ".exe" else path


def windows_payload(body: str) -> bytes:
    if struct.calcsize("P") != 8:
        raise AssertionError("fixture launchers require the declared Windows x64 Python toolchain")
    wheels = list(Path(ensurepip.__file__).with_name("_bundled").glob("pip-*.whl"))
    if len(wheels) != 1:
        raise AssertionError("fixture launchers require exactly one pinned-Python ensurepip wheel")
    with zipfile.ZipFile(wheels[0]) as wheel:
        launcher = wheel.read("pip/_vendor/distlib/t64.exe")
    report = os.environ.get("CONVENTIONS_TEST_REPORTS_ROOT")
    if report:
        destination = Path(report)
        destination.mkdir(parents=True, exist_ok=True)
        provenance = {
            "wheel": str(wheels[0]),
            "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
            "resource": "pip/_vendor/distlib/t64.exe",
            "launcher_sha256": hashlib.sha256(launcher).hexdigest(),
            "python": sys.version,
            "interpreter": sys.executable,
            "generated_on": sys.platform,
        }
        (destination / "launcher-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    # PyPA's console-script layout: native launcher, quoted interpreter shebang, then a __main__ ZIP.
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("__main__.py", body)
    shebang = f'#!"{sys.executable}"\n'.encode()
    return launcher + shebang + archive.getvalue()


def script(path: Path, body: str, *, posix: str | None = None) -> Path:
    selected = command_path(path)
    if os.name == "nt":
        selected.write_bytes(windows_payload(body))
    else:
        selected.write_text(posix if posix is not None else f"#!{sys.executable}\n{body}")
    selected.chmod(0o755)
    return selected


def forward(path: Path, target: str | Path) -> None:
    if os.name == "nt":
        script(
            path,
            "import subprocess, sys\n"
            f"sys.exit(subprocess.run([{json.dumps(str(target))}, *sys.argv[1:]], check=False).returncode)\n",
        )
    else:
        path.symlink_to(target)


def directory(source: Path, destination: Path) -> None:
    if os.name == "nt":
        shutil.copytree(source, destination)
    else:
        destination.symlink_to(source, target_is_directory=True)


def environment(values: dict[str, str]) -> dict[str, str]:
    inherited = {key: os.environ[key] for key in ("SYSTEMROOT", "COMSPEC", "PATHEXT") if key in os.environ}
    return {**inherited, **values} if os.name == "nt" else values


def producer_python(relative: str) -> str:
    body = (
        "import os,runpy,sys; "
        f"p=os.path.join(os.environ['POLY_HOOK_SOURCE_ROOT'],{relative!r}); "
        "sys.path.insert(0,os.path.dirname(p)); sys.argv[0]=p; runpy.run_path(p,run_name='__main__')"
    )
    return f'python3 -c "{body}"'


def cwd_provider(path: Path, condition: str, *, posix: str) -> None:
    body = (
        "import os,sys\nfrom pathlib import Path\n"
        f"version='5.9.6' if {condition} else '5.9.8'\n"
        "with Path(os.environ['PROVIDER_TRACE']).open('a') as trace:\n"
        " trace.write(str(Path.cwd())+'|'+' '.join(sys.argv[1:])+'|'+version+'\\n')\n"
        "sys.stdout.write('ai-rulez version '+version+'\\n')\n"
    )
    script(path, body, posix=posix)
