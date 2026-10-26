"""Shared test fixtures: a tiny generated checkout matching the recorded transcripts under testdata/.

The transcripts were recorded (synthetically) with the checkout at /work/xberg; the fixture corpus lives in
testdata/cases. Generated files (CLAUDE.md, .claude/) are gitignored in this repository, so the checkout is built
in a temporary directory rather than committed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

HERE = Path(__file__).parent
TESTDATA = HERE / "testdata"
TRANSCRIPTS = TESTDATA / "transcripts"
CASES = TESTDATA / "cases"
RUN_ROOT = "/work/xberg"

FILES = {
    "CLAUDE.md": "@AGENTS.md\n",
    "AGENTS.md": "# xberg\n\n## Rules\n\n### be-brief\n\nAnswer briefly.\n",
    ".claude/rules/general.md": "Prefer the standard library.\n",
    ".claude/rules/ocr-scoped.md": '---\npaths:\n  - "crates/xberg/src/ocr/**"\n---\nOCR code renders at 300 DPI.\n',
    ".claude/rules/web-scoped.md": "---\npaths: crates/xberg/src/web/*.rs\n---\nThe crawler fetches pages.\n",
    ".claude/skills/ocr-pipeline-and-quality/SKILL.md": (
        "---\nname: ocr-pipeline-and-quality\ndescription: OCR pipeline and quality checks.\n---\nUse tesseract.\n"
    ),
    ".claude/skills/crawl-tuning/SKILL.md": (
        "---\nname: crawl-tuning\ndescription: Tune crawlberg crawl depth.\n---\nSet depth.\n"
    ),
    "crates/xberg/CLAUDE.md": "Crate notes.\n",
    "crates/xberg/src/ocr/CLAUDE.md": "OCR module notes.\n",
    "crates/xberg/src/ocr/mod.rs": "pub const DEFAULT_DPI: u32 = 300;\n",
    "crates/xberg/src/web/fetch.rs": "pub fn fetch() {}\n",
    "crates/xberg/src/lib.rs": "pub mod ocr;\n",
}


def make_checkout(root: Path) -> Path:
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def domains() -> dict:
    return tomllib.loads((HERE / "domains.toml").read_text())


def transcript_text(name: str) -> str:
    return (TRANSCRIPTS / f"{name}.jsonl").read_text()
